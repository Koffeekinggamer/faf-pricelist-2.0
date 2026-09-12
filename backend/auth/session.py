"""Session dict helpers for Streamlit cookies."""

from __future__ import annotations

from typing import Mapping

from backend.auth.roles import SessionUser, email_local_part, parse_role


def session_from_user(user: Mapping[str, object] | SessionUser) -> dict[str, object]:
    """Floor session. Never includes password_hash."""
    if isinstance(user, SessionUser):
        email = user.email
        name = user.name or email_local_part(email)
        return {
            "user_id": user.id,
            "email": email,
            "name": name,
            "username": email,
            "display_name": name,
            "role": user.role,
            "active": user.active,
            "must_change_password": user.must_change_password,
        }
    email = str(user.get("email") or "").strip().lower()
    username = str(user.get("username") or "").strip()
    if not email and username and "@" in username:
        email = username.lower()
    if not email and username:
        email = f"{username.lower()}@faf.local"
    name = str(user.get("name") or user.get("display_name") or email_local_part(email) or username)
    user_id = user.get("id") if user.get("id") is not None else user.get("user_id")
    return {
        "user_id": int(user_id) if user_id is not None else None,
        "email": email,
        "name": name,
        "username": email or username,
        "display_name": name,
        "role": parse_role(user.get("role")),
        "active": bool(user.get("active", True)),
        "must_change_password": bool(user.get("must_change_password")),
        "source": user.get("source") or "local",
        "ordertrac_user_guid": user.get("ordertrac_user_guid"),
        "ordertrac_display_name": user.get("ordertrac_display_name"),
    }


def user_from_session(session: Mapping[str, object] | None) -> SessionUser | None:
    if not session:
        return None
    user_id = session.get("user_id") or session.get("id")
    email = str(session.get("email") or session.get("username") or "").strip().lower()
    if user_id is None or not email:
        return None
    return SessionUser(
        id=int(user_id),
        email=email,
        name=str(session.get("name") or session.get("display_name") or email_local_part(email)),
        role=parse_role(session.get("role")),
        active=bool(session.get("active", True)),
        must_change_password=bool(session.get("must_change_password")),
    )
