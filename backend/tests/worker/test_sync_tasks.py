"""Tests for the Celery sync tasks, against the test database."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import httpx
import pytest
from sqlmodel import Session

from app import crud
from app.core.config import settings
from app.integrations.oauth.base import TokenResponse
from app.models.integration import Integration, IntegrationStatus, Platform
from app.models.metrics import ContentType, PostUpsert
from app.worker.tasks.sync import (
    sync_all_active_integrations,
    sync_due_integrations,
    sync_integration,
)
from tests.utils.integration import create_fake_account, create_fake_integration
from tests.utils.user import create_random_user
from tests.utils.workspace import create_random_workspace

SYNC_FUNCTIONS = "app.worker.tasks.sync.SYNC_FUNCTIONS"


@pytest.fixture
def integration(db: Session) -> Integration:
    workspace = create_random_workspace(db, create_random_user(db))
    return create_fake_integration(db, workspace, platform=Platform.twitter)


def _run(db: Session, integration_id: uuid.UUID) -> dict:  # type: ignore[type-arg]
    """Run the task synchronously, using the test's database session."""
    with patch("app.worker.tasks.sync.Session") as session_cls:
        session_cls.return_value.__enter__.return_value = db
        result: dict = sync_integration.run(str(integration_id))  # type: ignore[type-arg]
    return result


def _http_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.com")
    return httpx.HTTPStatusError(
        "error", request=request, response=httpx.Response(status, request=request)
    )


def test_unknown_integration(db: Session) -> None:
    assert _run(db, uuid.uuid4())["status"] == "not_found"


def test_successful_sync(db: Session, integration: Integration) -> None:
    sync_fn = MagicMock()
    with patch.dict(SYNC_FUNCTIONS, {Platform.twitter: sync_fn}):
        result = _run(db, integration.id)

    assert result["status"] == "ok"
    sync_fn.assert_called_once_with(db, integration, "fake-access-token")
    db.refresh(integration)
    assert integration.last_synced_at is not None


def test_sync_of_recent_post_schedules_follow_up(
    db: Session, integration: Integration
) -> None:
    def sync_fn(session: Session, integ: Integration, _token: str) -> None:
        account = create_fake_account(session, integ)
        crud.upsert_post(
            session=session,
            platform_account_id=account.id,
            post_in=PostUpsert(
                external_id="just-posted",
                published_at=datetime.now(UTC) - timedelta(minutes=5),
                content_type=ContentType.post,
            ),
        )

    with patch.dict(SYNC_FUNCTIONS, {Platform.twitter: sync_fn}):
        assert _run(db, integration.id)["status"] == "ok"

    db.refresh(integration)
    assert integration.next_sync_at is not None
    expected = datetime.now(UTC) + timedelta(minutes=settings.SYNC_MIN_INTERVAL_MINUTES)
    assert abs(integration.next_sync_at - expected) < timedelta(minutes=1)


def test_sync_without_recent_posts_schedules_no_follow_up(
    db: Session, integration: Integration
) -> None:
    integration.next_sync_at = datetime.now(UTC)
    crud.save(db, integration)
    with patch.dict(SYNC_FUNCTIONS, {Platform.twitter: MagicMock()}):
        assert _run(db, integration.id)["status"] == "ok"

    db.refresh(integration)
    assert integration.next_sync_at is None


def test_successful_sync_clears_previous_error(
    db: Session, integration: Integration
) -> None:
    crud.mark_integration_error(session=db, integration=integration, error="boom")
    with patch.dict(SYNC_FUNCTIONS, {Platform.twitter: MagicMock()}):
        assert _run(db, integration.id)["status"] == "ok"

    db.refresh(integration)
    assert integration.status == IntegrationStatus.active
    assert integration.sync_error is None


@pytest.mark.parametrize(
    "status", [IntegrationStatus.expired, IntegrationStatus.disconnected]
)
def test_integrations_needing_reconnect_are_skipped(
    db: Session, integration: Integration, status: IntegrationStatus
) -> None:
    integration.status = status
    crud.save(db, integration)
    sync_fn = MagicMock()
    with patch.dict(SYNC_FUNCTIONS, {Platform.twitter: sync_fn}):
        assert _run(db, integration.id) == {"status": "skipped", "reason": status.value}
    sync_fn.assert_not_called()


def test_integrations_of_unavailable_platforms_are_skipped(
    db: Session, integration: Integration, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "TWITTER_CLIENT_ID", "")
    sync_fn = MagicMock()
    with patch.dict(SYNC_FUNCTIONS, {Platform.twitter: sync_fn}):
        result = _run(db, integration.id)

    assert result == {"status": "skipped", "reason": "platform_unavailable"}
    sync_fn.assert_not_called()
    db.refresh(integration)
    assert integration.status == IntegrationStatus.active


def test_failure_records_error_and_retries(
    db: Session, integration: Integration
) -> None:
    sync_fn = MagicMock(side_effect=RuntimeError("API exploded"))
    with patch.dict(SYNC_FUNCTIONS, {Platform.twitter: sync_fn}):
        # Outside a worker, Celery's retry() re-raises the original error
        with pytest.raises(RuntimeError, match="API exploded"):
            _run(db, integration.id)

    db.refresh(integration)
    assert integration.status == IntegrationStatus.error
    assert integration.sync_error == "API exploded"


def test_rejected_token_marks_expired(db: Session, integration: Integration) -> None:
    sync_fn = MagicMock(side_effect=_http_error(401))
    with patch.dict(SYNC_FUNCTIONS, {Platform.twitter: sync_fn}):
        assert _run(db, integration.id)["status"] == "expired"

    db.refresh(integration)
    assert integration.status == IntegrationStatus.expired


def test_missing_token_marks_expired(db: Session, integration: Integration) -> None:
    integration.access_token_encrypted = None
    crud.save(db, integration)
    sync_fn = MagicMock()
    with patch.dict(SYNC_FUNCTIONS, {Platform.twitter: sync_fn}):
        assert _run(db, integration.id)["status"] == "expired"
    sync_fn.assert_not_called()


def test_unrefreshable_token_marks_expired(
    db: Session, integration: Integration
) -> None:
    integration.token_expires_at = datetime.now(UTC) - timedelta(hours=1)
    crud.save(db, integration)
    provider = MagicMock()
    provider.refresh_credential.return_value = "refresh"
    provider.refresh.side_effect = _http_error(400)
    sync_fn = MagicMock()

    with (
        patch.dict(SYNC_FUNCTIONS, {Platform.twitter: sync_fn}),
        patch("app.integrations.oauth.registry.get_provider", return_value=provider),
    ):
        assert _run(db, integration.id)["status"] == "expired"

    sync_fn.assert_not_called()
    db.refresh(integration)
    assert integration.status == IntegrationStatus.expired
    assert integration.sync_error


def test_expiring_token_is_refreshed_before_sync(
    db: Session, integration: Integration
) -> None:
    integration.token_expires_at = datetime.now(UTC) + timedelta(minutes=1)
    crud.save(db, integration)
    provider = MagicMock()
    provider.refresh_credential.return_value = "refresh"
    provider.refresh.return_value = TokenResponse(
        access_token="fresh-token", refresh_token=None, expires_at=None, raw={}
    )
    sync_fn = MagicMock()

    with (
        patch.dict(SYNC_FUNCTIONS, {Platform.twitter: sync_fn}),
        patch("app.integrations.oauth.registry.get_provider", return_value=provider),
    ):
        assert _run(db, integration.id)["status"] == "ok"

    assert sync_fn.call_args.args[2] == "fresh-token"


def test_nightly_sync_enqueues_only_syncable_integrations(db: Session) -> None:
    workspace = create_random_workspace(db, create_random_user(db))
    by_status = {
        status: create_fake_integration(
            db, workspace, platform=Platform.twitter, external_account_id=status.value
        )
        for status in IntegrationStatus
    }
    for status, integ in by_status.items():
        integ.status = status
        crud.save(db, integ)

    with (
        patch("app.worker.tasks.sync.Session") as session_cls,
        patch("app.worker.tasks.sync.sync_integration") as task,
    ):
        session_cls.return_value.__enter__.return_value = db
        sync_all_active_integrations.run()

    enqueued = {call.args[0] for call in task.delay.call_args_list}
    assert str(by_status[IntegrationStatus.active].id) in enqueued
    assert str(by_status[IntegrationStatus.error].id) in enqueued
    assert str(by_status[IntegrationStatus.expired].id) not in enqueued
    assert str(by_status[IntegrationStatus.disconnected].id) not in enqueued


def test_nightly_sync_skips_unavailable_platforms(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = create_random_workspace(db, create_random_user(db))
    twitter = create_fake_integration(db, workspace, platform=Platform.twitter)
    linkedin = create_fake_integration(db, workspace, platform=Platform.linkedin)
    monkeypatch.setattr(settings, "LINKEDIN_CLIENT_SECRET", "")

    with (
        patch("app.worker.tasks.sync.Session") as session_cls,
        patch("app.worker.tasks.sync.sync_integration") as task,
    ):
        session_cls.return_value.__enter__.return_value = db
        sync_all_active_integrations.run()

    enqueued = {call.args[0] for call in task.delay.call_args_list}
    assert str(twitter.id) in enqueued
    assert str(linkedin.id) not in enqueued


def test_due_follow_up_syncs_are_enqueued_once(db: Session) -> None:
    workspace = create_random_workspace(db, create_random_user(db))
    now = datetime.now(UTC)
    due = create_fake_integration(
        db, workspace, platform=Platform.twitter, external_account_id="due"
    )
    later = create_fake_integration(
        db, workspace, platform=Platform.twitter, external_account_id="later"
    )
    expired = create_fake_integration(
        db, workspace, platform=Platform.twitter, external_account_id="expired"
    )
    due.next_sync_at = now - timedelta(minutes=1)
    later.next_sync_at = now + timedelta(hours=1)
    expired.next_sync_at = now - timedelta(minutes=1)
    expired.status = IntegrationStatus.expired
    for integ in (due, later, expired):
        crud.save(db, integ)

    with (
        patch("app.worker.tasks.sync.Session") as session_cls,
        patch("app.worker.tasks.sync.sync_integration") as task,
    ):
        session_cls.return_value.__enter__.return_value = db
        sync_due_integrations.run()
        sync_due_integrations.run()

    enqueued = [call.args[0] for call in task.delay.call_args_list]
    assert enqueued.count(str(due.id)) == 1
    assert str(later.id) not in enqueued
    assert str(expired.id) not in enqueued
    db.refresh(due)
    assert due.next_sync_at is None
