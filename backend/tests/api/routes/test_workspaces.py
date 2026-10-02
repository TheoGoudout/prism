import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.models.workspace import WorkspaceRole
from tests.utils.user import create_user_with_headers
from tests.utils.workspace import add_member, create_random_workspace, get_member_role

PREFIX = f"{settings.API_V1_STR}/workspaces"


# ---------------------------------------------------------------------------
# Workspace creation
# ---------------------------------------------------------------------------


def test_create_workspace(
    client: TestClient, normal_user_token_headers: dict, db: Session
) -> None:
    data = {"name": "My Brand"}
    r = client.post(PREFIX + "/", headers=normal_user_token_headers, json=data)
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "My Brand"
    assert body["slug"] == "my-brand"
    assert body["role"] == WorkspaceRole.owner


def test_create_workspace_custom_slug(
    client: TestClient, normal_user_token_headers: dict, db: Session
) -> None:
    data = {"name": "My Brand", "slug": "custom-slug"}
    r = client.post(PREFIX + "/", headers=normal_user_token_headers, json=data)
    assert r.status_code == 200
    assert r.json()["slug"] == "custom-slug"


def test_create_workspace_slug_deduplication(
    client: TestClient, normal_user_token_headers: dict, db: Session
) -> None:
    data = {"name": "Duplicate Slug"}
    r1 = client.post(PREFIX + "/", headers=normal_user_token_headers, json=data)
    r2 = client.post(PREFIX + "/", headers=normal_user_token_headers, json=data)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["slug"] != r2.json()["slug"]


def test_create_workspace_requires_auth(client: TestClient) -> None:
    r = client.post(PREFIX + "/", json={"name": "No Auth"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Workspace listing
# ---------------------------------------------------------------------------


def test_list_workspaces_oldest_first_with_role(
    client: TestClient, db: Session
) -> None:
    owner, _ = create_user_with_headers(client, db)
    user, headers = create_user_with_headers(client, db)
    first = create_random_workspace(db, user)
    shared = create_random_workspace(db, owner)
    add_member(db, shared, user, WorkspaceRole.viewer)

    r = client.get(PREFIX + "/", headers=headers)
    assert r.status_code == 200
    assert [(ws["id"], ws["role"]) for ws in r.json()] == [
        (str(first.id), "owner"),
        (str(shared.id), "viewer"),
    ]


def test_list_workspaces_only_own(client: TestClient, db: Session) -> None:
    user_a, _ = create_user_with_headers(client, db)
    _, headers_b = create_user_with_headers(client, db)
    create_random_workspace(db, user_a)

    r = client.get(PREFIX + "/", headers=headers_b)
    assert r.status_code == 200
    assert r.json() == []


# ---------------------------------------------------------------------------
# Workspace update
# ---------------------------------------------------------------------------


def test_update_workspace_name(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    r = client.patch(f"{PREFIX}/{ws.id}", headers=headers, json={"name": "New Name"})
    assert r.status_code == 200
    assert r.json()["name"] == "New Name"
    assert r.json()["role"] == "owner"


def test_update_workspace_requires_owner_or_admin(
    client: TestClient, db: Session
) -> None:
    owner, _ = create_user_with_headers(client, db)
    viewer, viewer_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    add_member(db, ws, viewer, WorkspaceRole.viewer)

    r = client.patch(
        f"{PREFIX}/{ws.id}", headers=viewer_headers, json={"name": "Hacked"}
    )
    assert r.status_code == 403


def test_update_workspace_not_member_returns_404(
    client: TestClient, db: Session
) -> None:
    owner, _ = create_user_with_headers(client, db)
    _, outsider_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)

    r = client.patch(
        f"{PREFIX}/{ws.id}", headers=outsider_headers, json={"name": "Hacked"}
    )
    assert r.status_code == 404


def test_update_workspace_nonexistent(
    client: TestClient, normal_user_token_headers: dict
) -> None:
    r = client.patch(
        f"{PREFIX}/{uuid.uuid4()}", headers=normal_user_token_headers, json={}
    )
    assert r.status_code == 404


def test_update_workspace_to_taken_slug_gets_suffix(
    client: TestClient, db: Session
) -> None:
    _, headers = create_user_with_headers(client, db)
    taken = client.post(PREFIX + "/", headers=headers, json={"name": "Taken"}).json()
    other = client.post(PREFIX + "/", headers=headers, json={"name": "Other"}).json()

    r = client.patch(
        f"{PREFIX}/{other['id']}", headers=headers, json={"slug": taken["slug"]}
    )
    assert r.status_code == 200
    assert r.json()["slug"].startswith(taken["slug"] + "-")

    # Keeping its own slug doesn't add a suffix
    r = client.patch(
        f"{PREFIX}/{taken['id']}", headers=headers, json={"slug": taken["slug"]}
    )
    assert r.json()["slug"] == taken["slug"]


# ---------------------------------------------------------------------------
# Workspace deletion
# ---------------------------------------------------------------------------


def test_delete_workspace(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    r = client.delete(f"{PREFIX}/{ws.id}", headers=headers)
    assert r.status_code == 204

    r = client.get(PREFIX + "/", headers=headers)
    assert r.json() == []


def test_delete_workspace_requires_owner(client: TestClient, db: Session) -> None:
    owner, _ = create_user_with_headers(client, db)
    admin, admin_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    add_member(db, ws, admin, WorkspaceRole.admin)

    r = client.delete(f"{PREFIX}/{ws.id}", headers=admin_headers)
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


def test_list_members(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    r = client.get(f"{PREFIX}/{ws.id}/members", headers=headers)
    assert r.status_code == 200
    members = r.json()
    assert len(members) == 1
    assert members[0]["user_id"] == str(user.id)
    assert members[0]["user_email"] == user.email
    assert members[0]["role"] == "owner"


def test_add_member_by_email(client: TestClient, db: Session) -> None:
    owner, owner_headers = create_user_with_headers(client, db)
    new_user, _ = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)

    r = client.post(
        f"{PREFIX}/{ws.id}/members",
        headers=owner_headers,
        # Emails are matched case-insensitively
        json={"email": new_user.email.upper(), "role": "admin"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["user_id"] == str(new_user.id)
    assert r.json()["role"] == "admin"


def test_add_member_defaults_to_viewer(client: TestClient, db: Session) -> None:
    owner, owner_headers = create_user_with_headers(client, db)
    new_user, _ = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)

    r = client.post(
        f"{PREFIX}/{ws.id}/members",
        headers=owner_headers,
        json={"email": new_user.email},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "viewer"


def test_add_member_duplicate_returns_409(client: TestClient, db: Session) -> None:
    owner, owner_headers = create_user_with_headers(client, db)
    new_user, _ = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    payload = {"email": new_user.email, "role": "viewer"}

    client.post(f"{PREFIX}/{ws.id}/members", headers=owner_headers, json=payload)
    r = client.post(f"{PREFIX}/{ws.id}/members", headers=owner_headers, json=payload)
    assert r.status_code == 409


def test_add_member_unknown_email_returns_404(client: TestClient, db: Session) -> None:
    owner, owner_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)

    r = client.post(
        f"{PREFIX}/{ws.id}/members",
        headers=owner_headers,
        json={"email": "nobody-here@example.com"},
    )
    assert r.status_code == 404
    assert "sign up" in r.json()["detail"]


def test_add_member_requires_email(client: TestClient, db: Session) -> None:
    owner, owner_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)

    r = client.post(
        f"{PREFIX}/{ws.id}/members", headers=owner_headers, json={"role": "viewer"}
    )
    assert r.status_code == 422


def test_viewer_cannot_add_member(client: TestClient, db: Session) -> None:
    owner, _ = create_user_with_headers(client, db)
    viewer, viewer_headers = create_user_with_headers(client, db)
    outsider, _ = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    add_member(db, ws, viewer, WorkspaceRole.viewer)

    r = client.post(
        f"{PREFIX}/{ws.id}/members",
        headers=viewer_headers,
        json={"email": outsider.email},
    )
    assert r.status_code == 403


def test_admin_cannot_add_owner(client: TestClient, db: Session) -> None:
    owner, _ = create_user_with_headers(client, db)
    admin, admin_headers = create_user_with_headers(client, db)
    outsider, _ = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    add_member(db, ws, admin, WorkspaceRole.admin)

    r = client.post(
        f"{PREFIX}/{ws.id}/members",
        headers=admin_headers,
        json={"email": outsider.email, "role": "owner"},
    )
    assert r.status_code == 403


def test_update_member_role(client: TestClient, db: Session) -> None:
    owner, owner_headers = create_user_with_headers(client, db)
    member, _ = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    add_member(db, ws, member, WorkspaceRole.viewer)

    r = client.patch(
        f"{PREFIX}/{ws.id}/members/{member.id}",
        headers=owner_headers,
        json={"role": "admin"},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


def test_cannot_demote_last_owner(client: TestClient, db: Session) -> None:
    owner, owner_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)

    r = client.patch(
        f"{PREFIX}/{ws.id}/members/{owner.id}",
        headers=owner_headers,
        json={"role": "admin"},
    )
    assert r.status_code == 409


def test_remove_member(client: TestClient, db: Session) -> None:
    owner, owner_headers = create_user_with_headers(client, db)
    member, _ = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    add_member(db, ws, member, WorkspaceRole.viewer)

    r = client.delete(f"{PREFIX}/{ws.id}/members/{member.id}", headers=owner_headers)
    assert r.status_code == 204
    db.expire_all()
    assert get_member_role(db, ws, member) is None

    r = client.delete(f"{PREFIX}/{ws.id}/members/{member.id}", headers=owner_headers)
    assert r.status_code == 404


def test_member_can_remove_themselves(client: TestClient, db: Session) -> None:
    owner, _ = create_user_with_headers(client, db)
    member, member_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    add_member(db, ws, member, WorkspaceRole.viewer)

    r = client.delete(f"{PREFIX}/{ws.id}/members/{member.id}", headers=member_headers)
    assert r.status_code == 204


def test_viewer_cannot_remove_others(client: TestClient, db: Session) -> None:
    owner, _ = create_user_with_headers(client, db)
    viewer, viewer_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    add_member(db, ws, viewer, WorkspaceRole.viewer)

    r = client.delete(f"{PREFIX}/{ws.id}/members/{owner.id}", headers=viewer_headers)
    assert r.status_code == 403


def test_cannot_remove_last_owner(client: TestClient, db: Session) -> None:
    owner, owner_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)

    r = client.delete(f"{PREFIX}/{ws.id}/members/{owner.id}", headers=owner_headers)
    assert r.status_code == 409
