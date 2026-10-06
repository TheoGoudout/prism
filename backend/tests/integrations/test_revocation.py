"""Revoking a platform grant when an integration is disconnected."""

import uuid
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.integrations.oauth.facebook import facebook_provider
from app.integrations.oauth.google_analytics import google_analytics_provider
from app.integrations.oauth.linkedin import linkedin_provider
from app.integrations.oauth.tiktok import tiktok_provider
from app.integrations.oauth.twitter import twitter_provider
from app.integrations.revocation import revoke_access
from app.models.integration import Platform
from tests.utils.integration import create_fake_integration
from tests.utils.user import create_user_with_headers
from tests.utils.workspace import create_random_workspace


def _ok() -> MagicMock:
    response = MagicMock()
    response.raise_for_status.return_value = None
    return response


def _unique() -> str:
    return f"ext-{uuid.uuid4()}"


# ---------------------------------------------------------------------------
# Provider revoke calls
# ---------------------------------------------------------------------------


def test_facebook_revoke_deletes_permissions() -> None:
    with patch("httpx.delete", return_value=_ok()) as delete:
        assert facebook_provider.revoke(access_token="tok", refresh_token=None)
    assert delete.call_args.args[0].endswith("/me/permissions")
    assert delete.call_args.kwargs["params"] == {"access_token": "tok"}


def test_google_revoke_prefers_refresh_token() -> None:
    with patch("httpx.post", return_value=_ok()) as post:
        assert google_analytics_provider.revoke(access_token="acc", refresh_token="ref")
    assert post.call_args.args[0] == "https://oauth2.googleapis.com/revoke"
    assert post.call_args.kwargs["data"] == {"token": "ref"}


def test_twitter_revoke_revokes_both_tokens() -> None:
    with patch("httpx.post", return_value=_ok()) as post:
        assert twitter_provider.revoke(access_token="acc", refresh_token="ref")
    sent = [c.kwargs["data"] for c in post.call_args_list]
    assert sent == [
        {"token": "acc", "token_type_hint": "access_token"},
        {"token": "ref", "token_type_hint": "refresh_token"},
    ]


def test_tiktok_revoke_sends_access_token() -> None:
    with patch("httpx.post", return_value=_ok()) as post:
        assert tiktok_provider.revoke(access_token="acc", refresh_token="ref")
    assert post.call_args.kwargs["data"]["token"] == "acc"


def test_linkedin_has_no_revoke() -> None:
    with patch("httpx.post") as post:
        assert not linkedin_provider.revoke(access_token="acc", refresh_token=None)
    post.assert_not_called()


# ---------------------------------------------------------------------------
# revoke_access: shared grants and failures
# ---------------------------------------------------------------------------


def test_revoke_access_revokes_unshared_grant(client: TestClient, db: Session) -> None:
    user, _ = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(
        db, ws, platform=Platform.google_analytics, external_account_id=_unique()
    )
    with patch("httpx.post", return_value=_ok()) as post:
        assert revoke_access(db, integration)
    assert post.call_args.kwargs["data"] == {"token": "fake-refresh-token"}


def test_revoke_access_skips_api_key_platform(client: TestClient, db: Session) -> None:
    """Only the user can delete their API key on the platform."""
    user, _ = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(
        db, ws, platform=Platform.brevo, external_account_id=_unique()
    )
    with patch("httpx.post") as post, patch("httpx.delete") as delete:
        assert not revoke_access(db, integration)
    post.assert_not_called()
    delete.assert_not_called()


def test_revoke_access_skips_unavailable_platform(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, _ = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(
        db, ws, platform=Platform.google_analytics, external_account_id=_unique()
    )
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "")
    with patch("httpx.post") as post:
        assert not revoke_access(db, integration)
    post.assert_not_called()


def test_revoke_access_skips_grant_used_by_another_workspace(
    client: TestClient, db: Session
) -> None:
    """The same Google account connected elsewhere would lose its access."""
    user, _ = create_user_with_headers(client, db)
    account_id = _unique()
    integration = create_fake_integration(
        db,
        create_random_workspace(db, user),
        platform=Platform.google_analytics,
        external_account_id=account_id,
    )
    create_fake_integration(
        db,
        create_random_workspace(db, user),
        platform=Platform.google_analytics,
        external_account_id=account_id,
    )
    with patch("httpx.post") as post:
        assert not revoke_access(db, integration)
    post.assert_not_called()


def test_revoke_access_skips_facebook_grant_used_by_instagram(
    client: TestClient, db: Session
) -> None:
    """Facebook and Instagram share the Meta grant of the Facebook user."""
    user, _ = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    fb_user = _unique()
    facebook = create_fake_integration(
        db, ws, platform=Platform.facebook, external_account_id=fb_user
    )
    create_fake_integration(
        db, ws, platform=Platform.instagram, external_account_id=_unique()
    )
    me = _ok()
    me.json.return_value = {"id": fb_user}
    with (
        patch("httpx.get", return_value=me),
        patch("httpx.delete") as delete,
    ):
        assert not revoke_access(db, facebook)
    delete.assert_not_called()


def test_revoke_access_never_raises(client: TestClient, db: Session) -> None:
    user, _ = create_user_with_headers(client, db)
    integration = create_fake_integration(
        db,
        create_random_workspace(db, user),
        platform=Platform.tiktok,
        external_account_id=_unique(),
    )
    with patch("httpx.post", side_effect=httpx.ConnectError("down")):
        assert not revoke_access(db, integration)
