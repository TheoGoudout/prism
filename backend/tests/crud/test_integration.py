"""Unit tests for integration CRUD helpers that aren't reachable via HTTP yet."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.crud import integration as icrud
from app.models.integration import Integration, IntegrationCreate, Platform
from tests.utils.integration import create_fake_account, create_fake_integration
from tests.utils.user import create_random_user
from tests.utils.workspace import create_random_workspace


def _make_workspace(db: Session):  # type: ignore[no-untyped-def]
    user = create_random_user(db)
    return create_random_workspace(db, user)


def test_update_integration_tokens(db: Session) -> None:
    ws = _make_workspace(db)
    integration = create_fake_integration(db, ws)

    updated = icrud.update_integration_tokens(
        session=db,
        integration=integration,
        access_token="new-access",
        refresh_token="new-refresh",
    )
    assert icrud.get_access_token(updated) == "new-access"
    assert icrud.get_refresh_token(updated) == "new-refresh"


def test_update_integration_tokens_no_refresh(db: Session) -> None:
    ws = _make_workspace(db)
    integration = create_fake_integration(db, ws)
    old_refresh = icrud.get_refresh_token(integration)

    updated = icrud.update_integration_tokens(
        session=db,
        integration=integration,
        access_token="new-access-only",
    )
    # Refresh token unchanged when not provided
    assert icrud.get_access_token(updated) == "new-access-only"
    assert icrud.get_refresh_token(updated) == old_refresh


def test_mark_integration_error(db: Session) -> None:
    ws = _make_workspace(db)
    integration = create_fake_integration(db, ws)

    from app.models.integration import IntegrationStatus

    errored = icrud.mark_integration_error(
        session=db, integration=integration, error="rate limit exceeded"
    )
    assert errored.status == IntegrationStatus.error
    assert errored.sync_error == "rate limit exceeded"


def test_mark_integration_error_truncates_long_message(db: Session) -> None:
    ws = _make_workspace(db)
    integration = create_fake_integration(db, ws)
    long_error = "x" * 2000

    errored = icrud.mark_integration_error(
        session=db, integration=integration, error=long_error
    )
    assert len(errored.sync_error or "") == 1024  # type: ignore[arg-type]


def test_mark_integration_synced(db: Session) -> None:
    ws = _make_workspace(db)
    integration = create_fake_integration(db, ws)
    # First mark as error, then mark synced to verify it clears the error
    icrud.mark_integration_error(session=db, integration=integration, error="oops")

    synced = icrud.mark_integration_synced(session=db, integration=integration)
    assert synced.last_synced_at is not None
    assert synced.sync_error is None


def test_get_access_token_none_when_not_set(db: Session) -> None:
    ws = _make_workspace(db)
    integration = create_fake_integration(db, ws)
    integration.access_token_encrypted = None

    assert icrud.get_access_token(integration) is None


def test_get_refresh_token_none_when_not_set(db: Session) -> None:
    ws = _make_workspace(db)
    integration = create_fake_integration(db, ws)
    integration.refresh_token_encrypted = None

    assert icrud.get_refresh_token(integration) is None


def test_get_accounts_for_workspace(db: Session) -> None:
    ws = _make_workspace(db)
    integration = create_fake_integration(db, ws)
    create_fake_account(db, integration, external_id="page-ws-1")

    accounts = icrud.get_accounts_for_workspace(session=db, workspace_id=ws.id)
    assert len(accounts) == 1
    assert accounts[0].external_id == "page-ws-1"


def test_get_accounts_for_workspace_platform_filter(db: Session) -> None:
    ws = _make_workspace(db)
    fb = create_fake_integration(db, ws, platform=Platform.facebook)
    ig = create_fake_integration(
        db, ws, platform=Platform.instagram, external_account_id="ig-2"
    )
    create_fake_account(db, fb, external_id="fb-page")
    create_fake_account(db, ig, external_id="ig-profile")

    fb_accounts = icrud.get_accounts_for_workspace(
        session=db, workspace_id=ws.id, platform=Platform.facebook
    )
    assert len(fb_accounts) == 1
    assert fb_accounts[0].platform == Platform.facebook


def test_upsert_platform_account_creates(db: Session) -> None:
    ws = _make_workspace(db)
    integration = create_fake_integration(db, ws)

    account = icrud.upsert_platform_account(
        session=db, integration=integration, external_id="upsert-new", name="New"
    )
    db.commit()
    assert account.external_id == "upsert-new"
    assert account.name == "New"
    # Ownership comes from the integration
    assert account.workspace_id == ws.id
    assert account.platform == integration.platform


def test_upsert_platform_account_updates(db: Session) -> None:
    ws = _make_workspace(db)
    integration = create_fake_integration(db, ws)

    created = icrud.upsert_platform_account(
        session=db, integration=integration, external_id="same", name="Original"
    )
    db.commit()
    updated = icrud.upsert_platform_account(
        session=db, integration=integration, external_id="same", name="Updated"
    )
    db.commit()
    assert updated.id == created.id  # same row
    assert updated.name == "Updated"


def test_long_avatar_urls_are_stored(db: Session) -> None:
    """Instagram's CDN avatar URLs carry long signed query strings."""
    ws = _make_workspace(db)
    avatar = "https://scontent.cdninstagram.com/v/pic.jpg?" + "x" * 700

    integration = icrud.upsert_integration(
        session=db,
        integration_in=IntegrationCreate(
            platform=Platform.instagram,
            workspace_id=ws.id,
            access_token="IG-token",
            external_account_id="ig-long-avatar",
            external_account_name="Long avatar",
            external_account_avatar=avatar,
        ),
    )
    account = icrud.upsert_platform_account(
        session=db,
        integration=integration,
        external_id="ig-long-avatar",
        name="Long avatar",
        avatar_url=avatar,
    )
    db.commit()

    db.refresh(integration)
    db.refresh(account)
    assert integration.external_account_avatar == avatar
    assert account.avatar_url == avatar


def test_get_integrations_for_workspace(db: Session) -> None:
    ws = _make_workspace(db)
    create_fake_integration(db, ws, platform=Platform.facebook)
    create_fake_integration(
        db, ws, platform=Platform.twitter, external_account_id="tw-2"
    )

    all_integrations = icrud.get_integrations_for_workspace(
        session=db, workspace_id=ws.id
    )
    assert len(all_integrations) == 2


def test_an_account_has_one_integration_per_workspace(db: Session) -> None:
    """The database refuses a second integration of the same account."""
    ws = _make_workspace(db)
    integration = create_fake_integration(db, ws)
    db.add(
        Integration(
            workspace_id=ws.id,
            platform=integration.platform,
            external_account_id=integration.external_account_id,
            external_account_name="Duplicate",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
