from sqlmodel import Session

from app import crud
from app.models.integration import (
    Integration,
    IntegrationCreate,
    Platform,
    PlatformAccount,
    PlatformAccountCreate,
)
from app.models.workspace import Workspace


def create_fake_integration(
    db: Session,
    workspace: Workspace,
    platform: Platform = Platform.facebook,
    external_account_id: str = "ext-123",
    external_account_name: str = "Test Page",
) -> Integration:
    integration_in = IntegrationCreate(
        platform=platform,
        workspace_id=workspace.id,
        access_token="fake-access-token",
        refresh_token="fake-refresh-token",
        external_account_id=external_account_id,
        external_account_name=external_account_name,
    )
    return crud.create_integration(session=db, integration_in=integration_in)


def create_fake_account(
    db: Session,
    integration: Integration,
    external_id: str = "page-456",
    name: str = "Test Account",
) -> PlatformAccount:
    account_in = PlatformAccountCreate(
        integration_id=integration.id,
        workspace_id=integration.workspace_id,
        platform=integration.platform,
        external_id=external_id,
        name=name,
        account_type="page",
    )
    return crud.create_platform_account(session=db, account_in=account_in)
