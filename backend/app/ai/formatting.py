"""Render workspace metrics as plain text for the LLM prompts."""

from collections.abc import Sequence
from typing import Any

from app.models.metrics import MetricsSummary, MetricTotals, PostPublic
from app.services.metrics import MetricsQuery

# How the cross-platform metrics are defined, for the model's benefit
METRIC_DEFINITIONS = """\
- exposures: views, or impressions where a platform only reports impressions
- engagements: likes + comments + shares + saves (engaged sessions for websites)
- engagement_rate: engagements / exposures
- reach: unique people per day, summed over the days (not deduplicated)"""


def _format_value(name: str, value: float) -> str:
    return f"{value:.2%}" if name == "engagement_rate" else f"{value:,}"


def _metric_lines(totals: MetricTotals, indent: str) -> list[str]:
    """One line per non-zero metric, e.g. "  impressions: 1,234"."""
    return [
        f"{indent}{name}: {_format_value(name, value)}"
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
        "metric_definitions": METRIC_DEFINITIONS,
        "date_from": query.date_from.isoformat(),
        "date_to": query.date_to.isoformat(),
        "platform_context": (
            f" · platform filter: {query.platform.value}" if query.platform else ""
        ),
        "totals_text": "\n".join(_metric_lines(summary.totals, "  ")) or "  (no data)",
        "platforms_text": "\n".join(platform_blocks) or "  (no platform data)",
    }


def format_posts(posts: Sequence[PostPublic]) -> str:
    if not posts:
        return "  (no posts)"
    lines = []
    for rank, post in enumerate(posts, 1):
        snippet = (post.text or "")[:80].replace("\n", " ")
        lines.append(
            f"  {rank}. [{post.platform.value} {post.content_type.value}] "
            f"engagements={post.engagements or 0:,}  — {snippet!r}"
        )
    return "\n".join(lines)
