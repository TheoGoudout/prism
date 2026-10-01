"""
Report chain — generates a markdown performance report from full metrics data.
"""

from __future__ import annotations

from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable

from app.ai.llm import get_llm

_SYSTEM = """\
You are an expert social media analyst writing a performance report for a brand.
Write a clear, professional markdown report. Use ## for sections.

Structure:
## Executive Summary
## Platform Performance
## Top Content
## Recommendations

Rules:
- Be data-driven: cite specific numbers.
- Keep each section concise (3–6 bullet points or short paragraphs).
- Output only the markdown — no preamble, no trailing commentary.
"""

_HUMAN = """\
Workspace: {workspace_name}
Report period: {date_from} to {date_to}{platform_context}

=== Aggregate totals ===
{totals_text}

=== Per-platform breakdown ===
{platforms_text}

=== Top posts (by engagements) ===
{posts_text}
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


def _fmt_posts(posts: list[dict[str, Any]]) -> str:
    if not posts:
        return "  (no posts)"
    lines = []
    for i, p in enumerate(posts[:10], 1):
        snippet = (p.get("text") or "")[:80].replace("\n", " ")
        eng = p.get("engagements") or 0
        ctype = p.get("content_type", "")
        lines.append(f"  {i}. [{ctype}] engagements={eng:,}  — {snippet!r}")
    return "\n".join(lines)


def build_report_chain() -> RunnableSerializable[dict[str, Any], str]:
    prompt = ChatPromptTemplate.from_messages([("system", _SYSTEM), ("human", _HUMAN)])
    llm = get_llm()
    return prompt | llm | StrOutputParser()


def build_report_input(
    *,
    workspace_name: str,
    date_from: str,
    date_to: str,
    platform: str | None,
    totals: dict[str, Any],
    by_platform: dict[str, dict[str, Any]],
    posts: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "workspace_name": workspace_name,
        "date_from": date_from,
        "date_to": date_to,
        "platform_context": f" · platform filter: {platform}" if platform else "",
        "totals_text": _fmt_totals(totals),
        "platforms_text": _fmt_platforms(by_platform),
        "posts_text": _fmt_posts(posts),
    }
