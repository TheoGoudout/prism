import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app import crud
from app.core.config import settings
from app.migrate.sources import SOURCES, ProfileData, SourceAuthError
from app.models.integration import Platform
from app.models.metrics import (
    ContentType,
    MetricSnapshot,
    MetricSnapshotUpsert,
    Post,
    PostUpsert,
)
from app.models.migration import (
    Migration,
    MigrationSource,
    MigrationStatus,
    RemoteProfile,
    SourceCredentials,
)
from app.models.workspace import Workspace, WorkspaceRole
from app.worker.tasks.migration import run_migration
from tests.utils.integration import create_fake_account, create_fake_integration
from tests.utils.user import create_user_with_headers
from tests.utils.workspace import add_member, create_random_workspace


def _url(workspace: Workspace, path: str = "") -> str:
    return f"{settings.API_V1_STR}/workspaces/{workspace.id}/migrate/{path}"


POSTS_CSV = (
    "Date,Post ID,Post Message,Post Permalink,Impressions,Likes,Comments,Shares\n"
    "2024-03-01 14:30,p-1,Hello,https://facebook.com/1/posts/1,1000,40,5,5\n"
    "2024-03-02 09:00,p-2,,https://facebook.com/1/posts/2,500,10,2,0\n"
    "oops,p-3,,,1,1,1,1\n"
)


def test_list_migration_accounts(client: TestClient, db: Session) -> None:
    owner, _ = create_user_with_headers(client, db)
    viewer, viewer_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    add_member(db, ws, viewer, WorkspaceRole.viewer)
    account = create_fake_account(db, create_fake_integration(db, ws))

    r = client.get(_url(ws, "accounts"), headers=viewer_headers)
    assert r.status_code == 200
    assert [a["id"] for a in r.json()] == [str(account.id)]
    assert r.json()[0]["platform"] == "facebook"


def test_upload_posts(client: TestClient, db: Session) -> None:
    owner, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    account = create_fake_account(db, create_fake_integration(db, ws))
    # A post the sync already stored, with a metric the file doesn't have
    crud.upsert_post(
        session=db,
        platform_account_id=account.id,
        post_in=PostUpsert(
            external_id="p-2",
            content_type=ContentType.post,
            text="Synced text",
            published_at=datetime(2024, 3, 2, 9, tzinfo=UTC),
            views=900,
            raw_data={"from": "sync"},
        ),
    )
    db.commit()

    r = client.post(
        _url(ws, "upload"),
        headers=headers,
        data={"platform_account_id": str(account.id)},
        files={"file": ("posts.csv", POSTS_CSV, "text/csv")},
    )
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["format"] == "hootsuite"
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
        _url(ws, "upload"),
        headers=headers,
        data={"platform_account_id": str(account.id), "export_format": "csv"},
        files={"file": ("posts.csv", POSTS_CSV, "text/csv")},
    )
    assert r.status_code == 200
    assert (r.json()["created"], r.json()["updated"]) == (0, 2)
    assert r.json()["format"] == "csv"


def test_upload_daily_metrics(client: TestClient, db: Session) -> None:
    owner, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    account = create_fake_account(
        db, create_fake_integration(db, ws, platform=Platform.instagram)
    )
    csv = "Date;Followers;Impressions\n2024-01-01;100;50\n2024-01-02;105;70\n"

    r = client.post(
        _url(ws, "upload"),
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
        .order_by(col(MetricSnapshot.date))
    ).all()
    assert [s.followers_count for s in snapshots] == [100, 105]


def test_upload_requires_manager(client: TestClient, db: Session) -> None:
    owner, _ = create_user_with_headers(client, db)
    viewer, viewer_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    add_member(db, ws, viewer, WorkspaceRole.viewer)
    account = create_fake_account(db, create_fake_integration(db, ws))

    r = client.post(
        _url(ws, "upload"),
        headers=viewer_headers,
        data={"platform_account_id": str(account.id)},
        files={"file": ("posts.csv", POSTS_CSV, "text/csv")},
    )
    assert r.status_code == 403


def test_upload_into_another_workspace_account_returns_404(
    client: TestClient, db: Session
) -> None:
    owner, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    other_owner, _ = create_user_with_headers(client, db)
    other_ws = create_random_workspace(db, other_owner)
    other_account = create_fake_account(db, create_fake_integration(db, other_ws))

    r = client.post(
        _url(ws, "upload"),
        headers=headers,
        data={"platform_account_id": str(other_account.id)},
        files={"file": ("posts.csv", POSTS_CSV, "text/csv")},
    )
    assert r.status_code == 404


def test_upload_unreadable_file_returns_422(client: TestClient, db: Session) -> None:
    owner, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    account = create_fake_account(db, create_fake_integration(db, ws))

    for content, detail in [
        ("name,email\nJane,jane@example.com\n", "No header row"),
        ("Date,Likes\nyesterday,3\n", "No row could be imported"),
    ]:
        r = client.post(
            _url(ws, "upload"),
            headers=headers,
            data={"platform_account_id": str(account.id)},
            files={"file": ("x.csv", content, "text/csv")},
        )
        assert r.status_code == 422
        assert detail in r.json()["detail"]


# ---------------------------------------------------------------------------
# API migrations
# ---------------------------------------------------------------------------


class FakeSource:
    """A source with one Facebook page and one YouTube channel."""

    def __init__(self, native_id: str = "page-456") -> None:
        self.native_id = native_id

    def list_profiles(self, credentials: SourceCredentials) -> list[RemoteProfile]:
        if credentials.api_token == "bad":
            raise SourceAuthError("The credentials were rejected.")
        return [
            RemoteProfile(
                id="c:1",
                name="Acme FB",
                network="facebook",
                platform=Platform.facebook,
                native_id=self.native_id,
            ),
            RemoteProfile(id="c:2", name="Acme TV", network="youtube"),
        ]

    def fetch(
        self,
        credentials: SourceCredentials,
        profile: RemoteProfile,
        date_from: date,
        date_to: date,
    ) -> ProfileData:
        return ProfileData(
            snapshots=[MetricSnapshotUpsert(date=date(2024, 1, 1), followers_count=10)],
            posts=[
                PostUpsert(
                    external_id="p-9",
                    content_type=ContentType.post,
                    published_at=datetime(2024, 1, 1, tzinfo=UTC),
                    likes=3,
                    engagements=3,
                    impressions=30,
                )
            ],
            errors=["Posts 2024-02: HTTP 500"],
        )


@pytest.fixture
def fake_source() -> Iterator[FakeSource]:
    source = FakeSource()
    with patch.dict(SOURCES, {MigrationSource.sprout_social: source}):
        yield source


@pytest.fixture
def enqueued() -> Iterator[MagicMock]:
    with patch("app.api.routes.migrate.migration_tasks.run_migration.delay") as mock:
        yield mock


def test_list_source_profiles_suggests_accounts(
    client: TestClient, db: Session, fake_source: FakeSource
) -> None:
    owner, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    account = create_fake_account(db, create_fake_integration(db, ws))

    r = client.post(
        _url(ws, "sprout_social/profiles"), headers=headers, json={"api_token": "t"}
    )
    assert r.status_code == 200, r.text
    facebook, youtube = r.json()
    assert facebook["suggested_account_id"] == str(account.id)
    assert youtube["platform"] is None
    assert youtube["suggested_account_id"] is None


def test_list_source_profiles_rejected_credentials(
    client: TestClient, db: Session, fake_source: FakeSource
) -> None:
    owner, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)

    r = client.post(
        _url(ws, "sprout_social/profiles"), headers=headers, json={"api_token": "bad"}
    )
    assert r.status_code == 400
    assert "rejected" in r.json()["detail"]


def test_run_migration(
    client: TestClient, db: Session, fake_source: FakeSource, enqueued: MagicMock
) -> None:
    owner, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    account = create_fake_account(db, create_fake_integration(db, ws))

    r = client.post(
        _url(ws, "sprout_social"),
        headers=headers,
        json={
            "credentials": {"api_token": "t"},
            "profiles": [
                {"remote_profile_id": "c:1", "platform_account_id": str(account.id)}
            ],
            "date_from": "2024-01-01",
        },
    )
    assert r.status_code == 202, r.text
    migration_id = r.json()["id"]
    assert r.json()["status"] == "pending"
    assert r.json()["profiles"][0]["name"] == "Acme FB"
    enqueued.assert_called_once_with(migration_id)

    # A second one waits for the first
    r = client.post(
        _url(ws, "sprout_social"),
        headers=headers,
        json={
            "credentials": {"api_token": "t"},
            "profiles": [
                {"remote_profile_id": "c:1", "platform_account_id": str(account.id)}
            ],
            "date_from": "2024-01-01",
        },
    )
    assert r.status_code == 409

    run_migration(migration_id)

    db.expire_all()
    migration = db.get(Migration, uuid.UUID(migration_id))
    assert migration is not None
    assert migration.status is MigrationStatus.completed
    assert migration.credentials_encrypted is None
    [progress] = migration.profiles
    assert progress["done"] is True
    assert (progress["posts"], progress["days"]) == (1, 1)
    assert progress["errors"] == ["Posts 2024-02: HTTP 500"]
    post = db.exec(select(Post).where(Post.platform_account_id == account.id)).one()
    assert post.raw_data == {"imported_from": "sprout_social"}

    r = client.get(_url(ws, "runs"), headers=headers)
    assert r.status_code == 200
    assert [m["status"] for m in r.json()] == ["completed"]
    assert "credentials" not in str(r.json())


def test_start_migration_validates_mappings(
    client: TestClient, db: Session, fake_source: FakeSource, enqueued: MagicMock
) -> None:
    owner, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    instagram = create_fake_account(
        db, create_fake_integration(db, ws, platform=Platform.instagram)
    )

    for remote_id, account_id, detail in [
        ("c:9", instagram.id, "Unknown profile"),
        ("c:1", uuid.uuid4(), "Unknown account"),
        ("c:1", instagram.id, "can't be migrated into a instagram account"),
    ]:
        r = client.post(
            _url(ws, "sprout_social"),
            headers=headers,
            json={
                "credentials": {"api_token": "t"},
                "profiles": [
                    {
                        "remote_profile_id": remote_id,
                        "platform_account_id": str(account_id),
                    }
                ],
                "date_from": "2024-01-01",
            },
        )
        assert r.status_code == 422
        assert detail in r.json()["detail"]
    enqueued.assert_not_called()


def test_migrations_require_manager(
    client: TestClient, db: Session, fake_source: FakeSource
) -> None:
    owner, _ = create_user_with_headers(client, db)
    viewer, viewer_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    add_member(db, ws, viewer, WorkspaceRole.viewer)

    r = client.post(
        _url(ws, "sprout_social/profiles"),
        headers=viewer_headers,
        json={"api_token": "t"},
    )
    assert r.status_code == 403
    r = client.get(_url(ws, "runs"), headers=viewer_headers)
    assert r.status_code == 200


def test_failed_migration_records_the_error(
    client: TestClient, db: Session, fake_source: FakeSource, enqueued: MagicMock
) -> None:
    owner, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    account = create_fake_account(db, create_fake_integration(db, ws))
    r = client.post(
        _url(ws, "sprout_social"),
        headers=headers,
        json={
            "credentials": {"api_token": "t"},
            "profiles": [
                {"remote_profile_id": "c:1", "platform_account_id": str(account.id)}
            ],
            "date_from": "2024-01-01",
        },
    )
    migration_id = r.json()["id"]

    def revoked(*args: object) -> ProfileData:
        raise SourceAuthError("The credentials were rejected.")

    with patch.object(fake_source, "fetch", revoked):
        run_migration(migration_id)

    db.expire_all()
    migration = db.get(Migration, uuid.UUID(migration_id))
    assert migration is not None
    assert migration.status is MigrationStatus.failed
    assert migration.error == "The credentials were rejected."
    assert migration.credentials_encrypted is None
