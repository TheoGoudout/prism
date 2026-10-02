"""
Performance analysis chain — a full review of a workspace's posts and metrics.

A yearly analysis uses the same chain with extra instructions: it also judges
each month, and only analyzes the most notable posts one by one (a year has
too many posts for a per-post answer to fit the model's output).

The model sees every post of the period (up to a cap) under a short reference
("P1", "P2"…), answers with one JSON object, and the references are mapped
back to post ids by `to_result`.
"""

import logging
import uuid
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable
from pydantic import BaseModel, ValidationError

from app.ai.formatting import parse_json
from app.ai.llm import get_llm
from app.models.analysis import (
    AnalysisKind,
    AnalysisResult,
    Finding,
    PeriodAnalysis,
    PlatformAnalysis,
    PostAnalysis,
    Recommendation,
    TopicAnalysis,
)

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are a senior social media strategist reviewing a brand's performance
across every platform it publishes on. You receive the period's metrics, the
previous period's metrics for comparison, and every post published in the
period with its own metrics.

Do a complete performance analysis:
1. Analyze each post: how it performed relative to the other posts of its
   platform (see the benchmarks), and why it likely did so (topic, format,
   timing, wording, call to action…).
2. Group posts that are about the same subject (campaign, product, theme) into
   topics, and judge each topic as a whole.
3. Judge each platform, comparing with the previous period.
4. Conclude globally: what worked, what didn't, and concrete, prioritized
   recommendations to improve next period.

Rules:
- Be specific and data-driven: cite actual numbers and post references.
- "verdict" is always one of "strong", "average", "weak".
- "priority" is always one of "high", "medium", "low".
- Every post reference must be one of the given ones (e.g. "P3").
- {posts_rule}
- Output ONLY a valid JSON object — no markdown fences, no prose — with exactly
  these keys:
{{
  "summary": "3–5 sentence executive summary of the period",
  "what_worked": [{{"title": "...", "detail": "..."}}],
  "what_didnt_work": [{{"title": "...", "detail": "..."}}],
  "recommendations": [{{"title": "...", "detail": "...", "priority": "high"}}],
  "platforms": [{{"platform": "instagram", "verdict": "strong", "summary": "..."}}],
  "topics": [{{"name": "...", "verdict": "average", "summary": "...", "posts": ["P1", "P4"]}}],
  "posts": [{{"ref": "P1", "verdict": "weak", "topic": "...", "analysis": "1–2 sentences", "suggestion": "how to improve it, or null"}}]{periods_key}
}}
"""

_STANDARD_POSTS_RULE = "Analyze every post exactly once."

_YEARLY_POSTS_RULE = """This is a year in review. In "posts", analyze individually only the most
  notable posts (the best and worst performers, and any striking outlier),
  at most {max_post_analyses} of them, but group ALL posts into topics. Look for
  trends over the year: seasonality, growth or decline, which topics and
  formats gained or lost traction, and how the cadence evolved."""

_YEARLY_PERIODS_KEY = """,
  "periods": [{{"label": "2026-03", "verdict": "average", "summary": "1–2 sentences on that month"}}]"""

MAX_YEARLY_POST_ANALYSES = 40

_HUMAN = """\
Workspace: {workspace_name}
Period: {date_from} to {date_to}
Previous period: {previous_date_from} to {previous_date_to}

=== Totals this period ===
{totals_text}

=== Totals previous period ===
{previous_totals_text}

=== Per-platform this period ===
{platforms_text}

=== Per-platform previous period ===
{previous_platforms_text}

=== Post benchmarks per platform (this period) ===
{benchmarks_text}

=== Posts ({post_count}{posts_note}) ===
{posts_text}
{monthly_text}"""


def build_analysis_prompt(kind: AnalysisKind) -> ChatPromptTemplate:
    rules = {
        AnalysisKind.standard: (_STANDARD_POSTS_RULE, ""),
        AnalysisKind.yearly: (
            _YEARLY_POSTS_RULE.replace(
                "{max_post_analyses}", str(MAX_YEARLY_POST_ANALYSES)
            ),
            _YEARLY_PERIODS_KEY,
        ),
    }
    posts_rule, periods_key = rules[kind]
    system = _SYSTEM.replace("{posts_rule}", posts_rule).replace(
        "{periods_key}", periods_key
    )
    return ChatPromptTemplate.from_messages([("system", system), ("human", _HUMAN)])


def build_analysis_chain(
    kind: AnalysisKind = AnalysisKind.standard,
) -> RunnableSerializable[dict[str, Any], Any]:
    """Prompt variables in (see app.services.analysis), parsed JSON out."""
    return build_analysis_prompt(kind) | get_llm() | StrOutputParser() | parse_json


def _valid_items[ModelT: BaseModel](
    model: type[ModelT], raw: Any, prepare: Any = None
) -> list[ModelT]:
    """Validate each item of a list, dropping malformed ones rather than failing."""
    items = []
    for item in raw if isinstance(raw, list) else []:
        try:
            items.append(model.model_validate(prepare(item) if prepare else item))
        except ValidationError, TypeError, KeyError, AttributeError:
            logger.warning("Dropping malformed %s from the model: %r", model, item)
    return items


def to_result(raw: Any, post_refs: dict[str, uuid.UUID]) -> AnalysisResult:
    """
    Validate the model's JSON. Post references are mapped to post ids, and
    references to posts we didn't send are dropped. Raises ValueError when the
    output has no summary: then there's nothing worth showing.
    """
    if not isinstance(raw, dict) or not isinstance(raw.get("summary"), str):
        raise ValueError("The model's answer is not a valid analysis")

    def post_item(item: dict[str, Any]) -> dict[str, Any]:
        return {**item, "post_id": post_refs[item["ref"]]}

    def topic_item(item: dict[str, Any]) -> dict[str, Any]:
        refs = item.get("posts") or []
        return {**item, "post_ids": [post_refs[r] for r in refs if r in post_refs]}

    posts = _valid_items(PostAnalysis, raw.get("posts"), post_item)
    # Keep the first analysis of each post if the model repeated one
    unique_posts = list({p.post_id: p for p in reversed(posts)}.values())[::-1]

    return AnalysisResult(
        summary=raw["summary"],
        what_worked=_valid_items(Finding, raw.get("what_worked")),
        what_didnt_work=_valid_items(Finding, raw.get("what_didnt_work")),
        recommendations=_valid_items(Recommendation, raw.get("recommendations")),
        platforms=_valid_items(PlatformAnalysis, raw.get("platforms")),
        topics=_valid_items(TopicAnalysis, raw.get("topics"), topic_item),
        posts=unique_posts,
        periods=_valid_items(PeriodAnalysis, raw.get("periods")),
    )
