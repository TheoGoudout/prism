import uuid
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app import crud
from app.core.config import settings
from app.models.integration import Platform, PlatformAccount
from app.models.workspace import Workspace, WorkspaceRole
from tests.utils.integration import create_fake_account, create_fake_integration
from tests.utils.user import create_user_with_headers
from tests.utils.workspace import add_member, create_random_workspace


def _url(workspace: Workspace, path: str = "") -> str:
    return f"{settings.API_V1_STR}/workspaces/{workspace.id}/integrations/{path}"


@pytest.fixture(autouse=True)
def revoke_access() -> Iterator[MagicMock]:
    """Never contact a real platform when disconnecting."""
    with patch("app.api.routes.integrations.revoke_access", return_value=True) as mock:
        yield mock


# ---------------------------------------------------------------------------
# Available platforms
# ---------------------------------------------------------------------------


def test_list_available_platforms(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "TWITTER_CLIENT_SECRET", "")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "")
    owner, _ = create_user_with_headers(client, db)
    viewer, viewer_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    add_member(db, ws, viewer, WorkspaceRole.viewer)

    r = client.get(_url(ws, "platforms"), headers=viewer_headers)
    assert r.status_code == 200
    assert r.json() == ["facebook", "instagram", "linkedin", "tiktok"]


def test_list_available_platforms_non_member_returns_404(
    client: TestClient, db: Session
) -> None:
    owner, _ = create_user_with_headers(client, db)
    _, outsider_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)

    r = client.get(_url(ws, "platforms"), headers=outsider_headers)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Listing integrations
# ---------------------------------------------------------------------------


def test_list_integrations_empty(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    r = client.get(_url(ws), headers=headers)
    assert r.status_code == 200
    assert r.json() == []


def test_list_integrations(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    create_fake_integration(db, ws, platform=Platform.facebook)
    create_fake_integration(
        db, ws, platform=Platform.instagram, external_account_id="ig-1"
    )

    r = client.get(_url(ws), headers=headers)
    assert r.status_code == 200
    assert [i["platform"] for i in r.json()] == ["facebook", "instagram"]


def test_list_integrations_tokens_never_exposed(
    client: TestClient, db: Session
) -> None:
    """Encrypted tokens must never appear in the API response."""
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    create_fake_integration(db, ws)

    body = r = client.get(_url(ws), headers=headers).text
    for secret in ("access_token", "refresh_token", "encrypted", "fake-access-token"):
        assert secret not in body, r


def test_list_integrations_non_member_returns_404(
    client: TestClient, db: Session
) -> None:
    owner, _ = create_user_with_headers(client, db)
    _, outsider_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)

    r = client.get(_url(ws), headers=outsider_headers)
    assert r.status_code == 404


def test_list_integrations_workspace_isolation(client: TestClient, db: Session) -> None:
    user_a, _ = create_user_with_headers(client, db)
    user_b, headers_b = create_user_with_headers(client, db)
    ws_a = create_random_workspace(db, user_a)
    ws_b = create_random_workspace(db, user_b)
    create_fake_integration(db, ws_a)

    r = client.get(_url(ws_b), headers=headers_b)
    assert r.status_code == 200
    assert r.json() == []


# ---------------------------------------------------------------------------
# Delete integration
# ---------------------------------------------------------------------------


def test_delete_integration_cascades_accounts(client: TestClient, db: Session) -> None:
    """Deleting an integration also deletes its platform accounts."""
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws)
    account = create_fake_account(db, integration)

    r = client.delete(_url(ws, str(integration.id)), headers=headers)
    assert r.status_code == 204

    db.expunge_all()
    assert crud.get_integration(session=db, integration_id=integration.id) is None
    assert db.get(PlatformAccount, account.id) is None


def test_delete_integration_revokes_access(
    client: TestClient, db: Session, revoke_access: MagicMock
) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws)

    r = client.delete(_url(ws, str(integration.id)), headers=headers)
    assert r.status_code == 204
    revoke_access.assert_called_once()
    assert revoke_access.call_args.args[1].id == integration.id


def test_delete_integration_viewer_forbidden(
    client: TestClient, db: Session, revoke_access: MagicMock
) -> None:
    owner, _ = create_user_with_headers(client, db)
    viewer, viewer_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    add_member(db, ws, viewer, WorkspaceRole.viewer)
    integration = create_fake_integration(db, ws)

    r = client.delete(_url(ws, str(integration.id)), headers=viewer_headers)
    assert r.status_code == 403
    revoke_access.assert_not_called()


def test_delete_integration_not_found(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    r = client.delete(_url(ws, str(uuid.uuid4())), headers=headers)
    assert r.status_code == 404


def test_delete_integration_of_another_workspace_returns_404(
    client: TestClient, db: Session
) -> None:
    """An integration can only be reached through its own workspace."""
    user, headers = create_user_with_headers(client, db)
    other, _ = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    foreign = create_fake_integration(db, create_random_workspace(db, other))

    r = client.delete(_url(ws, str(foreign.id)), headers=headers)
    assert r.status_code == 404
    assert crud.get_integration(session=db, integration_id=foreign.id) is not None


# ---------------------------------------------------------------------------
# Token encryption round-trip (unit-level, no HTTP)
# ---------------------------------------------------------------------------


def test_token_encryption_round_trip(client: TestClient, db: Session) -> None:
    """Tokens stored in DB are encrypted; decrypt_token returns the original."""
    user, _ = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws, external_account_id="enc-test")

    assert integration.access_token_encrypted != "fake-access-token"
    assert crud.get_access_token(integration) == "fake-access-token"
    assert crud.get_refresh_token(integration) == "fake-refresh-token"


# ---------------------------------------------------------------------------
# Manual sync
# ---------------------------------------------------------------------------


def test_trigger_sync_accepted(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws)

    with patch("app.worker.tasks.sync.sync_integration") as mock_task:
        r = client.post(_url(ws, f"{integration.id}/sync"), headers=headers)

    assert r.status_code == 202
    mock_task.delay.assert_called_once_with(str(integration.id))


def test_trigger_sync_unavailable_platform_rejected(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws, platform=Platform.facebook)
    monkeypatch.setattr(settings, "FACEBOOK_APP_ID", "")

    with patch("app.worker.tasks.sync.sync_integration") as mock_task:
        r = client.post(_url(ws, f"{integration.id}/sync"), headers=headers)

    assert r.status_code == 400
    mock_task.delay.assert_not_called()


def test_trigger_sync_viewer_forbidden(client: TestClient, db: Session) -> None:
    owner, _ = create_user_with_headers(client, db)
    viewer, viewer_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    add_member(db, ws, viewer, WorkspaceRole.viewer)
    integration = create_fake_integration(db, ws)

    r = client.post(_url(ws, f"{integration.id}/sync"), headers=viewer_headers)
    assert r.status_code == 403
