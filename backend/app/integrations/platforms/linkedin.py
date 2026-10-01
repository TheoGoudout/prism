"""
LinkedIn Company Page sync (Marketing API v2).

Fetches:
  - Company pages administered by the authenticated user → PlatformAccounts
  - Page follower statistics (snapshotted daily)
  - Organic share statistics for the 20 most recent posts (last 30 days)

Uses the LinkedIn REST API v2 with the Bearer token from the Integration.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlmodel import Session

from app import crud
from app.models.integration import Integration, Platform, PlatformAccountCreate
from app.models.metrics import ContentType, MetricSnapshotUpsert, PostUpsert
from app.worker.tasks.sync import register_platform_sync

logger = logging.getLogger(__name__)

LI_API = "https://api.linkedin.com/v2"


# ---------------------------------------------------------------------------
# Internal HTTP helper
# ---------------------------------------------------------------------------


def _get(path: str, token: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    resp = httpx.get(
        f"{LI_API}/{path}",
        params=params or {},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Restli-Protocol-Version": "2.0.0",
        },
        timeout=15,
    )
    resp.raise_for_status()
    result: dict[str, Any] = resp.json()
    return result


# ---------------------------------------------------------------------------
# Company page discovery
# ---------------------------------------------------------------------------


def _fetch_admin_organizations(token: str) -> list[dict[str, Any]]:
    """
    Return company pages where the user has ADMINISTRATOR role.
    Uses /organizationAcls endpoint.
    """
    resp = _get(
        "organizationAcls",
        token,
        {
            "q": "roleAssignee",
            "role": "ADMINISTRATOR",
            "state": "APPROVED",
            "projection": (
                "(elements*(organization~(id,localizedName,logoV2("
                "original~:playableStreams)),organization))"
            ),
        },
    )

    orgs = []
    for element in resp.get("elements", []):
        org_detail = element.get("organization~", {})
        org_urn = element.get("organization", "")  # urn:li:organization:XXXXX
        org_id = org_urn.split(":")[-1] if ":" in org_urn else org_urn

        name = org_detail.get("localizedName", org_id)
        try:
            logo_elements = (
                org_detail.get("logoV2", {}).get("original~", {}).get("elements", [])
            )
            avatar_url = (
                logo_elements[0]["identifiers"][0]["identifier"]
                if logo_elements
                else None
            )
        except (KeyError, IndexError):
            avatar_url = None

        orgs.append(
            {
                "org_id": org_id,
                "org_urn": org_urn,
                "name": name,
                "avatar_url": avatar_url,
            }
        )
    return orgs


# ---------------------------------------------------------------------------
# Follower stats → daily snapshot
# ---------------------------------------------------------------------------


def _sync_follower_stats(
    session: Session,
    platform_account_id: Any,
    org_id: str,
    token: str,
) -> None:
    resp = _get(
        "networkSizes",
        token,
        {
            "edgeType": "CompanyFollowedByMember",
            "q": "edges",
            "organizationId": org_id,
        },
    )
    followers = resp.get("firstDegreeSize", None)
    today = datetime.now(timezone.utc).date()
    snapshot = MetricSnapshotUpsert(
        date=today,
        followers_count=followers,
        raw_data=resp,
    )
    crud.upsert_metric_snapshot(
        session=session,
        platform_account_id=platform_account_id,
        snapshot_in=snapshot,
    )


# ---------------------------------------------------------------------------
# Organic share statistics (posts)
# ---------------------------------------------------------------------------


def _sync_org_posts(
    session: Session,
    platform_account_id: Any,
    org_urn: str,
    token: str,
) -> None:
    start_ms = int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp() * 1000)

    # Fetch recent shares/posts
    shares_resp = _get(
        "shares",
        token,
        {
            "q": "owners",
            "owners": org_urn,
            "count": 20,
            "sharesPerOwner": 20,
        },
    )

    for share in shares_resp.get("elements", []):
        share_id: str = share.get("id", "")
        if not share_id:
            continue

        created_ms = share.get("created", {}).get("time", 0)
        if created_ms and created_ms < start_ms:
            continue  # outside 30-day window

        # Fetch organic statistics for this share
        stats: dict[str, Any] = {}
        try:
            stats_resp = _get(
                "organizationalEntityShareStatistics",
                token,
                {
                    "q": "organizationalEntity",
                    "organizationalEntity": org_urn,
                    "shares[0]": f"urn:li:share:{share_id}",
                },
            )
            elements = stats_resp.get("elements", [])
            if elements:
                ts = elements[0].get("totalShareStatistics", {})
                stats = ts
        except httpx.HTTPStatusError as exc:
            logger.warning("Could not fetch stats for share %s: %s", share_id, exc)

        published_at: datetime | None = None
        if created_ms:
            published_at = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc)
        else:
            published_at = datetime.now(timezone.utc)

        # Extract text from share content
        text: str | None = None
        try:
            text = share.get("text", {}).get("text") or share.get(
                "specificContent", {}
            ).get("com.linkedin.ugc.ShareContent", {}).get("shareCommentary", {}).get(
                "text"
            )
        except (AttributeError, KeyError):
            pass

        post = PostUpsert(
            external_id=share_id,
            published_at=published_at,
            content_type=ContentType.article,
            text=text,
            impressions=stats.get("impressionCount"),
            reach=stats.get("uniqueImpressionsCount"),
            engagements=stats.get("engagement"),
            likes=stats.get("likeCount"),
            comments=stats.get("commentCount"),
            shares=stats.get("shareCount"),
            clicks=stats.get("clickCount"),
            raw_data=stats or None,
        )
        crud.upsert_post(
            session=session,
            platform_account_id=platform_account_id,
            post_in=post,
        )


# ---------------------------------------------------------------------------
# Main entry-point
# ---------------------------------------------------------------------------


def sync_linkedin(session: Session, integration: Integration) -> None:
    """Sync LinkedIn Company Pages for this integration."""
    token = crud.get_access_token(integration)
    if not token:
        raise ValueError("No access token available for LinkedIn integration")

    orgs = _fetch_admin_organizations(token)
    if not orgs:
        logger.info(
            "sync_linkedin: no admin organisations for integration %s", integration.id
        )
        return

    for org in orgs:
        org_id: str = org["org_id"]
        org_urn: str = org["org_urn"]

        account_in = PlatformAccountCreate(
            integration_id=integration.id,
            workspace_id=integration.workspace_id,
            platform=Platform.linkedin,
            external_id=org_id,
            name=org["name"],
            avatar_url=org.get("avatar_url"),
            account_type="organization",
        )
        account = crud.upsert_platform_account(session=session, account_in=account_in)

        try:
            _sync_follower_stats(session, account.id, org_id, token)
        except httpx.HTTPStatusError as exc:
            logger.error("sync_linkedin: follower stats error for %s: %s", org_id, exc)

        try:
            _sync_org_posts(session, account.id, org_urn, token)
        except httpx.HTTPStatusError as exc:
            logger.error("sync_linkedin: posts error for %s: %s", org_id, exc)


# Register with the Celery sync dispatcher (side-effect on import)
register_platform_sync(Platform.linkedin.value, sync_linkedin)
