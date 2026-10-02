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
    followers_count: int | None = 500,
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
    published_on: date = TODAY,
    engagements: int = 50,
    **metrics: int,
) -> None:
    crud.upsert_post(
        session=db,
        platform_account_id=account_id,
        post_in=PostUpsert(
            external_id=external_id,
            published_at=f"{published_on}T12:00:00+00:00",
            content_type=ContentType.post,
            engagements=engagements,
            **metrics,
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
    # Nothing reported: unknown, not zero
    assert body["totals"]["impressions"] is None
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


def test_summary_counts_posts_of_platforms_without_daily_metrics(
    client: TestClient, db: Session
) -> None:
    """Twitter only reports followers daily: its engagement comes from posts."""
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws, platform=Platform.twitter)
    account = create_fake_account(db, integration)

    crud.upsert_metric_snapshot(
        session=db,
        platform_account_id=account.id,
        snapshot_in=MetricSnapshotUpsert(date=TODAY, followers_count=300),
    )
    _add_post(db, account.id, external_id="t1", engagements=40, impressions=1000)
    _add_post(db, account.id, external_id="t2", engagements=10, impressions=500)

    r = client.get(_url(ws, "summary"), headers=headers)
    assert r.status_code == 200
    twitter = r.json()["by_platform"]["twitter"]
    assert twitter["engagements"] == 50
    assert twitter["impressions"] == 1500
    # No views on Twitter: impressions are its exposures
    assert twitter["exposures"] == 1500
    assert twitter["engagement_rate"] == round(50 / 1500, 6)
    assert twitter["followers_count"] == 300


def test_summary_prefers_daily_metrics_over_posts(
    client: TestClient, db: Session
) -> None:
    """A field the daily snapshots report isn't counted again from posts."""
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws, platform=Platform.facebook)
    account = create_fake_account(db, integration)

    crud.upsert_metric_snapshot(
        session=db,
        platform_account_id=account.id,
        snapshot_in=MetricSnapshotUpsert(date=TODAY, views=2000, reach=800),
    )
    _add_post(db, account.id, engagements=30, views=900, reach=600, likes=25)

    r = client.get(_url(ws, "summary"), headers=headers)
    totals = r.json()["totals"]
    assert totals["views"] == 2000
    assert totals["reach"] == 800
    # Not reported daily, so taken from the posts
    assert totals["engagements"] == 30
    assert totals["likes"] == 25
    assert totals["exposures"] == 2000


def test_summary_engagement_rate_across_platforms(
    client: TestClient, db: Session
) -> None:
    """
    Exposures add views and impressions-only platforms together; engagements
    of accounts without exposures stay out of the rate.
    """
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    accounts = {}
    for platform in (Platform.instagram, Platform.twitter, Platform.linkedin):
        integration = create_fake_integration(
            db, ws, platform=platform, external_account_id=platform.value
        )
        accounts[platform] = create_fake_account(
            db, integration, external_id=platform.value
        )

    _add_post(db, accounts[Platform.instagram].id, engagements=60, views=1000)
    _add_post(db, accounts[Platform.twitter].id, engagements=20, impressions=1000)
    _add_post(db, accounts[Platform.linkedin].id, engagements=100)

    r = client.get(_url(ws, "summary"), headers=headers)
    totals = r.json()["totals"]
    assert totals["exposures"] == 2000
    assert totals["engagements"] == 180
    assert totals["engagement_rate"] == round(80 / 2000, 6)
    assert r.json()["by_platform"]["linkedin"]["engagement_rate"] is None
    # Platforms that don't report a metric show it as unknown, not zero
    assert r.json()["by_platform"]["twitter"]["reach"] is None


def _add_followers(db: Session, account_id: uuid.UUID, counts: dict[date, int]) -> None:
    for day, count in counts.items():
        crud.upsert_metric_snapshot(
            session=db,
            platform_account_id=account_id,
            snapshot_in=MetricSnapshotUpsert(date=day, followers_count=count),
        )


def test_summary_follower_growth(client: TestClient, db: Session) -> None:
    """Growth is the latest count minus the first, for every social platform."""
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    accounts = {}
    for platform in (Platform.tiktok, Platform.linkedin, Platform.twitter):
        integration = create_fake_integration(
            db, ws, platform=platform, external_account_id=platform.value
        )
        accounts[platform] = create_fake_account(
            db, integration, external_id=platform.value
        )
    two_days_ago = TODAY - timedelta(days=2)
    _add_followers(db, accounts[Platform.tiktok].id, {two_days_ago: 1000, TODAY: 1100})
    _add_followers(db, accounts[Platform.linkedin].id, {YESTERDAY: 500, TODAY: 450})
    # A single count: the total is known, the growth isn't
    _add_followers(db, accounts[Platform.twitter].id, {TODAY: 300})

    r = client.get(
        _url(ws, "summary"),
        headers=headers,
        params={"date_from": str(two_days_ago), "date_to": str(TODAY)},
    )
    body = r.json()
    assert body["totals"]["followers_count"] == 1100 + 450 + 300
    assert body["totals"]["followers_growth"] == 100 - 50
    assert body["totals"]["followers_growth_rate"] == round(50 / 1500, 6)
    assert body["by_platform"]["tiktok"]["followers_growth"] == 100
    assert body["by_platform"]["tiktok"]["followers_growth_rate"] == 0.1
    assert body["by_platform"]["linkedin"]["followers_growth"] == -50
    assert body["by_platform"]["twitter"]["followers_count"] == 300
    assert body["by_platform"]["twitter"]["followers_growth"] is None


# ---------------------------------------------------------------------------
# /followers
# ---------------------------------------------------------------------------


def test_followers_per_platform_and_day(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    ig_int = create_fake_integration(db, ws, platform=Platform.instagram)
    ga_int = create_fake_integration(
        db, ws, platform=Platform.google_analytics, external_account_id="ga"
    )
    ig = create_fake_account(db, ig_int, external_id="ig")
    ga = create_fake_account(db, ga_int, external_id="ga")
    three_days_ago = TODAY - timedelta(days=3)
    # No count two days ago (no sync): yesterday's carries the day before over
    _add_followers(db, ig.id, {three_days_ago: 800, YESTERDAY: 820, TODAY: 830})
    _add_snapshot(db, ga.id, followers_count=None)

    r = client.get(
        _url(ws, "followers"),
        headers=headers,
        params={
            "date_from": str(three_days_ago - timedelta(days=1)),
            "date_to": str(TODAY),
        },
    )
    assert r.status_code == 200
    # Google Analytics has no followers
    assert [series["platform"] for series in r.json()] == ["instagram"]
    assert [p["followers"] for p in r.json()[0]["points"]] == [800, 800, 820, 830]


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


def test_timeseries_counts_posts_on_their_publication_day(
    client: TestClient, db: Session
) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    integration = create_fake_integration(db, ws, platform=Platform.tiktok)
    account = create_fake_account(db, integration)

    _add_post(db, account.id, external_id="v1", engagements=7, views=100)
    _add_post(
        db,
        account.id,
        external_id="v2",
        published_on=YESTERDAY,
        engagements=3,
        views=50,
    )

    r = client.get(
        _url(ws, "timeseries"),
        headers=headers,
        params={"date_from": str(YESTERDAY), "date_to": str(TODAY)},
    )
    assert r.status_code == 200
    assert [(p["exposures"], p["engagements"]) for p in r.json()] == [
        (50, 3),
        (100, 7),
    ]


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
    assert body[0]["platform"] == "instagram"


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
