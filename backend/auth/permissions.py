"""Server-side permission checks. Hiding a button is not security."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from backend.auth.roles import Role, SessionUser

Action = Literal[
    "catalog.view",
    "quote.create",
    "quote.edit.own",
    "quote.edit.any",
    "quote.delete.own",
    "quote.delete.any",
    "quote.view.own",
    "quote.view.team",
    "tax.select",
    "users.manage",
    "settings.edit",
    "activity.view",
]

MATRIX: dict[str, frozenset[Role]] = {
    "catalog.view": frozenset({"admin", "manager", "sales", "viewer"}),
    "quote.create": frozenset({"admin", "manager", "sales"}),
    "quote.edit.own": frozenset({"admin", "manager", "sales"}),
    "quote.edit.any": frozenset({"admin", "manager"}),
    "quote.delete.own": frozenset({"admin", "manager", "sales"}),
    "quote.delete.any": frozenset({"admin"}),
    "quote.view.own": frozenset({"admin", "manager", "sales"}),
    "quote.view.team": frozenset({"admin", "manager"}),
    "tax.select": frozenset({"admin", "manager", "sales"}),
    "users.manage": frozenset({"admin"}),
    "settings.edit": frozenset({"admin"}),
    "activity.view": frozenset({"admin"}),
}


@dataclass
class AuthDenied(Exception):
    message: str
    status_code: int = 403
    action: str = ""
    reason: str = "denied"

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class QuoteResource:
    owner_id: int
    quote_id: int | None = None


def can(
    user: SessionUser | None,
    action: str,
    resource: QuoteResource | None = None,
) -> bool:
    if user is None or not user.active:
        return False
    allowed = MATRIX.get(action)
    if allowed is None or user.role not in allowed:
        return False
    if action.endswith(".own") and resource is not None:
        if user.role in {"admin", "manager"} and action.startswith("quote."):
            # own is implied for team roles; still true when they own it
            return True
        return int(resource.owner_id) == int(user.id)
    return True


def require(
    user: SessionUser | None,
    action: str,
    resource: QuoteResource | None = None,
) -> SessionUser:
    if user is None:
        raise AuthDenied(
            "Sign in required.", status_code=401, action=action, reason="unauthenticated"
        )
    if not user.active:
        raise AuthDenied(
            "This account is disabled. Contact an admin.",
            status_code=401,
            action=action,
            reason="inactive",
        )
    if not can(user, action, resource):
        raise AuthDenied("Not allowed.", status_code=403, action=action, reason="denied")
    return user
