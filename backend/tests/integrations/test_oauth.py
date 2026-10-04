"""
OAuth2 provider unit tests and connect/callback route tests.
All external HTTP calls are mocked — no real provider is contacted.
"""

import logging
import urllib.parse
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.integrations.oauth.base import AccountNotFoundError, OAuthState
from app.integrations.oauth.facebook import facebook_provider
from app.integrations.oauth.google_analytics import google_analytics_provider
from app.integrations.oauth.instagram import instagram_provider
from app.integrations.oauth.registry import (
    available_platforms,
    get_provider,
    is_available,
    log_availability,
)
from app.integrations.oauth.tiktok import tiktok_provider
from app.integrations.oauth.twitter import twitter_provider
from app.models.integration import Platform
from app.models.workspace import Workspace, WorkspaceRole
from tests.utils.user import create_user_with_headers
from tests.utils.workspace import add_member, create_random_workspace

PREFIX = f"{settings.API_V1_STR}/oauth"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    platform: Platform = Platform.facebook,
    pkce_verifier: str | None = None,
) -> str:
    return OAuthState(
        workspace_id=workspace_id,
        user_id=user_id,
        platform=platform,
        pkce_verifier=pkce_verifier,
    ).encode()


def _connect_url(workspace: Workspace, platform: str) -> str:
    return f"{settings.API_V1_STR}/workspaces/{workspace.id}/integrations/connect/{platform}"


def _query(url: str) -> dict[str, str]:
    return dict(
        urllib.parse.parse_qsl(urllib.parse.urlparse(url).query, keep_blank_values=True)
    )


# ---------------------------------------------------------------------------
# OAuthProvider base: state encode/decode
# ---------------------------------------------------------------------------


def test_state_encode_decode_roundtrip() -> None:
    ws_id, user_id = uuid.uuid4(), uuid.uuid4()
    state = _make_state(ws_id, user_id, Platform.twitter, pkce_verifier="secret-v")
    decoded = OAuthState.decode(state)
    assert decoded.workspace_id == ws_id
    assert decoded.user_id == user_id
    assert decoded.platform == Platform.twitter
    assert decoded.pkce_verifier == "secret-v"


def test_state_is_opaque() -> None:
    """Neither the workspace id nor the PKCE verifier are readable in the URL."""
    ws_id = uuid.uuid4()
    state = _make_state(ws_id, uuid.uuid4(), pkce_verifier="secret-v")
    assert str(ws_id) not in state
    assert "secret-v" not in state


def test_state_decode_invalid_raises() -> None:
    with pytest.raises(ValueError):
        OAuthState.decode("not-valid-json!!!")


def test_state_decode_forged_plain_json_raises() -> None:
    """The pre-fix format (plain URL-encoded JSON) must be rejected."""
    forged = urllib.parse.quote(f'{{"workspace_id": "{uuid.uuid4()}", "csrf": "x"}}')
    with pytest.raises(ValueError):
        OAuthState.decode(forged)


def test_state_decode_tampered_raises() -> None:
    state = _make_state(uuid.uuid4(), uuid.uuid4())
    tampered = state[:-6] + ("A" if state[-6] != "A" else "B") + state[-5:]
    with pytest.raises(ValueError):
        OAuthState.decode(tampered)


def test_state_decode_expired_raises() -> None:
    from app.integrations.oauth import base

    state = _make_state(uuid.uuid4(), uuid.uuid4())
    with patch.object(base, "STATE_MAX_AGE_SECONDS", -1):
        with pytest.raises(ValueError):
            OAuthState.decode(state)


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------


def test_all_platforms_registered() -> None:
    for platform in Platform:
        provider = get_provider(platform)
        assert provider.PLATFORM == platform


def test_get_provider_unknown_raises() -> None:
    with pytest.raises(ValueError):
        get_provider("nonexistent")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Platform availability
# ---------------------------------------------------------------------------


def test_every_platform_available_once_its_app_is_set_up() -> None:
    assert available_platforms() == list(Platform)


@pytest.mark.parametrize("missing", ["TWITTER_CLIENT_ID", "TWITTER_CLIENT_SECRET"])
def test_platform_unavailable_without_its_credentials(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    monkeypatch.setattr(settings, missing, "")
    assert not twitter_provider.is_configured
    assert twitter_provider.missing_settings == [missing]
    assert not is_available(Platform.twitter)
    assert Platform.twitter not in available_platforms()
    assert is_available(Platform.linkedin)


def test_meta_platforms_share_the_facebook_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FACEBOOK_APP_SECRET", "")
    assert not is_available(Platform.facebook)
    assert not is_available(Platform.instagram)


def test_log_availability(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(settings, "TIKTOK_CLIENT_KEY", "")
    monkeypatch.setattr(settings, "TIKTOK_CLIENT_SECRET", "")
    with caplog.at_level(logging.INFO, logger="app.integrations.oauth.registry"):
        log_availability()

    messages = [r.getMessage() for r in caplog.records]
    assert "Platform integration activated: twitter" in messages
    assert (
        "Platform integration not activated: tiktok "
        "(missing TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET)"
    ) in messages
    assert "Platform integration activated: tiktok" not in messages
    assert messages[-1].startswith("5 of 6 platform integrations activated: ")


# ---------------------------------------------------------------------------
# Facebook provider — mocked HTTP
# ---------------------------------------------------------------------------


def test_facebook_exchange_code_upgrades_to_long_lived() -> None:
    short = MagicMock()
    short.json.return_value = {"access_token": "short-tok", "expires_in": 3600}
    long = MagicMock()
    long.json.return_value = {"access_token": "long-tok", "expires_in": 5184000}

    with patch(
        "app.integrations.oauth.base.httpx.post", side_effect=[short, long]
    ) as mock_post:
        result = facebook_provider.exchange_code(
            code="c", redirect_uri="http://localhost/cb"
        )

    assert result.access_token == "long-tok"
    second_call = mock_post.call_args_list[1]
    assert second_call.kwargs["data"]["grant_type"] == "fb_exchange_token"
    assert second_call.kwargs["data"]["fb_exchange_token"] == "short-tok"
    assert result.expires_at is not None
    assert (result.expires_at - datetime.now(UTC)).days >= 59


def test_facebook_refresh_credential_is_access_token() -> None:
    assert (
        facebook_provider.refresh_credential(access_token="a", refresh_token=None)
        == "a"
    )


def test_facebook_refresh() -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = {"access_token": "fb-long", "expires_in": 5184000}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_response):
        result = facebook_provider.refresh("old-token")

    assert result.access_token == "fb-long"


def test_facebook_get_account_info() -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "id": "123456",
        "name": "My Page",
        "picture": {"data": {"url": "https://example.com/pic.jpg"}},
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.get", return_value=mock_response):
        info = facebook_provider.get_account_info("fb-token")

    assert info.external_id == "123456"
    assert info.name == "My Page"
    assert info.avatar_url == "https://example.com/pic.jpg"


# ---------------------------------------------------------------------------
# Instagram provider — mocked HTTP
# ---------------------------------------------------------------------------


def test_instagram_get_account_info_with_ig_account() -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [
            {
                "id": "page-1",
                "instagram_business_account": {
                    "id": "ig-789",
                    "name": "My IG",
                    "profile_picture_url": "https://example.com/ig.jpg",
                },
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.get", return_value=mock_response):
        info = instagram_provider.get_account_info("ig-token")

    assert info.external_id == "ig-789"
    assert info.name == "My IG"


def test_instagram_get_account_info_without_business_account_raises() -> None:
    """Without a linked IG Business account there is nothing to sync."""
    pages_response = MagicMock()
    pages_response.json.return_value = {"data": [{"id": "page-without-ig"}]}

    with patch("httpx.get", return_value=pages_response):
        with pytest.raises(AccountNotFoundError) as exc_info:
            instagram_provider.get_account_info("token")
    assert exc_info.value.error_code == "no_instagram_account"


def test_instagram_get_account_info_follows_pagination() -> None:
    """The linked Page may not be on the first page of /me/accounts."""
    first = MagicMock()
    first.json.return_value = {
        "data": [{"id": "page-1"}],
        "paging": {"next": "https://graph.facebook.com/next-page"},
    }
    second = MagicMock()
    second.json.return_value = {
        "data": [{"id": "page-2", "instagram_business_account": {"id": "ig-2"}}]
    }

    with patch("httpx.get", side_effect=[first, second]) as mock_get:
        info = instagram_provider.get_account_info("token")

    assert info.external_id == "ig-2"
    assert mock_get.call_args.args[0] == "https://graph.facebook.com/next-page"


# ---------------------------------------------------------------------------
# Twitter provider — mocked HTTP, PKCE
# ---------------------------------------------------------------------------


def test_twitter_auth_url_contains_pkce() -> None:
    url = twitter_provider.get_auth_url(
        redirect_uri="http://localhost/cb", state="s", code_challenge="chal"
    )
    params = _query(url)
    assert params["code_challenge"] == "chal"
    assert params["code_challenge_method"] == "S256"
    assert params["state"] == "s"


def test_twitter_exchange_code_requires_verifier() -> None:
    with pytest.raises(ValueError):
        twitter_provider.exchange_code(code="c", redirect_uri="http://localhost/cb")


def test_tiktok_auth_url_uses_client_key() -> None:
    url = tiktok_provider.get_auth_url(redirect_uri="http://localhost/cb", state="s")
    params = _query(url)
    assert "client_key" in params
    assert "client_id" not in params
    assert "," in params["scope"]


def test_twitter_exchange_code() -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "access_token": "tw-tok",
        "refresh_token": "tw-refresh",
        "expires_in": 7200,
    }
    mock_response.raise_for_status = MagicMock()

    with patch("app.integrations.oauth.twitter.httpx.post", return_value=mock_response):
        result = twitter_provider.exchange_code(
            code="tw-code", redirect_uri="http://localhost/cb", code_verifier="verifier"
        )

    assert result.access_token == "tw-tok"
    assert result.refresh_token == "tw-refresh"


def test_twitter_get_account_info() -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": {
            "id": "tw-uid",
            "name": "Twitter User",
            "profile_image_url": "https://pbs.twimg.com/img.jpg",
        }
    }
    mock_response.raise_for_status = MagicMock()

    with patch("app.integrations.oauth.twitter.httpx.get", return_value=mock_response):
        info = twitter_provider.get_account_info("tw-tok")

    assert info.external_id == "tw-uid"


# ---------------------------------------------------------------------------
# Google Analytics provider — mocked HTTP
# ---------------------------------------------------------------------------


def test_google_analytics_auth_url_has_offline_access() -> None:
    url = google_analytics_provider.get_auth_url(
        redirect_uri="http://localhost/cb", state="s"
    )
    assert "access_type=offline" in url
    assert "prompt=consent" in url


def test_google_analytics_refresh_keeps_same_refresh_token() -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = {"access_token": "new-ga-tok", "expires_in": 3600}
    mock_response.raise_for_status = MagicMock()

    with patch(
        "app.integrations.oauth.google_analytics.httpx.post", return_value=mock_response
    ):
        result = google_analytics_provider.refresh("original-refresh")

    assert result.refresh_token == "original-refresh"


# ---------------------------------------------------------------------------
# Connect route
# ---------------------------------------------------------------------------


def test_connect_returns_authorization_url(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    r = client.get(
        _connect_url(ws, "facebook"),
        headers=headers,
    )
    assert r.status_code == 200
    assert "authorization_url" in r.json()
    url = r.json()["authorization_url"]
    assert "facebook.com" in url
    state = OAuthState.decode(_query(url)["state"])
    assert state.workspace_id == ws.id
    assert state.user_id == user.id
    assert state.platform == Platform.facebook
    assert state.pkce_verifier is None


def test_connect_twitter_keeps_pkce_verifier_server_side(
    client: TestClient, db: Session
) -> None:
    import base64
    import hashlib

    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    r = client.get(
        _connect_url(ws, "twitter"),
        headers=headers,
    )
    assert r.status_code == 200
    params = _query(r.json()["authorization_url"])
    verifier = OAuthState.decode(params["state"]).pkce_verifier
    assert verifier
    assert verifier not in r.json()["authorization_url"]
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    assert params["code_challenge"] == expected


def test_connect_unavailable_platform_rejected(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "LINKEDIN_CLIENT_ID", "")
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    r = client.get(_connect_url(ws, "linkedin"), headers=headers)
    assert r.status_code == 400
    assert "not set up" in r.json()["detail"]


def test_connect_viewer_forbidden(client: TestClient, db: Session) -> None:
    owner, owner_headers = create_user_with_headers(client, db)
    viewer, viewer_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    add_member(db, ws, viewer, WorkspaceRole.viewer)

    r = client.get(
        _connect_url(ws, "facebook"),
        headers=viewer_headers,
    )
    assert r.status_code == 403


def test_connect_non_member_returns_404(client: TestClient, db: Session) -> None:
    owner, _ = create_user_with_headers(client, db)
    outsider, outsider_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)

    r = client.get(
        _connect_url(ws, "facebook"),
        headers=outsider_headers,
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Callback route
# ---------------------------------------------------------------------------


def _mock_token_response():  # type: ignore[no-untyped-def]
    from app.integrations.oauth.base import TokenResponse

    return TokenResponse(
        access_token="cb-access-tok",
        refresh_token="cb-refresh-tok",
        expires_at=datetime(2025, 1, 1, tzinfo=UTC),
        raw={},
    )


def _mock_account_info():  # type: ignore[no-untyped-def]
    from app.integrations.oauth.base import AccountInfo

    return AccountInfo(external_id="ext-cb-123", name="Callback Page", avatar_url=None)


def _mock_provider():  # type: ignore[no-untyped-def]
    mock_provider = MagicMock()
    mock_provider.exchange_code.return_value = _mock_token_response()
    mock_provider.get_account_info.return_value = _mock_account_info()
    return mock_provider


def _callback(client: TestClient, platform: str = "facebook", **params: str):  # type: ignore[no-untyped-def]
    return client.get(
        f"{PREFIX}/callback/{platform}", params=params, follow_redirects=False
    )


def test_callback_creates_integration(client: TestClient, db: Session) -> None:
    user, _ = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    state = _make_state(ws.id, user.id)

    with (
        patch(
            "app.integrations.oauth.registry.get_provider",
            return_value=_mock_provider(),
        ),
        patch("app.worker.tasks.sync.sync_integration") as mock_task,
    ):
        r = _callback(client, code="auth-code", state=state)

    assert r.status_code == 302
    assert "connected=1" in r.headers["location"]

    from app import crud

    integrations = crud.get_integrations_for_workspace(session=db, workspace_id=ws.id)
    assert len(integrations) == 1
    assert integrations[0].external_account_name == "Callback Page"
    # An initial sync is enqueued straight away
    mock_task.delay.assert_called_once_with(str(integrations[0].id))


def test_callback_reconnect_updates_existing_integration(
    client: TestClient, db: Session
) -> None:
    from app import crud
    from app.models.integration import IntegrationStatus

    user, _ = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    with (
        patch(
            "app.integrations.oauth.registry.get_provider",
            return_value=_mock_provider(),
        ),
        patch("app.worker.tasks.sync.sync_integration"),
    ):
        _callback(client, code="c1", state=_make_state(ws.id, user.id))
        first = crud.get_integrations_for_workspace(session=db, workspace_id=ws.id)[0]
        crud.mark_integration_expired(session=db, integration=first, error="expired")

        r = _callback(client, code="c2", state=_make_state(ws.id, user.id))

    assert "connected=1" in r.headers["location"]
    integrations = crud.get_integrations_for_workspace(session=db, workspace_id=ws.id)
    assert len(integrations) == 1
    db.refresh(integrations[0])
    assert integrations[0].id == first.id
    assert integrations[0].status == IntegrationStatus.active
    assert integrations[0].sync_error is None


def test_callback_passes_pkce_verifier(client: TestClient, db: Session) -> None:
    user, _ = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    state = _make_state(ws.id, user.id, Platform.twitter, pkce_verifier="the-verifier")
    provider = _mock_provider()

    with (
        patch("app.integrations.oauth.registry.get_provider", return_value=provider),
        patch("app.worker.tasks.sync.sync_integration"),
    ):
        _callback(client, "twitter", code="c", state=state)

    assert provider.exchange_code.call_args.kwargs["code_verifier"] == "the-verifier"


def test_callback_forged_state_does_not_create_integration(
    client: TestClient, db: Session
) -> None:
    """A hand-crafted state naming a victim's workspace must be rejected."""
    from app import crud

    victim, _ = create_user_with_headers(client, db)
    ws = create_random_workspace(db, victim)
    forged = urllib.parse.quote(f'{{"workspace_id": "{ws.id}", "csrf": "anything"}}')
    provider = _mock_provider()

    with patch("app.integrations.oauth.registry.get_provider", return_value=provider):
        r = _callback(client, code="attacker-code", state=forged)

    assert "error=invalid_state" in r.headers["location"]
    provider.exchange_code.assert_not_called()
    assert crud.get_integrations_for_workspace(session=db, workspace_id=ws.id) == []


def test_callback_platform_mismatch_rejected(client: TestClient, db: Session) -> None:
    user, _ = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    state = _make_state(ws.id, user.id, Platform.facebook)

    r = _callback(client, "twitter", code="c", state=state)
    assert "error=invalid_state" in r.headers["location"]


def test_callback_rejects_user_no_longer_admin(client: TestClient, db: Session) -> None:
    from app import crud
    from app.models.workspace import WorkspaceRole

    owner, _ = create_user_with_headers(client, db)
    admin, _ = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    member = crud.add_member(
        session=db, workspace_id=ws.id, user_id=admin.id, role=WorkspaceRole.admin
    )
    state = _make_state(ws.id, admin.id)
    crud.update_member_role(session=db, member=member, role=WorkspaceRole.viewer)
    provider = _mock_provider()

    with patch("app.integrations.oauth.registry.get_provider", return_value=provider):
        r = _callback(client, code="c", state=state)

    assert "error=forbidden" in r.headers["location"]
    provider.exchange_code.assert_not_called()


def test_callback_provider_error_redirects_with_error(
    client: TestClient, db: Session
) -> None:
    user, _ = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    state = _make_state(ws.id, user.id)

    mock_provider = MagicMock()
    mock_provider.exchange_code.side_effect = Exception("secret internal detail")

    with patch(
        "app.integrations.oauth.registry.get_provider", return_value=mock_provider
    ):
        r = _callback(client, code="bad-code", state=state)

    assert r.status_code == 302
    assert "error=connection_failed" in r.headers["location"]
    assert "secret" not in r.headers["location"]


def test_callback_account_not_found_redirects_with_its_code(
    client: TestClient, db: Session
) -> None:
    user, _ = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    state = _make_state(ws.id, user.id)
    provider = _mock_provider()
    provider.get_account_info.side_effect = AccountNotFoundError(
        "no_instagram_account", "nothing linked"
    )

    with patch("app.integrations.oauth.registry.get_provider", return_value=provider):
        r = _callback(client, code="c", state=state)

    assert r.status_code == 302
    assert "error=no_instagram_account" in r.headers["location"]


def test_callback_invalid_state_redirects(client: TestClient) -> None:
    r = _callback(client, code="x", state="invalid-state!!!")
    assert r.status_code == 302
    assert "error=invalid_state" in r.headers["location"]


def test_callback_missing_state_redirects(client: TestClient) -> None:
    r = _callback(client, code="x")
    assert r.status_code == 302
    assert "error=invalid_state" in r.headers["location"]


def test_callback_user_denied_without_code(client: TestClient, db: Session) -> None:
    """Providers send `error` and no `code` when the user clicks Deny."""
    user, _ = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    state = _make_state(ws.id, user.id)

    r = _callback(client, state=state, error="access_denied")
    assert r.status_code == 302
    assert "error=access_denied" in r.headers["location"]


def test_callback_missing_code_redirects(client: TestClient, db: Session) -> None:
    user, _ = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    r = _callback(client, state=_make_state(ws.id, user.id))
    assert "error=missing_code" in r.headers["location"]


def test_callback_unavailable_platform_redirects(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The app may be removed while the user is on the provider's site."""
    user, _ = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    state = _make_state(ws.id, user.id)
    monkeypatch.setattr(settings, "FACEBOOK_APP_ID", "")

    with patch.object(facebook_provider, "exchange_code") as exchange:
        r = _callback(client, code="x", state=state)
    assert r.status_code == 302
    assert "error=platform_unavailable" in r.headers["location"]
    exchange.assert_not_called()
