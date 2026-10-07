"""Tests for the follow-up sync schedule."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session

from app import crud
from app.core.config import settings
from app.models.integration import Integration
from app.models.metrics import ContentType, PostUpsert
from app.services import sync_schedule
from tests.utils.integration import create_fake_account, create_fake_integration
from tests.utils.user import create_random_user
from tests.utils.workspace import create_random_workspace

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def schedule_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SYNC_QUIET_DAYS", 2)
    monkeypatch.setattr(settings, "SYNC_FOLLOW_POST_DAYS", 7)
    monkeypatch.setattr(settings, "SYNC_MIN_INTERVAL_MINUTES", 30)
    monkeypatch.setattr(settings, "SYNC_MAX_INTERVAL_HOURS", 12)


@pytest.mark.parametrize(
    ("quiet_for", "interval"),
    [
        (timedelta(minutes=5), timedelta(minutes=30)),  # just posted
        (timedelta(hours=2), timedelta(hours=2)),  # spreads out
        (timedelta(hours=30), timedelta(hours=12)),  # capped
    ],
)
def test_interval_grows_with_time_since_last_interaction(
    quiet_for: timedelta, interval: timedelta
) -> None:
    assert sync_schedule.next_sync_at(NOW - quiet_for, NOW) == NOW + interval


def test_stops_after_quiet_days() -> None:
    assert sync_schedule.next_sync_at(NOW - timedelta(days=2), NOW) is None


def test_no_recent_post_means_no_follow_up() -> None:
    assert sync_schedule.next_sync_at(None, NOW) is None


def _integration(db: Session) -> Integration:
    workspace = create_random_workspace(db, create_random_user(db))
    return create_fake_integration(db, workspace)


def _post(
    db: Session,
    integration: Integration,
    published_at: datetime,
    external_id: str,
    account_id: str = "page-456",
) -> None:
    account = create_fake_account(db, integration, external_id=account_id)
    crud.upsert_post(
        session=db,
        platform_account_id=account.id,
        post_in=PostUpsert(
            external_id=external_id,
            published_at=published_at,
            content_type=ContentType.post,
        ),
    )
    db.commit()


def test_latest_interaction_of_recent_posts(db: Session) -> None:
    integration = _integration(db)
    _post(db, integration, NOW - timedelta(hours=3), "older")
    _post(db, integration, NOW - timedelta(hours=1), "newer", account_id="page-2")
    # A post outside the followed window doesn't count
    _post(db, integration, NOW - timedelta(days=8), "old")

    assert sync_schedule.latest_interaction(db, integration, NOW) == NOW - timedelta(
        hours=1
    )


def test_latest_interaction_ignores_old_posts_and_other_integrations(
    db: Session,
) -> None:
    integration = _integration(db)
    _post(db, integration, NOW - timedelta(days=8), "old")
    _post(db, _integration(db), NOW - timedelta(hours=1), "elsewhere")

    assert sync_schedule.latest_interaction(db, integration, NOW) is None


def test_schedule_next_sync(db: Session) -> None:
    integration = _integration(db)
    _post(db, integration, NOW - timedelta(hours=2), "post")

    assert sync_schedule.schedule_next_sync(db, integration, NOW) == NOW + timedelta(
        hours=2
    )
    assert integration.next_sync_at == NOW + timedelta(hours=2)
