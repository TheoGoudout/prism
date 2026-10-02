"""Tests for the Celery analysis tasks, against the test database."""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import Session

from app import crud
from app.models.analysis import (
    AnalysisFrequency,
    AnalysisSchedule,
    AnalysisStatus,
    AnalysisTrigger,
    PerformanceAnalysis,
)
from app.models.common import get_datetime_utc
from app.models.integration import Platform
from app.models.metrics import ContentType, PostUpsert
from app.models.workspace import Workspace
from app.worker.tasks.analysis import run_analysis, start_scheduled_analyses
from tests.utils.integration import create_fake_account, create_fake_integration
from tests.utils.user import create_random_user
from tests.utils.workspace import create_random_workspace

TASKS = "app.worker.tasks.analysis"


@pytest.fixture
def workspace(db: Session) -> Workspace:
    return create_random_workspace(db, create_random_user(db))


def _analysis(
    db: Session,
    workspace: Workspace,
    trigger: AnalysisTrigger = AnalysisTrigger.manual,
) -> PerformanceAnalysis:
    return crud.save(
        db,
        PerformanceAnalysis(
            workspace_id=workspace.id,
            date_from=date(2026, 9, 1),
            date_to=date(2026, 9, 7),
            trigger=trigger,
        ),
    )


def _run(db: Session, analysis_id: uuid.UUID, answer: Any) -> dict[str, Any]:
    """Run the task synchronously with a mocked LLM chain."""
    chain = MagicMock()
    if isinstance(answer, Exception):
        chain.invoke.side_effect = answer
    else:
        chain.invoke.return_value = answer
    with (
        patch(f"{TASKS}.Session") as session_cls,
        patch("app.services.analysis.build_analysis_chain", return_value=chain),
    ):
        session_cls.return_value.__enter__.return_value = db
        result: dict[str, Any] = run_analysis.run(str(analysis_id))
    return result


def test_run_analysis(db: Session, workspace: Workspace) -> None:
    account = create_fake_account(
        db, create_fake_integration(db, workspace, platform=Platform.linkedin)
    )
    post = crud.upsert_post(
        session=db,
        platform_account_id=account.id,
        post_in=PostUpsert(
            external_id="li-1",
            content_type=ContentType.article,
            text="Hiring!",
            published_at=datetime(2026, 9, 3, 9, tzinfo=UTC),
            engagements=42,
        ),
    )
    analysis = _analysis(db, workspace)

    answer = {
        "summary": "Hiring posts work.",
        "posts": [{"ref": "P1", "verdict": "strong", "analysis": "Great."}],
    }
    assert _run(db, analysis.id, answer)["status"] == "completed"

    db.refresh(analysis)
    assert analysis.status == AnalysisStatus.completed
    assert analysis.post_count == 1
    assert analysis.completed_at is not None
    assert analysis.result is not None
    assert analysis.result["posts"][0]["post_id"] == str(post.id)
    assert analysis.emailed_at is None  # manual analyses aren't emailed


def test_run_analysis_records_failures(db: Session, workspace: Workspace) -> None:
    analysis = _analysis(db, workspace)
    assert _run(db, analysis.id, RuntimeError("rate limited"))["status"] == "failed"
    db.refresh(analysis)
    assert analysis.status == AnalysisStatus.failed
    assert analysis.error == "AI generation failed: rate limited"

    invalid = _analysis(db, workspace)
    assert _run(db, invalid.id, ["not", "an", "object"])["status"] == "failed"


def test_run_analysis_skips_finished_and_unknown(
    db: Session, workspace: Workspace
) -> None:
    analysis = _analysis(db, workspace)
    analysis.status = AnalysisStatus.completed
    crud.save(db, analysis)
    assert _run(db, analysis.id, {})["status"] == "skipped"
    assert _run(db, uuid.uuid4(), {})["status"] == "not_found"


def test_scheduled_analysis_is_emailed(db: Session, workspace: Workspace) -> None:
    crud.save(
        db,
        AnalysisSchedule(
            workspace_id=workspace.id,
            enabled=True,
            email_enabled=True,
            email_recipients=["a@example.com", "b@example.com"],
        ),
    )
    analysis = _analysis(db, workspace, AnalysisTrigger.scheduled)

    with (
        patch("app.core.config.settings.SMTP_HOST", "smtp.example.com"),
        patch("app.core.config.settings.EMAILS_FROM_EMAIL", "admin@example.com"),
        patch("app.services.analysis.send_email") as send_email,
    ):
        _run(db, analysis.id, {"summary": "Quiet <b>week</b>."})

    assert [c.kwargs["email_to"] for c in send_email.call_args_list] == [
        "a@example.com",
        "b@example.com",
    ]
    html = send_email.call_args.kwargs["html_content"]
    assert "Quiet &lt;b&gt;week&lt;/b&gt;." in html  # AI output is escaped
    assert f"/ai-analysis?analysis={analysis.id}" in html
    db.refresh(analysis)
    assert analysis.emailed_at is not None


def test_scheduled_analysis_email_failure_keeps_result(
    db: Session, workspace: Workspace
) -> None:
    crud.save(
        db,
        AnalysisSchedule(
            workspace_id=workspace.id,
            enabled=True,
            email_enabled=True,
            email_recipients=["a@example.com"],
        ),
    )
    analysis = _analysis(db, workspace, AnalysisTrigger.scheduled)

    with (
        patch("app.core.config.settings.SMTP_HOST", "smtp.example.com"),
        patch("app.core.config.settings.EMAILS_FROM_EMAIL", "admin@example.com"),
        patch("app.services.analysis.send_email", side_effect=OSError("SMTP down")),
    ):
        assert _run(db, analysis.id, {"summary": "Ok."})["status"] == "completed"

    db.refresh(analysis)
    assert analysis.status == AnalysisStatus.completed
    assert analysis.emailed_at is None


def test_start_scheduled_analyses(db: Session, workspace: Workspace) -> None:
    due_at = get_datetime_utc() - timedelta(minutes=2)
    schedule = crud.save(
        db,
        AnalysisSchedule(
            workspace_id=workspace.id,
            enabled=True,
            frequency=AnalysisFrequency.weekly,
            weekday=due_at.weekday(),
            hour=due_at.hour,
            next_run_at=due_at,
        ),
    )
    idle = create_random_workspace(db, create_random_user(db))
    crud.save(
        db,
        AnalysisSchedule(
            workspace_id=idle.id,
            enabled=True,
            next_run_at=get_datetime_utc() + timedelta(days=1),
        ),
    )

    with (
        patch(f"{TASKS}.Session") as session_cls,
        patch(f"{TASKS}.run_analysis") as task,
    ):
        session_cls.return_value.__enter__.return_value = db
        start_scheduled_analyses.run()

    analyses, _ = crud.get_analyses(session=db, workspace_id=workspace.id)
    assert len(analyses) == 1
    analysis = analyses[0]
    assert analysis.trigger == AnalysisTrigger.scheduled
    assert analysis.date_to == due_at.date() - timedelta(days=1)
    assert analysis.date_from == due_at.date() - timedelta(days=7)
    task.delay.assert_any_call(str(analysis.id))
    assert crud.get_analyses(session=db, workspace_id=idle.id)[1] == 0

    db.refresh(schedule)
    assert schedule.last_run_at is not None
    assert schedule.next_run_at is not None
    assert schedule.next_run_at > get_datetime_utc()
