"""
AI performance analyses: run one on demand, browse past ones, and configure
the workspace's schedule (and who receives each scheduled analysis by email).

Analyses run in the worker (see app.worker.tasks.analysis): starting one
returns it `pending`, and clients poll it until it is completed or failed.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status

from app import crud
from app.api.deps import CurrentMember, CurrentUser, SessionDep, require_manager
from app.core.config import settings
from app.models.analysis import (
    AnalysesPublic,
    AnalysisCreate,
    AnalysisPublic,
    AnalysisSchedule,
    AnalysisStatus,
    PerformanceAnalysis,
    SchedulePublic,
    ScheduleSettings,
)
from app.models.common import get_datetime_utc
from app.models.workspace import WorkspaceMember
from app.services import analysis as analysis_service
from app.worker.tasks import analysis as analysis_tasks

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["analyses"])

# Fields that decide when a schedule runs: changing one recomputes the next run
_TIMING_FIELDS = ("enabled", "frequency", "weekday", "day_of_month", "hour", "timezone")


def _get_analysis(
    session: SessionDep, member: WorkspaceMember, analysis_id: uuid.UUID
) -> PerformanceAnalysis:
    analysis = crud.get_analysis(
        session=session, workspace_id=member.workspace_id, analysis_id=analysis_id
    )
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis


@router.get("/analyses", response_model=AnalysesPublic)
def list_analyses(
    session: SessionDep,
    member: CurrentMember,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Any:
    """The workspace's analyses, newest first, without their results."""
    analyses, count = crud.get_analyses(
        session=session, workspace_id=member.workspace_id, skip=skip, limit=limit
    )
    return AnalysesPublic(data=analyses, count=count)  # type: ignore[arg-type]


@router.post(
    "/analyses", response_model=AnalysisPublic, status_code=status.HTTP_202_ACCEPTED
)
def create_analysis(
    session: SessionDep, member: CurrentMember, analysis_in: AnalysisCreate
) -> Any:
    """Start an analysis of a period (by default the last 7 days)."""
    if crud.has_unfinished_analysis(session=session, workspace_id=member.workspace_id):
        raise HTTPException(
            status_code=409, detail="An analysis is already running for this workspace"
        )
    default_from, default_to = analysis_service.default_period()
    date_from = analysis_in.date_from or default_from
    date_to = analysis_in.date_to or default_to
    if date_from > date_to:
        raise HTTPException(
            status_code=422, detail="date_from must be on or before date_to"
        )
    analysis = crud.save(
        session,
        PerformanceAnalysis(
            workspace_id=member.workspace_id, date_from=date_from, date_to=date_to
        ),
    )
    analysis_tasks.run_analysis.delay(str(analysis.id))
    return analysis_service.to_public(session, analysis)


@router.get("/analyses/{analysis_id}", response_model=AnalysisPublic)
def read_analysis(
    session: SessionDep, member: CurrentMember, analysis_id: uuid.UUID
) -> Any:
    """An analysis with its full result and the posts it analyzed."""
    analysis = _get_analysis(session, member, analysis_id)
    return analysis_service.to_public(session, analysis)


@router.delete("/analyses/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_analysis(
    session: SessionDep, member: CurrentMember, analysis_id: uuid.UUID
) -> None:
    require_manager(member, "delete analyses")
    crud.delete(session, _get_analysis(session, member, analysis_id))


@router.post("/analyses/{analysis_id}/email", status_code=status.HTTP_204_NO_CONTENT)
def email_analysis(
    session: SessionDep,
    member: CurrentMember,
    current_user: CurrentUser,
    analysis_id: uuid.UUID,
) -> None:
    """Email a completed analysis to the current user."""
    analysis = _get_analysis(session, member, analysis_id)
    if analysis.status != AnalysisStatus.completed:
        raise HTTPException(status_code=400, detail="The analysis is not completed")
    if not settings.emails_enabled:
        raise HTTPException(status_code=503, detail="Emails are not configured")
    assert member.workspace is not None  # guaranteed by the foreign key
    analysis_service.send_by_email(
        analysis, workspace_name=member.workspace.name, recipients=[current_user.email]
    )


@router.get("/analysis-schedule", response_model=SchedulePublic)
def read_schedule(session: SessionDep, member: CurrentMember) -> Any:
    """The workspace's schedule; disabled defaults if it was never set."""
    schedule = crud.get_schedule(session=session, workspace_id=member.workspace_id)
    return schedule or SchedulePublic()


@router.put("/analysis-schedule", response_model=SchedulePublic)
def update_schedule(
    session: SessionDep, member: CurrentMember, schedule_in: ScheduleSettings
) -> Any:
    require_manager(member, "schedule analyses")
    schedule = crud.get_schedule(session=session, workspace_id=member.workspace_id)
    timing_changed = schedule is None or any(
        getattr(schedule, field) != getattr(schedule_in, field)
        for field in _TIMING_FIELDS
    )
    if schedule is None:
        schedule = AnalysisSchedule(workspace_id=member.workspace_id)
    schedule.sqlmodel_update(schedule_in.model_dump())
    if not schedule.enabled:
        schedule.next_run_at = None
    elif timing_changed or schedule.next_run_at is None:
        schedule.next_run_at = analysis_service.next_occurrence(
            schedule, get_datetime_utc()
        )
    return crud.save(session, schedule)
