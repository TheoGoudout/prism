import random
import string

from sqlmodel import Session

from app import crud
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceCreate, WorkspaceRole


def random_slug() -> str:
    return "ws-" + "".join(random.choices(string.ascii_lowercase, k=8))


def create_random_workspace(db: Session, owner: User) -> Workspace:
    workspace_in = WorkspaceCreate(name="Test Workspace " + random_slug())
    return crud.create_workspace(
        session=db, workspace_in=workspace_in, owner_id=owner.id
    )


def get_member_role(
    db: Session, workspace: Workspace, user: User
) -> WorkspaceRole | None:
    member = crud.get_member(session=db, workspace_id=workspace.id, user_id=user.id)
    return member.role if member else None
