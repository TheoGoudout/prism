"""Tests for the instrack.app history importer."""

from datetime import date
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.import_instrack import import_days, main, parse
from app.models.integration import Integration, IntegrationStatus, Platform
from app.models.metrics import MetricSnapshot
from tests.utils.user import create_random_user
from tests.utils.workspace import create_random_workspace

FIXTURE = Path(__file__).parent.parent / "fixtures" / "instrack_airt_de_famille.txt"


def test_parse_copied_table() -> None:
    days = parse(FIXTURE.read_text())

    assert len(days) == 89
    assert days[0].date == date(2026, 7, 9)  # oldest first
    latest = days[-1]
    assert latest.date == date(2026, 10, 5)
    assert latest.followers == 21980
    assert latest.followers_change == -109
    assert latest.following == 542
    assert latest.media == 501
    assert latest.engagement_rate == 0.81


def test_parse_day_without_change() -> None:
    (day,) = parse("Sep 17 2026 Thu\t21 573\t528\t485 +2\t1.05% +0,01")
    assert day.followers == 21573
    assert day.followers_change is None
    assert day.media == 485


def test_parse_space_separated_cells_and_narrow_spaces() -> None:
    (day,) = parse("Oct 5 2026 Mon  21 980 -1 109  542  501  0.81%")
    assert day.followers == 21980
    assert day.followers_change == -1109


def test_parse_rejects_missing_cells() -> None:
    with pytest.raises(ValueError, match="Line 1"):
        parse("Oct 5 2026 Mon\t21 980 -109\t542")


def test_import_creates_unsynced_account_with_snapshots(db: Session) -> None:
    workspace = create_random_workspace(db, create_random_user(db))
    days = parse(FIXTURE.read_text())

    account = import_days(
        session=db, workspace=workspace, username="airt_de_famille", days=days
    )

    integration = db.get(Integration, account.integration_id)
    assert integration is not None
    assert integration.platform == Platform.instagram
    assert integration.status == IntegrationStatus.disconnected
    assert integration.access_token_encrypted is None

    snapshots = {
        s.date: s
        for s in db.exec(
            select(MetricSnapshot).where(
                MetricSnapshot.platform_account_id == account.id
            )
        )
    }
    assert len(snapshots) == 89
    latest = snapshots[date(2026, 10, 5)]
    assert latest.followers_count == 21980
    assert latest.followers_gained == 0
    assert latest.followers_lost == 109
    assert latest.posts_count == 501
    assert latest.raw_data == {
        "source": "instrack",
        "following_count": 542,
        "engagement_rate_percent": 0.81,
    }
    assert snapshots[date(2026, 10, 3)].followers_gained == 36


def test_import_again_updates_the_same_account(db: Session) -> None:
    workspace = create_random_workspace(db, create_random_user(db))
    first = import_days(
        session=db,
        workspace=workspace,
        username="airt_de_famille",
        days=parse("Oct 5 2026 Mon\t21 980 -109\t542\t501\t0.81%"),
    )
    second = import_days(
        session=db,
        workspace=workspace,
        username="airt_de_famille",
        days=parse("Oct 5 2026 Mon\t22 000 -89\t542\t501\t0.81%"),
    )

    assert second.id == first.id
    snapshots = db.exec(
        select(MetricSnapshot).where(MetricSnapshot.platform_account_id == first.id)
    ).all()
    assert [s.followers_count for s in snapshots] == [22000]


def test_main_imports_into_workspace_by_slug(db: Session) -> None:
    workspace = create_random_workspace(db, create_random_user(db))

    main([str(FIXTURE), "--workspace", workspace.slug, "--username", "airt_de_famille"])

    integration = db.exec(
        select(Integration).where(Integration.workspace_id == workspace.id)
    ).one()
    assert integration.external_account_id == "instrack:airt_de_famille"


def test_main_rejects_unknown_workspace() -> None:
    with pytest.raises(SystemExit):
        main([str(FIXTURE), "--workspace", "no-such-workspace", "--username", "x"])
