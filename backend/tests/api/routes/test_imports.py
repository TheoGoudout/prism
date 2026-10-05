from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import crud
from app.core.config import settings
from app.models.integration import Platform
from app.models.metrics import MetricSnapshot, Post, PostUpsert
from app.models.workspace import Workspace, WorkspaceRole
from tests.utils.integration import create_fake_account, create_fake_integration
from tests.utils.user import create_user_with_headers
from tests.utils.workspace import add_member, create_random_workspace


def _url(workspace: Workspace, path: str = "") -> str:
    return f"{settings.API_V1_STR}/workspaces/{workspace.id}/imports/{path}"


POSTS_CSV = (
    "Date,Post ID,Post Message,Post Permalink,Impressions,Likes,Comments,Shares\n"
    "2024-03-01 14:30,p-1,Hello,https://facebook.com/1/posts/1,1000,40,5,5\n"
    "2024-03-02 09:00,p-2,,https://facebook.com/1/posts/2,500,10,2,0\n"
    "oops,p-3,,,1,1,1,1\n"
)


def test_list_import_accounts(client: TestClient, db: Session) -> None:
    owner, _ = create_user_with_headers(client, db)
    viewer, viewer_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    add_member(db, ws, viewer, WorkspaceRole.viewer)
    account = create_fake_account(db, create_fake_integration(db, ws))

    r = client.get(_url(ws, "accounts"), headers=viewer_headers)
    assert r.status_code == 200
    assert [a["id"] for a in r.json()] == [str(account.id)]
    assert r.json()[0]["platform"] == "facebook"


def test_import_posts(client: TestClient, db: Session) -> None:
    owner, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    account = create_fake_account(db, create_fake_integration(db, ws))
    # A post the sync already stored, with a metric the file doesn't have
    crud.upsert_post(
        session=db,
        platform_account_id=account.id,
        post_in=PostUpsert(
            external_id="p-2",
            content_type="post",
            text="Synced text",
            published_at="2024-03-02T09:00:00Z",
            views=900,
            raw_data={"from": "sync"},
        ),
    )

    r = client.post(
        _url(ws),
        headers=headers,
        data={"platform_account_id": str(account.id)},
        files={"file": ("posts.csv", POSTS_CSV, "text/csv")},
    )
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["source"] == "hootsuite"
    assert result["kind"] == "posts"
    assert result["rows_read"] == 3
    assert (result["created"], result["updated"], result["rejected"]) == (1, 1, 1)
    assert result["errors"] == ["Line 4: 'oops' is not a date"]
    assert (result["date_from"], result["date_to"]) == ("2024-03-01", "2024-03-02")

    db.expire_all()
    posts = {
        p.external_id: p
        for p in db.exec(select(Post).where(Post.platform_account_id == account.id))
    }
    assert posts["p-1"].engagements == 50
    assert posts["p-1"].engagement_rate == 0.05
    # Filled in, without erasing what the sync stored
    assert posts["p-2"].impressions == 500
    assert posts["p-2"].views == 900
    assert posts["p-2"].text == "Synced text"
    assert posts["p-2"].raw_data == {"from": "sync", "imported_from": "hootsuite"}

    # Importing the same file again updates rather than duplicates
    r = client.post(
        _url(ws),
        headers=headers,
        data={"platform_account_id": str(account.id), "source": "csv"},
        files={"file": ("posts.csv", POSTS_CSV, "text/csv")},
    )
    assert r.status_code == 200
    assert (r.json()["created"], r.json()["updated"]) == (0, 2)
    assert r.json()["source"] == "csv"


def test_import_daily_metrics(client: TestClient, db: Session) -> None:
    owner, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    account = create_fake_account(
        db, create_fake_integration(db, ws, platform=Platform.instagram)
    )
    csv = "Date;Followers;Impressions\n2024-01-01;100;50\n2024-01-02;105;70\n"

    r = client.post(
        _url(ws),
        headers=headers,
        data={"platform_account_id": str(account.id)},
        files={"file": ("account.csv", csv.encode(), "text/csv")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == "daily_metrics"
    assert r.json()["created"] == 2

    snapshots = db.exec(
        select(MetricSnapshot)
        .where(MetricSnapshot.platform_account_id == account.id)
        .order_by(MetricSnapshot.date)
    ).all()
    assert [s.followers_count for s in snapshots] == [100, 105]


def test_import_requires_manager(client: TestClient, db: Session) -> None:
    owner, _ = create_user_with_headers(client, db)
    viewer, viewer_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    add_member(db, ws, viewer, WorkspaceRole.viewer)
    account = create_fake_account(db, create_fake_integration(db, ws))

    r = client.post(
        _url(ws),
        headers=viewer_headers,
        data={"platform_account_id": str(account.id)},
        files={"file": ("posts.csv", POSTS_CSV, "text/csv")},
    )
    assert r.status_code == 403


def test_import_into_another_workspace_account_returns_404(
    client: TestClient, db: Session
) -> None:
    owner, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    other_owner, _ = create_user_with_headers(client, db)
    other_ws = create_random_workspace(db, other_owner)
    other_account = create_fake_account(db, create_fake_integration(db, other_ws))

    r = client.post(
        _url(ws),
        headers=headers,
        data={"platform_account_id": str(other_account.id)},
        files={"file": ("posts.csv", POSTS_CSV, "text/csv")},
    )
    assert r.status_code == 404


def test_import_unreadable_file_returns_422(client: TestClient, db: Session) -> None:
    owner, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    account = create_fake_account(db, create_fake_integration(db, ws))

    for content, detail in [
        ("name,email\nJane,jane@example.com\n", "No header row"),
        ("Date,Likes\nyesterday,3\n", "No row could be imported"),
    ]:
        r = client.post(
            _url(ws),
            headers=headers,
            data={"platform_account_id": str(account.id)},
            files={"file": ("x.csv", content, "text/csv")},
        )
        assert r.status_code == 422
        assert detail in r.json()["detail"]
