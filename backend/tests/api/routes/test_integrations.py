import uuid
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app import crud
from app.core.config import settings
from app.integrations.apikey.base import InvalidApiKeyError
from app.integrations.oauth.base import AccountInfo
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
    assert r.json() == [
        "facebook",
        "instagram",
        "linkedin",
        "tiktok",
        "mailchimp",
        "klaviyo",
        # Connected with an API key: always available
        "brevo",
    ]


def test_list_available_platforms_non_member_returns_404(
    client: TestClient, db: Session
) -> None:
    owner, _ = create_user_with_headers(client, db)
    _, outsider_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)

    r = client.get(_url(ws, "platforms"), headers=outsider_headers)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Connecting with an API key
# ---------------------------------------------------------------------------

BREVO_ACCOUNT = "app.integrations.apikey.brevo.brevo_provider.get_account_info"


def _brevo_account(external_id: str = "org-1") -> AccountInfo:
    return AccountInfo(external_id=external_id, name="Acme", avatar_url=None)


def test_connect_with_api_key(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    with (
        patch(BREVO_ACCOUNT, return_value=_brevo_account()) as account_info,
        patch("app.worker.tasks.sync.sync_integration") as mock_task,
    ):
        r = client.post(
            _url(ws, "connect/brevo/api-key"),
            headers=headers,
            json={"api_key": "  xkeysib-secret  "},
        )

    assert r.status_code == 200
    body = r.json()
    assert body["platform"] == "brevo"
    assert body["status"] == "active"
    assert body["external_account_name"] == "Acme"
    assert "xkeysib-secret" not in r.text
    account_info.assert_called_once_with("xkeysib-secret")
    mock_task.delay.assert_called_once_with(body["id"])

    integration = crud.get_integration(session=db, integration_id=uuid.UUID(body["id"]))
    assert integration is not None
    assert crud.get_access_token(integration) == "xkeysib-secret"
    assert integration.token_expires_at is None


def test_connect_with_api_key_again_replaces_the_key(
    client: TestClient, db: Session
) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    ids = []
    for key in ("first-key", "second-key"):
        with (
            patch(BREVO_ACCOUNT, return_value=_brevo_account()),
            patch("app.worker.tasks.sync.sync_integration"),
        ):
            r = client.post(
                _url(ws, "connect/brevo/api-key"),
                headers=headers,
                json={"api_key": key},
            )
        assert r.status_code == 200
        ids.append(r.json()["id"])

    assert ids[0] == ids[1]
    db.expunge_all()
    integration = crud.get_integration(session=db, integration_id=uuid.UUID(ids[0]))
    assert integration is not None
    assert crud.get_access_token(integration) == "second-key"


def test_connect_with_rejected_api_key(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    with patch(BREVO_ACCOUNT, side_effect=InvalidApiKeyError("rejected")):
        r = client.post(
            _url(ws, "connect/brevo/api-key"), headers=headers, json={"api_key": "bad"}
        )

    assert r.status_code == 400
    assert "rejected" in r.json()["detail"]
    assert client.get(_url(ws), headers=headers).json() == []


def test_connect_with_api_key_platform_unreachable(
    client: TestClient, db: Session
) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    with patch(BREVO_ACCOUNT, side_effect=httpx.ConnectError("down")):
        r = client.post(
            _url(ws, "connect/brevo/api-key"), headers=headers, json={"api_key": "k"}
        )

    assert r.status_code == 502


def test_connect_with_api_key_empty_key_rejected(
    client: TestClient, db: Session
) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    r = client.post(
        _url(ws, "connect/brevo/api-key"), headers=headers, json={"api_key": ""}
    )
    assert r.status_code == 422


def test_connect_oauth_platform_with_api_key_rejected(
    client: TestClient, db: Session
) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    r = client.post(
        _url(ws, "connect/mailchimp/api-key"), headers=headers, json={"api_key": "k"}
    )
    assert r.status_code == 400


def test_connect_api_key_platform_with_oauth_rejected(
    client: TestClient, db: Session
) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    r = client.get(_url(ws, "connect/brevo"), headers=headers)
    assert r.status_code == 400


def test_connect_with_api_key_viewer_forbidden(client: TestClient, db: Session) -> None:
    owner, _ = create_user_with_headers(client, db)
    viewer, viewer_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    add_member(db, ws, viewer, WorkspaceRole.viewer)

    with patch(BREVO_ACCOUNT) as account_info:
        r = client.post(
            _url(ws, "connect/brevo/api-key"),
            headers=viewer_headers,
            json={"api_key": "k"},
        )
    assert r.status_code == 403
    account_info.assert_not_called()


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


# ---------------------------------------------------------------------------
# Choosing the accounts shown (e.g. which Facebook Pages)
# ---------------------------------------------------------------------------


def test_list_integrations_includes_accounts(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws)
    create_fake_account(db, integration, external_id="p-2", name="Page B")
    create_fake_account(db, integration, external_id="p-1", name="Page A")

    r = client.get(_url(ws), headers=headers)
    assert r.status_code == 200
    accounts = r.json()[0]["accounts"]
    assert [(a["name"], a["is_active"]) for a in accounts] == [
        ("Page A", True),
        ("Page B", True),
    ]


def test_hide_and_show_account(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws)
    shown = create_fake_account(db, integration, external_id="p-1")
    hidden = create_fake_account(db, integration, external_id="p-2")
    url = _url(ws, f"{integration.id}/accounts/{hidden.id}")

    r = client.patch(url, headers=headers, json={"is_active": False})
    assert r.status_code == 200
    assert r.json()["is_active"] is False
    active = crud.get_accounts_for_workspace(session=db, workspace_id=ws.id)
    assert [a.id for a in active] == [shown.id]

    r = client.patch(url, headers=headers, json={"is_active": True})
    assert r.status_code == 200
    active = crud.get_accounts_for_workspace(session=db, workspace_id=ws.id)
    assert {a.id for a in active} == {shown.id, hidden.id}


def test_hidden_account_stays_hidden_after_sync(
    client: TestClient, db: Session
) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws)
    account = create_fake_account(db, integration)
    client.patch(
        _url(ws, f"{integration.id}/accounts/{account.id}"),
        headers=headers,
        json={"is_active": False},
    )

    # A sync finds the account again
    synced = create_fake_account(db, integration, name="Renamed Page")
    assert synced.id == account.id
    assert synced.is_active is False


def test_update_account_viewer_forbidden(client: TestClient, db: Session) -> None:
    owner, _ = create_user_with_headers(client, db)
    viewer, viewer_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    add_member(db, ws, viewer, WorkspaceRole.viewer)
    integration = create_fake_integration(db, ws)
    account = create_fake_account(db, integration)

    r = client.patch(
        _url(ws, f"{integration.id}/accounts/{account.id}"),
        headers=viewer_headers,
        json={"is_active": False},
    )
    assert r.status_code == 403
    db.refresh(account)
    assert account.is_active is True


def test_update_account_of_another_integration_returns_404(
    client: TestClient, db: Session
) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    facebook = create_fake_integration(db, ws)
    instagram = create_fake_integration(
        db, ws, platform=Platform.instagram, external_account_id="ig-1"
    )
    account = create_fake_account(db, instagram)

    r = client.patch(
        _url(ws, f"{facebook.id}/accounts/{account.id}"),
        headers=headers,
        json={"is_active": False},
    )
    assert r.status_code == 404


def test_update_account_of_another_workspace_returns_404(
    client: TestClient, db: Session
) -> None:
    user_a, _ = create_user_with_headers(client, db)
    user_b, headers_b = create_user_with_headers(client, db)
    ws_a = create_random_workspace(db, user_a)
    ws_b = create_random_workspace(db, user_b)
    integration = create_fake_integration(db, ws_a)
    account = create_fake_account(db, integration)

    r = client.patch(
        _url(ws_b, f"{integration.id}/accounts/{account.id}"),
        headers=headers_b,
        json={"is_active": False},
    )
    assert r.status_code == 404
