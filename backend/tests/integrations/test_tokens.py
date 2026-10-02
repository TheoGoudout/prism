"""Tests for access-token refresh before sync (app.integrations.tokens)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import httpx
import pytest
from sqlmodel import Session

from app import crud
from app.integrations.oauth.base import TokenResponse
from app.integrations.tokens import TokenExpiredError, ensure_fresh_token
from app.models.integration import Integration, Platform
from tests.utils.integration import create_fake_integration
from tests.utils.user import create_random_user
from tests.utils.workspace import create_random_workspace

PROVIDER = "app.integrations.oauth.registry.get_provider"


def _integration(
    db: Session, platform: Platform, expires_in: timedelta | None
) -> Integration:
    ws = create_random_workspace(db, create_random_user(db))
    integ = create_fake_integration(db, ws, platform=platform)
    integ.token_expires_at = (
        datetime.now(UTC) + expires_in if expires_in is not None else None
    )
    db.add(integ)
    db.commit()
    db.refresh(integ)
    return integ


def _provider(
    refresh_result: TokenResponse | Exception, credential: str | None = "cred"
) -> MagicMock:
    provider = MagicMock()
    provider.refresh_credential.return_value = credential
    if isinstance(refresh_result, Exception):
        provider.refresh.side_effect = refresh_result
    else:
        provider.refresh.return_value = refresh_result
    return provider


def _http_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.com/token")
    return httpx.HTTPStatusError(
        "error", request=request, response=httpx.Response(status, request=request)
    )


def test_non_expiring_token_not_refreshed(db: Session) -> None:
    integ = _integration(db, Platform.twitter, None)
    provider = _provider(Exception("should not be called"))
    with patch(PROVIDER, return_value=provider):
        ensure_fresh_token(session=db, integration=integ)
    provider.refresh.assert_not_called()


def test_token_far_from_expiry_not_refreshed(db: Session) -> None:
    integ = _integration(db, Platform.twitter, timedelta(hours=1))
    provider = _provider(Exception("should not be called"))
    with patch(PROVIDER, return_value=provider):
        ensure_fresh_token(session=db, integration=integ)
    provider.refresh.assert_not_called()


def test_expired_token_is_refreshed_and_stored(db: Session) -> None:
    integ = _integration(db, Platform.google_analytics, timedelta(hours=-3))
    new_expiry = datetime.now(UTC) + timedelta(hours=1)
    provider = _provider(
        TokenResponse(
            access_token="new-access",
            refresh_token="new-refresh",
            expires_at=new_expiry,
            raw={},
        )
    )
    with patch(PROVIDER, return_value=provider):
        ensure_fresh_token(session=db, integration=integ)

    provider.refresh_credential.assert_called_once_with(
        access_token="fake-access-token", refresh_token="fake-refresh-token"
    )
    provider.refresh.assert_called_once_with("cred")
    db.refresh(integ)
    assert crud.get_access_token(integ) == "new-access"
    assert crud.get_refresh_token(integ) == "new-refresh"
    assert integ.token_expires_at == new_expiry


def test_meta_token_renewed_a_week_ahead(db: Session) -> None:
    integ = _integration(db, Platform.facebook, timedelta(days=3))
    provider = _provider(
        TokenResponse(
            access_token="renewed", refresh_token=None, expires_at=None, raw={}
        )
    )
    with patch(PROVIDER, return_value=provider):
        ensure_fresh_token(session=db, integration=integ)
    provider.refresh.assert_called_once()


def test_expired_without_credential_raises(db: Session) -> None:
    integ = _integration(db, Platform.linkedin, timedelta(minutes=-1))
    provider = _provider(Exception("unused"), credential=None)
    with patch(PROVIDER, return_value=provider), pytest.raises(TokenExpiredError):
        ensure_fresh_token(session=db, integration=integ)


def test_expired_and_refresh_rejected_raises(db: Session) -> None:
    integ = _integration(db, Platform.tiktok, timedelta(minutes=-1))
    provider = _provider(_http_error(400))
    with patch(PROVIDER, return_value=provider), pytest.raises(TokenExpiredError):
        ensure_fresh_token(session=db, integration=integ)


def test_refresh_rejected_but_still_valid_does_not_raise(db: Session) -> None:
    integ = _integration(db, Platform.tiktok, timedelta(minutes=5))
    provider = _provider(_http_error(400))
    with patch(PROVIDER, return_value=provider):
        ensure_fresh_token(session=db, integration=integ)


def test_server_error_propagates_for_retry(db: Session) -> None:
    integ = _integration(db, Platform.tiktok, timedelta(minutes=-1))
    provider = _provider(_http_error(503))
    with patch(PROVIDER, return_value=provider), pytest.raises(httpx.HTTPStatusError):
        ensure_fresh_token(session=db, integration=integ)
