"""
Helpers shared by the CRUD modules.

Transactions: an API request or a worker task is one unit of work, committed
once when it is complete. CRUD functions that stand for a whole unit on their
own (creating a user, renaming a workspace...) commit through ``save`` or
``delete``. Those that are steps of a larger unit (storing the posts a sync
fetched, importing a file...) only add their changes to the session, and say
so: their caller commits, so that the unit is stored entirely or not at all.
"""

import uuid
from typing import Any

from sqlmodel import Session, SQLModel, select

from app.models.workspace import Workspace


def save[ModelT: SQLModel](session: Session, obj: ModelT) -> ModelT:
    """Persist ``obj`` and reload it so server-side defaults are populated."""
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def delete(session: Session, obj: SQLModel) -> None:
    session.delete(obj)
    session.commit()


def get_for_workspace[ModelT: SQLModel](
    session: Session, model: type[ModelT], obj_id: Any, workspace_id: uuid.UUID
) -> ModelT | None:
    """The object with this id, provided it belongs to the workspace."""
    obj = session.get(model, obj_id)
    if obj is None or getattr(obj, "workspace_id", None) != workspace_id:
        return None
    return obj


def lock_workspace(session: Session, workspace_id: uuid.UUID) -> None:
    """
    Lock the workspace's row until the transaction ends, so that transactions
    checking a rule over its rows and then writing (e.g. "no other analysis
    is running") run one after the other instead of both passing the check.
    """
    session.exec(
        select(Workspace.id).where(Workspace.id == workspace_id).with_for_update()
    ).one()
