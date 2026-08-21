"""Signed login tokens survive a page reload; Sign out forgets them."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.auth import login_user, session_from_user
from backend.db import init_db
from backend.login_session import (
    COOKIE_NAME,
    clear_persisted_token,
    issue_login_token,
    load_persisted_token,
    persist_token,
    restore_login_session,
)
from backend.users import UserRepository


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "users.db"
    init_db(path)
    repo = UserRepository(path)
    repo.create_user(
        username="judson",
        password="secret",
        display_name="Judson",
        role="admin",
        must_change_password=False,
        active=True,
    )
    return path


def test_reload_restores_the_same_signed_in_user(tmp_path: Path) -> None:
    db = _db(tmp_path)
    session = login_user("judson", "secret", db_path=db)
    assert session is not None
    token = issue_login_token(session, secret="unit-test-secret")
    restored = restore_login_session(token, secret="unit-test-secret", db_path=db)
    assert restored is not None
    assert restored["username"] == "judson"
    assert restored["display_name"] == "Judson"
    assert restored["role"] == "admin"
    assert restored["user_id"] == session["user_id"]
    assert "password_hash" not in restored


def test_tampered_or_expired_token_does_not_sign_in(tmp_path: Path) -> None:
    db = _db(tmp_path)
    session = login_user("judson", "secret", db_path=db)
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


def test_deactivated_user_cannot_come_back_on_reload(tmp_path: Path) -> None:
    db = _db(tmp_path)
    session = login_user("judson", "secret", db_path=db)
    token = issue_login_token(session, secret="unit-test-secret")
    UserRepository(db).update_user(int(session["user_id"]), active=False)
    assert restore_login_session(token, secret="unit-test-secret", db_path=db) is None


def test_sign_out_clears_the_persisted_token(tmp_path: Path) -> None:
    persist_token("abc.token", root=tmp_path)
    assert load_persisted_token(root=tmp_path) == "abc.token"
    clear_persisted_token(root=tmp_path)
    assert load_persisted_token(root=tmp_path) == ""
    assert COOKIE_NAME == "faf_login"


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
