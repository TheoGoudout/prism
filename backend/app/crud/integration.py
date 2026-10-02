import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlmodel import Session, col, select

from app.core.encryption import decrypt_token, encrypt_token
from app.crud.common import save
from app.models.integration import (
    Integration,
    IntegrationCreate,
    IntegrationStatus,
    Platform,
    PlatformAccount,
)

# ---------------------------------------------------------------------------
# Integrations
# ---------------------------------------------------------------------------


def upsert_integration(
    *, session: Session, integration_in: IntegrationCreate
) -> Integration:
    """
    Create an integration, or — if this workspace already has one for the same
    platform account — refresh its tokens and reactivate it. Reconnecting an
    expired account therefore keeps its history instead of duplicating it.
    """
    integration = session.exec(
        select(Integration).where(
            Integration.workspace_id == integration_in.workspace_id,
            Integration.platform == integration_in.platform,
            Integration.external_account_id == integration_in.external_account_id,
        )
    ).first() or Integration(
        workspace_id=integration_in.workspace_id,
        platform=integration_in.platform,
        external_account_id=integration_in.external_account_id,
        external_account_name=integration_in.external_account_name,
    )
    integration.external_account_name = integration_in.external_account_name
    integration.external_account_avatar = integration_in.external_account_avatar
    # A fresh authorization replaces the refresh token too, even with None
    integration.refresh_token_encrypted = None
    return update_integration_tokens(
        session=session,
        integration=integration,
        access_token=integration_in.access_token,
        refresh_token=integration_in.refresh_token,
        expires_at=integration_in.token_expires_at,
    )


def get_integration(
    *, session: Session, integration_id: uuid.UUID
) -> Integration | None:
    return session.get(Integration, integration_id)


def get_integrations_for_workspace(
    *, session: Session, workspace_id: uuid.UUID
) -> Sequence[Integration]:
    statement = (
        select(Integration)
        .where(Integration.workspace_id == workspace_id)
        .order_by(col(Integration.created_at))
    )
    return session.exec(statement).all()


def update_integration_tokens(
    *,
    session: Session,
    integration: Integration,
    access_token: str,
    refresh_token: str | None = None,
    expires_at: datetime | None = None,
) -> Integration:
    """Store new tokens and mark the integration as working again.

    ``refresh_token=None`` keeps the stored refresh token: most providers only
    return one when they rotate it.
    """
    integration.access_token_encrypted = encrypt_token(access_token)
    if refresh_token:
        integration.refresh_token_encrypted = encrypt_token(refresh_token)
    integration.token_expires_at = expires_at
    integration.status = IntegrationStatus.active
    integration.sync_error = None
    return save(session, integration)


def mark_integration_synced(
    *, session: Session, integration: Integration
) -> Integration:
    integration.status = IntegrationStatus.active
    integration.last_synced_at = datetime.now(UTC)
    integration.sync_error = None
    return save(session, integration)


def mark_integration_error(
    *, session: Session, integration: Integration, error: str
) -> Integration:
    """A sync failed; it will be retried by the next scheduled sync."""
    return _set_failed_status(session, integration, IntegrationStatus.error, error)


def mark_integration_expired(
    *, session: Session, integration: Integration, error: str
) -> Integration:
    """The user must reconnect: tokens are expired and can't be refreshed."""
    return _set_failed_status(session, integration, IntegrationStatus.expired, error)


def _set_failed_status(
    session: Session, integration: Integration, status: IntegrationStatus, error: str
) -> Integration:
    integration.status = status
    integration.sync_error = error[:1024]
    return save(session, integration)


# ---------------------------------------------------------------------------
# Tokens (decrypted on demand — never stored in plain text)
# ---------------------------------------------------------------------------


def get_access_token(integration: Integration) -> str | None:
    if integration.access_token_encrypted is None:
        return None
    return decrypt_token(integration.access_token_encrypted)


def get_refresh_token(integration: Integration) -> str | None:
    if integration.refresh_token_encrypted is None:
        return None
    return decrypt_token(integration.refresh_token_encrypted)


# ---------------------------------------------------------------------------
# Platform accounts (pages, profiles, properties found during a sync)
# ---------------------------------------------------------------------------


def get_accounts_for_workspace(
    *, session: Session, workspace_id: uuid.UUID, platform: Platform | None = None
) -> Sequence[PlatformAccount]:
    """Active accounts of a workspace, optionally for a single platform."""
    statement = select(PlatformAccount).where(
        PlatformAccount.workspace_id == workspace_id,
        PlatformAccount.is_active == True,  # noqa: E712
    )
    if platform is not None:
        statement = statement.where(PlatformAccount.platform == platform)
    return session.exec(statement).all()


def upsert_platform_account(
    *,
    session: Session,
    integration: Integration,
    external_id: str,
    name: str,
    avatar_url: str | None = None,
    account_type: str | None = None,
) -> PlatformAccount:
    """Create the account found during a sync, or refresh its details."""
    account = session.exec(
        select(PlatformAccount).where(
            PlatformAccount.integration_id == integration.id,
            PlatformAccount.external_id == external_id,
        )
    ).first() or PlatformAccount(
        integration_id=integration.id,
        workspace_id=integration.workspace_id,
        platform=integration.platform,
        external_id=external_id,
        name=name,
    )
    account.name = name
    account.avatar_url = avatar_url
    account.account_type = account_type
    account.is_active = True
    return save(session, account)
