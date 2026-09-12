"""Signed login tokens survive a page reload; Sign out forgets them."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.auth import login_user, session_from_user
from backend.auth.store import AuthStore
from backend.login_session import (
    COOKIE_NAME,
    clear_persisted_token,
    ensure_travel_login_token,
    issue_login_token,
    load_persisted_token,
    login_secret,
    may_use_persisted_login,
    persist_token,
    restore_login_session,
)


def _db(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.delenv("PRICEBOOK_APP_DB", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    catalog = tmp_path / "users.db"
    app = tmp_path / "pricebook_app.db"
    AuthStore(app).insert_user(
        email="judson@example.com",
        password="secret-pass",
        name="Judson",
        role="admin",
    )
    return catalog


def test_reload_restores_the_same_signed_in_user(tmp_path: Path, monkeypatch) -> None:
    db = _db(tmp_path, monkeypatch)
    session = login_user("judson@example.com", "secret-pass", db_path=db)
    assert session is not None
    token = issue_login_token(session, secret="unit-test-secret")
    restored = restore_login_session(token, secret="unit-test-secret", db_path=db)
    assert restored is not None
    assert restored["email"] == "judson@example.com"
    assert restored["display_name"] == "Judson"
    assert restored["role"] == "admin"
    assert restored["user_id"] == session["user_id"]
    assert "password_hash" not in restored


def test_tampered_or_expired_token_does_not_sign_in(tmp_path: Path, monkeypatch) -> None:
    db = _db(tmp_path, monkeypatch)
    session = login_user("judson@example.com", "secret-pass", db_path=db)
    token = issue_login_token(session, secret="unit-test-secret")
    replacement = "0" if token[-1] != "0" else "1"
    tampered = token[:-1] + replacement
    assert restore_login_session(tampered, secret="unit-test-secret", db_path=db) is None
    assert restore_login_session(token, secret="other-secret", db_path=db) is None
    expired = issue_login_token(
        session,
        secret="unit-test-secret",
        now=datetime.now(timezone.utc) - timedelta(days=400),
    )
    assert restore_login_session(expired, secret="unit-test-secret", db_path=db) is None


def test_deactivated_user_cannot_come_back_on_reload(tmp_path: Path, monkeypatch) -> None:
    db = _db(tmp_path, monkeypatch)
    session = login_user("judson@example.com", "secret-pass", db_path=db)
    token = issue_login_token(session, secret="unit-test-secret")
    store = AuthStore(tmp_path / "pricebook_app.db")
    admin = store.get_by_email("judson@example.com")
    assert admin is not None
    extra = store.insert_user(
        email="other@example.com",
        password="other-pass1",
        role="admin",
        name="Other",
    )
    store.set_active(extra, admin.id, False)
    assert restore_login_session(token, secret="unit-test-secret", db_path=db) is None


def test_sign_out_clears_the_persisted_token(tmp_path: Path) -> None:
    persist_token("abc.token", root=tmp_path)
    assert load_persisted_token(root=tmp_path) == "abc.token"
    clear_persisted_token(root=tmp_path)
    assert load_persisted_token(root=tmp_path) == ""
    assert COOKIE_NAME == "faf_login"


def test_traveling_drive_restores_login_without_a_browser_cookie(
    tmp_path: Path, monkeypatch
) -> None:
    db = _db(tmp_path, monkeypatch)
    monkeypatch.setenv("FAF_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FAF_DB_PATH", str(db))
    monkeypatch.delenv("FLY_APP_NAME", raising=False)
    monkeypatch.delenv("FLY_ALLOC_ID", raising=False)
    assert may_use_persisted_login(local_browser=False) is True
    assert ensure_travel_login_token(root=tmp_path, db_path=db) is True
    token = load_persisted_token(root=tmp_path)
    assert token
    restored = restore_login_session(token, secret=login_secret(root=tmp_path), db_path=db)
    assert restored is not None
    assert restored["email"] == "judson@example.com"
    assert restored["role"] == "admin"


def test_fly_does_not_use_a_persisted_drive_login(monkeypatch) -> None:
    monkeypatch.delenv("FAF_DATA_DIR", raising=False)
    monkeypatch.setenv("FLY_APP_NAME", "faf-pricebook")
    assert may_use_persisted_login(local_browser=True) is False


def test_session_from_user_drops_the_password_hash() -> None:
    session = session_from_user(
        {
            "id": 3,
            "username": "floor",
            "display_name": "Floor",
            "role": "floor",
            "must_change_password": 0,
            "source": "local",
            "password_hash": "should-not-leak",
            "ordertrac_user_guid": None,
            "ordertrac_display_name": None,
        }
    )
    assert session["user_id"] == 3
    assert "password_hash" not in session
    assert session["email"] == "floor@faf.local"
