"""Activity log sanitize, filters, and CSV — no secrets in metadata."""

from __future__ import annotations

from pathlib import Path

from backend.activity.log_activity import (
    ACTION_GROUPS,
    ActivityStore,
    export_activity_csv,
    human_action_label,
    sanitize_metadata,
)


def test_sanitize_strips_secrets_and_truncates_tokens() -> None:
    raw = {
        "password": "hunter2",
        "password_hash": "abc",
        "invite_token": "ABCDEFGHIJKL",
        "token": "XYZTOKEN99",
        "DATABASE_URL": "sqlite:///secret.db",
        "ADMIN_PASSWORD": "nope",
        "summary": "ok",
    }
    clean = sanitize_metadata(raw)
    assert "password" not in clean
    assert "password_hash" not in clean
    assert "DATABASE_URL" not in clean
    assert "ADMIN_PASSWORD" not in clean
    assert clean["invite_token"] == "…IJKL"
    assert clean["token"] == "…EN99"
    assert clean["summary"] == "ok"


def test_problems_only_and_csv(tmp_path: Path) -> None:
    store = ActivityStore(tmp_path / "app.db")
    actor = {"id": 1, "email": "jane@example.com", "role": "sales"}
    store.log_activity(
        actor,
        action="auth.login.failure",
        status="failure",
        summary="bad password",
        resource_type="auth",
    )
    store.log_activity(
        actor,
        action="quote.line.add",
        status="success",
        summary="added chair",
        resource_type="quote",
        resource_id="9",
    )
    store.log_activity(
        actor,
        action="quote.view.denied",
        status="denied",
        summary="not owner",
        resource_type="quote",
        resource_id="2",
    )
    problems = store.list_events(problems_only=True)
    assert [r.action for r in problems] == ["quote.view.denied", "auth.login.failure"]
    jane = store.list_events(actor_id=1)
    assert len(jane) == 3
    csv_text = export_activity_csv(problems)
    assert csv_text.splitlines()[0].startswith("created_at")
    assert "auth.login.failure" in csv_text
    assert "quote.line.add" not in csv_text
    assert human_action_label("quote.view.denied") == "Quote view denied"
    assert "Auth" in ACTION_GROUPS
