"""
Facebook Pages sync.

Fetches:
  - Managed pages  → upserted as PlatformAccounts
  - Page-level daily insights (impressions, reach, engagement, fan growth)
  - Post metrics for the 100 most recent posts per page

Uses the user long-lived access token stored in Integration.
Each page's own token (from /me/accounts) is used for page-specific Graph API
calls.

Metric names follow Meta's November 2025 Page Insights changes, which retired
the "impressions" and "page fans" metrics in favour of "media views" and
"follows": https://developers.facebook.com/docs/graph-api/reference/insights/
"""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from sqlmodel import Session

from app import crud
from app.integrations.meta import GRAPH_API
from app.models.integration import Integration, Platform, PlatformAccountCreate
from app.models.metrics import ContentType, MetricSnapshotUpsert, PostUpsert
from app.worker.tasks.sync import register_platform_sync

logger = logging.getLogger(__name__)

# Page-level daily metrics → MetricSnapshot field
_PAGE_METRIC_FIELDS = {
    "page_media_view": "views",
    "page_total_media_view_unique": "reach",
    "page_post_engagements": "engagements",
    "page_follows": "followers_count",
    "page_daily_follows_unique": "followers_gained",
    "page_daily_unfollows_unique": "followers_lost",
}
_PAGE_METRICS = ",".join(_PAGE_METRIC_FIELDS)

_POST_METRICS = ",".join(
    [
        "post_media_view",
        "post_total_media_view_unique",
        "post_reactions_like_total",
        "post_clicks",
    ]
)

# Post fields; comment and share counts come from the post object itself
_POST_FIELDS = (
    "id,message,created_time,permalink_url,full_picture,"
    "shares,comments.limit(0).summary(true)"
)


# ---------------------------------------------------------------------------
# Internal HTTP helper
# ---------------------------------------------------------------------------


def _get(path: str, token: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    p: dict[str, Any] = dict(params or {})
    p["access_token"] = token
    resp = httpx.get(f"{GRAPH_API}/{path}", params=p, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Page discovery
# ---------------------------------------------------------------------------


def _fetch_managed_pages(user_token: str) -> list[dict[str, Any]]:
    """Return the pages managed by the authenticated user."""
    data = _get("me/accounts", user_token, {"fields": "id,name,access_token,picture"})
    pages: list[dict[str, Any]] = data.get("data", [])
    return pages


# ---------------------------------------------------------------------------
# Page-level insights
# ---------------------------------------------------------------------------


def _sync_page_insights(
    session: Session,
    platform_account_id: Any,
    page_id: str,
    page_token: str,
) -> None:
    end = date.today()
    start = end - timedelta(days=30)
    params: dict[str, Any] = {
        "period": "day",
        "since": int(
            datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp()
        ),
        "until": int(
            datetime(end.year, end.month, end.day, tzinfo=timezone.utc).timestamp()
        ),
    }

    entries: list[dict[str, Any]]
    try:
        resp = _get(f"{page_id}/insights", page_token, {**params, "metric": _PAGE_METRICS})
        entries = resp.get("data", [])
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 400:
            raise
        # Meta rejects the whole request if any one metric is invalid (e.g.
        # newly deprecated, or not available for this Page). Fall back to one
        # request per metric so the others still sync.
        entries = []
        for metric in _PAGE_METRIC_FIELDS:
            try:
                single = _get(f"{page_id}/insights", page_token, {**params, "metric": metric})
                entries.extend(single.get("data", []))
            except httpx.HTTPStatusError as metric_exc:
                logger.warning(
                    "Page %s: metric %s unavailable: %s", page_id, metric, metric_exc
                )

    # Build date → {metric_name: value}
    by_date: dict[date, dict[str, Any]] = {}
    for entry in entries:
        metric_name: str = entry["name"]
        for val_item in entry.get("values", []):
            try:
                d = datetime.fromisoformat(
                    val_item["end_time"].replace("Z", "+00:00")
                ).date()
            except (KeyError, ValueError):
                continue
            by_date.setdefault(d, {})[metric_name] = val_item["value"]

    for d, vals in by_date.items():
        fields = {
            field: vals.get(metric) for metric, field in _PAGE_METRIC_FIELDS.items()
        }
        snapshot = MetricSnapshotUpsert(date=d, raw_data=vals, **fields)
        crud.upsert_metric_snapshot(
            session=session,
            platform_account_id=platform_account_id,
            snapshot_in=snapshot,
        )


# ---------------------------------------------------------------------------
# Post metrics
# ---------------------------------------------------------------------------


def _sync_page_posts(
    session: Session,
    platform_account_id: Any,
    page_id: str,
    page_token: str,
) -> None:
    resp = _get(
        f"{page_id}/posts",
        page_token,
        {"fields": _POST_FIELDS, "limit": 100},
    )

    for post_data in resp.get("data", []):
        post_id: str = post_data["id"]

        pvals: dict[str, Any] = {}
        try:
            insights_resp = _get(
                f"{post_id}/insights",
                page_token,
                {"metric": _POST_METRICS},
            )
            for entry in insights_resp.get("data", []):
                vals = entry.get("values", [])
                pvals[entry["name"]] = vals[0]["value"] if vals else None
        except httpx.HTTPStatusError as exc:
            logger.warning("Could not fetch insights for post %s: %s", post_id, exc)

        try:
            published_at = datetime.fromisoformat(
                post_data["created_time"].replace("Z", "+00:00")
            )
        except (KeyError, ValueError):
            logger.warning("Skipping post %s: missing or invalid created_time", post_id)
            continue

        likes = pvals.get("post_reactions_like_total")
        comments = ((post_data.get("comments") or {}).get("summary") or {}).get(
            "total_count"
        )
        shares = (post_data.get("shares") or {}).get("count")
        counted = [v for v in (likes, comments, shares) if isinstance(v, int)]
        engagements = sum(counted) if counted else None

        post = PostUpsert(
            external_id=post_id,
            published_at=published_at,
            content_type=ContentType.post,
            text=post_data.get("message"),
            media_url=post_data.get("full_picture"),
            permalink=post_data.get("permalink_url"),
            views=pvals.get("post_media_view"),
            reach=pvals.get("post_total_media_view_unique"),
            engagements=engagements,
            likes=likes,
            comments=comments,
            shares=shares,
            clicks=pvals.get("post_clicks"),
            raw_data=pvals or None,
        )
        crud.upsert_post(
            session=session,
            platform_account_id=platform_account_id,
            post_in=post,
        )


# ---------------------------------------------------------------------------
# Main entry-point
# ---------------------------------------------------------------------------


def sync_facebook(session: Session, integration: Integration) -> None:
    """Sync all Facebook Pages for this integration."""
    user_token = crud.get_access_token(integration)
    if not user_token:
        raise ValueError("No access token available for Facebook integration")

    pages = _fetch_managed_pages(user_token)
    if not pages:
        logger.info("sync_facebook: no managed pages for integration %s", integration.id)
        return

    for page in pages:
        page_id: str = page["id"]
        page_name: str = page.get("name", page_id)
        page_token: str = page.get("access_token", user_token)
        avatar_url: str | None = (page.get("picture") or {}).get("data", {}).get("url")

        account_in = PlatformAccountCreate(
            integration_id=integration.id,
            workspace_id=integration.workspace_id,
            platform=Platform.facebook,
            external_id=page_id,
            name=page_name,
            avatar_url=avatar_url,
            account_type="page",
        )
        account = crud.upsert_platform_account(session=session, account_in=account_in)

        try:
            _sync_page_insights(session, account.id, page_id, page_token)
        except httpx.HTTPStatusError as exc:
            logger.error("sync_facebook: insights error for page %s: %s", page_id, exc)

        try:
            _sync_page_posts(session, account.id, page_id, page_token)
        except httpx.HTTPStatusError as exc:
            logger.error("sync_facebook: posts error for page %s: %s", page_id, exc)


# Register with the Celery sync dispatcher (side-effect on import)
register_platform_sync(Platform.facebook.value, sync_facebook)
