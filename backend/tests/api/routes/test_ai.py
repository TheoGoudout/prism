"""
Tests for POST /ai/insights and /ai/report.

The LLM is mocked so tests run without a real API key and deterministically.
"""

import json
from datetime import date
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.models.integration import Platform
from app.models.metrics import MetricSnapshotUpsert
from app.models.workspace import Workspace
from tests.utils.integration import create_fake_account, create_fake_integration
from tests.utils.user import create_user_with_headers
from tests.utils.workspace import create_random_workspace


def _url(workspace: Workspace, path: str) -> str:
    return f"{settings.API_V1_STR}/workspaces/{workspace.id}/ai/{path}"


TODAY = date.today()

_FAKE_INSIGHTS = json.dumps(
    [
        {
            "title": "Strong reach growth",
            "body": "Reach increased 20%.",
            "type": "positive",
            "metric": "reach",
        },
        {
            "title": "Low engagement rate",
            "body": "Engagement rate is below average.",
            "type": "negative",
            "metric": "engagements",
        },
    ]
)
_FAKE_REPORT = "## Executive Summary\nGood performance overall.\n## Recommendations\n- Post more reels."


# ---------------------------------------------------------------------------
# /ai/insights
# ---------------------------------------------------------------------------


def test_insights_non_member_returns_404(client: TestClient, db: Session) -> None:
    owner, _ = create_user_with_headers(client, db)
    outsider, outsider_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)

    r = client.post(
        _url(ws, "insights"),
        headers=outsider_headers,
    )
    assert r.status_code == 404


def test_insights_returns_structured_response(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    parsed = json.loads(_FAKE_INSIGHTS)
    mock_chain = MagicMock()
    mock_chain.invoke.return_value = parsed

    with patch("app.api.routes.ai.build_insights_chain", return_value=mock_chain):
        r = client.post(
            _url(ws, "insights"),
            headers=headers,
        )

    assert r.status_code == 200
    body = r.json()
    assert "insights" in body
    assert "generated_at" in body
    assert isinstance(body["insights"], list)
    assert len(body["insights"]) == 2
    assert body["insights"][0]["type"] == "positive"
    assert body["insights"][1]["type"] == "negative"


def test_insights_with_metrics_data(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    # Seed real metric data
    integration = create_fake_integration(db, ws, platform=Platform.instagram)
    account = create_fake_account(db, integration)
    from app import crud

    crud.upsert_metric_snapshot(
        session=db,
        platform_account_id=account.id,
        snapshot_in=MetricSnapshotUpsert(
            date=TODAY, impressions=500, engagements=40, followers_count=2000
        ),
    )
    db.commit()

    parsed = json.loads(_FAKE_INSIGHTS)
    mock_chain = MagicMock()
    mock_chain.invoke.return_value = parsed

    with patch("app.api.routes.ai.build_insights_chain", return_value=mock_chain):
        r = client.post(
            _url(ws, "insights"),
            headers=headers,
            params={
                "date_from": str(TODAY),
                "date_to": str(TODAY),
            },
        )

    assert r.status_code == 200
    assert len(r.json()["insights"]) > 0


def test_insights_llm_error_returns_502(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    mock_chain = MagicMock()
    mock_chain.invoke.side_effect = RuntimeError("LLM unavailable")

    with patch("app.api.routes.ai.build_insights_chain", return_value=mock_chain):
        r = client.post(
            _url(ws, "insights"),
            headers=headers,
        )

    assert r.status_code == 502
    assert "AI generation failed" in r.json()["detail"]


# ---------------------------------------------------------------------------
# /ai/report
# ---------------------------------------------------------------------------


def test_report_non_member_returns_404(client: TestClient, db: Session) -> None:
    owner, _ = create_user_with_headers(client, db)
    outsider, outsider_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)

    r = client.post(
        _url(ws, "report"),
        headers=outsider_headers,
    )
    assert r.status_code == 404


def test_report_returns_markdown(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    mock_chain = MagicMock()
    mock_chain.invoke.return_value = _FAKE_REPORT

    with patch("app.api.routes.ai.build_report_chain", return_value=mock_chain):
        r = client.post(
            _url(ws, "report"),
            headers=headers,
        )

    assert r.status_code == 200
    body = r.json()
    assert "report" in body
    assert "generated_at" in body
    assert "## Executive Summary" in body["report"]


def test_report_llm_error_returns_502(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    mock_chain = MagicMock()
    mock_chain.invoke.side_effect = RuntimeError("timeout")

    with patch("app.api.routes.ai.build_report_chain", return_value=mock_chain):
        r = client.post(
            _url(ws, "report"),
            headers=headers,
        )

    assert r.status_code == 502


def test_report_with_platform_filter(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    mock_chain = MagicMock()
    mock_chain.invoke.return_value = _FAKE_REPORT

    with patch("app.api.routes.ai.build_report_chain", return_value=mock_chain):
        r = client.post(
            _url(ws, "report"),
            headers=headers,
            params={"platform": "instagram"},
        )

    assert r.status_code == 200


def test_insights_invalid_workspace_id_returns_422(
    client: TestClient, db: Session
) -> None:
    _, headers = create_user_with_headers(client, db)
    r = client.post(
        f"{settings.API_V1_STR}/workspaces/not-a-uuid/ai/insights", headers=headers
    )
    assert r.status_code == 422
