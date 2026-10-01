"""
AI endpoints — on-demand insights and performance reports.

Both summarize the same metrics as the dashboard (see app.services.metrics)
and pass them to an LLM chain. LangSmith tracing is enabled automatically when
LANGCHAIN_TRACING_V2=true and LANGCHAIN_API_KEY are set in the environment.
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from langchain_core.runnables import Runnable

from app.ai.formatting import format_posts, prompt_variables
from app.ai.insights import build_insights_chain, to_insights
from app.ai.report import build_report_chain
from app.api.deps import CurrentUser, SessionDep, get_workspace_member
from app.models.ai import AIRequest, InsightsResponse, ReportResponse
from app.services import metrics as metrics_service
from app.services.metrics import MetricsQuery

router = APIRouter(prefix="/ai", tags=["ai"])


def _prepare(
    body: AIRequest, session: SessionDep, current_user: CurrentUser
) -> tuple[MetricsQuery, dict[str, Any]]:
    """Check access and build the metrics query and the shared prompt variables."""
    member = get_workspace_member(session, current_user, body.workspace_id)
    assert member.workspace is not None  # guaranteed by the foreign key
    query = MetricsQuery.build(
        body.workspace_id, body.platform, body.date_from, body.date_to
    )
    variables = prompt_variables(
        workspace_name=member.workspace.name,
        query=query,
        summary=metrics_service.summarize(session, query),
    )
    return query, variables


def _invoke(chain: Runnable[dict[str, Any], Any], variables: dict[str, Any]) -> Any:
    try:
        return chain.invoke(variables)
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"AI generation failed: {exc}"
        ) from exc


@router.post("/insights", response_model=InsightsResponse)
def generate_insights(
    body: AIRequest, session: SessionDep, current_user: CurrentUser
) -> Any:
    """4–6 structured, actionable insights about the workspace's metrics."""
    _, variables = _prepare(body, session, current_user)
    raw = _invoke(build_insights_chain(), variables)
    return InsightsResponse(insights=to_insights(raw))


@router.post("/report", response_model=ReportResponse)
def generate_report(
    body: AIRequest, session: SessionDep, current_user: CurrentUser
) -> Any:
    """A markdown report: summary, per-platform analysis, top content, advice."""
    query, variables = _prepare(body, session, current_user)
    variables["posts_text"] = format_posts(metrics_service.top_posts(session, query))
    return ReportResponse(report=_invoke(build_report_chain(), variables))
