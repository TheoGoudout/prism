import uuid

import pytest

from app.ai.analysis import to_result

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
