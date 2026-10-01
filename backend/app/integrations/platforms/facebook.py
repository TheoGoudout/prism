"""
Facebook Pages sync.

For every Page the user manages:
  - the Page is stored as a PlatformAccount
  - daily Page insights become MetricSnapshots
  - the 100 most recent posts and their insights become Posts

Page-level calls use each Page's own token (from /me/accounts).

Metric names follow Meta's November 2025 Page Insights changes, which retired
the "impressions" and "page fans" metrics in favour of "media views" and
"follows": https://developers.facebook.com/docs/graph-api/reference/insights/
"""

import logging
import uuid
from typing import Any

import httpx
from sqlmodel import Session

from app import crud
from app.integrations.common import log_http_errors, parse_datetime, sum_known
from app.integrations.meta import daily_insights, first_value, graph_get
from app.models.integration import Integration
from app.models.metrics import ContentType, MetricSnapshotUpsert, PostUpsert

logger = logging.getLogger(__name__)

# Daily Page metric → MetricSnapshot field
_PAGE_METRIC_FIELDS = {
    "page_media_view": "views",
    "page_total_media_view_unique": "reach",
    "page_post_engagements": "engagements",
    "page_follows": "followers_count",
    "page_daily_follows_unique": "followers_gained",
    "page_daily_unfollows_unique": "followers_lost",
}

_POST_METRICS = ",".join(
    [
        "post_media_view",
        "post_total_media_view_unique",
        "post_reactions_like_total",
        "post_clicks",
    ]
)

# Comment and share counts come from the post object itself
_POST_FIELDS = (
    "id,message,created_time,permalink_url,full_picture,"
    "shares,comments.limit(0).summary(true)"
)


def _fetch_managed_pages(user_token: str) -> list[dict[str, Any]]:
    data = graph_get(
        "me/accounts", user_token, {"fields": "id,name,access_token,picture"}
    )
    pages: list[dict[str, Any]] = data.get("data", [])
    return pages


def _sync_page_insights(
    session: Session, platform_account_id: uuid.UUID, page_id: str, page_token: str
) -> None:
    for day, values in daily_insights(
        page_id, page_token, list(_PAGE_METRIC_FIELDS)
    ).items():
        fields = {
            field: values.get(metric) for metric, field in _PAGE_METRIC_FIELDS.items()
        }
        crud.upsert_metric_snapshot(
            session=session,
            platform_account_id=platform_account_id,
            snapshot_in=MetricSnapshotUpsert(date=day, raw_data=values, **fields),
        )


def _post_insights(post_id: str, page_token: str) -> dict[str, Any]:
    """{metric name: value}, or {} if Meta won't return insights for the post."""
    try:
        data = graph_get(f"{post_id}/insights", page_token, {"metric": _POST_METRICS})
    except httpx.HTTPStatusError as exc:
        logger.warning("Could not fetch insights for post %s: %s", post_id, exc)
        return {}
    return {entry["name"]: first_value(entry) for entry in data.get("data", [])}


def _sync_page_posts(
    session: Session, platform_account_id: uuid.UUID, page_id: str, page_token: str
) -> None:
    data = graph_get(
        f"{page_id}/posts", page_token, {"fields": _POST_FIELDS, "limit": 100}
    )
    for post in data.get("data", []):
        published_at = parse_datetime(post.get("created_time"))
        if published_at is None:
            logger.warning(
                "Skipping post %s: missing or invalid created_time", post["id"]
            )
            continue

        insights = _post_insights(post["id"], page_token)
        likes = insights.get("post_reactions_like_total")
        comments = post.get("comments", {}).get("summary", {}).get("total_count")
        shares = post.get("shares", {}).get("count")

        crud.upsert_post(
            session=session,
            platform_account_id=platform_account_id,
            post_in=PostUpsert(
                external_id=post["id"],
                published_at=published_at,
                content_type=ContentType.post,
                text=post.get("message"),
                media_url=post.get("full_picture"),
                permalink=post.get("permalink_url"),
                views=insights.get("post_media_view"),
                reach=insights.get("post_total_media_view_unique"),
                engagements=sum_known(likes, comments, shares),
                likes=likes,
                comments=comments,
                shares=shares,
                clicks=insights.get("post_clicks"),
                raw_data=insights or None,
            ),
        )


def sync_facebook(
    session: Session, integration: Integration, access_token: str
) -> None:
    """Sync every Facebook Page the connected user manages."""
    for page in _fetch_managed_pages(access_token):
        page_id: str = page["id"]
        page_token: str = page.get("access_token", access_token)
        account = crud.upsert_platform_account(
            session=session,
            integration=integration,
            external_id=page_id,
            name=page.get("name", page_id),
            avatar_url=page.get("picture", {}).get("data", {}).get("url"),
            account_type="page",
        )
        with log_http_errors(f"Facebook insights for page {page_id}"):
            _sync_page_insights(session, account.id, page_id, page_token)
        with log_http_errors(f"Facebook posts for page {page_id}"):
            _sync_page_posts(session, account.id, page_id, page_token)
