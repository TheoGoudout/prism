"""
Insights chain — 4–6 short, actionable insights about a workspace's metrics.

The model answers with a JSON array, parsed into Insight objects.
"""

import json
import logging
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable
from pydantic import ValidationError

from app.ai.llm import get_llm
from app.models.ai import Insight

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are an expert social media analytics consultant.
Given aggregated metrics for a workspace, produce 4–6 concise, actionable insights.

Rules:
- Be specific: reference actual numbers when they are meaningful.
- Classify each insight as "positive", "negative", or "neutral".
- Output ONLY a valid JSON array — no markdown fences, no prose.
- Each element must have exactly these keys:
    "title"  : short headline (≤10 words)
    "body"   : 1–2 sentence explanation with context
    "type"   : "positive" | "negative" | "neutral"
    "metric" : the primary metric this insight relates to (e.g. "impressions"), or null
"""

_HUMAN = """\
Workspace: {workspace_name}
Period: {date_from} to {date_to}{platform_context}

=== Metric definitions (the same on every platform) ===
{metric_definitions}

=== Overall totals ===
{totals_text}

=== Per-platform breakdown ===
{platforms_text}
"""


def _parse_json(text: str) -> Any:
    # Strip markdown fences in case the model ignores the instructions
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return json.loads(text)


def build_insights_chain() -> RunnableSerializable[dict[str, Any], Any]:
    """Prompt variables in (see app.ai.formatting), parsed JSON out."""
    prompt = ChatPromptTemplate.from_messages([("system", _SYSTEM), ("human", _HUMAN)])
    return prompt | get_llm() | StrOutputParser() | _parse_json


def to_insights(raw: Any) -> list[Insight]:
    """Validate the model's JSON, dropping malformed items rather than failing."""
    insights = []
    for item in raw if isinstance(raw, list) else []:
        try:
            insights.append(Insight.model_validate(item))
        except ValidationError:
            logger.warning("Dropping malformed insight from the model: %r", item)
    return insights
