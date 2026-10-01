import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.models.integration import Platform
from tests.utils.integration import create_fake_account, create_fake_integration
from tests.utils.user import create_user_with_headers
from tests.utils.workspace import create_random_workspace

PREFIX = f"{settings.API_V1_STR}/integrations"


# ---------------------------------------------------------------------------
# Listing integrations
# ---------------------------------------------------------------------------


def test_list_integrations_empty(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    r = client.get(PREFIX + "/", headers=headers, params={"workspace_id": str(ws.id)})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    assert body["data"] == []


def test_list_integrations(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    create_fake_integration(db, ws, platform=Platform.facebook)
    create_fake_integration(
        db, ws, platform=Platform.instagram, external_account_id="ig-1"
    )

    r = client.get(PREFIX + "/", headers=headers, params={"workspace_id": str(ws.id)})
    assert r.status_code == 200
    assert r.json()["count"] == 2


def test_list_integrations_filtered_by_platform(
    client: TestClient, db: Session
) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    create_fake_integration(db, ws, platform=Platform.facebook)
    create_fake_integration(
        db, ws, platform=Platform.twitter, external_account_id="tw-1"
    )

    r = client.get(
        PREFIX + "/",
        headers=headers,
        params={"workspace_id": str(ws.id), "platform": "facebook"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["data"][0]["platform"] == "facebook"


def test_list_integrations_non_member_returns_404(
    client: TestClient, db: Session
) -> None:
    owner, _ = create_user_with_headers(client, db)
    outsider, outsider_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)

    r = client.get(
        PREFIX + "/", headers=outsider_headers, params={"workspace_id": str(ws.id)}
    )
    assert r.status_code == 404


def test_list_integrations_workspace_isolation(client: TestClient, db: Session) -> None:
    user_a, headers_a = create_user_with_headers(client, db)
    user_b, headers_b = create_user_with_headers(client, db)
    ws_a = create_random_workspace(db, user_a)
    ws_b = create_random_workspace(db, user_b)
    create_fake_integration(db, ws_a)

    r = client.get(
        PREFIX + "/", headers=headers_b, params={"workspace_id": str(ws_b.id)}
    )
    assert r.status_code == 200
    assert r.json()["count"] == 0


# ---------------------------------------------------------------------------
# Get integration
# ---------------------------------------------------------------------------


def test_get_integration(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws)

    r = client.get(f"{PREFIX}/{integration.id}", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == str(integration.id)
    assert body["platform"] == "facebook"
    assert body["external_account_name"] == "Test Page"


def test_get_integration_tokens_never_exposed(client: TestClient, db: Session) -> None:
    """Encrypted tokens must never appear in the API response."""
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws)

    r = client.get(f"{PREFIX}/{integration.id}", headers=headers)
    body = r.json()
    body_str = str(body)
    assert "access_token" not in body_str
    assert "refresh_token" not in body_str
    assert "encrypted" not in body_str
    assert "fake-access-token" not in body_str
    assert "fake-refresh-token" not in body_str


def test_get_integration_non_member_returns_404(
    client: TestClient, db: Session
) -> None:
    owner, _ = create_user_with_headers(client, db)
    outsider, outsider_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    integration = create_fake_integration(db, ws)

    r = client.get(f"{PREFIX}/{integration.id}", headers=outsider_headers)
    assert r.status_code == 404


def test_get_integration_not_found(
    client: TestClient, normal_user_token_headers: dict
) -> None:
    r = client.get(f"{PREFIX}/{uuid.uuid4()}", headers=normal_user_token_headers)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Delete integration
# ---------------------------------------------------------------------------


def test_delete_integration(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws)

    r = client.delete(f"{PREFIX}/{integration.id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["message"] == "Integration disconnected successfully"

    r = client.get(f"{PREFIX}/{integration.id}", headers=headers)
    assert r.status_code == 404


def test_delete_integration_cascades_accounts(client: TestClient, db: Session) -> None:
    """Deleting an integration must also delete its platform accounts."""
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws)
    create_fake_account(db, integration)

    client.delete(f"{PREFIX}/{integration.id}", headers=headers)

    # Accounts endpoint should 404 since integration is gone
    r = client.get(f"{PREFIX}/{integration.id}/accounts", headers=headers)
    assert r.status_code == 404


def test_delete_integration_viewer_forbidden(client: TestClient, db: Session) -> None:
    owner, owner_headers = create_user_with_headers(client, db)
    viewer, viewer_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)

    # Add viewer to workspace
    client.post(
        f"{settings.API_V1_STR}/workspaces/{ws.id}/members",
        headers=owner_headers,
        json={"user_id": str(viewer.id), "role": "viewer"},
    )
    integration = create_fake_integration(db, ws)

    r = client.delete(f"{PREFIX}/{integration.id}", headers=viewer_headers)
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Platform accounts
# ---------------------------------------------------------------------------


def test_list_accounts_empty(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws)

    r = client.get(f"{PREFIX}/{integration.id}/accounts", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0


def test_list_accounts(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws)
    create_fake_account(db, integration, external_id="page-1", name="Page One")
    create_fake_account(db, integration, external_id="page-2", name="Page Two")

    r = client.get(f"{PREFIX}/{integration.id}/accounts", headers=headers)
    assert r.status_code == 200
    assert r.json()["count"] == 2


def test_list_accounts_non_member_returns_404(client: TestClient, db: Session) -> None:
    owner, _ = create_user_with_headers(client, db)
    outsider, outsider_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    integration = create_fake_integration(db, ws)
    create_fake_account(db, integration)

    r = client.get(f"{PREFIX}/{integration.id}/accounts", headers=outsider_headers)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Token encryption round-trip (unit-level, no HTTP)
# ---------------------------------------------------------------------------


def test_token_encryption_round_trip(db: Session) -> None:
    """Tokens stored in DB are encrypted; decrypt_token returns the original."""
    from app.crud.integration import get_access_token, get_refresh_token
    from app.crud.user import create_user
    from app.models.user import UserCreate
    from tests.utils.utils import random_email, random_lower_string

    user = create_user(
        session=db,
        user_create=UserCreate(email=random_email(), password=random_lower_string()),
    )
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws, external_account_id="enc-test")

    assert integration.access_token_encrypted != "fake-access-token"
    assert get_access_token(integration) == "fake-access-token"
    assert get_refresh_token(integration) == "fake-refresh-token"


# ---------------------------------------------------------------------------
# Sync endpoint (stub)
# ---------------------------------------------------------------------------


def test_trigger_sync_accepted(client: TestClient, db: Session) -> None:
    from unittest.mock import patch

    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws)

    with patch("app.worker.tasks.sync.sync_integration") as mock_task:
        r = client.post(f"{PREFIX}/{integration.id}/sync", headers=headers)

    assert r.status_code == 202
    assert r.json()["message"] == "Sync enqueued"
    mock_task.delay.assert_called_once_with(str(integration.id))


def test_trigger_sync_viewer_forbidden(client: TestClient, db: Session) -> None:
    owner, owner_headers = create_user_with_headers(client, db)
    viewer, viewer_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    client.post(
        f"{settings.API_V1_STR}/workspaces/{ws.id}/members",
        headers=owner_headers,
        json={"user_id": str(viewer.id), "role": "viewer"},
    )
    integration = create_fake_integration(db, ws)

    r = client.post(f"{PREFIX}/{integration.id}/sync", headers=viewer_headers)
    assert r.status_code == 403
