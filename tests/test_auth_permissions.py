"""Role matrix and last-admin guards."""

from __future__ import annotations

from backend.auth.permissions import can
from backend.auth.roles import Role, SessionUser


def _user(role: Role, user_id: int = 1, active: bool = True) -> SessionUser:
    return SessionUser(
        id=user_id,
        email=f"{role}@example.com",
        name=role,
        role=role,
        active=active,
    )


def test_permission_matrix() -> None:
    admin = _user("admin")
    manager = _user("manager")
    sales = _user("sales")
    viewer = _user("viewer")
    assert can(viewer, "catalog.view")
    assert not can(viewer, "quote.create")
    assert can(sales, "quote.create")
    assert can(sales, "quote.edit.own")
    assert not can(sales, "quote.edit.any")
    assert not can(sales, "quote.view.team")
    assert can(manager, "quote.edit.any")
    assert can(manager, "quote.view.team")
    assert not can(manager, "quote.delete.any")
    assert not can(manager, "users.manage")
    assert can(admin, "quote.delete.any")
    assert can(admin, "users.manage")
    assert can(admin, "activity.view")
    assert can(sales, "tax.select")
    assert not can(viewer, "tax.select")


def test_inactive_user_cannot() -> None:
    dead = _user("admin", active=False)
    assert not can(dead, "catalog.view")
    assert not can(None, "catalog.view")
