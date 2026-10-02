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
from app.api.deps import CurrentMember, MetricsQueryDep, SessionDep
from app.models.ai import InsightsResponse, ReportResponse
from app.services import metrics as metrics_service
from app.services.metrics import MetricsQuery

router = APIRouter(prefix="/workspaces/{workspace_id}/ai", tags=["ai"])


def _prompt_variables(
    session: SessionDep, member: CurrentMember, query: MetricsQuery
) -> dict[str, Any]:
    """The prompt variables shared by every chain."""
    assert member.workspace is not None  # guaranteed by the foreign key
    return prompt_variables(
        workspace_name=member.workspace.name,
        query=query,
        summary=metrics_service.summarize(session, query),
    )


def _invoke(chain: Runnable[dict[str, Any], Any], variables: dict[str, Any]) -> Any:
    try:
        return chain.invoke(variables)
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"AI generation failed: {exc}"
        ) from exc


@router.post("/insights", response_model=InsightsResponse)
def generate_insights(
    session: SessionDep, member: CurrentMember, query: MetricsQueryDep
) -> Any:
    """4–6 structured, actionable insights about the workspace's metrics."""
    variables = _prompt_variables(session, member, query)
    raw = _invoke(build_insights_chain(), variables)
    return InsightsResponse(insights=to_insights(raw))


@router.post("/report", response_model=ReportResponse)
def generate_report(
    session: SessionDep, member: CurrentMember, query: MetricsQueryDep
) -> Any:
    """A markdown report: summary, per-platform analysis, top content, advice."""
    variables = _prompt_variables(session, member, query)
    variables["posts_text"] = format_posts(metrics_service.top_posts(session, query))
    return ReportResponse(report=_invoke(build_report_chain(), variables))
