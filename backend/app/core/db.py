from sqlmodel import Session, create_engine

from app import crud
from app.core.config import settings
from app.models.user import UserCreate

engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))


def init_db(session: Session) -> None:
    """Create the first superuser if needed. Tables come from Alembic migrations."""
    if crud.get_user_by_email(session=session, email=settings.FIRST_SUPERUSER):
        return
    crud.create_user(
        session=session,
        user_create=UserCreate(
            email=settings.FIRST_SUPERUSER,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            is_superuser=True,
        ),
    )
