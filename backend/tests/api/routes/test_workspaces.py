import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.models.workspace import WorkspaceRole

PREFIX = f"{settings.API_V1_STR}/workspaces"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auth(client: TestClient, email: str, password: str) -> dict[str, str]:
    r = client.post(
        f"{settings.API_V1_STR}/login/access-token",
        data={"username": email, "password": password},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _create_user_with_headers(client: TestClient, db: Session) -> tuple:
    """Return (user, password, auth_headers)."""
    from app.crud.user import create_user
    from app.models.user import UserCreate
    from tests.utils.utils import random_email, random_lower_string

    email = random_email()
    password = random_lower_string()
    user = create_user(
        session=db, user_create=UserCreate(email=email, password=password)
    )
    headers = _auth(client, email, password)
    return user, password, headers


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
    data = {"name": "Dup Slug"}
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


def test_list_workspaces(
    client: TestClient, normal_user_token_headers: dict, db: Session
) -> None:
    # ensure at least one workspace exists for this user
    client.post(
        PREFIX + "/", headers=normal_user_token_headers, json={"name": "Listed WS"}
    )
    r = client.get(PREFIX + "/", headers=normal_user_token_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert len(body["data"]) >= 1


def test_list_workspaces_only_own(client: TestClient, db: Session) -> None:
    user_a, _, headers_a = _create_user_with_headers(client, db)
    user_b, _, headers_b = _create_user_with_headers(client, db)
    client.post(PREFIX + "/", headers=headers_a, json={"name": "A only"})
    r = client.get(PREFIX + "/", headers=headers_b)
    assert r.status_code == 200
    ids_b = {ws["id"] for ws in r.json()["data"]}
    r_a = client.get(PREFIX + "/", headers=headers_a)
    ids_a = {ws["id"] for ws in r_a.json()["data"]}
    assert ids_a.isdisjoint(ids_b)


# ---------------------------------------------------------------------------
# Workspace retrieval
# ---------------------------------------------------------------------------


def test_get_workspace(
    client: TestClient, normal_user_token_headers: dict, db: Session
) -> None:
    r_create = client.post(
        PREFIX + "/", headers=normal_user_token_headers, json={"name": "Get Me"}
    )
    ws_id = r_create.json()["id"]
    r = client.get(f"{PREFIX}/{ws_id}", headers=normal_user_token_headers)
    assert r.status_code == 200
    assert r.json()["id"] == ws_id


def test_get_workspace_not_member_returns_404(client: TestClient, db: Session) -> None:
    user_a, _, headers_a = _create_user_with_headers(client, db)
    user_b, _, headers_b = _create_user_with_headers(client, db)
    r = client.post(PREFIX + "/", headers=headers_a, json={"name": "Private WS"})
    ws_id = r.json()["id"]
    r = client.get(f"{PREFIX}/{ws_id}", headers=headers_b)
    assert r.status_code == 404


def test_get_workspace_nonexistent(
    client: TestClient, normal_user_token_headers: dict
) -> None:
    r = client.get(f"{PREFIX}/{uuid.uuid4()}", headers=normal_user_token_headers)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Workspace update
# ---------------------------------------------------------------------------


def test_update_workspace_name(
    client: TestClient, normal_user_token_headers: dict, db: Session
) -> None:
    r = client.post(
        PREFIX + "/", headers=normal_user_token_headers, json={"name": "Old Name"}
    )
    ws_id = r.json()["id"]
    r = client.patch(
        f"{PREFIX}/{ws_id}",
        headers=normal_user_token_headers,
        json={"name": "New Name"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "New Name"


def test_update_workspace_requires_owner_or_admin(
    client: TestClient, db: Session
) -> None:
    owner, _, owner_headers = _create_user_with_headers(client, db)
    viewer, _, viewer_headers = _create_user_with_headers(client, db)

    r = client.post(PREFIX + "/", headers=owner_headers, json={"name": "Owner WS"})
    ws_id = r.json()["id"]

    # Add viewer
    client.post(
        f"{PREFIX}/{ws_id}/members",
        headers=owner_headers,
        json={"user_id": str(viewer.id), "role": "viewer"},
    )

    r = client.patch(
        f"{PREFIX}/{ws_id}", headers=viewer_headers, json={"name": "Hacked"}
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Workspace deletion
# ---------------------------------------------------------------------------


def test_delete_workspace(client: TestClient, db: Session) -> None:
    user, _, headers = _create_user_with_headers(client, db)
    r = client.post(PREFIX + "/", headers=headers, json={"name": "To Delete"})
    ws_id = r.json()["id"]

    r = client.delete(f"{PREFIX}/{ws_id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["message"] == "Workspace deleted successfully"

    r = client.get(f"{PREFIX}/{ws_id}", headers=headers)
    assert r.status_code == 404


def test_delete_workspace_requires_owner(client: TestClient, db: Session) -> None:
    owner, _, owner_headers = _create_user_with_headers(client, db)
    admin, _, admin_headers = _create_user_with_headers(client, db)

    r = client.post(
        PREFIX + "/", headers=owner_headers, json={"name": "Owner Only Delete"}
    )
    ws_id = r.json()["id"]
    client.post(
        f"{PREFIX}/{ws_id}/members",
        headers=owner_headers,
        json={"user_id": str(admin.id), "role": "admin"},
    )

    r = client.delete(f"{PREFIX}/{ws_id}", headers=admin_headers)
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Member management
# ---------------------------------------------------------------------------


def test_list_members(client: TestClient, db: Session) -> None:
    owner, _, headers = _create_user_with_headers(client, db)
    r = client.post(PREFIX + "/", headers=headers, json={"name": "Members WS"})
    ws_id = r.json()["id"]

    r = client.get(f"{PREFIX}/{ws_id}/members", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["data"][0]["role"] == WorkspaceRole.owner


def test_add_member(client: TestClient, db: Session) -> None:
    owner, _, owner_headers = _create_user_with_headers(client, db)
    new_user, _, _ = _create_user_with_headers(client, db)

    r = client.post(PREFIX + "/", headers=owner_headers, json={"name": "Add Test WS"})
    ws_id = r.json()["id"]

    r = client.post(
        f"{PREFIX}/{ws_id}/members",
        headers=owner_headers,
        json={"user_id": str(new_user.id), "role": "admin"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == str(new_user.id)
    assert body["role"] == "admin"


def test_add_member_duplicate_returns_409(client: TestClient, db: Session) -> None:
    owner, _, owner_headers = _create_user_with_headers(client, db)
    new_user, _, _ = _create_user_with_headers(client, db)

    r = client.post(PREFIX + "/", headers=owner_headers, json={"name": "Dup Member WS"})
    ws_id = r.json()["id"]
    payload = {"user_id": str(new_user.id), "role": "viewer"}
    client.post(f"{PREFIX}/{ws_id}/members", headers=owner_headers, json=payload)
    r = client.post(f"{PREFIX}/{ws_id}/members", headers=owner_headers, json=payload)
    assert r.status_code == 409


def test_add_member_by_email(client: TestClient, db: Session) -> None:
    owner, _, owner_headers = _create_user_with_headers(client, db)
    new_user, _, _ = _create_user_with_headers(client, db)
    r = client.post(PREFIX + "/", headers=owner_headers, json={"name": "Email WS"})
    ws_id = r.json()["id"]

    r = client.post(
        f"{PREFIX}/{ws_id}/members",
        headers=owner_headers,
        json={"email": new_user.email.upper(), "role": "viewer"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["user_id"] == str(new_user.id)
    assert r.json()["user_email"] == new_user.email


def test_add_member_unknown_email_returns_404(client: TestClient, db: Session) -> None:
    owner, _, owner_headers = _create_user_with_headers(client, db)
    r = client.post(
        PREFIX + "/", headers=owner_headers, json={"name": "Ghost Email WS"}
    )
    ws_id = r.json()["id"]

    r = client.post(
        f"{PREFIX}/{ws_id}/members",
        headers=owner_headers,
        json={"email": "nobody-here@example.com"},
    )
    assert r.status_code == 404
    assert "sign up" in r.json()["detail"]


def test_add_member_requires_exactly_one_identifier(
    client: TestClient, db: Session
) -> None:
    owner, _, owner_headers = _create_user_with_headers(client, db)
    new_user, _, _ = _create_user_with_headers(client, db)
    r = client.post(PREFIX + "/", headers=owner_headers, json={"name": "Both WS"})
    ws_id = r.json()["id"]

    for payload in (
        {"role": "viewer"},
        {"user_id": str(new_user.id), "email": new_user.email},
    ):
        r = client.post(
            f"{PREFIX}/{ws_id}/members", headers=owner_headers, json=payload
        )
        assert r.status_code == 422


def test_add_member_nonexistent_user(client: TestClient, db: Session) -> None:
    owner, _, owner_headers = _create_user_with_headers(client, db)
    r = client.post(
        PREFIX + "/", headers=owner_headers, json={"name": "Ghost Member WS"}
    )
    ws_id = r.json()["id"]

    r = client.post(
        f"{PREFIX}/{ws_id}/members",
        headers=owner_headers,
        json={"user_id": str(uuid.uuid4()), "role": "viewer"},
    )
    assert r.status_code == 404


def test_viewer_cannot_add_member(client: TestClient, db: Session) -> None:
    owner, _, owner_headers = _create_user_with_headers(client, db)
    viewer, _, viewer_headers = _create_user_with_headers(client, db)
    outsider, _, _ = _create_user_with_headers(client, db)

    r = client.post(
        PREFIX + "/", headers=owner_headers, json={"name": "Viewer Perm WS"}
    )
    ws_id = r.json()["id"]
    client.post(
        f"{PREFIX}/{ws_id}/members",
        headers=owner_headers,
        json={"user_id": str(viewer.id), "role": "viewer"},
    )

    r = client.post(
        f"{PREFIX}/{ws_id}/members",
        headers=viewer_headers,
        json={"user_id": str(outsider.id), "role": "viewer"},
    )
    assert r.status_code == 403


def test_update_member_role(client: TestClient, db: Session) -> None:
    owner, _, owner_headers = _create_user_with_headers(client, db)
    member, _, _ = _create_user_with_headers(client, db)

    r = client.post(
        PREFIX + "/", headers=owner_headers, json={"name": "Role Update WS"}
    )
    ws_id = r.json()["id"]
    client.post(
        f"{PREFIX}/{ws_id}/members",
        headers=owner_headers,
        json={"user_id": str(member.id), "role": "viewer"},
    )

    r = client.patch(
        f"{PREFIX}/{ws_id}/members/{member.id}",
        headers=owner_headers,
        json={"role": "admin"},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


def test_cannot_demote_last_owner(client: TestClient, db: Session) -> None:
    owner, _, owner_headers = _create_user_with_headers(client, db)
    r = client.post(
        PREFIX + "/", headers=owner_headers, json={"name": "Single Owner WS"}
    )
    ws_id = r.json()["id"]

    r = client.patch(
        f"{PREFIX}/{ws_id}/members/{owner.id}",
        headers=owner_headers,
        json={"role": "admin"},
    )
    assert r.status_code == 409


def test_remove_member(client: TestClient, db: Session) -> None:
    owner, _, owner_headers = _create_user_with_headers(client, db)
    member, _, member_headers = _create_user_with_headers(client, db)

    r = client.post(
        PREFIX + "/", headers=owner_headers, json={"name": "Remove Test WS"}
    )
    ws_id = r.json()["id"]
    client.post(
        f"{PREFIX}/{ws_id}/members",
        headers=owner_headers,
        json={"user_id": str(member.id), "role": "viewer"},
    )

    r = client.delete(f"{PREFIX}/{ws_id}/members/{member.id}", headers=owner_headers)
    assert r.status_code == 200

    # Removed member can no longer see the workspace
    r = client.get(f"{PREFIX}/{ws_id}", headers=member_headers)
    assert r.status_code == 404


def test_member_can_remove_themselves(client: TestClient, db: Session) -> None:
    owner, _, owner_headers = _create_user_with_headers(client, db)
    member, _, member_headers = _create_user_with_headers(client, db)

    r = client.post(PREFIX + "/", headers=owner_headers, json={"name": "Self Leave WS"})
    ws_id = r.json()["id"]
    client.post(
        f"{PREFIX}/{ws_id}/members",
        headers=owner_headers,
        json={"user_id": str(member.id), "role": "viewer"},
    )

    r = client.delete(f"{PREFIX}/{ws_id}/members/{member.id}", headers=member_headers)
    assert r.status_code == 200


def test_cannot_remove_last_owner(client: TestClient, db: Session) -> None:
    owner, _, owner_headers = _create_user_with_headers(client, db)
    r = client.post(
        PREFIX + "/", headers=owner_headers, json={"name": "Last Owner Leave"}
    )
    ws_id = r.json()["id"]

    r = client.delete(f"{PREFIX}/{ws_id}/members/{owner.id}", headers=owner_headers)
    assert r.status_code == 409
