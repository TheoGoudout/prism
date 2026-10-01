"""Tests for GET /metrics/summary, /metrics/timeseries, /metrics/posts."""

import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session

from app import crud
from app.core.config import settings
from app.models.integration import Platform
from app.models.metrics import ContentType, MetricSnapshotUpsert, PostUpsert
from tests.utils.integration import create_fake_account, create_fake_integration
from tests.utils.user import create_user_with_headers
from tests.utils.workspace import create_random_workspace

PREFIX = f"{settings.API_V1_STR}/metrics"

TODAY = date.today()

YESTERDAY = TODAY - timedelta(days=1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _add_snapshot(
    db: Session,
    account_id: uuid.UUID,
    *,
    snap_date: date = TODAY,
    impressions: int = 100,
    engagements: int = 10,
    followers_count: int = 500,
) -> None:
    crud.upsert_metric_snapshot(
        session=db,
        platform_account_id=account_id,
        snapshot_in=MetricSnapshotUpsert(
            date=snap_date,
            impressions=impressions,
            engagements=engagements,
            followers_count=followers_count,
        ),
    )


def _add_post(
    db: Session,
    account_id: uuid.UUID,
    *,
    external_id: str = "post-1",
    engagements: int = 50,
) -> None:
    crud.upsert_post(
        session=db,
        platform_account_id=account_id,
        post_in=PostUpsert(
            external_id=external_id,
            published_at=f"{TODAY}T12:00:00+00:00",
            content_type=ContentType.post,
            engagements=engagements,
        ),
    )


# ---------------------------------------------------------------------------
# /summary
# ---------------------------------------------------------------------------


def test_summary_non_member_returns_404(client: TestClient, db: Session) -> None:
    owner, _ = create_user_with_headers(client, db)
    outsider, outsider_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)

    r = client.get(
        PREFIX + "/summary",
        headers=outsider_headers,
        params={"workspace_id": str(ws.id)},
    )
    assert r.status_code == 404


def test_summary_empty_workspace(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    r = client.get(
        PREFIX + "/summary",
        headers=headers,
        params={"workspace_id": str(ws.id)},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["totals"]["impressions"] == 0
    assert body["by_platform"] == {}


def test_summary_aggregates_metrics(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws, platform=Platform.instagram)
    account = create_fake_account(db, integration)

    _add_snapshot(db, account.id, snap_date=TODAY, impressions=200, engagements=20)
    _add_snapshot(db, account.id, snap_date=YESTERDAY, impressions=100, engagements=5)

    r = client.get(
        PREFIX + "/summary",
        headers=headers,
        params={
            "workspace_id": str(ws.id),
            "date_from": str(YESTERDAY),
            "date_to": str(TODAY),
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["totals"]["impressions"] == 300
    assert body["totals"]["engagements"] == 25


def test_summary_by_platform_breakdown(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    fb_int = create_fake_integration(db, ws, platform=Platform.facebook)
    ig_int = create_fake_integration(
        db, ws, platform=Platform.instagram, external_account_id="ig-1"
    )
    fb_acc = create_fake_account(db, fb_int, external_id="fb-acc")
    ig_acc = create_fake_account(db, ig_int, external_id="ig-acc")

    _add_snapshot(db, fb_acc.id, impressions=100)
    _add_snapshot(db, ig_acc.id, impressions=200)

    r = client.get(
        PREFIX + "/summary",
        headers=headers,
        params={"workspace_id": str(ws.id)},
    )
    assert r.status_code == 200
    body = r.json()
    assert "facebook" in body["by_platform"]
    assert "instagram" in body["by_platform"]
    assert body["by_platform"]["facebook"]["impressions"] == 100
    assert body["by_platform"]["instagram"]["impressions"] == 200


def test_summary_platform_filter(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    fb_int = create_fake_integration(db, ws, platform=Platform.facebook)
    tw_int = create_fake_integration(
        db, ws, platform=Platform.twitter, external_account_id="tw-1"
    )
    fb_acc = create_fake_account(db, fb_int, external_id="fb-acc")
    tw_acc = create_fake_account(db, tw_int, external_id="tw-acc")

    _add_snapshot(db, fb_acc.id, impressions=50)
    _add_snapshot(db, tw_acc.id, impressions=80)

    r = client.get(
        PREFIX + "/summary",
        headers=headers,
        params={"workspace_id": str(ws.id), "platform": "twitter"},
    )
    assert r.status_code == 200
    body = r.json()
    # Only twitter data
    assert body["totals"]["impressions"] == 80
    assert "twitter" in body["by_platform"]
    assert "facebook" not in body["by_platform"]


def test_summary_followers_count_uses_latest_snapshot(
    client: TestClient, db: Session
) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws, platform=Platform.instagram)
    account = create_fake_account(db, integration)

    # Older snapshot has more followers (shouldn't win)
    _add_snapshot(db, account.id, snap_date=YESTERDAY, followers_count=1000)
    _add_snapshot(db, account.id, snap_date=TODAY, followers_count=1200)

    r = client.get(
        PREFIX + "/summary",
        headers=headers,
        params={
            "workspace_id": str(ws.id),
            "date_from": str(YESTERDAY),
            "date_to": str(TODAY),
        },
    )
    assert r.status_code == 200
    # Latest snapshot followers win
    assert r.json()["totals"]["followers_count"] == 1200


# ---------------------------------------------------------------------------
# /timeseries
# ---------------------------------------------------------------------------


def test_timeseries_non_member_returns_404(client: TestClient, db: Session) -> None:
    owner, _ = create_user_with_headers(client, db)
    outsider, outsider_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)

    r = client.get(
        PREFIX + "/timeseries",
        headers=outsider_headers,
        params={"workspace_id": str(ws.id)},
    )
    assert r.status_code == 404


def test_timeseries_returns_all_days_in_range(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    # Need at least one account so the endpoint queries and fills the date range
    integration = create_fake_integration(db, ws, platform=Platform.instagram)
    create_fake_account(db, integration)

    date_from = TODAY - timedelta(days=6)
    date_to = TODAY

    r = client.get(
        PREFIX + "/timeseries",
        headers=headers,
        params={
            "workspace_id": str(ws.id),
            "date_from": str(date_from),
            "date_to": str(date_to),
        },
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data) == 7  # 7 days


def test_timeseries_fills_zero_for_missing_days(
    client: TestClient, db: Session
) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws, platform=Platform.instagram)
    account = create_fake_account(db, integration)

    # Only add one day of data
    _add_snapshot(db, account.id, snap_date=TODAY, impressions=999)

    date_from = TODAY - timedelta(days=2)
    r = client.get(
        PREFIX + "/timeseries",
        headers=headers,
        params={
            "workspace_id": str(ws.id),
            "date_from": str(date_from),
            "date_to": str(TODAY),
        },
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data) == 3
    # The day with data should have correct value
    today_point = next(p for p in data if p["date"] == str(TODAY))
    assert today_point["impressions"] == 999
    # Other days should be zero
    for point in data:
        if point["date"] != str(TODAY):
            assert point["impressions"] == 0


def test_timeseries_aggregates_multiple_accounts(
    client: TestClient, db: Session
) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    fb_int = create_fake_integration(db, ws, platform=Platform.facebook)
    ig_int = create_fake_integration(
        db, ws, platform=Platform.instagram, external_account_id="ig-1"
    )
    fb_acc = create_fake_account(db, fb_int, external_id="fb-acc")
    ig_acc = create_fake_account(db, ig_int, external_id="ig-acc")

    _add_snapshot(db, fb_acc.id, snap_date=TODAY, impressions=100)
    _add_snapshot(db, ig_acc.id, snap_date=TODAY, impressions=50)

    r = client.get(
        PREFIX + "/timeseries",
        headers=headers,
        params={
            "workspace_id": str(ws.id),
            "date_from": str(TODAY),
            "date_to": str(TODAY),
        },
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data[0]["impressions"] == 150


# ---------------------------------------------------------------------------
# /posts
# ---------------------------------------------------------------------------


def test_posts_non_member_returns_404(client: TestClient, db: Session) -> None:
    owner, _ = create_user_with_headers(client, db)
    outsider, outsider_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)

    r = client.get(
        PREFIX + "/posts",
        headers=outsider_headers,
        params={"workspace_id": str(ws.id)},
    )
    assert r.status_code == 404


def test_posts_empty(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    r = client.get(
        PREFIX + "/posts",
        headers=headers,
        params={"workspace_id": str(ws.id)},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    assert body["data"] == []


def test_posts_returns_top_by_engagements(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws, platform=Platform.instagram)
    account = create_fake_account(db, integration)

    _add_post(db, account.id, external_id="post-1", engagements=10)
    _add_post(db, account.id, external_id="post-2", engagements=999)
    _add_post(db, account.id, external_id="post-3", engagements=50)

    r = client.get(
        PREFIX + "/posts",
        headers=headers,
        params={"workspace_id": str(ws.id)},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 3
    # Should be sorted by engagements desc
    assert body["data"][0]["engagements"] == 999


def test_posts_limit(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws, platform=Platform.instagram)
    account = create_fake_account(db, integration)

    for i in range(5):
        _add_post(db, account.id, external_id=f"post-{i}", engagements=i * 10)

    r = client.get(
        PREFIX + "/posts",
        headers=headers,
        params={"workspace_id": str(ws.id), "limit": 3},
    )
    assert r.status_code == 200
    assert r.json()["count"] == 3
