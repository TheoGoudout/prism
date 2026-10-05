"""
Import an Instagram account's daily history copied from instrack.app.

instrack.app tracks public Instagram profiles. Its history table (Date,
Followers Count, Following Count, Media Count, Engagement Rate) can be copied
from the browser and imported into a workspace, to try Prism on real data
without connecting the account:

    python -m app.import_instrack --workspace <slug> --username <handle> history.txt

The account is attached to a `disconnected` Instagram integration with no
tokens, so the scheduled sync leaves it alone. Importing again updates the
same days. Delete the integration to remove the imported data.

Each row becomes a daily snapshot: followers and media counts, and the day's
net follower change as followers gained (or lost). instrack's engagement rate
(average interactions per post / followers) isn't Prism's engagement rate
(engagements / views), so it is kept with the following count in raw_data.
"""

import argparse
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from sqlmodel import Session, select

from app import crud
from app.core.db import engine
from app.crud.common import save
from app.models.integration import (
    Integration,
    IntegrationStatus,
    Platform,
    PlatformAccount,
)
from app.models.metrics import MetricSnapshotUpsert
from app.models.workspace import Workspace

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SOURCE = "instrack"

# "Oct 5 2026 Mon", then the cells, separated by tabs (or runs of 2+ spaces)
_ROW = re.compile(r"^([A-Z][a-z]{2} \d{1,2} \d{4}) [A-Z][a-z]{2}\s+(.+)$")
_CELL_SEPARATOR = re.compile(r"\t+| {2,}")
# A value with its change on the previous day: "21 980 -109", "0.81% +0,02"
_CELL = re.compile(r"^([\d\s.,]+?)(%?)(?:\s*([+-][\d\s.,]+))?$")


@dataclass(frozen=True)
class InstrackDay:
    date: date
    followers: int
    followers_change: int | None
    following: int
    media: int
    engagement_rate: float | None  # percent


def _int(text: str) -> int:
    """'21 980' or '+1' → int. Thousands are separated by (any) spaces."""
    return int(re.sub(r"\s", "", text))


def _cell(text: str) -> tuple[str, str | None]:
    """A cell's value and its change on the previous day, if shown."""
    match = _CELL.match(text.strip())
    if match is None:
        raise ValueError(f"Unexpected value: {text!r}")
    return match.group(1), match.group(3)


def parse(text: str) -> list[InstrackDay]:
    """
    Parse instrack's history table as copied from the page. Lines that aren't
    a day (headers, blank lines) are skipped. Days are returned oldest first.
    """
    days: dict[date, InstrackDay] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = _ROW.match(line.strip())
        if match is None:
            continue
        cells = _CELL_SEPARATOR.split(match.group(2).strip())
        if len(cells) != 4:
            raise ValueError(
                f"Line {line_number}: expected 4 values separated by tabs, "
                f"got {len(cells)}: {line!r}"
            )
        try:
            followers, followers_change = _cell(cells[0])
            following, _ = _cell(cells[1])
            media, _ = _cell(cells[2])
            rate, _ = _cell(cells[3])
            day = InstrackDay(
                date=datetime.strptime(match.group(1), "%b %d %Y").date(),
                followers=_int(followers),
                followers_change=(_int(followers_change) if followers_change else None),
                following=_int(following),
                media=_int(media),
                engagement_rate=float(rate.replace(",", ".")) if rate else None,
            )
        except ValueError as exc:
            raise ValueError(f"Line {line_number}: {exc}") from exc
        days[day.date] = day
    return [days[d] for d in sorted(days)]


def _snapshot(day: InstrackDay) -> MetricSnapshotUpsert:
    change = day.followers_change
    if change is None:
        # A day without a change shown has the same count as the day before
        change = 0
    return MetricSnapshotUpsert(
        date=day.date,
        followers_count=day.followers,
        followers_gained=max(change, 0),
        followers_lost=max(-change, 0),
        posts_count=day.media,
        raw_data={
            "source": SOURCE,
            "following_count": day.following,
            "engagement_rate_percent": day.engagement_rate,
        },
    )


def import_days(
    *, session: Session, workspace: Workspace, username: str, days: list[InstrackDay]
) -> PlatformAccount:
    """Store the days on the workspace's imported account for `username`."""
    external_id = f"{SOURCE}:{username}"
    integration = session.exec(
        select(Integration).where(
            Integration.workspace_id == workspace.id,
            Integration.platform == Platform.instagram,
            Integration.external_account_id == external_id,
        )
    ).first() or Integration(
        workspace_id=workspace.id,
        platform=Platform.instagram,
        external_account_id=external_id,
        external_account_name=username,
    )
    # No tokens: a disconnected integration is never synced
    integration.status = IntegrationStatus.disconnected
    integration.sync_error = f"Imported from {SOURCE}.app, not connected."
    integration = save(session, integration)

    account = crud.upsert_platform_account(
        session=session,
        integration=integration,
        external_id=external_id,
        name=username,
        account_type="imported",
    )
    for day in days:
        crud.upsert_metric_snapshot(
            session=session,
            platform_account_id=account.id,
            snapshot_in=_snapshot(day),
        )
    return account


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("file", type=Path, help="the copied history table")
    parser.add_argument("--workspace", required=True, help="workspace slug")
    parser.add_argument("--username", required=True, help="Instagram username")
    args = parser.parse_args(argv)

    days = parse(args.file.read_text(encoding="utf-8"))
    if not days:
        parser.error(f"no days found in {args.file}")

    with Session(engine) as session:
        workspace = session.exec(
            select(Workspace).where(Workspace.slug == args.workspace)
        ).first()
        if workspace is None:
            parser.error(f"no workspace with slug {args.workspace!r}")
        import_days(
            session=session, workspace=workspace, username=args.username, days=days
        )
    logger.info(
        "Imported %d days (%s to %s) of @%s into %s",
        len(days),
        days[0].date,
        days[-1].date,
        args.username,
        args.workspace,
    )


if __name__ == "__main__":
    main()
