"""Render workspace metrics as plain text for the LLM prompts, and parse answers."""

import json
from collections.abc import Sequence
from typing import Any

from app.models.metrics import MetricsSummary, MetricTotals, Post
from app.services.metrics import MetricsQuery


def _metric_lines(totals: MetricTotals, indent: str) -> list[str]:
    """One line per non-zero metric, e.g. "  impressions: 1,234"."""
    return [
        f"{indent}{name}: {value:,}"
        for name, value in totals.model_dump().items()
        if value  # skip zeros and unknowns: they only add noise
    ]


def prompt_variables(
    *, workspace_name: str, query: MetricsQuery, summary: MetricsSummary
) -> dict[str, Any]:
    """Template variables shared by every prompt."""
    platform_blocks = [
        "\n".join([f"  [{platform}]", *_metric_lines(totals, "    ")])
        for platform, totals in summary.by_platform.items()
    ]
    return {
        "workspace_name": workspace_name,
        "date_from": query.date_from.isoformat(),
        "date_to": query.date_to.isoformat(),
        "platform_context": (
            f" · platform filter: {query.platform.value}" if query.platform else ""
        ),
        "totals_text": "\n".join(_metric_lines(summary.totals, "  ")) or "  (no data)",
        "platforms_text": "\n".join(platform_blocks) or "  (no platform data)",
    }


def format_posts(posts: Sequence[Post]) -> str:
    if not posts:
        return "  (no posts)"
    lines = []
    for rank, post in enumerate(posts, 1):
        snippet = (post.text or "")[:80].replace("\n", " ")
        lines.append(
            f"  {rank}. [{post.content_type.value}] "
            f"engagements={post.engagements or 0:,}  — {snippet!r}"
        )
    return "\n".join(lines)


def parse_json(text: str) -> Any:
    """Parse a JSON answer, stripping markdown fences in case the model added them."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return json.loads(text)
