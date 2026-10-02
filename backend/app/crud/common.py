from typing import TypeVar

from sqlmodel import Session, SQLModel

ModelT = TypeVar("ModelT", bound=SQLModel)


def save[ModelT: SQLModel](session: Session, obj: ModelT) -> ModelT:
    """Persist ``obj`` and reload it so server-side defaults are populated."""
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def delete(session: Session, obj: SQLModel) -> None:
    session.delete(obj)
    session.commit()
