import uuid

import pytest

from app.ai.analysis import (
    MAX_YEARLY_POST_ANALYSES,
    build_analysis_prompt,
    to_result,
)
from app.models.analysis import AnalysisKind

P1, P2 = uuid.uuid4(), uuid.uuid4()
REFS = {"P1": P1, "P2": P2}


def test_to_result_maps_post_references() -> None:
    raw = {
        "summary": "A good week.",
        "what_worked": [{"title": "Reels", "detail": "Reels doubled reach."}],
        "what_didnt_work": [{"title": "Links", "detail": "Link posts flopped."}],
        "recommendations": [
            {"title": "More reels", "detail": "Post 3 a week.", "priority": "high"}
        ],
        "platforms": [
            {"platform": "instagram", "verdict": "strong", "summary": "Up 20%."}
        ],
        "topics": [
            {
                "name": "Launch",
                "verdict": "strong",
                "summary": "The launch posts led.",
                "posts": ["P1", "P2", "P9"],
            }
        ],
        "posts": [
            {
                "ref": "P1",
                "verdict": "strong",
                "topic": "Launch",
                "analysis": "Top post.",
                "suggestion": None,
            },
            {"ref": "P2", "verdict": "weak", "analysis": "Posted at 3am."},
        ],
    }
    result = to_result(raw, REFS)

    assert result.summary == "A good week."
    assert result.recommendations[0].priority == "high"
    # Unknown references are dropped
    assert result.topics[0].post_ids == [P1, P2]
    assert [(p.post_id, p.verdict) for p in result.posts] == [
        (P1, "strong"),
        (P2, "weak"),
    ]


def test_to_result_drops_malformed_items() -> None:
    raw = {
        "summary": "Mixed.",
        "what_worked": [{"title": "No detail"}, "text", {"title": "a", "detail": "b"}],
        "platforms": [{"platform": "x", "verdict": "amazing", "summary": "?"}],
        "posts": [
            {"ref": "P7", "verdict": "weak", "analysis": "Unknown post."},
            {"ref": "P1", "verdict": "weak", "analysis": "First."},
            {"ref": "P1", "verdict": "strong", "analysis": "Duplicate."},
            {"verdict": "weak", "analysis": "No reference."},
        ],
        "topics": "not a list",
    }
    result = to_result(raw, REFS)

    assert [f.title for f in result.what_worked] == ["a"]
    assert result.platforms == []
    assert result.topics == []
    assert [(p.post_id, p.analysis) for p in result.posts] == [(P1, "First.")]


@pytest.mark.parametrize("raw", [[], {"what_worked": []}, {"summary": 3}])
def test_to_result_requires_a_summary(raw: object) -> None:
    with pytest.raises(ValueError):
        to_result(raw, REFS)


def test_to_result_parses_periods() -> None:
    raw = {
        "summary": "Year in review.",
        "periods": [
            {"label": "2026-01", "verdict": "weak", "summary": "Slow start."},
            {"label": "2026-02", "verdict": "excellent", "summary": "Bad verdict."},
        ],
    }
    assert [p.label for p in to_result(raw, REFS).periods] == ["2026-01"]


def test_yearly_prompt_asks_for_months_and_notable_posts() -> None:
    standard = build_analysis_prompt(AnalysisKind.standard).messages[0]
    yearly = build_analysis_prompt(AnalysisKind.yearly).messages[0]
    standard_text = standard.prompt.template  # type: ignore[union-attr]
    yearly_text = yearly.prompt.template  # type: ignore[union-attr]

    assert "Analyze every post exactly once." in standard_text
    assert '"periods"' not in standard_text
    assert '"periods"' in yearly_text
    assert f"at most {MAX_YEARLY_POST_ANALYSES}" in yearly_text
    assert "{posts_rule}" not in yearly_text
