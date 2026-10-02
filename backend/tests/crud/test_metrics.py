"""Tests for MetricSnapshot and Post CRUD helpers."""

from datetime import UTC, date, datetime

from sqlmodel import Session

from app.crud import metrics as mcrud
from app.models.metrics import ContentType, MetricSnapshotUpsert, PostUpsert
from tests.utils.integration import create_fake_account, create_fake_integration
from tests.utils.user import create_random_user
from tests.utils.workspace import create_random_workspace


def _make_account(db: Session):  # type: ignore[no-untyped-def]
    user = create_random_user(db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws)
    return create_fake_account(db, integration)


# ---------------------------------------------------------------------------
# MetricSnapshot
# ---------------------------------------------------------------------------


def test_upsert_snapshot_creates(db: Session) -> None:
    account = _make_account(db)
    snap_in = MetricSnapshotUpsert(
        date=date(2024, 3, 1),
        followers_count=1000,
        impressions=5000,
        reach=3000,
        engagements=150,
    )
    snap = mcrud.upsert_metric_snapshot(
        session=db, platform_account_id=account.id, snapshot_in=snap_in
    )
    assert snap.id is not None
    assert snap.followers_count == 1000
    assert snap.impressions == 5000
    # engagements / views, or impressions when there are no views
    assert snap.engagement_rate == round(150 / 5000, 6)


def test_upsert_snapshot_updates_existing(db: Session) -> None:
    account = _make_account(db)
    d = date(2024, 3, 2)
    mcrud.upsert_metric_snapshot(
        session=db,
        platform_account_id=account.id,
        snapshot_in=MetricSnapshotUpsert(date=d, followers_count=900),
    )
    updated = mcrud.upsert_metric_snapshot(
        session=db,
        platform_account_id=account.id,
        snapshot_in=MetricSnapshotUpsert(
            date=d, followers_count=1100, impressions=2000
        ),
    )
    assert updated.followers_count == 1100
    assert updated.impressions == 2000

    # Only one row exists
    rows = mcrud.get_snapshots_for_accounts(
        session=db, platform_account_ids=[account.id], start_date=d, end_date=d
    )
    assert len(rows) == 1


def test_upsert_snapshot_engagement_rate_none_when_no_reach(db: Session) -> None:
    account = _make_account(db)
    snap = mcrud.upsert_metric_snapshot(
        session=db,
        platform_account_id=account.id,
        snapshot_in=MetricSnapshotUpsert(date=date(2024, 3, 3), engagements=50),
    )
    assert snap.engagement_rate is None


def test_get_snapshots_for_accounts(db: Session) -> None:
    user = create_random_user(db)
    ws = create_random_workspace(db, user)
    integ = create_fake_integration(db, ws)
    acc1 = create_fake_account(db, integ, external_id="acc-bulk-1")
    acc2 = create_fake_account(db, integ, external_id="acc-bulk-2")

    d = date(2024, 5, 1)
    mcrud.upsert_metric_snapshot(
        session=db,
        platform_account_id=acc1.id,
        snapshot_in=MetricSnapshotUpsert(date=d, followers_count=10),
    )
    mcrud.upsert_metric_snapshot(
        session=db,
        platform_account_id=acc2.id,
        snapshot_in=MetricSnapshotUpsert(date=d, followers_count=20),
    )

    rows = mcrud.get_snapshots_for_accounts(
        session=db,
        platform_account_ids=[acc1.id, acc2.id],
        start_date=d,
        end_date=d,
    )
    assert len(rows) == 2


def test_get_snapshots_for_accounts_empty_list(db: Session) -> None:
    rows = mcrud.get_snapshots_for_accounts(
        session=db,
        platform_account_ids=[],
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
    )
    assert list(rows) == []


def test_snapshot_stores_raw_data(db: Session) -> None:
    account = _make_account(db)
    raw = {"page_fans_city": {"Paris": 400, "Lyon": 100}}
    snap = mcrud.upsert_metric_snapshot(
        session=db,
        platform_account_id=account.id,
        snapshot_in=MetricSnapshotUpsert(date=date(2024, 7, 1), raw_data=raw),
    )
    assert snap.raw_data == raw


# ---------------------------------------------------------------------------
# Post
# ---------------------------------------------------------------------------


def test_upsert_post_creates(db: Session) -> None:
    account = _make_account(db)
    post_in = PostUpsert(
        external_id="post-abc",
        published_at=datetime(2024, 3, 10, 12, 0, tzinfo=UTC),
        content_type=ContentType.reel,
        text="Check out this reel!",
        impressions=8000,
        reach=4000,
        engagements=320,
    )
    post = mcrud.upsert_post(
        session=db, platform_account_id=account.id, post_in=post_in
    )
    assert post.id is not None
    assert post.content_type == ContentType.reel
    assert post.engagement_rate == round(320 / 8000, 6)


def test_upsert_post_updates_existing(db: Session) -> None:
    account = _make_account(db)
    post_in = PostUpsert(
        external_id="post-update",
        published_at=datetime(2024, 3, 11, 9, 0, tzinfo=UTC),
        content_type=ContentType.post,
        likes=100,
    )
    created = mcrud.upsert_post(
        session=db, platform_account_id=account.id, post_in=post_in
    )
    post_in.likes = 250
    updated = mcrud.upsert_post(
        session=db, platform_account_id=account.id, post_in=post_in
    )

    assert updated.id == created.id
    assert updated.likes == 250


def test_get_top_posts(db: Session) -> None:
    account = _make_account(db)
    for i, eng in enumerate([10, 500, 50, 200, 1]):
        mcrud.upsert_post(
            session=db,
            platform_account_id=account.id,
            post_in=PostUpsert(
                external_id=f"top-{i}",
                published_at=datetime(2024, 7, 1, tzinfo=UTC),
                content_type=ContentType.post,
                engagements=eng,
            ),
        )
    top = mcrud.get_top_posts(
        session=db,
        platform_account_ids=[account.id],
        start_date=date(2024, 7, 1),
        end_date=date(2024, 7, 31),
        limit=3,
    )
    assert len(top) == 3
    assert top[0].engagements == 500
    assert top[1].engagements == 200


def test_get_top_posts_empty_accounts(db: Session) -> None:
    result = mcrud.get_top_posts(
        session=db,
        platform_account_ids=[],
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
    )
    assert list(result) == []
