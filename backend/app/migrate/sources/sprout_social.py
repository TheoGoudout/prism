"""
Sprout Social, through its public API (https://api.sproutsocial.com/docs/).

The credentials are an API token, created in Sprout under Settings → Global
Features → API (plans with API access only). Each customer (account) has
profiles; for each we fetch:

  - daily profile metrics: POST /v1/{customer}/analytics/profiles, one
    request per year at most (the API's limit), 1000 days per page
  - posts with their lifetime metrics: POST /v1/{customer}/analytics/posts,
    month by month, 100 posts per page

Requests are spaced to stay under the limit of 60 per minute.
"""

from datetime import UTC, date, datetime
from typing import Any

import httpx

from app.integrations.common import engagement_total
from app.migrate.files.parser import guess_content_type
from app.migrate.sources.base import (
    ApiClient,
    ProfileData,
    date_windows,
    describe_error,
)
from app.models.integration import Platform
from app.models.metrics import MetricSnapshotUpsert, PostUpsert
from app.models.migration import RemoteProfile, SourceCredentials

API_URL = "https://api.sproutsocial.com"
PAGE_SIZE = 100

NETWORKS: dict[str, Platform] = {
    "facebook": Platform.facebook,
    "fb_instagram_account": Platform.instagram,
    "instagram": Platform.instagram,
    "linkedin": Platform.linkedin,
    "linkedin_company": Platform.linkedin,
    "tiktok": Platform.tiktok,
    "twitter": Platform.twitter,
}

# Profile metrics requested per network (the API rejects unknown ones), and
# the Prism field each fills. The first metric the API returns wins.
_FOLLOWERS = "lifetime_snapshot.followers_count"
PROFILE_METRICS: dict[Platform, list[str]] = {
    Platform.facebook: [
        _FOLLOWERS,
        "followers_gained",
        "followers_lost",
        "impressions",
        "impressions_unique",
        "reactions",
        "comments_count",
        "shares_count",
        "post_link_clicks",
        "video_views",
        "posts_sent_count",
    ],
    Platform.instagram: [
        _FOLLOWERS,
        "followers_gained",
        "followers_lost",
        "impressions",
        "impressions_unique",
        "views",
        "video_views",
        "likes",
        "comments_count",
        "saves",
        "shares_count",
        "posts_sent_count",
    ],
    Platform.linkedin: [
        _FOLLOWERS,
        "followers_gained",
        "followers_lost",
        "impressions",
        "impressions_unique",
        "reactions",
        "comments_count",
        "shares_count",
        "post_content_clicks",
        "posts_sent_count",
    ],
    Platform.tiktok: [
        _FOLLOWERS,
        "video_views_total",
        "likes_total",
        "comments_count_total",
        "shares_count_total",
        "posts_sent_count",
    ],
    Platform.twitter: [
        _FOLLOWERS,
        "impressions",
        "video_views",
        "likes",
        "comments_count",
        "shares_count",
        "post_link_clicks",
        "posts_sent_count",
    ],
}
PROFILE_FIELDS: dict[str, tuple[str, ...]] = {
    "followers_count": (_FOLLOWERS,),
    "followers_gained": ("followers_gained",),
    "followers_lost": ("followers_lost",),
    "impressions": ("impressions",),
    "reach": ("impressions_unique",),
    "views": ("views", "video_views", "video_views_total"),
    "likes": ("likes", "reactions", "likes_total"),
    "comments": ("comments_count", "comments_count_total"),
    "shares": ("shares_count", "shares_count_total"),
    "saves": ("saves",),
    "clicks": ("post_link_clicks", "post_content_clicks"),
    "posts_count": ("posts_sent_count",),
}

POST_METRICS: dict[Platform, list[str]] = {
    Platform.facebook: [
        "lifetime.impressions",
        "lifetime.impressions_unique",
        "lifetime.reactions",
        "lifetime.comments_count",
        "lifetime.shares_count",
        "lifetime.post_link_clicks",
        "lifetime.video_views",
    ],
    Platform.instagram: [
        "lifetime.impressions",
        "lifetime.impressions_unique",
        "lifetime.views",
        "lifetime.video_views",
        "lifetime.likes",
        "lifetime.comments_count",
        "lifetime.shares_count",
        "lifetime.saves",
    ],
    Platform.linkedin: [
        "lifetime.impressions",
        "lifetime.impressions_unique",
        "lifetime.reactions",
        "lifetime.comments_count",
        "lifetime.shares_count",
        "lifetime.post_content_clicks",
        "lifetime.video_views",
    ],
    Platform.tiktok: [
        "lifetime.impressions_unique",
        "lifetime.video_views",
        "lifetime.likes",
        "lifetime.comments_count",
        "lifetime.shares_count",
    ],
    Platform.twitter: [
        "lifetime.impressions",
        "lifetime.video_views",
        "lifetime.likes",
        "lifetime.comments_count",
        "lifetime.shares_count",
        "lifetime.post_link_clicks",
    ],
}
POST_FIELDS = ["guid", "created_time", "perma_link", "text", "post_type"]


class SproutSocial:
    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def _client(self, credentials: SourceCredentials) -> ApiClient:
        return ApiClient(
            API_URL,
            {"Authorization": f"Bearer {credentials.api_token}"},
            min_interval=1.0,
            transport=self._transport,
        )

    def list_profiles(self, credentials: SourceCredentials) -> list[RemoteProfile]:
        client = self._client(credentials)
        profiles = []
        for customer in client.json("GET", "/v1/metadata/client").get("data", []):
            customer_id = customer["customer_id"]
            data = client.json("GET", f"/v1/{customer_id}/metadata/customer")
            for item in data.get("data", []):
                network = str(item.get("network_type", ""))
                profiles.append(
                    RemoteProfile(
                        id=f"{customer_id}:{item['customer_profile_id']}",
                        name=item.get("name") or str(item["customer_profile_id"]),
                        network=network,
                        platform=NETWORKS.get(network),
                        native_id=_str_or_none(item.get("native_id")),
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
        assert profile.platform is not None  # only supported networks are fetched
        client = self._client(credentials)
        customer_id, profile_id = profile.id.split(":", 1)
        result = ProfileData()

        for start, end in date_windows(date_from, date_to, days=365):
            try:
                result.snapshots += _profile_metrics(
                    client, customer_id, profile_id, profile.platform, start, end
                )
            except httpx.HTTPError as exc:
                result.errors.append(
                    f"Daily metrics {start}–{end}: {describe_error(exc)}"
                )

        for start, end in date_windows(date_from, date_to, days=31):
            try:
                result.posts += _posts(
                    client, customer_id, profile_id, profile.platform, start, end
                )
            except httpx.HTTPError as exc:
                result.errors.append(f"Posts {start}–{end}: {describe_error(exc)}")
        return result


def _pages(client: ApiClient, url: str, body: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        data = client.json("POST", url, json={**body, "page": page})
        items += data.get("data") or []
        paging = data.get("paging") or {}
        if page >= int(paging.get("total_pages") or 1):
            return items
        page += 1


def _profile_metrics(
    client: ApiClient,
    customer_id: str,
    profile_id: str,
    platform: Platform,
    start: date,
    end: date,
) -> list[MetricSnapshotUpsert]:
    rows = _pages(
        client,
        f"/v1/{customer_id}/analytics/profiles",
        {
            "filters": [
                f"customer_profile_id.eq({profile_id})",
                f"reporting_period.in({start.isoformat()}...{end.isoformat()})",
            ],
            "metrics": PROFILE_METRICS[platform],
        },
    )
    snapshots = []
    for row in rows:
        day = (row.get("dimensions") or {}).get("reporting_period.by(day)")
        if not day:
            continue
        metrics = row.get("metrics") or {}
        values: dict[str, Any] = {
            name: _first_int(metrics, keys) for name, keys in PROFILE_FIELDS.items()
        }
        snapshots.append(
            MetricSnapshotUpsert(
                date=date.fromisoformat(str(day)[:10]),
                engagements=engagement_total(
                    values["likes"],
                    values["comments"],
                    values["shares"],
                    values["saves"],
                ),
                **values,
            )
        )
    return snapshots


def _posts(
    client: ApiClient,
    customer_id: str,
    profile_id: str,
    platform: Platform,
    start: date,
    end: date,
) -> list[PostUpsert]:
    rows = _pages(
        client,
        f"/v1/{customer_id}/analytics/posts",
        {
            "fields": POST_FIELDS,
            "filters": [
                f"customer_profile_id.eq({profile_id})",
                f"created_time.in({start.isoformat()}T00:00:00..{end.isoformat()}T23:59:59)",
            ],
            "metrics": POST_METRICS[platform],
            "timezone": "UTC",
            "limit": PAGE_SIZE,
        },
    )
    posts = []
    for row in rows:
        if not row.get("guid") or not row.get("created_time"):
            continue
        metrics = row.get("metrics") or {}
        likes = _first_int(metrics, ("lifetime.likes", "lifetime.reactions"))
        comments = _first_int(metrics, ("lifetime.comments_count",))
        shares = _first_int(metrics, ("lifetime.shares_count",))
        saves = _first_int(metrics, ("lifetime.saves",))
        permalink = _str_or_none(row.get("perma_link"))
        posts.append(
            PostUpsert(
                external_id=native_post_id(str(row["guid"])),
                content_type=guess_content_type(
                    str(row.get("post_type", "")), platform
                ),
                text=_str_or_none(row.get("text")),
                permalink=permalink[:2048] if permalink else None,
                published_at=_utc(str(row["created_time"])),
                impressions=_first_int(metrics, ("lifetime.impressions",)),
                reach=_first_int(metrics, ("lifetime.impressions_unique",)),
                views=_first_int(metrics, ("lifetime.views", "lifetime.video_views")),
                likes=likes,
                comments=comments,
                shares=shares,
                saves=saves,
                clicks=_first_int(
                    metrics,
                    ("lifetime.post_link_clicks", "lifetime.post_content_clicks"),
                ),
                engagements=engagement_total(likes, comments, shares, saves),
            )
        )
    return posts


def native_post_id(guid: str) -> str:
    """
    Sprout prefixes the network's post ID with a code ("fbpo:123_456"); without
    it, the post merges with the one Prism's own sync stores.
    """
    return guid.split(":", 1)[1] if ":" in guid else guid


def _first_int(metrics: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = metrics.get(key)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return round(value)
    return None


def _str_or_none(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def _utc(value: str) -> datetime:
    moment = datetime.fromisoformat(value)
    return (
        moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)
    )
