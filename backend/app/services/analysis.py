"""
AI performance analyses: gathering their data, running them, scheduling them.

An analysis covers a period. It is created `pending`, then run by a worker
(see app.worker.tasks.analysis), which moves it to `completed` or `failed`.
"""

import logging
import statistics
import uuid
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlmodel import Session

from app import crud
from app.ai.analysis import build_analysis_chain, to_result
from app.ai.formatting import format_value, prompt_variables
from app.core.config import settings
from app.models.analysis import (
    AnalysisFrequency,
    AnalysisKind,
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


@dataclass(frozen=True)
class PromptLimits:
    """How many posts are sent to the model (see _select_posts), and how much
    of each post's text: enough for a thorough review while keeping the
    prompt a reasonable size."""

    max_posts: int
    text_chars: int


PROMPT_LIMITS = {
    AnalysisKind.standard: PromptLimits(max_posts=60, text_chars=280),
    # A year has many more posts: send more of them, each more briefly
    AnalysisKind.yearly: PromptLimits(max_posts=300, text_chars=160),
}
DEFAULT_PERIOD_DAYS = {AnalysisKind.standard: 7, AnalysisKind.yearly: 365}
MAX_PERIOD_DAYS = {AnalysisKind.standard: 92, AnalysisKind.yearly: 366}


# ---------------------------------------------------------------------------
# Prompt data
# ---------------------------------------------------------------------------


def _format_rate(rate: float | None) -> str:
    return f"{rate:.2%}" if rate is not None else "n/a"


def _post_line(ref: str, post: Post, account: str, text_chars: int) -> str:
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
    text = " ".join((post.text or "(no text)").split())[:text_chars]
    published = post.published_at.astimezone(UTC)
    return (
        f"  {ref} [{account} · {post.content_type.value}] "
        f"published {published:%a %Y-%m-%d %H:%M} UTC\n"
        f"     metrics: {', '.join(metrics) or 'none reported'}; "
        f"engagement rate={_format_rate(post.engagement_rate)}\n"
        f"     text: {text!r}"
    )


def _account_labels(session: Session, query: MetricsQuery) -> dict[uuid.UUID, str]:
    """{account id: "platform · account name"} for the workspace's accounts."""
    accounts = metrics_service.query_accounts(session, query)
    return {a.id: f"{a.platform.value} · {a.name}" for a in accounts}


def _select_posts(posts: Sequence[Post], max_posts: int) -> list[Post]:
    """
    The posts to send to the model, best first: each account's posts ranked by
    engagements, then the same top share of every account's posts. Ranking
    across accounts by engagements alone would fill the prompt with a popular
    account's posts and leave out a small account's best ones.
    """
    by_account: dict[uuid.UUID, list[Post]] = defaultdict(list)
    for post in posts:
        by_account[post.platform_account_id].append(post)

    ranked: list[tuple[float, int, Post]] = []
    for account_posts in by_account.values():
        account_posts.sort(key=lambda p: (p.engagements is None, -(p.engagements or 0)))
        ranked.extend(
            ((rank + 0.5) / len(account_posts), -(post.engagements or 0), post)
            for rank, post in enumerate(account_posts)
        )
    ranked.sort(key=lambda r: r[:2])
    return [post for *_, post in ranked[:max_posts]]


def _benchmarks(posts: Sequence[Post], accounts: dict[uuid.UUID, str]) -> str:
    """Per account: post count, median engagements and engagement rate."""
    by_account: dict[str, list[Post]] = defaultdict(list)
    for post in posts:
        by_account[accounts[post.platform_account_id]].append(post)

    lines = []
    for account, account_posts in sorted(by_account.items()):
        engagements = [
            p.engagements for p in account_posts if p.engagements is not None
        ]
        rates = [
            p.engagement_rate for p in account_posts if p.engagement_rate is not None
        ]
        lines.append(
            f"  [{account}] posts={len(account_posts)}"
            f"; median engagements="
            f"{f'{statistics.median(engagements):,.0f}' if engagements else 'n/a'}"
            f"; median engagement rate="
            f"{_format_rate(statistics.median(rates) if rates else None)}"
        )
    return "\n".join(lines) or "  (no posts)"


def _months(date_from: date, date_to: date) -> list[tuple[date, date]]:
    """The calendar months overlapping a range, clipped to it."""
    months = []
    start = date_from
    while start <= date_to:
        year, month = divmod(start.year * 12 + start.month, 12)
        next_month = date(year, month + 1, 1)
        months.append((start, min(next_month - timedelta(days=1), date_to)))
        start = next_month
    return months


def _monthly_breakdown(
    session: Session, query: MetricsQuery, posts: Sequence[Post]
) -> str:
    """One line of totals per month, for yearly analyses."""
    post_months = Counter(f"{p.published_at.astimezone(UTC):%Y-%m}" for p in posts)
    lines = []
    for start, end in _months(query.date_from, query.date_to):
        month_query = MetricsQuery(query.workspace_id, query.platform, start, end)
        totals = metrics_service.summarize(session, month_query).totals
        metrics = ", ".join(
            f"{name}={format_value(name, value)}"
            for name, value in totals.model_dump().items()
            if value
        )
        label = f"{start:%Y-%m}"
        lines.append(
            f"  {label}: {metrics or 'no data'}; "
            f"posts listed above={post_months.get(label, 0)}"
        )
    return "\n=== Month by month ===\n" + "\n".join(lines) + "\n"


def build_prompt(
    session: Session,
    *,
    workspace_name: str,
    query: MetricsQuery,
    kind: AnalysisKind = AnalysisKind.standard,
) -> tuple[dict[str, Any], dict[str, uuid.UUID]]:
    """The chain's variables, and the post id behind each post reference."""
    limits = PROMPT_LIMITS[kind]
    previous = query.previous()
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

    accounts = _account_labels(session, query)
    all_posts = crud.get_posts_for_accounts(
        session=session,
        platform_account_ids=list(accounts),
        start_date=query.date_from,
        end_date=query.date_to,
    )
    posts = _select_posts(all_posts, limits.max_posts)
    refs = {f"P{i}": post for i, post in enumerate(posts, 1)}

    variables.update(
        previous_date_from=previous.date_from.isoformat(),
        previous_date_to=previous.date_to.isoformat(),
        previous_totals_text=previous_variables["totals_text"],
        previous_platforms_text=previous_variables["platforms_text"],
        benchmarks_text=_benchmarks(all_posts, accounts),
        post_count=len(posts),
        posts_note=f" of {len(all_posts)}: each account's most engaging"
        if len(posts) < len(all_posts)
        else "",
        posts_text="\n".join(
            _post_line(ref, post, accounts[post.platform_account_id], limits.text_chars)
            for ref, post in refs.items()
        )
        or "  (no posts)",
        monthly_text=_monthly_breakdown(session, query, posts)
        if kind == AnalysisKind.yearly
        else "",
    )
    return variables, {ref: post.id for ref, post in refs.items()}


# ---------------------------------------------------------------------------
# Running an analysis
# ---------------------------------------------------------------------------


def default_period(
    kind: AnalysisKind = AnalysisKind.standard, today: date | None = None
) -> tuple[date, date]:
    """The last 7 days (or 365 for a yearly analysis), today included."""
    today = today or date.today()
    return today - timedelta(days=DEFAULT_PERIOD_DAYS[kind] - 1), today


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
            session, workspace_name=workspace.name, query=query, kind=analysis.kind
        )
        raw = build_analysis_chain(analysis.kind).invoke(variables)
        result = to_result(raw, post_refs)
    except Exception as exc:
        logger.exception("Analysis %s failed", analysis.id)
        return fail(session, analysis, f"AI generation failed: {exc}")
    analysis.status = AnalysisStatus.completed
    analysis.result = result.model_dump(mode="json")
    analysis.post_count = len(post_refs)
    analysis.completed_at = get_datetime_utc()
    return crud.save(session, analysis)


def fail(
    session: Session, analysis: PerformanceAnalysis, error: str
) -> PerformanceAnalysis:
    """Record that the analysis failed, and why."""
    analysis.status = AnalysisStatus.failed
    analysis.error = error[:1024]
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
        yearly=analysis.kind == AnalysisKind.yearly,
    )
    for recipient in recipients:
        send_email(email_to=recipient, email=email)
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
            email_recipients=list(schedule.email_recipients)
            if schedule.email_enabled
            else [],
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
