"""Tests for GET /metrics/summary, /metrics/timeseries, /metrics/posts."""

import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session

from app import crud
from app.core.config import settings
from app.models.integration import Platform
from app.models.metrics import ContentType, MetricSnapshotUpsert, PostUpsert
from app.models.workspace import Workspace
from tests.utils.integration import create_fake_account, create_fake_integration
from tests.utils.user import create_user_with_headers
from tests.utils.workspace import create_random_workspace


def _url(workspace: Workspace, path: str) -> str:
    return f"{settings.API_V1_STR}/workspaces/{workspace.id}/metrics/{path}"


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
        _url(ws, "summary"),
        headers=outsider_headers,
    )
    assert r.status_code == 404


def test_summary_empty_workspace(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    r = client.get(
        _url(ws, "summary"),
        headers=headers,
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
        _url(ws, "summary"),
        headers=headers,
        params={
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
        _url(ws, "summary"),
        headers=headers,
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
        _url(ws, "summary"),
        headers=headers,
        params={"platform": "twitter"},
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
        _url(ws, "summary"),
        headers=headers,
        params={
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
        _url(ws, "timeseries"),
        headers=outsider_headers,
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
        _url(ws, "timeseries"),
        headers=headers,
        params={
            "date_from": str(date_from),
            "date_to": str(date_to),
        },
    )
    assert r.status_code == 200
    data = r.json()
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
        _url(ws, "timeseries"),
        headers=headers,
        params={
            "date_from": str(date_from),
            "date_to": str(TODAY),
        },
    )
    assert r.status_code == 200
    data = r.json()
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
        _url(ws, "timeseries"),
        headers=headers,
        params={
            "date_from": str(TODAY),
            "date_to": str(TODAY),
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data[0]["impressions"] == 150


# ---------------------------------------------------------------------------
# /posts
# ---------------------------------------------------------------------------


def test_posts_non_member_returns_404(client: TestClient, db: Session) -> None:
    owner, _ = create_user_with_headers(client, db)
    outsider, outsider_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)

    r = client.get(
        _url(ws, "posts"),
        headers=outsider_headers,
    )
    assert r.status_code == 404


def test_posts_empty(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    r = client.get(
        _url(ws, "posts"),
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body == []


def test_posts_returns_top_by_engagements(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws, platform=Platform.instagram)
    account = create_fake_account(db, integration)

    _add_post(db, account.id, external_id="post-1", engagements=10)
    _add_post(db, account.id, external_id="post-2", engagements=999)
    _add_post(db, account.id, external_id="post-3", engagements=50)

    r = client.get(
        _url(ws, "posts"),
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 3
    # Should be sorted by engagements desc
    assert body[0]["engagements"] == 999


def test_posts_limit(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws, platform=Platform.instagram)
    account = create_fake_account(db, integration)

    for i in range(5):
        _add_post(db, account.id, external_id=f"post-{i}", engagements=i * 10)

    r = client.get(
        _url(ws, "posts"),
        headers=headers,
        params={"limit": 3},
    )
    assert r.status_code == 200
    assert len(r.json()) == 3


# ---------------------------------------------------------------------------
# /posts/performance
# ---------------------------------------------------------------------------


def _add_dated_post(
    db: Session,
    account_id: uuid.UUID,
    *,
    external_id: str,
    days_ago: int,
    engagements: int,
    likes: int | None = None,
) -> None:
    crud.upsert_post(
        session=db,
        platform_account_id=account_id,
        post_in=PostUpsert(
            external_id=external_id,
            published_at=f"{TODAY - timedelta(days=days_ago)}T12:00:00+00:00",
            content_type=ContentType.post,
            engagements=engagements,
            likes=likes,
        ),
    )


def test_post_performance_non_member_returns_404(
    client: TestClient, db: Session
) -> None:
    owner, _ = create_user_with_headers(client, db)
    _, outsider_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)

    r = client.get(_url(ws, "posts/performance"), headers=outsider_headers)
    assert r.status_code == 404


def test_post_performance_empty(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws, platform=Platform.google_analytics)
    create_fake_account(db, integration)

    r = client.get(_url(ws, "posts/performance"), headers=headers)
    assert r.status_code == 200
    assert r.json() == []


def test_post_performance_benchmarks_and_ranks(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws, platform=Platform.twitter)
    account = create_fake_account(db, integration)

    # 21 posts, one per day: engagements 0, 10, …, 200 (newest has the most).
    # Only 3 report likes, too few to benchmark.
    for i in range(21):
        _add_dated_post(
            db,
            account.id,
            external_id=f"tw-{i}",
            days_ago=20 - i,
            engagements=i * 10,
            likes=i if i < 3 else None,
        )

    r = client.get(_url(ws, "posts/performance"), headers=headers, params={"limit": 3})
    assert r.status_code == 200
    [report] = r.json()
    assert report["platform"] == "twitter"
    assert report["history_size"] == 21
    assert len(report["history"]) == 21
    # History is oldest first, for plotting
    assert report["history"][0]["engagements"] == 0

    benchmark = report["benchmarks"]["engagements"]
    assert benchmark["sample_size"] == 21
    assert benchmark["p5"] == 10
    assert benchmark["p50"] == 100
    assert benchmark["p95"] == 190
    assert "likes" not in report["benchmarks"]

    # Latest posts come newest first, ranked against the whole history
    posts = report["posts"]
    assert [p["external_id"] for p in posts] == ["tw-20", "tw-19", "tw-18"]
    assert posts[0]["percentile_ranks"] == {"engagements": 97.6}
    assert posts[2]["percentile_ranks"]["engagements"] == 88.1


def test_post_performance_benchmarks_each_platform_separately(
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

    for i in range(5):
        _add_dated_post(db, fb_acc.id, external_id=f"fb-{i}", days_ago=i, engagements=1)
        _add_dated_post(
            db, ig_acc.id, external_id=f"ig-{i}", days_ago=i, engagements=1000
        )

    r = client.get(_url(ws, "posts/performance"), headers=headers)
    assert r.status_code == 200
    reports = {report["platform"]: report for report in r.json()}
    assert reports["facebook"]["benchmarks"]["engagements"]["p95"] == 1
    assert reports["instagram"]["benchmarks"]["engagements"]["p5"] == 1000

    r = client.get(
        _url(ws, "posts/performance"),
        headers=headers,
        params={"platform": "instagram"},
    )
    assert [report["platform"] for report in r.json()] == ["instagram"]


def test_post_performance_history_window(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws, platform=Platform.linkedin)
    account = create_fake_account(db, integration)

    _add_dated_post(db, account.id, external_id="old", days_ago=60, engagements=5)
    _add_dated_post(db, account.id, external_id="new", days_ago=1, engagements=5)

    r = client.get(
        _url(ws, "posts/performance"),
        headers=headers,
        params={"history_days": 30},
    )
    assert r.status_code == 200
    [report] = r.json()
    assert report["history_size"] == 1
    assert report["history_from"] == str(TODAY - timedelta(days=29))
    # Too few posts to benchmark
    assert report["benchmarks"] == {}
    assert report["posts"][0]["percentile_ranks"] == {}
