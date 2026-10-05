import json
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime

import httpx
import pytest

from app.migrate.sources.base import SourceAuthError, date_windows
from app.migrate.sources.metricool import Metricool
from app.migrate.sources.sprout_social import SproutSocial, native_post_id
from app.models.integration import Platform
from app.models.metrics import ContentType
from app.models.migration import RemoteProfile, SourceCredentials

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Skip the delays between requests."""
    monkeypatch.setattr("app.migrate.sources.base.time.sleep", lambda _: None)
    yield


def test_date_windows() -> None:
    assert date_windows(date(2024, 1, 1), date(2024, 3, 5), days=31) == [
        (date(2024, 1, 1), date(2024, 1, 31)),
        (date(2024, 2, 1), date(2024, 3, 2)),
        (date(2024, 3, 3), date(2024, 3, 5)),
    ]


# ---------------------------------------------------------------------------
# Sprout Social
# ---------------------------------------------------------------------------

SPROUT_CREDENTIALS = SourceCredentials(api_token="sprout-token")


def _sprout_handler(requests: list[httpx.Request]) -> Handler:
    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer sprout-token"
        path = request.url.path
        if path == "/v1/metadata/client":
            return httpx.Response(200, json={"data": [{"customer_id": 42}]})
        if path == "/v1/42/metadata/customer":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "customer_profile_id": 7,
                            "network_type": "facebook",
                            "name": "Acme",
                            "native_id": "1234",
                        },
                        {
                            "customer_profile_id": 8,
                            "network_type": "youtube",
                            "name": "Acme TV",
                            "native_id": "UC1",
                        },
                    ]
                },
            )
        body = json.loads(request.content)
        if path == "/v1/42/analytics/profiles":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "dimensions": {
                                "reporting_period.by(day)": "2024-01-01",
                                "customer_profile_id": 7,
                            },
                            "metrics": {
                                "lifetime_snapshot.followers_count": 1000,
                                "followers_gained": 12,
                                "impressions": 500,
                                "reactions": 40,
                                "comments_count": 5,
                                "shares_count": 3,
                                "posts_sent_count": 1,
                            },
                        }
                    ],
                    "paging": {"current_page": 1, "total_pages": 1},
                },
            )
        if path == "/v1/42/analytics/posts":
            page = body["page"]
            posts = {
                1: {
                    "guid": "fbpo:1234_1",
                    "created_time": "2024-01-01T10:00:00Z",
                    "perma_link": "https://facebook.com/1234_1",
                    "text": "Hello",
                    "post_type": "FACEBOOK_POST",
                    "metrics": {
                        "lifetime.impressions": 300,
                        "lifetime.reactions": 20,
                        "lifetime.comments_count": 2,
                        "lifetime.shares_count": 1,
                        "lifetime.post_link_clicks": 9,
                    },
                },
                2: {
                    "guid": "fbpo:1234_2",
                    "created_time": "2024-01-02T10:00:00Z",
                    "post_type": "FACEBOOK_REEL",
                    "metrics": {"lifetime.video_views": 800},
                },
            }
            in_january = (
                "2024-01-01T00:00:00..2024-01-31T23:59:59" in body["filters"][1]
            )
            return httpx.Response(
                200,
                json={
                    "data": [posts[page]] if in_january else [],
                    "paging": {
                        "current_page": page,
                        "total_pages": 2 if in_january else 1,
                    },
                },
            )
        return httpx.Response(404)

    return handle


def test_sprout_social_list_profiles() -> None:
    requests: list[httpx.Request] = []
    source = SproutSocial(httpx.MockTransport(_sprout_handler(requests)))
    facebook, youtube = source.list_profiles(SPROUT_CREDENTIALS)
    assert facebook.id == "42:7"
    assert facebook.platform is Platform.facebook
    assert facebook.native_id == "1234"
    assert youtube.platform is None


def test_sprout_social_fetch() -> None:
    requests: list[httpx.Request] = []
    source = SproutSocial(httpx.MockTransport(_sprout_handler(requests)))
    profile = RemoteProfile(
        id="42:7", name="Acme", network="facebook", platform=Platform.facebook
    )
    data = source.fetch(
        SPROUT_CREDENTIALS, profile, date(2024, 1, 1), date(2024, 2, 15)
    )

    assert data.errors == []
    [snapshot] = data.snapshots
    assert snapshot.date == date(2024, 1, 1)
    assert snapshot.followers_count == 1000
    assert snapshot.followers_gained == 12
    assert snapshot.likes == 40
    assert snapshot.engagements == 48
    assert snapshot.posts_count == 1

    first, second = data.posts
    assert first.external_id == "1234_1"  # merges with Prism's own sync
    assert first.published_at == datetime(2024, 1, 1, 10, tzinfo=UTC)
    assert first.engagements == 23
    assert first.clicks == 9
    assert second.content_type is ContentType.reel
    assert second.views == 800

    profile_request = next(r for r in requests if r.url.path.endswith("/profiles"))
    body = json.loads(profile_request.content)
    assert body["filters"] == [
        "customer_profile_id.eq(7)",
        "reporting_period.in(2024-01-01...2024-02-15)",
    ]
    assert "lifetime_snapshot.followers_count" in body["metrics"]


def test_sprout_social_rejected_token() -> None:
    source = SproutSocial(httpx.MockTransport(lambda _: httpx.Response(401)))
    with pytest.raises(SourceAuthError):
        source.list_profiles(SPROUT_CREDENTIALS)


def test_sprout_social_retries_rate_limits() -> None:
    calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "1"})
        return httpx.Response(200, json={"data": []})

    assert (
        SproutSocial(httpx.MockTransport(handle)).list_profiles(SPROUT_CREDENTIALS)
        == []
    )
    assert len(calls) == 2


def test_sprout_social_errors_are_kept_per_part() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/profiles"):
            return httpx.Response(400, json={"error": "bad metric"})
        return httpx.Response(200, json={"data": [], "paging": {"total_pages": 1}})

    profile = RemoteProfile(
        id="42:7", name="Acme", network="facebook", platform=Platform.facebook
    )
    data = SproutSocial(httpx.MockTransport(handle)).fetch(
        SPROUT_CREDENTIALS, profile, date(2024, 1, 1), date(2024, 1, 10)
    )
    assert data.errors == [
        "Daily metrics 2024-01-01–2024-01-10: HTTP 400 from /v1/42/analytics/profiles"
    ]


def test_native_post_id() -> None:
    assert native_post_id("fbpo:123_456") == "123_456"
    assert native_post_id("789") == "789"


# ---------------------------------------------------------------------------
# Metricool
# ---------------------------------------------------------------------------

METRICOOL_CREDENTIALS = SourceCredentials(api_token="mc-token", user_id="99")


def _metricool_handler(requests: list[httpx.Request]) -> Handler:
    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["X-Mc-Auth"] == "mc-token"
        assert request.url.params["userId"] == "99"
        path = request.url.path
        if path == "/api/admin/simpleProfiles":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 555,
                        "label": "Acme",
                        "facebook": "Acme page",
                        "facebookPageId": "1234",
                        "instagram": "acme",
                        "twitter": "",
                    }
                ],
            )
        if path == "/api/v2/analytics/posts/instagram":
            assert request.url.params["blogId"] == "555"
            if not request.url.params["from"].startswith("2024-01-01"):
                return httpx.Response(200, json={"data": []})
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "postId": "ig-1",
                            "type": "CAROUSEL_ALBUM",
                            "publishedAt": {
                                "dateTime": "2024-01-05T10:00:00",
                                "timezone": "Europe/Madrid",
                            },
                            "url": "https://instagram.com/p/1",
                            "content": "Hi",
                            "likes": 30,
                            "comments": 4,
                            "saved": 2,
                            "shares": 1,
                            "reach": 700,
                            "impressionsTotal": 900,
                        }
                    ]
                },
            )
        if path == "/api/v2/analytics/reels/instagram":
            # Some endpoints answer with a CSV download
            csv = (
                "Date;Url;Content;Likes;Comments;Views\n"
                "2024-01-06 12:00;https://instagram.com/reel/2;Reel;50;5;2000\n"
            )
            if not request.url.params["from"].startswith("2024-01-01"):
                csv = csv.splitlines()[0] + "\n"
            return httpx.Response(200, text=csv, headers={"content-type": "text/csv"})
        if path == "/api/v2/analytics/timelines":
            assert request.url.params["subject"] == "account"
            values = {
                "followers_gained": [
                    {"dateTime": "2024-01-01T00:00:00+01:00", "value": 10},
                    {"dateTime": "2024-01-02T00:00:00+01:00", "value": 4},
                ],
                "followers_lost": [
                    {"dateTime": "2024-01-01T00:00:00+01:00", "value": 2}
                ],
            }.get(request.url.params["metric"], [])
            if not request.url.params["from"].startswith("2024-01-01"):
                values = []
            return httpx.Response(
                200,
                json={
                    "data": [{"metric": request.url.params["metric"], "values": values}]
                },
            )
        return httpx.Response(404)

    return handle


def test_metricool_list_profiles() -> None:
    requests: list[httpx.Request] = []
    source = Metricool(httpx.MockTransport(_metricool_handler(requests)))
    facebook, instagram = source.list_profiles(METRICOOL_CREDENTIALS)
    assert (facebook.id, facebook.platform, facebook.native_id) == (
        "555:facebook",
        Platform.facebook,
        "1234",
    )
    assert instagram.name == "Acme · acme"
    assert instagram.platform is Platform.instagram


def test_metricool_requires_user_id() -> None:
    with pytest.raises(ValueError, match="user ID"):
        Metricool().list_profiles(SourceCredentials(api_token="mc-token"))


def test_metricool_fetch() -> None:
    requests: list[httpx.Request] = []
    source = Metricool(httpx.MockTransport(_metricool_handler(requests)))
    profile = RemoteProfile(
        id="555:instagram",
        name="Acme",
        network="instagram",
        platform=Platform.instagram,
    )
    data = source.fetch(
        METRICOOL_CREDENTIALS, profile, date(2024, 1, 1), date(2024, 2, 10)
    )

    assert data.errors == []
    post, reel = data.posts
    assert post.external_id == "ig-1"
    assert post.published_at == datetime(2024, 1, 5, 9, tzinfo=UTC)  # from Madrid
    assert post.content_type is ContentType.post
    assert post.impressions == 900
    assert post.reach == 700
    assert post.saves == 2
    assert post.engagements == 37
    assert reel.content_type is ContentType.reel
    assert reel.views == 2000

    first, second = data.snapshots
    assert (first.date, first.followers_gained, first.followers_lost) == (
        date(2024, 1, 1),
        10,
        2,
    )
    assert (second.date, second.followers_gained) == (date(2024, 1, 2), 4)
