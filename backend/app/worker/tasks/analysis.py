"""
Analysis tasks — run AI performance analyses.

`run_analysis` runs one pending analysis and emails it to its recipients (for
a scheduled analysis, the schedule's recipients when it started). `start_scheduled_analyses` runs every few minutes
and starts the analyses whose schedule is due.
"""

import logging
import uuid
from typing import Any

from sqlmodel import Session

from app import crud
from app.core.db import engine
from app.crud.analysis import UNFINISHED_STATUSES
from app.models.analysis import AnalysisStatus, PerformanceAnalysis
from app.models.common import get_datetime_utc
from app.services import analysis as analysis_service
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _email(session: Session, analysis: PerformanceAnalysis) -> None:
    workspace = crud.get_workspace(session=session, workspace_id=analysis.workspace_id)
    assert workspace is not None  # guaranteed by the foreign key
    try:
        sent = analysis_service.send_by_email(
            analysis,
            workspace_name=workspace.name,
            recipients=analysis.email_recipients,
        )
    except Exception:
        # The analysis itself succeeded: keep it, just without the email
        logger.exception("run_analysis: emailing %s failed", analysis.id)
        return
    if sent:
        analysis.emailed_at = get_datetime_utc()
        crud.save(session, analysis)


@celery_app.task(name="app.worker.tasks.analysis.run_analysis")
def run_analysis(analysis_id: str) -> dict[str, Any]:
    """Run one analysis. LLM failures aren't retried: they're recorded on it."""
    with Session(engine) as session:
        analysis = session.get(PerformanceAnalysis, uuid.UUID(analysis_id))
        if analysis is None:
            logger.warning("run_analysis: analysis %s not found", analysis_id)
            return {"status": "not_found", "analysis_id": analysis_id}
        # `running` too: a task redelivered after a worker crash resumes it
        if analysis.status not in UNFINISHED_STATUSES:
            return {"status": "skipped", "reason": analysis.status.value}

        analysis_service.run(session, analysis)
        if analysis.status == AnalysisStatus.completed and analysis.email_recipients:
            _email(session, analysis)
        return {"status": analysis.status.value, "analysis_id": analysis_id}


@celery_app.task(name="app.worker.tasks.analysis.start_scheduled_analyses")
def start_scheduled_analyses() -> dict[str, Any]:
    """Create and enqueue the analyses of every due schedule."""
    with Session(engine) as session:
        analyses = analysis_service.start_due_analyses(session, get_datetime_utc())
    for analysis in analyses:
        run_analysis.delay(str(analysis.id))
    if analyses:
        logger.info("start_scheduled_analyses: started %d analyses", len(analyses))
    return {"started": len(analyses)}
