import uuid
from datetime import UTC, date, datetime

from app.ai.formatting import format_posts, parse_json, prompt_variables
from app.ai.insights import to_insights
from app.models.integration import Platform
from app.models.metrics import ContentType, MetricsSummary, MetricTotals, PostPublic
from app.services.metrics import MetricsQuery

QUERY = MetricsQuery(
    uuid.uuid4(), Platform.twitter, date(2024, 1, 1), date(2024, 1, 31)
)


def test_prompt_variables_skip_zero_metrics() -> None:
    summary = MetricsSummary(
        totals=MetricTotals(impressions=1500, likes=0),
        by_platform={"twitter": MetricTotals(impressions=1500)},
        date_from=QUERY.date_from,
        date_to=QUERY.date_to,
    )
    variables = prompt_variables(workspace_name="Acme", query=QUERY, summary=summary)

    assert variables["workspace_name"] == "Acme"
    assert variables["date_from"] == "2024-01-01"
    assert variables["platform_context"] == " · platform filter: twitter"
    assert variables["totals_text"] == "  impressions: 1,500"
    assert variables["platforms_text"] == "  [twitter]\n    impressions: 1,500"


def test_prompt_variables_format_engagement_rate_as_percentage() -> None:
    summary = MetricsSummary(
        totals=MetricTotals(exposures=2000, engagements=50, engagement_rate=0.025),
        by_platform={},
        date_from=QUERY.date_from,
        date_to=QUERY.date_to,
    )
    variables = prompt_variables(workspace_name="Acme", query=QUERY, summary=summary)
    assert variables["totals_text"] == (
        "  exposures: 2,000\n  engagements: 50\n  engagement_rate: 2.50%"
    )
    assert "engagement_rate: engagements / exposures" in variables["metric_definitions"]


def test_prompt_variables_without_data() -> None:
    summary = MetricsSummary(
        totals=MetricTotals(),
        by_platform={},
        date_from=QUERY.date_from,
        date_to=QUERY.date_to,
    )
    variables = prompt_variables(workspace_name="Acme", query=QUERY, summary=summary)
    assert variables["totals_text"] == "  (no data)"
    assert variables["platforms_text"] == "  (no platform data)"


def test_format_posts() -> None:
    post = PostPublic(
        id=uuid.uuid4(),
        platform_account_id=uuid.uuid4(),
        platform=Platform.twitter,
        external_id="1",
        content_type=ContentType.tweet,
        published_at=datetime(2024, 1, 2, tzinfo=UTC),
        text="Hello\nworld",
        engagements=1234,
    )
    assert (
        format_posts([post])
        == "  1. [twitter tweet] engagements=1,234  — 'Hello world'"
    )
    assert format_posts([]) == "  (no posts)"


def test_parse_json_strips_markdown_fences() -> None:
    assert parse_json('```json\n[{"a": 1}]\n```') == [{"a": 1}]


def test_to_insights_drops_malformed_items() -> None:
    raw = [
        {"title": "Up", "body": "Reach grew", "type": "positive", "metric": "reach"},
        {"title": "Bad type", "body": "x", "type": "unknown"},
        "not an object",
    ]
    insights = to_insights(raw)
    assert [i.title for i in insights] == ["Up"]
    assert to_insights({"not": "a list"}) == []
