"""Report chain — a markdown performance report for a workspace."""

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


def build_report_chain() -> RunnableSerializable[dict[str, Any], str]:
    """Prompt variables in (see app.ai.formatting, plus posts_text), markdown out."""
    prompt = ChatPromptTemplate.from_messages([("system", _SYSTEM), ("human", _HUMAN)])
    return prompt | get_llm() | StrOutputParser()
