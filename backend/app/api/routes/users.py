import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app import crud
from app.api.deps import (
    CurrentUser,
    SessionDep,
    get_current_active_superuser,
)
from app.core.config import settings
from app.core.security import get_password_hash, verify_password
from app.models.user import (
    UpdatePassword,
    User,
    UserCreate,
    UserPublic,
    UserRegister,
    UserUpdate,
    UserUpdateMe,
)
from app.utils import generate_new_account_email, send_email

router = APIRouter(prefix="/users", tags=["users"])


def _ensure_email_available(
    session: SessionDep, email: str | None, user_id: uuid.UUID | None = None
) -> None:
    """409 if another user than ``user_id`` already has the email."""
    if not email:
        return
    existing = crud.get_user_by_email(session=session, email=email)
    if existing and existing.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The user with this email already exists in the system",
        )


def _get_user(session: SessionDep, user_id: uuid.UUID) -> User:
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get(
    "/",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=list[UserPublic],
)
def read_users(session: SessionDep) -> Any:
    """
    Retrieve all users, newest first.
    """
    return crud.get_users(session=session)


@router.post(
    "/", dependencies=[Depends(get_current_active_superuser)], response_model=UserPublic
)
def create_user(*, session: SessionDep, user_in: UserCreate) -> Any:
    """
    Create new user.
    """
    _ensure_email_available(session, user_in.email)
    user = crud.create_user(session=session, user_create=user_in)
    if settings.emails_enabled:
        send_email(
            email_to=user_in.email,
            email=generate_new_account_email(
                email_to=user_in.email,
                username=user_in.email,
                password=user_in.password,
            ),
        )
    return user


@router.patch("/me", response_model=UserPublic)
def update_user_me(
    *, session: SessionDep, user_in: UserUpdateMe, current_user: CurrentUser
) -> Any:
    """
    Update own user.
    """
    _ensure_email_available(session, user_in.email, current_user.id)
    current_user.sqlmodel_update(user_in.model_dump(exclude_unset=True))
    return crud.save(session, current_user)


@router.patch("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def update_password_me(
    *, session: SessionDep, body: UpdatePassword, current_user: CurrentUser
) -> None:
    """
    Update own password.
    """
    verified, _ = verify_password(body.current_password, current_user.hashed_password)
    if not verified:
        raise HTTPException(status_code=400, detail="Incorrect password")
    if body.current_password == body.new_password:
        raise HTTPException(
            status_code=400, detail="New password cannot be the same as the current one"
        )
    current_user.hashed_password = get_password_hash(body.new_password)
    crud.save(session, current_user)


@router.get("/me", response_model=UserPublic)
def read_user_me(current_user: CurrentUser) -> Any:
    """
    Get current user.
    """
    return current_user


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_me(session: SessionDep, current_user: CurrentUser) -> None:
    """
    Delete own user.
    """
    if current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="Super users are not allowed to delete themselves"
        )
    crud.delete(session, current_user)


@router.post("/signup", response_model=UserPublic)
def register_user(session: SessionDep, user_in: UserRegister) -> Any:
    """
    Create new user without the need to be logged in.
    """
    _ensure_email_available(session, user_in.email)
    return crud.create_user(
        session=session, user_create=UserCreate.model_validate(user_in)
    )


@router.patch(
    "/{user_id}",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=UserPublic,
)
def update_user(
    *,
    session: SessionDep,
    user_id: uuid.UUID,
    user_in: UserUpdate,
) -> Any:
    """
    Update a user.
    """
    db_user = _get_user(session, user_id)
    _ensure_email_available(session, user_in.email, user_id)
    return crud.update_user(session=session, db_user=db_user, user_in=user_in)


@router.delete(
    "/{user_id}",
    dependencies=[Depends(get_current_active_superuser)],
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_user(
    session: SessionDep, current_user: CurrentUser, user_id: uuid.UUID
) -> None:
    """
    Delete a user.
    """
    user = _get_user(session, user_id)
    if user == current_user:
        raise HTTPException(
            status_code=403, detail="Super users are not allowed to delete themselves"
        )
    crud.delete(session, user)
