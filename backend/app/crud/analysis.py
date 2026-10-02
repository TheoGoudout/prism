"""Storage for AI performance analyses and their schedules."""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.models.analysis import AnalysisSchedule, AnalysisStatus, PerformanceAnalysis

UNFINISHED_STATUSES = (AnalysisStatus.pending, AnalysisStatus.running)


def get_analysis(
    *, session: Session, workspace_id: uuid.UUID, analysis_id: uuid.UUID
) -> PerformanceAnalysis | None:
    analysis = session.get(PerformanceAnalysis, analysis_id)
    if analysis is None or analysis.workspace_id != workspace_id:
        return None
    return analysis


def get_analyses(
    *, session: Session, workspace_id: uuid.UUID, skip: int = 0, limit: int = 20
) -> tuple[Sequence[PerformanceAnalysis], int]:
    """A page of the workspace's analyses, newest first, and their total count."""
    in_workspace = PerformanceAnalysis.workspace_id == workspace_id
    count = session.exec(
        select(func.count()).select_from(PerformanceAnalysis).where(in_workspace)
    ).one()
    analyses = session.exec(
        select(PerformanceAnalysis)
        .where(in_workspace)
        .order_by(col(PerformanceAnalysis.created_at).desc())
        .offset(skip)
        .limit(limit)
    ).all()
    return analyses, count


def has_unfinished_analysis(*, session: Session, workspace_id: uuid.UUID) -> bool:
    statement = select(PerformanceAnalysis.id).where(
        PerformanceAnalysis.workspace_id == workspace_id,
        col(PerformanceAnalysis.status).in_(UNFINISHED_STATUSES),
    )
    return session.exec(statement).first() is not None


def get_schedule(
    *, session: Session, workspace_id: uuid.UUID
) -> AnalysisSchedule | None:
    return session.get(AnalysisSchedule, workspace_id)


def get_due_schedules(*, session: Session, now: datetime) -> Sequence[AnalysisSchedule]:
    """
    Enabled schedules whose next run is due, locked so that two overlapping
    scheduler runs can't both start the same analysis.
    """
    statement = (
        select(AnalysisSchedule)
        .where(col(AnalysisSchedule.enabled).is_(True))
        .where(col(AnalysisSchedule.next_run_at) <= now)
        .with_for_update(skip_locked=True)
    )
    return session.exec(statement).all()
