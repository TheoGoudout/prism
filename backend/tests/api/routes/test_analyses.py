"""Tests for the /analyses and /analysis-schedule endpoints."""

import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlmodel import Session

from app import crud
from app.core.config import settings
from app.models.analysis import AnalysisStatus, PerformanceAnalysis
from app.models.integration import Platform
from app.models.metrics import ContentType, PostUpsert
from app.models.workspace import Workspace, WorkspaceRole
from tests.utils.integration import create_fake_account, create_fake_integration
from tests.utils.user import create_user_with_headers
from tests.utils.workspace import add_member, create_random_workspace

RUN_ANALYSIS = "app.worker.tasks.analysis.run_analysis"


def _url(workspace: Workspace, path: str = "analyses") -> str:
    return f"{settings.API_V1_STR}/workspaces/{workspace.id}/{path}"


def _viewer(client: TestClient, db: Session, workspace: Workspace) -> dict[str, str]:
    viewer, headers = create_user_with_headers(client, db)
    add_member(db, workspace, viewer, WorkspaceRole.viewer)
    return headers


def _completed_analysis(db: Session, workspace: Workspace) -> PerformanceAnalysis:
    account = create_fake_account(
        db, create_fake_integration(db, workspace, platform=Platform.tiktok)
    )
    post = crud.upsert_post(
        session=db,
        platform_account_id=account.id,
        post_in=PostUpsert(
            external_id="v1",
            content_type=ContentType.video,
            text="Behind the scenes",
            published_at=datetime(2026, 9, 2, tzinfo=UTC),
            engagements=120,
        ),
    )
    result = {
        "summary": "Video drove the week.",
        "topics": [
            {
                "name": "BTS",
                "verdict": "strong",
                "summary": "Loved.",
                "post_ids": [str(post.id)],
            }
        ],
        "posts": [
            {"post_id": str(post.id), "verdict": "strong", "analysis": "Top."},
            # A post deleted since the analysis ran
            {"post_id": str(uuid.uuid4()), "verdict": "weak", "analysis": "Gone."},
        ],
    }
    return crud.save(
        db,
        PerformanceAnalysis(
            workspace_id=workspace.id,
            date_from=date(2026, 9, 1),
            date_to=date(2026, 9, 7),
            status=AnalysisStatus.completed,
            result=result,
            post_count=1,
        ),
    )


# ---------------------------------------------------------------------------
# Analyses
# ---------------------------------------------------------------------------


def test_create_analysis_enqueues_it(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    with patch(RUN_ANALYSIS) as task:
        r = client.post(_url(ws), headers=headers, json={})

    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "pending"
    assert body["trigger"] == "manual"
    assert body["date_to"] == date.today().isoformat()
    assert body["date_from"] == (date.today() - timedelta(days=6)).isoformat()
    task.delay.assert_called_once_with(body["id"])

    # Only one analysis at a time
    with patch(RUN_ANALYSIS):
        r = client.post(_url(ws), headers=headers, json={})
    assert r.status_code == 409


def test_create_analysis_viewer_with_dates(client: TestClient, db: Session) -> None:
    owner, _ = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    headers = _viewer(client, db, ws)

    with patch(RUN_ANALYSIS):
        r = client.post(
            _url(ws),
            headers=headers,
            json={"date_from": "2026-08-01", "date_to": "2026-08-31"},
        )
    assert r.status_code == 202
    assert (r.json()["date_from"], r.json()["date_to"]) == ("2026-08-01", "2026-08-31")


def test_create_analysis_rejects_inverted_dates(
    client: TestClient, db: Session
) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    with patch(RUN_ANALYSIS) as task:
        r = client.post(
            _url(ws),
            headers=headers,
            json={"date_from": "2026-08-31", "date_to": "2026-08-01"},
        )
        r_future = client.post(
            _url(ws),
            headers=headers,
            json={"date_from": (date.today() + timedelta(days=3)).isoformat()},
        )
    assert r.status_code == 422
    assert r_future.status_code == 422
    task.delay.assert_not_called()


def test_non_member_cannot_access_analyses(client: TestClient, db: Session) -> None:
    owner, _ = create_user_with_headers(client, db)
    _, outsider_headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)
    analysis = _completed_analysis(db, ws)

    assert client.get(_url(ws), headers=outsider_headers).status_code == 404
    r = client.get(_url(ws, f"analyses/{analysis.id}"), headers=outsider_headers)
    assert r.status_code == 404


def test_read_analysis_includes_result_and_posts(
    client: TestClient, db: Session
) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    analysis = _completed_analysis(db, ws)

    r = client.get(_url(ws, f"analyses/{analysis.id}"), headers=headers)

    assert r.status_code == 200
    body = r.json()
    assert body["result"]["summary"] == "Video drove the week."
    assert len(body["result"]["posts"]) == 2
    assert [(p["platform"], p["text"]) for p in body["posts"]] == [
        ("tiktok", "Behind the scenes")
    ]


def test_analysis_of_another_workspace_is_not_found(
    client: TestClient, db: Session
) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    other = create_random_workspace(db, user)
    analysis = _completed_analysis(db, other)

    r = client.get(_url(ws, f"analyses/{analysis.id}"), headers=headers)
    assert r.status_code == 404


def test_list_analyses(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    first = _completed_analysis(db, ws)
    with patch(RUN_ANALYSIS):
        second = client.post(_url(ws), headers=headers, json={}).json()

    r = client.get(_url(ws), headers=headers)

    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    assert [a["id"] for a in body["data"]] == [second["id"], str(first.id)]
    assert "result" not in body["data"][0]


def test_delete_analysis_requires_manager(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    analysis = _completed_analysis(db, ws)
    url = _url(ws, f"analyses/{analysis.id}")

    assert client.delete(url, headers=_viewer(client, db, ws)).status_code == 403
    assert client.delete(url, headers=headers).status_code == 204
    assert client.get(url, headers=headers).status_code == 404


def test_email_analysis_to_current_user(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    analysis = _completed_analysis(db, ws)

    with (
        patch("app.core.config.settings.SMTP_HOST", "smtp.example.com"),
        patch("app.core.config.settings.EMAILS_FROM_EMAIL", "admin@example.com"),
        patch("app.services.analysis.send_email") as send_email,
    ):
        r = client.post(_url(ws, f"analyses/{analysis.id}/email"), headers=headers)

    assert r.status_code == 204
    send_email.assert_called_once()
    kwargs = send_email.call_args.kwargs
    assert kwargs["email_to"] == user.email
    assert "Video drove the week." in kwargs["html_content"]


def test_email_unfinished_analysis_is_rejected(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    with patch(RUN_ANALYSIS):
        analysis = client.post(_url(ws), headers=headers, json={}).json()

    r = client.post(_url(ws, f"analyses/{analysis['id']}/email"), headers=headers)
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

SCHEDULE = {
    "enabled": True,
    "frequency": "weekly",
    "weekday": 0,
    "hour": 8,
    "timezone": "Europe/Paris",
    "email_enabled": True,
    "email_recipients": ["team@example.com"],
}


def test_schedule_defaults_to_disabled(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    r = client.get(_url(ws, "analysis-schedule"), headers=headers)

    assert r.status_code == 200
    assert r.json()["enabled"] is False
    assert r.json()["next_run_at"] is None


def test_update_schedule(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)

    r = client.put(_url(ws, "analysis-schedule"), headers=headers, json=SCHEDULE)

    assert r.status_code == 200
    body = r.json()
    assert body["email_recipients"] == ["team@example.com"]
    next_run = datetime.fromisoformat(body["next_run_at"])
    assert next_run > datetime.now(UTC)
    assert next_run.astimezone(UTC).hour in (6, 7)  # 8am in Paris, DST or not

    # Changing only the recipients keeps the next run
    r = client.put(
        _url(ws, "analysis-schedule"),
        headers=headers,
        json={**SCHEDULE, "email_recipients": []},
    )
    assert r.json()["next_run_at"] == body["next_run_at"]

    # Disabling clears it
    r = client.put(
        _url(ws, "analysis-schedule"),
        headers=headers,
        json={**SCHEDULE, "enabled": False},
    )
    assert r.json()["next_run_at"] is None
    assert (
        client.get(_url(ws, "analysis-schedule"), headers=headers).json()["enabled"]
        is False
    )


def test_update_schedule_validation(client: TestClient, db: Session) -> None:
    user, headers = create_user_with_headers(client, db)
    ws = create_random_workspace(db, user)
    url = _url(ws, "analysis-schedule")

    for invalid in (
        {"timezone": "Mars/Olympus"},
        {"hour": 24},
        {"weekday": 7},
        {"day_of_month": 31},
        {"email_recipients": ["not-an-email"]},
        {"email_recipients": [f"u{i}@example.com" for i in range(21)]},
    ):
        r = client.put(url, headers=headers, json={**SCHEDULE, **invalid})
        assert r.status_code == 422, invalid


def test_update_schedule_requires_manager(client: TestClient, db: Session) -> None:
    owner, _ = create_user_with_headers(client, db)
    ws = create_random_workspace(db, owner)

    r = client.put(
        _url(ws, "analysis-schedule"),
        headers=_viewer(client, db, ws),
        json=SCHEDULE,
    )
    assert r.status_code == 403
