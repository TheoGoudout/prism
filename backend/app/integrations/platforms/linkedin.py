"""
LinkedIn Company Page sync (REST API v2).

For every company Page the user administers:
  - the Page is stored as a PlatformAccount
  - today's follower count becomes a MetricSnapshot
  - shares from the sync window (latest 20) and their statistics become Posts
"""

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from sqlmodel import Session

from app import crud
from app.integrations.common import SYNC_WINDOW_DAYS, log_http_errors, sum_known
from app.integrations.http import get_json
from app.models.integration import Integration
from app.models.metrics import ContentType, MetricSnapshotUpsert, PostUpsert

logger = logging.getLogger(__name__)

LINKEDIN_API = "https://api.linkedin.com/v2"


def _get(path: str, token: str, params: dict[str, Any]) -> dict[str, Any]:
    return get_json(
        f"{LINKEDIN_API}/{path}",
        token=token,
        params=params,
        headers={"X-Restli-Protocol-Version": "2.0.0"},
    )


def _logo_url(org: dict[str, Any]) -> str | None:
    try:
        return str(
            org["logoV2"]["original~"]["elements"][0]["identifiers"][0]["identifier"]
        )
    except (KeyError, IndexError, TypeError):
        return None


def _fetch_admin_organizations(token: str) -> list[dict[str, Any]]:
    """The company Pages where the user has the ADMINISTRATOR role."""
    data = _get(
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
    for element in data.get("elements", []):
        org_urn: str = element.get("organization", "")  # urn:li:organization:123
        org_id = org_urn.rsplit(":", 1)[-1]
        details = element.get("organization~", {})
        orgs.append(
            {
                "org_id": org_id,
                "org_urn": org_urn,
                "name": details.get("localizedName", org_id),
                "avatar_url": _logo_url(details),
            }
        )
    return orgs


def _sync_follower_stats(
    session: Session, platform_account_id: uuid.UUID, org_id: str, token: str
) -> None:
    data = _get(
        "networkSizes",
        token,
        {"edgeType": "CompanyFollowedByMember", "q": "edges", "organizationId": org_id},
    )
    crud.upsert_metric_snapshot(
        session=session,
        platform_account_id=platform_account_id,
        snapshot_in=MetricSnapshotUpsert(
            date=date.today(),
            followers_count=data.get("firstDegreeSize"),
            raw_data=data,
        ),
    )


def _share_statistics(org_urn: str, share_id: str, token: str) -> dict[str, Any]:
    """The share's totalShareStatistics, or {} if unavailable."""
    try:
        data = _get(
            "organizationalEntityShareStatistics",
            token,
            {
                "q": "organizationalEntity",
                "organizationalEntity": org_urn,
                "shares[0]": f"urn:li:share:{share_id}",
            },
        )
    except httpx.HTTPStatusError as exc:
        logger.warning("Could not fetch stats for share %s: %s", share_id, exc)
        return {}
    elements = data.get("elements") or [{}]
    stats: dict[str, Any] = elements[0].get("totalShareStatistics", {})
    return stats


def _share_text(share: dict[str, Any]) -> str | None:
    text: str | None = share.get("text", {}).get("text")
    if text:
        return text
    content = share.get("specificContent", {}).get("com.linkedin.ugc.ShareContent", {})
    commentary: str | None = content.get("shareCommentary", {}).get("text")
    return commentary


def _sync_org_posts(
    session: Session, platform_account_id: uuid.UUID, org_urn: str, token: str
) -> None:
    window_start = datetime.now(timezone.utc) - timedelta(days=SYNC_WINDOW_DAYS)
    data = _get(
        "shares",
        token,
        {"q": "owners", "owners": org_urn, "count": 20, "sharesPerOwner": 20},
    )
    for share in data.get("elements", []):
        created_ms = share.get("created", {}).get("time")
        if not share.get("id") or not created_ms:
            continue
        published_at = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc)
        if published_at < window_start:
            continue

        stats = _share_statistics(org_urn, share["id"], token)
        likes = stats.get("likeCount")
        comments = stats.get("commentCount")
        shares = stats.get("shareCount")
        clicks = stats.get("clickCount")
        crud.upsert_post(
            session=session,
            platform_account_id=platform_account_id,
            post_in=PostUpsert(
                external_id=share["id"],
                published_at=published_at,
                content_type=ContentType.article,
                text=_share_text(share),
                impressions=stats.get("impressionCount"),
                reach=stats.get("uniqueImpressionsCount"),
                # LinkedIn's own `engagement` is a rate; keep it in raw_data
                engagements=sum_known(likes, comments, shares, clicks),
                likes=likes,
                comments=comments,
                shares=shares,
                clicks=clicks,
                raw_data=stats or None,
            ),
        )


def sync_linkedin(
    session: Session, integration: Integration, access_token: str
) -> None:
    """Sync every LinkedIn company Page the user administers."""
    for org in _fetch_admin_organizations(access_token):
        account = crud.upsert_platform_account(
            session=session,
            integration=integration,
            external_id=org["org_id"],
            name=org["name"],
            avatar_url=org["avatar_url"],
            account_type="organization",
        )
        with log_http_errors(f"LinkedIn follower stats for {org['org_id']}"):
            _sync_follower_stats(session, account.id, org["org_id"], access_token)
        with log_http_errors(f"LinkedIn posts for {org['org_id']}"):
            _sync_org_posts(session, account.id, org["org_urn"], access_token)
