from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


def get_datetime_utc() -> datetime:
    return datetime.now(UTC)


def timestamp_field(*, now: bool = False) -> Any:
    """A timezone-aware timestamp column: the current time if ``now``, else None."""
    if now:
        return Field(default_factory=get_datetime_utc, sa_type=DateTime(timezone=True))
    return Field(default=None, sa_type=DateTime(timezone=True))


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)
