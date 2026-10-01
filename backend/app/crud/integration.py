import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.core.encryption import decrypt_token, encrypt_token
from app.models.integration import (
    Integration,
    IntegrationCreate,
    IntegrationStatus,
    Platform,
    PlatformAccount,
    PlatformAccountCreate,
)


# ---------------------------------------------------------------------------
# Integration CRUD
# ---------------------------------------------------------------------------


def create_integration(
    *, session: Session, integration_in: IntegrationCreate
) -> Integration:
    integration = Integration(
        workspace_id=integration_in.workspace_id,
        platform=integration_in.platform,
        status=IntegrationStatus.active,
        access_token_encrypted=encrypt_token(integration_in.access_token),
        refresh_token_encrypted=(
            encrypt_token(integration_in.refresh_token)
            if integration_in.refresh_token
            else None
        ),
        token_expires_at=integration_in.token_expires_at,
        external_account_id=integration_in.external_account_id,
        external_account_name=integration_in.external_account_name,
        external_account_avatar=integration_in.external_account_avatar,
    )
    session.add(integration)
    session.commit()
    session.refresh(integration)
    return integration


def upsert_integration(
    *, session: Session, integration_in: IntegrationCreate
) -> Integration:
    """
    Create an integration, or — if this workspace already has one for the same
    platform account — refresh its tokens and reactivate it. Reconnecting an
    expired account therefore keeps its history instead of duplicating it.
    """
    existing = session.exec(
        select(Integration).where(
            Integration.workspace_id == integration_in.workspace_id,
            Integration.platform == integration_in.platform,
            Integration.external_account_id == integration_in.external_account_id,
        )
    ).first()
    if existing is None:
        return create_integration(session=session, integration_in=integration_in)

    existing.access_token_encrypted = encrypt_token(integration_in.access_token)
    existing.refresh_token_encrypted = (
        encrypt_token(integration_in.refresh_token)
        if integration_in.refresh_token
        else None
    )
    existing.token_expires_at = integration_in.token_expires_at
    existing.external_account_name = integration_in.external_account_name
    existing.external_account_avatar = integration_in.external_account_avatar
    existing.status = IntegrationStatus.active
    existing.sync_error = None
    session.add(existing)
    session.commit()
    session.refresh(existing)
    return existing


def get_integration(
    *, session: Session, integration_id: uuid.UUID
) -> Integration | None:
    return session.get(Integration, integration_id)


def get_integrations_for_workspace(
    *, session: Session, workspace_id: uuid.UUID, platform: Platform | None = None
) -> Sequence[Integration]:
    statement = select(Integration).where(
        Integration.workspace_id == workspace_id
    )
    if platform is not None:
        statement = statement.where(Integration.platform == platform)
    return session.exec(statement).all()


def update_integration_tokens(
    *,
    session: Session,
    integration: Integration,
    access_token: str,
    refresh_token: str | None = None,
    expires_at: datetime | None = None,
) -> Integration:
    integration.access_token_encrypted = encrypt_token(access_token)
    if refresh_token:
        integration.refresh_token_encrypted = encrypt_token(refresh_token)
    integration.token_expires_at = expires_at
    integration.status = IntegrationStatus.active
    integration.sync_error = None
    session.add(integration)
    session.commit()
    session.refresh(integration)
    return integration


def mark_integration_error(
    *, session: Session, integration: Integration, error: str
) -> Integration:
    integration.status = IntegrationStatus.error
    integration.sync_error = error[:1024]
    session.add(integration)
    session.commit()
    session.refresh(integration)
    return integration


def mark_integration_expired(
    *, session: Session, integration: Integration, error: str
) -> Integration:
    """The user must reconnect: tokens are expired and can't be refreshed."""
    integration.status = IntegrationStatus.expired
    integration.sync_error = error[:1024]
    session.add(integration)
    session.commit()
    session.refresh(integration)
    return integration


def mark_integration_synced(
    *, session: Session, integration: Integration
) -> Integration:
    integration.status = IntegrationStatus.active
    integration.last_synced_at = datetime.now(timezone.utc)
    integration.sync_error = None
    session.add(integration)
    session.commit()
    session.refresh(integration)
    return integration


def delete_integration(*, session: Session, integration: Integration) -> None:
    session.delete(integration)
    session.commit()


# ---------------------------------------------------------------------------
# Token access (decrypts on demand — never stored in plain text)
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
# PlatformAccount CRUD
# ---------------------------------------------------------------------------


def create_platform_account(
    *, session: Session, account_in: PlatformAccountCreate
) -> PlatformAccount:
    account = PlatformAccount(
        integration_id=account_in.integration_id,
        workspace_id=account_in.workspace_id,
        platform=account_in.platform,
        external_id=account_in.external_id,
        name=account_in.name,
        avatar_url=account_in.avatar_url,
        account_type=account_in.account_type,
    )
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


def get_platform_account(
    *, session: Session, account_id: uuid.UUID
) -> PlatformAccount | None:
    return session.get(PlatformAccount, account_id)


def get_accounts_for_integration(
    *, session: Session, integration_id: uuid.UUID
) -> Sequence[PlatformAccount]:
    statement = select(PlatformAccount).where(
        PlatformAccount.integration_id == integration_id
    )
    return session.exec(statement).all()


def get_accounts_for_workspace(
    *,
    session: Session,
    workspace_id: uuid.UUID,
    platform: Platform | None = None,
    active_only: bool = True,
) -> Sequence[PlatformAccount]:
    statement = select(PlatformAccount).where(
        PlatformAccount.workspace_id == workspace_id
    )
    if platform is not None:
        statement = statement.where(PlatformAccount.platform == platform)
    if active_only:
        statement = statement.where(PlatformAccount.is_active == True)  # noqa: E712
    return session.exec(statement).all()


def upsert_platform_account(
    *, session: Session, account_in: PlatformAccountCreate
) -> PlatformAccount:
    """Update existing account or create it if it doesn't exist."""
    existing = session.exec(
        select(PlatformAccount).where(
            PlatformAccount.integration_id == account_in.integration_id,
            PlatformAccount.external_id == account_in.external_id,
        )
    ).first()
    if existing:
        existing.name = account_in.name
        existing.avatar_url = account_in.avatar_url
        existing.account_type = account_in.account_type
        existing.is_active = True
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing
    return create_platform_account(session=session, account_in=account_in)
