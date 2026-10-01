"""
Tests for Celery sync tasks.
All DB and Celery broker calls are mocked — no external services needed.
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.models.integration import Integration, IntegrationStatus, Platform
from app.worker.tasks.sync import (
    _platform_sync,
    register_platform_sync,
    sync_all_active_integrations,
    sync_integration,
    sync_workspace_integrations,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _restore_sync_registry():
    """Tests below add/remove registry entries; undo that afterwards so the
    real platform registrations seen by other test modules stay intact."""
    with patch.dict(_platform_sync):
        yield


def _make_integration(
    status: IntegrationStatus = IntegrationStatus.active,
    platform: Platform = Platform.facebook,
) -> MagicMock:
    integ = MagicMock(spec=Integration)
    integ.id = uuid.uuid4()
    integ.status = status
    integ.platform = platform  # real enum — .value works naturally
    integ.workspace_id = uuid.uuid4()
    integ.token_expires_at = None  # non-expiring: no refresh attempted
    return integ


# ---------------------------------------------------------------------------
# register_platform_sync
# ---------------------------------------------------------------------------


def test_register_platform_sync_stores_function():
    sentinel = MagicMock()
    register_platform_sync("__test_platform__", sentinel)
    assert _platform_sync.get("__test_platform__") is sentinel
    # Cleanup
    del _platform_sync["__test_platform__"]


# ---------------------------------------------------------------------------
# sync_integration task
# crud is imported lazily inside the task; patch it at app.crud
# ---------------------------------------------------------------------------


@patch("app.worker.tasks.sync.Session")
@patch("app.crud.get_integration", return_value=None)
def test_sync_integration_not_found(mock_get_integration, mock_session_cls):
    session_ctx = MagicMock()
    mock_session_cls.return_value.__enter__ = MagicMock(return_value=session_ctx)
    mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

    result = sync_integration.run(str(uuid.uuid4()))
    assert result["status"] == "not_found"


@patch("app.worker.tasks.sync.Session")
@patch("app.crud.get_integration")
def test_sync_integration_disconnected(mock_get_integration, mock_session_cls):
    integ = _make_integration(status=IntegrationStatus.disconnected)
    mock_get_integration.return_value = integ

    session_ctx = MagicMock()
    mock_session_cls.return_value.__enter__ = MagicMock(return_value=session_ctx)
    mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

    result = sync_integration.run(str(integ.id))
    assert result["status"] == "skipped"
    assert result["reason"] == "disconnected"


@patch("app.worker.tasks.sync.Session")
@patch("app.crud.get_integration")
def test_sync_integration_no_sync_registered(mock_get_integration, mock_session_cls):
    integ = _make_integration(platform=Platform.tiktok)
    _platform_sync.pop(Platform.tiktok.value, None)
    mock_get_integration.return_value = integ

    session_ctx = MagicMock()
    mock_session_cls.return_value.__enter__ = MagicMock(return_value=session_ctx)
    mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

    result = sync_integration.run(str(integ.id))
    assert result["status"] == "skipped"
    assert "no sync" in result["reason"]


@patch("app.crud.mark_integration_synced")
@patch("app.crud.get_integration")
@patch("app.worker.tasks.sync.Session")
def test_sync_integration_calls_registered_fn(
    mock_session_cls, mock_get_integration, mock_mark_synced
):
    integ = _make_integration(platform=Platform.facebook)
    mock_get_integration.return_value = integ

    session_ctx = MagicMock()
    mock_session_cls.return_value.__enter__ = MagicMock(return_value=session_ctx)
    mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

    sync_fn = MagicMock()
    register_platform_sync(Platform.facebook.value, sync_fn)

    result = sync_integration.run(str(integ.id))

    sync_fn.assert_called_once_with(session=session_ctx, integration=integ)
    mock_mark_synced.assert_called_once()
    assert result["status"] == "ok"

    del _platform_sync[Platform.facebook.value]


@patch("app.crud.mark_integration_error")
@patch("app.crud.get_integration")
@patch("app.worker.tasks.sync.Session")
def test_sync_integration_error_marks_integration_and_retries(
    mock_session_cls, mock_get_integration, mock_mark_error
):
    integ = _make_integration(platform=Platform.instagram)
    mock_get_integration.return_value = integ

    session_ctx = MagicMock()
    mock_session_cls.return_value.__enter__ = MagicMock(return_value=session_ctx)
    mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

    sync_fn = MagicMock(side_effect=RuntimeError("API exploded"))
    register_platform_sync(Platform.instagram.value, sync_fn)

    with pytest.raises(Exception):
        sync_integration.run(str(integ.id))

    mock_mark_error.assert_called_once()
    call_kwargs = mock_mark_error.call_args.kwargs
    assert "API exploded" in call_kwargs["error"]

    del _platform_sync[Platform.instagram.value]


# ---------------------------------------------------------------------------
# sync_all_active_integrations
# ---------------------------------------------------------------------------


@patch("app.worker.tasks.sync.sync_integration")
@patch("app.worker.tasks.sync.Session")
def test_sync_all_active_enqueues_tasks(mock_session_cls, mock_sync_task):
    integrations = [_make_integration(), _make_integration()]

    session_mock = MagicMock()
    session_mock.exec.return_value.all.return_value = integrations
    mock_session_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
    mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

    result = sync_all_active_integrations.run()

    assert result["enqueued"] == 2
    assert mock_sync_task.delay.call_count == 2


@patch("app.worker.tasks.sync.sync_integration")
@patch("app.worker.tasks.sync.Session")
def test_sync_all_active_empty(mock_session_cls, mock_sync_task):
    session_mock = MagicMock()
    session_mock.exec.return_value.all.return_value = []
    mock_session_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
    mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

    result = sync_all_active_integrations.run()

    assert result["enqueued"] == 0
    mock_sync_task.delay.assert_not_called()


# ---------------------------------------------------------------------------
# sync_workspace_integrations
# ---------------------------------------------------------------------------


@patch("app.worker.tasks.sync.sync_integration")
@patch("app.worker.tasks.sync.Session")
def test_sync_workspace_integrations_enqueues_tasks(mock_session_cls, mock_sync_task):
    wid = uuid.uuid4()
    integrations = [_make_integration(), _make_integration(), _make_integration()]

    session_mock = MagicMock()
    session_mock.exec.return_value.all.return_value = integrations
    mock_session_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
    mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

    result = sync_workspace_integrations.run(str(wid))

    assert result["enqueued"] == 3
    assert result["workspace_id"] == str(wid)
    assert mock_sync_task.delay.call_count == 3
