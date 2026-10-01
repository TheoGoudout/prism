"""
Insights chain — generates actionable bullet-point insights from metrics data.

Returns a JSON array of insight objects parsed directly from the LLM response.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable

from app.ai.llm import get_llm

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

=== Overall totals ===
{totals_text}

=== Per-platform breakdown ===
{platforms_text}
"""


def _fmt_totals(totals: dict[str, Any]) -> str:
    lines = []
    for key, val in totals.items():
        if val is not None and val != 0:
            lines.append(f"  {key}: {val:,}")
    return "\n".join(lines) if lines else "  (no data)"


def _fmt_platforms(by_platform: dict[str, dict[str, Any]]) -> str:
    if not by_platform:
        return "  (no platform data)"
    blocks = []
    for plat, metrics in by_platform.items():
        lines = [f"  [{plat}]"]
        for key, val in metrics.items():
            if val is not None and val != 0:
                lines.append(f"    {key}: {val:,}")
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


def build_insights_chain() -> RunnableSerializable[
    dict[str, Any], list[dict[str, Any]]
]:
    """Return a chain that accepts a dict of template vars and returns parsed insights."""
    prompt = ChatPromptTemplate.from_messages([("system", _SYSTEM), ("human", _HUMAN)])
    llm = get_llm()

    def parse_json(text: str) -> list[dict[str, Any]]:
        # Strip accidental markdown fences if the model ignores instructions
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        return json.loads(text)  # type: ignore[no-any-return]

    return prompt | llm | StrOutputParser() | parse_json


def build_insights_input(
    *,
    workspace_name: str,
    date_from: str,
    date_to: str,
    platform: str | None,
    totals: dict[str, Any],
    by_platform: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "workspace_name": workspace_name,
        "date_from": date_from,
        "date_to": date_to,
        "platform_context": f" · platform filter: {platform}" if platform else "",
        "totals_text": _fmt_totals(totals),
        "platforms_text": _fmt_platforms(by_platform),
    }
