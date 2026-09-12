"""Roles for the price-book floor login."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Role = Literal["admin", "manager", "sales", "viewer"]
ROLES: tuple[Role, ...] = ("admin", "manager", "sales", "viewer")


@dataclass(frozen=True)
class SessionUser:
    id: int
    email: str
    name: str
    role: Role
    active: bool
    must_change_password: bool = False

    @property
    def display_name(self) -> str:
        return self.name or self.email


def parse_role(value: object, *, default: Role = "sales") -> Role:
    text = str(value or "").strip().lower()
    if text == "floor":
        return "viewer"
    if text in ROLES:
        return text  # type: ignore[return-value]
    return default


def email_local_part(email: str) -> str:
    return email.split("@", 1)[0] if email else ""
