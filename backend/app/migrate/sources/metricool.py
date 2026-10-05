"""
Metricool, through its API (https://app.metricool.com/resources/apidocs/).

The credentials are the user token (Account settings → API, sent as the
X-Mc-Auth header) and the user ID; both, with a brand's blogId, appear in
Metricool's URLs. Advanced plans only. Every brand (blog) has at most one
account per network; for each we fetch:

  - posts: GET /v2/analytics/posts/{network} (and reels for Instagram and
    Facebook), month by month. Some networks answer in CSV rather than
    JSON; those go through the CSV export parser.
  - daily account metrics: GET /v2/analytics/timelines, one metric at a time
"""

from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from app.integrations.common import engagement_total
from app.migrate.files.parser import guess_content_type, parse_export
from app.migrate.files.reading import ImportFileError
from app.migrate.sources.base import (
    ApiClient,
    ProfileData,
    date_windows,
    describe_error,
)
from app.models.integration import Platform
from app.models.metrics import ContentType, MetricSnapshotUpsert, PostUpsert
from app.models.migration import ExportFormat, RemoteProfile, SourceCredentials

API_URL = "https://app.metricool.com/api"

# Network → (brand field with the account's handle or name, Prism platform)
NETWORKS: dict[str, tuple[str, Platform]] = {
    "facebook": ("facebook", Platform.facebook),
    "instagram": ("instagram", Platform.instagram),
    "linkedin": ("linkedinCompany", Platform.linkedin),
    "tiktok": ("tiktok", Platform.tiktok),
    "twitter": ("twitter", Platform.twitter),
}

# Post list endpoints per network, with the content type of what they list
POST_ENDPOINTS: dict[str, list[tuple[str, ContentType | None]]] = {
    "facebook": [
        ("/v2/analytics/posts/facebook", None),
        ("/v2/analytics/reels/facebook", ContentType.reel),
    ],
    "instagram": [
        ("/v2/analytics/posts/instagram", None),
        ("/v2/analytics/reels/instagram", ContentType.reel),
    ],
    "linkedin": [("/v2/analytics/posts/linkedin", None)],
    "tiktok": [("/v2/analytics/posts/tiktok", ContentType.video)],
    "twitter": [("/v2/analytics/posts/twitter", ContentType.tweet)],
}

# Timeline metrics per network (as documented for /v2/analytics/timelines),
# and the Prism field each fills
TIMELINE_METRICS: dict[str, dict[str, str]] = {
    "facebook": {
        "pageFollows": "followers_count",
        "page_daily_follows_unique": "followers_gained",
        "page_daily_unfollows_unique": "followers_lost",
        "pageImpressions": "impressions",
        "postsCount": "posts_count",
    },
    "instagram": {
        "followers_gained": "followers_gained",
        "followers_lost": "followers_lost",
        "postsCount": "posts_count",
    },
    "linkedin": {
        "followers": "followers_count",
        "impressionCount": "impressions",
        "clickCount": "clicks",
        "likeCount": "likes",
        "commentCount": "comments",
        "shareCount": "shares",
        "postsCount": "posts_count",
    },
    "tiktok": {
        "followers_count": "followers_count",
        "video_views": "views",
        "likes": "likes",
        "comments": "comments",
        "shares": "shares",
    },
    "twitter": {"followers": "followers_count", "postsCount": "posts_count"},
}
# Instagram requires a subject; the other networks' account metrics have none
TIMELINE_SUBJECTS = {"instagram": "account"}

# The keys each network's post objects use for each field, first found wins
POST_KEYS: dict[str, tuple[str, ...]] = {
    "id": ("postId", "reelId", "videoId", "idStr", "tweetId", "id"),
    "published_at": ("publishedAt", "created", "createdAt", "createTime", "timestamp"),
    "text": ("content", "text", "fullText", "videoDescription", "description", "title"),
    "permalink": ("url", "link", "shareUrl"),
    "media_url": ("imageUrl", "picture", "coverImageUrl"),
    "type": ("type",),
    "impressions": ("impressionsTotal", "impressions"),
    "reach": ("reach", "impressionsUnique", "uniqueImpressions"),
    "views": ("views", "videoViewsTotal", "videoViews", "viewCount"),
    "likes": ("likes", "reactions", "likeCount", "favoriteCount", "favorites"),
    "comments": ("comments", "commentCount", "replies"),
    "shares": ("shares", "shareCount", "retweetCount", "retweets"),
    "saves": ("saved", "saves"),
    "clicks": ("clicks", "linkclicks", "linkClicks"),
}


class Metricool:
    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def _client(self, credentials: SourceCredentials) -> ApiClient:
        return ApiClient(
            API_URL,
            {"X-Mc-Auth": credentials.api_token},
            min_interval=0.2,
            transport=self._transport,
        )

    def list_profiles(self, credentials: SourceCredentials) -> list[RemoteProfile]:
        if not credentials.user_id:
            raise ValueError("Metricool needs your user ID as well as your token")
        client = self._client(credentials)
        params = {"userId": credentials.user_id}
        if credentials.blog_id:
            params["blogId"] = credentials.blog_id
        brands = client.json("GET", "/admin/simpleProfiles", params=params)
        profiles = []
        for brand in brands if isinstance(brands, list) else []:
            brand_name = brand.get("label") or brand.get("title") or str(brand["id"])
            for network, (handle_key, platform) in NETWORKS.items():
                handle = brand.get(handle_key)
                if not handle:
                    continue
                if network == "linkedin":
                    handle = brand.get("linkedInCompanyName") or handle
                native_id = (
                    brand.get("facebookPageId") if network == "facebook" else None
                )
                profiles.append(
                    RemoteProfile(
                        id=f"{brand['id']}:{network}",
                        name=f"{brand_name} · {handle}",
                        network=network,
                        platform=platform,
                        native_id=str(native_id) if native_id else None,
                    )
                )
        return profiles

    def fetch(
        self,
        credentials: SourceCredentials,
        profile: RemoteProfile,
        date_from: date,
        date_to: date,
    ) -> ProfileData:
        assert profile.platform is not None
        client = self._client(credentials)
        blog_id, network = profile.id.split(":", 1)
        params = {"userId": credentials.user_id, "blogId": blog_id}
        result = ProfileData()

        for start, end in date_windows(date_from, date_to, days=31):
            window = {**params, "from": f"{start}T00:00:00", "to": f"{end}T23:59:59"}
            for path, content_type in POST_ENDPOINTS[network]:
                try:
                    result.posts += _posts(
                        client, path, window, profile.platform, content_type
                    )
                except (httpx.HTTPError, ImportFileError) as exc:
                    result.errors.append(f"{path} {start}–{end}: {describe_error(exc)}")

        days: dict[date, dict[str, Any]] = defaultdict(dict)
        for start, end in date_windows(date_from, date_to, days=90):
            window = {**params, "from": f"{start}T00:00:00", "to": f"{end}T23:59:59"}
            for metric, field in TIMELINE_METRICS[network].items():
                try:
                    for day, value in _timeline(client, network, metric, window):
                        days[day][field] = value
                except httpx.HTTPError as exc:
                    result.errors.append(
                        f"{metric} {start}–{end}: {describe_error(exc)}"
                    )
        result.snapshots = [
            MetricSnapshotUpsert(
                date=day,
                engagements=engagement_total(
                    values.get("likes"), values.get("comments"), values.get("shares")
                ),
                **values,
            )
            for day, values in sorted(days.items())
        ]
        return result


def _posts(
    client: ApiClient,
    path: str,
    params: dict[str, Any],
    platform: Platform,
    content_type: ContentType | None,
) -> list[PostUpsert]:
    posts: list[PostUpsert] = []
    url: str | None = path
    while url:
        response = client.request(
            "GET", url, params=params, headers={"Accept": "application/json"}
        )
        if "json" not in response.headers.get("content-type", ""):
            # Documented as CSV downloads for some networks
            parsed = parse_export(
                response.content,
                platform=platform,
                export_format=ExportFormat.metricool,
            )
            if content_type is not None:
                return posts + [
                    p.model_copy(update={"content_type": content_type})
                    for p in parsed.posts
                ]
            return posts + parsed.posts
        data = response.json()
        items = data.get("data", []) if isinstance(data, dict) else data
        posts += [
            post
            for item in items or []
            if (post := _post(item, platform, content_type)) is not None
        ]
        url = (
            (data.get("page") or {}).get("next") if isinstance(data, dict) else None
        ) or None
        params = {}  # the next page's URL carries them
    return posts


def _post(
    item: dict[str, Any], platform: Platform, content_type: ContentType | None
) -> PostUpsert | None:
    def value(field: str) -> Any:
        for key in POST_KEYS[field]:
            if item.get(key) not in (None, ""):
                return item[key]
        return None

    def count(field: str) -> int | None:
        found = value(field)
        if isinstance(found, int | float) and not isinstance(found, bool):
            return round(found)
        return None

    post_id = value("id")
    published_at = _datetime(value("published_at"))
    if post_id is None or published_at is None:
        return None
    likes, comments = count("likes"), count("comments")
    shares, saves = count("shares"), count("saves")
    permalink, media_url = value("permalink"), value("media_url")
    return PostUpsert(
        external_id=str(post_id)[:255],
        content_type=content_type
        or guess_content_type(str(value("type") or ""), platform),
        text=str(value("text")) if value("text") else None,
        permalink=str(permalink)[:2048] if permalink else None,
        media_url=str(media_url)[:2048] if media_url else None,
        published_at=published_at,
        impressions=count("impressions"),
        reach=count("reach"),
        views=count("views"),
        likes=likes,
        comments=comments,
        shares=shares,
        saves=saves,
        clicks=count("clicks"),
        engagements=engagement_total(likes, comments, shares, saves),
    )


def _datetime(value: Any, zone: str = "UTC") -> datetime | None:
    """
    A Metricool date, in UTC: {"dateTime": local time, "timezone": "Europe/
    Madrid"}, an ISO string, or epoch seconds or milliseconds.
    """
    if isinstance(value, dict):
        return _datetime(value.get("dateTime"), value.get("timezone") or "UTC")
    if isinstance(value, int | float) and not isinstance(value, bool):
        seconds = value / 1000 if value > 100_000_000_000 else value
        return datetime.fromtimestamp(seconds, UTC)
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    if moment.tzinfo is None:
        try:
            moment = moment.replace(tzinfo=ZoneInfo(zone))
        except ZoneInfoNotFoundError, ValueError:
            moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _timeline(
    client: ApiClient, network: str, metric: str, params: dict[str, Any]
) -> list[tuple[date, int]]:
    query = {**params, "network": network, "metric": metric}
    if network in TIMELINE_SUBJECTS:
        query["subject"] = TIMELINE_SUBJECTS[network]
    data = client.json("GET", "/v2/analytics/timelines", params=query)
    points = []
    for series in (data.get("data") or []) if isinstance(data, dict) else []:
        for point in series.get("values") or []:
            moment, value = point.get("dateTime"), point.get("value")
            if isinstance(moment, str) and isinstance(value, int | float):
                points.append((date.fromisoformat(moment[:10]), round(value)))
    return points
