"""
AI performance analyses: gathering their data, running them, scheduling them.

An analysis covers a period. It is created `pending`, then run by a worker
(see app.worker.tasks.analysis), which moves it to `completed` or `failed`.
"""

import logging
import statistics
import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlmodel import Session

from app import crud
from app.ai.analysis import build_analysis_chain, to_result
from app.ai.formatting import prompt_variables
from app.core.config import settings
from app.models.analysis import (
    AnalysisFrequency,
    AnalysisPublic,
    AnalysisResult,
    AnalysisSchedule,
    AnalysisStatus,
    AnalysisTrigger,
    AnalyzedPost,
    PerformanceAnalysis,
    ScheduleSettings,
)
from app.models.common import get_datetime_utc
from app.models.metrics import Post
from app.services import metrics as metrics_service
from app.services.metrics import MetricsQuery
from app.utils import generate_analysis_email, send_email

logger = logging.getLogger(__name__)

# Posts sent to the model, most engaging first: enough for a thorough review
# while keeping the prompt and the answer a reasonable size
MAX_POSTS = 60
POST_TEXT_CHARS = 280
DEFAULT_PERIOD_DAYS = 7


# ---------------------------------------------------------------------------
# Prompt data
# ---------------------------------------------------------------------------


def _format_rate(rate: float | None) -> str:
    return f"{rate:.2%}" if rate is not None else "n/a"


def _post_line(ref: str, post: Post, platform: str) -> str:
    metrics = [
        f"{name}={value:,}"
        for name in (
            "impressions",
            "reach",
            "views",
            "engagements",
            "likes",
            "comments",
            "shares",
            "saves",
            "clicks",
        )
        if (value := getattr(post, name)) is not None
    ]
    text = " ".join((post.text or "(no text)").split())[:POST_TEXT_CHARS]
    published = post.published_at.astimezone(UTC)
    return (
        f"  {ref} [{platform} · {post.content_type.value}] "
        f"published {published:%a %Y-%m-%d %H:%M} UTC\n"
        f"     metrics: {', '.join(metrics) or 'none reported'}; "
        f"engagement rate={_format_rate(post.engagement_rate)}\n"
        f"     text: {text!r}"
    )


def _benchmarks(posts: Sequence[Post], platforms: dict[uuid.UUID, str]) -> str:
    """Per platform: post count, median engagements and engagement rate."""
    by_platform: dict[str, list[Post]] = defaultdict(list)
    for post in posts:
        by_platform[platforms[post.platform_account_id]].append(post)

    lines = []
    for platform, platform_posts in sorted(by_platform.items()):
        engagements = [
            p.engagements for p in platform_posts if p.engagements is not None
        ]
        rates = [
            p.engagement_rate for p in platform_posts if p.engagement_rate is not None
        ]
        lines.append(
            f"  [{platform}] posts={len(platform_posts)}"
            f"; median engagements="
            f"{f'{statistics.median(engagements):,.0f}' if engagements else 'n/a'}"
            f"; median engagement rate="
            f"{_format_rate(statistics.median(rates) if rates else None)}"
        )
    return "\n".join(lines) or "  (no posts)"


def build_prompt(
    session: Session, *, workspace_name: str, query: MetricsQuery
) -> tuple[dict[str, Any], dict[str, uuid.UUID]]:
    """The chain's variables, and the post id behind each post reference."""
    length = query.date_to - query.date_from + timedelta(days=1)
    previous = MetricsQuery(
        query.workspace_id,
        query.platform,
        query.date_from - length,
        query.date_from - timedelta(days=1),
    )
    variables = prompt_variables(
        workspace_name=workspace_name,
        query=query,
        summary=metrics_service.summarize(session, query),
    )
    previous_variables = prompt_variables(
        workspace_name=workspace_name,
        query=previous,
        summary=metrics_service.summarize(session, previous),
    )

    platforms = metrics_service.account_platforms(session, query)
    posts = crud.get_posts(
        session=session,
        platform_account_ids=list(platforms),
        start_date=query.date_from,
        end_date=query.date_to,
        limit=MAX_POSTS,
    )
    refs = {f"P{i}": post for i, post in enumerate(posts, 1)}

    variables.update(
        previous_date_from=previous.date_from.isoformat(),
        previous_date_to=previous.date_to.isoformat(),
        previous_totals_text=previous_variables["totals_text"],
        previous_platforms_text=previous_variables["platforms_text"],
        benchmarks_text=_benchmarks(posts, platforms),
        post_count=len(posts),
        posts_note=f", the {MAX_POSTS} most engaging"
        if len(posts) == MAX_POSTS
        else "",
        posts_text="\n".join(
            _post_line(ref, post, platforms[post.platform_account_id])
            for ref, post in refs.items()
        )
        or "  (no posts)",
    )
    return variables, {ref: post.id for ref, post in refs.items()}


# ---------------------------------------------------------------------------
# Running an analysis
# ---------------------------------------------------------------------------


def default_period(today: date | None = None) -> tuple[date, date]:
    """The last 7 days, today included."""
    today = today or date.today()
    return today - timedelta(days=DEFAULT_PERIOD_DAYS - 1), today


def run(session: Session, analysis: PerformanceAnalysis) -> PerformanceAnalysis:
    """Run a pending analysis, recording its result or its failure on it."""
    workspace = crud.get_workspace(session=session, workspace_id=analysis.workspace_id)
    assert workspace is not None  # guaranteed by the foreign key

    analysis.status = AnalysisStatus.running
    crud.save(session, analysis)

    query = MetricsQuery(
        analysis.workspace_id, None, analysis.date_from, analysis.date_to
    )
    try:
        variables, post_refs = build_prompt(
            session, workspace_name=workspace.name, query=query
        )
        raw = build_analysis_chain().invoke(variables)
        result = to_result(raw, post_refs)
    except Exception as exc:
        logger.exception("Analysis %s failed", analysis.id)
        analysis.status = AnalysisStatus.failed
        analysis.error = f"AI generation failed: {exc}"[:1024]
    else:
        analysis.status = AnalysisStatus.completed
        analysis.result = result.model_dump(mode="json")
        analysis.post_count = len(post_refs)
    analysis.completed_at = get_datetime_utc()
    return crud.save(session, analysis)


def to_public(session: Session, analysis: PerformanceAnalysis) -> AnalysisPublic:
    """The analysis with its result, and the posts it analyzed."""
    public = AnalysisPublic.model_validate(analysis)
    if public.result is None:
        return public
    posts = crud.get_posts_by_ids(
        session=session,
        post_ids=[p.post_id for p in public.result.posts],
        workspace_id=analysis.workspace_id,
    )
    public.posts = [
        AnalyzedPost.model_validate(
            post,
            update={
                "platform": post.platform_account.platform.value
                if post.platform_account
                else ""
            },
        )
        for post in posts
    ]
    return public


def send_by_email(
    analysis: PerformanceAnalysis, *, workspace_name: str, recipients: Sequence[str]
) -> bool:
    """Email a completed analysis; False when there's nothing or no one to send."""
    if not settings.emails_enabled or analysis.result is None or not recipients:
        return False
    email = generate_analysis_email(
        workspace_name=workspace_name,
        analysis_id=analysis.id,
        date_from=analysis.date_from,
        date_to=analysis.date_to,
        result=AnalysisResult.model_validate(analysis.result),
    )
    for recipient in recipients:
        send_email(
            email_to=recipient, subject=email.subject, html_content=email.html_content
        )
    return True


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------


def _add_month(day: datetime) -> datetime:
    """The same day and time next month (days are capped at 28)."""
    if day.month == 12:
        return day.replace(year=day.year + 1, month=1)
    return day.replace(month=day.month + 1)


def next_occurrence(schedule: ScheduleSettings, after: datetime) -> datetime:
    """
    The first time strictly after ``after`` matching the schedule's day and
    hour in its time zone, in UTC. Biweekly schedules match every week here:
    `advance` skips the week in between.
    """
    local = after.astimezone(ZoneInfo(schedule.timezone))
    if schedule.frequency == AnalysisFrequency.monthly:
        candidate = local.replace(
            day=schedule.day_of_month,
            hour=schedule.hour,
            minute=0,
            second=0,
            microsecond=0,
        )
        if candidate <= local:
            candidate = _add_month(candidate)
    else:
        days_ahead = (schedule.weekday - local.weekday()) % 7
        candidate = (local + timedelta(days=days_ahead)).replace(
            hour=schedule.hour, minute=0, second=0, microsecond=0
        )
        if candidate <= local:
            candidate += timedelta(days=7)
    return candidate.astimezone(UTC)


def advance(schedule: AnalysisSchedule, now: datetime) -> datetime:
    """The run after the one that is due now."""
    base = schedule.next_run_at or now
    if schedule.frequency == AnalysisFrequency.biweekly:
        base += timedelta(days=7)
    return next_occurrence(schedule, max(base, now))


def scheduled_period(frequency: AnalysisFrequency, run_date: date) -> tuple[date, date]:
    """
    The period a run on ``run_date`` covers: the full week, two weeks or month
    before that day.
    """
    date_to = run_date - timedelta(days=1)
    if frequency == AnalysisFrequency.monthly:
        year, month = divmod(run_date.year * 12 + run_date.month - 2, 12)
        return date(year, month + 1, min(run_date.day, 28)), date_to
    days = 14 if frequency == AnalysisFrequency.biweekly else 7
    return run_date - timedelta(days=days), date_to


def start_due_analyses(session: Session, now: datetime) -> list[PerformanceAnalysis]:
    """Create the analyses of every due schedule and move the schedules on."""
    created = []
    for schedule in crud.get_due_schedules(session=session, now=now):
        assert schedule.next_run_at is not None  # due schedules have one
        run_date = schedule.next_run_at.astimezone(ZoneInfo(schedule.timezone)).date()
        date_from, date_to = scheduled_period(schedule.frequency, run_date)
        analysis = PerformanceAnalysis(
            workspace_id=schedule.workspace_id,
            date_from=date_from,
            date_to=date_to,
            trigger=AnalysisTrigger.scheduled,
        )
        schedule.last_run_at = now
        schedule.next_run_at = advance(schedule, now)
        session.add(analysis)
        session.add(schedule)
        created.append(analysis)
    session.commit()
    for analysis in created:
        session.refresh(analysis)
    return created
