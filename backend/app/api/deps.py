import uuid
from collections.abc import Generator
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel import Session

from app import crud
from app.core import security
from app.core.config import settings
from app.core.db import engine
from app.models.common import TokenPayload
from app.models.user import User
from app.models.workspace import WorkspaceMember

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)


def get_db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]


def get_current_user(session: SessionDep, token: TokenDep) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    user = session.get(User, token_data.sub)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_active_superuser(current_user: CurrentUser) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="The user doesn't have enough privileges"
        )
    return current_user


# ---------------------------------------------------------------------------
# Workspace access
# ---------------------------------------------------------------------------


def get_workspace_member(
    session: Session, user: User, workspace_id: uuid.UUID
) -> WorkspaceMember:
    """
    The user's membership of the workspace. Non-members get a 404 rather than
    a 403 so that they can't probe which workspaces exist.
    """
    member = crud.get_member(
        session=session, workspace_id=workspace_id, user_id=user.id
    )
    if member is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return member


def require_manager(member: WorkspaceMember, action: str) -> None:
    """403 unless the member is an owner or admin; ``action`` completes the
    sentence "Only workspace owners and admins can ..."."""
    if not member.role.can_manage:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Only workspace owners and admins can {action}",
        )


def _get_current_member(
    workspace_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> WorkspaceMember:
    return get_workspace_member(session, current_user, workspace_id)


# Membership of the workspace named by the `workspace_id` path or query param
CurrentMember = Annotated[WorkspaceMember, Depends(_get_current_member)]
