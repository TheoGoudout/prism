import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlmodel import Session

from app import crud
from app.models.analysis import AnalysisFrequency, AnalysisSchedule
from app.models.integration import Platform
from app.models.metrics import ContentType, MetricSnapshotUpsert, PostUpsert
from app.services.analysis import (
    advance,
    build_prompt,
    next_occurrence,
    scheduled_period,
)
from app.services.metrics import MetricsQuery
from tests.utils.integration import create_fake_account, create_fake_integration
from tests.utils.user import create_random_user
from tests.utils.workspace import create_random_workspace

# Thursday 2026-10-01, 12:00 UTC
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def _schedule(**kwargs: object) -> AnalysisSchedule:
    return AnalysisSchedule.model_validate(
        {"workspace_id": uuid.uuid4(), "enabled": True, **kwargs}
    )


def test_next_occurrence_weekly_in_time_zone() -> None:
    # Mondays at 8am in Paris (UTC+2 in October)
    schedule = _schedule(weekday=0, hour=8, timezone="Europe/Paris")
    assert next_occurrence(schedule, NOW) == datetime(2026, 10, 5, 6, 0, tzinfo=UTC)


def test_next_occurrence_later_today() -> None:
    schedule = _schedule(weekday=3, hour=15)  # Thursdays at 3pm UTC
    assert next_occurrence(schedule, NOW) == datetime(2026, 10, 1, 15, tzinfo=UTC)


def test_next_occurrence_is_strictly_after() -> None:
    schedule = _schedule(weekday=3, hour=12)
    assert next_occurrence(schedule, NOW) == NOW + timedelta(days=7)


def test_next_occurrence_monthly() -> None:
    schedule = _schedule(frequency="monthly", day_of_month=1, hour=8)
    assert next_occurrence(schedule, NOW) == datetime(2026, 11, 1, 8, tzinfo=UTC)
    december = datetime(2026, 12, 15, tzinfo=UTC)
    assert next_occurrence(schedule, december) == datetime(2027, 1, 1, 8, tzinfo=UTC)


def test_advance_biweekly_skips_a_week() -> None:
    schedule = _schedule(frequency="biweekly", weekday=3, hour=12)
    schedule.next_run_at = NOW
    assert advance(schedule, NOW) == NOW + timedelta(days=14)


def test_advance_weekly_after_downtime_skips_missed_runs() -> None:
    schedule = _schedule(weekday=3, hour=12)
    schedule.next_run_at = NOW - timedelta(days=21)
    assert advance(schedule, NOW) == NOW + timedelta(days=7)


@pytest.mark.parametrize(
    ("frequency", "run_date", "expected"),
    [
        ("weekly", date(2026, 10, 5), (date(2026, 9, 28), date(2026, 10, 4))),
        ("biweekly", date(2026, 10, 5), (date(2026, 9, 21), date(2026, 10, 4))),
        ("monthly", date(2026, 10, 1), (date(2026, 9, 1), date(2026, 9, 30))),
        ("monthly", date(2026, 1, 15), (date(2025, 12, 15), date(2026, 1, 14))),
    ],
)
def test_scheduled_period(
    frequency: str, run_date: date, expected: tuple[date, date]
) -> None:
    assert scheduled_period(AnalysisFrequency(frequency), run_date) == expected


def test_build_prompt(db: Session) -> None:
    workspace = create_random_workspace(db, create_random_user(db))
    account = create_fake_account(
        db, create_fake_integration(db, workspace, platform=Platform.instagram)
    )
    day = date(2026, 9, 10)
    for snapshot_day, impressions in ((day, 900), (day - timedelta(days=7), 300)):
        crud.upsert_metric_snapshot(
            session=db,
            platform_account_id=account.id,
            snapshot_in=MetricSnapshotUpsert(
                date=snapshot_day, impressions=impressions
            ),
        )
    posts = [
        crud.upsert_post(
            session=db,
            platform_account_id=account.id,
            post_in=PostUpsert(
                external_id=external_id,
                content_type=ContentType.reel,
                text=text,
                published_at=datetime(2026, 9, 10, 18, tzinfo=UTC),
                engagements=engagements,
                reach=1000,
            ),
        )
        for external_id, text, engagements in (
            ("a", "Low performer", 10),
            ("b", "Launch\nday!", 90),
        )
    ]

    query = MetricsQuery(workspace.id, None, date(2026, 9, 8), date(2026, 9, 14))
    variables, refs = build_prompt(db, workspace_name="Acme", query=query)

    # Most engaging first
    assert refs == {"P1": posts[1].id, "P2": posts[0].id}
    assert variables["previous_date_from"] == "2026-09-01"
    assert variables["previous_date_to"] == "2026-09-07"
    assert variables["totals_text"] == "  impressions: 900"
    assert variables["previous_totals_text"] == "  impressions: 300"
    assert "[instagram] posts=2; median engagements=50" in variables["benchmarks_text"]
    assert (
        "P1 [instagram · reel] published Thu 2026-09-10 18:00 UTC"
        in (variables["posts_text"])
    )
    assert "engagement rate=9.00%" in variables["posts_text"]
    assert "'Launch day!'" in variables["posts_text"]
    assert variables["post_count"] == 2
