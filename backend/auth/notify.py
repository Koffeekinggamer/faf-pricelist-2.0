"""Email a live-app link when an account is created. Never log passwords or full tokens."""

from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Callable

from backend.config import resolve_secrets_path

logger = logging.getLogger(__name__)

LIVE_APP_URL = "https://faf-pricebook.fly.dev"
DEFAULT_FROM = "Foothills Amish Furniture <noreply@foothillsamish.com>"


def public_app_url() -> str:
    return (
        os.environ.get("APP_PUBLIC_URL") or os.environ.get("FAF_PUBLIC_URL") or LIVE_APP_URL
    ).rstrip("/")


def account_ready_message(
    *,
    to_email: str,
    name: str = "",
    invite_token: str | None = None,
) -> tuple[str, str, str]:
    """Return (subject, text body, link). Body never includes a password."""
    who = (name or "").strip() or "there"
    url = public_app_url()
    if invite_token:
        link = f"{url}/?invite={invite_token}"
        body = (
            f"Hi {who},\n\n"
            "Your Foothills Amish Furniture price book account is ready.\n\n"
            "Open this link to set your password and sign in:\n"
            f"{link}\n\n"
            "If you did not expect this, you can ignore this email.\n"
        )
    else:
        link = url
        body = (
            f"Hi {who},\n\n"
            "Your Foothills Amish Furniture price book account is ready.\n\n"
            "Sign in here with this email address:\n"
            f"{link}\n\n"
            "Use the temporary password your administrator gave you.\n"
        )
    return "Your Foothills price book account is ready", body, link


def _secrets_smtp() -> dict[str, str]:
    path = resolve_secrets_path()
    if not path.is_file():
        return {}
    try:
        import tomllib
    except ImportError:  # pragma: no cover
        return {}
    try:
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    block = data.get("smtp") or data.get("mail") or {}
    if not isinstance(block, dict):
        return {}
    return {str(k): str(v) for k, v in block.items() if v}


def smtp_config() -> dict[str, str] | None:
    secrets = _secrets_smtp()

    def pick(*names: str) -> str:
        for name in names:
            value = (
                os.environ.get(name)
                or secrets.get(name)
                or secrets.get(name.lower())
                or secrets.get(name.split("_", 1)[-1].lower())
                or ""
            ).strip()
            if value:
                return value
        return ""

    host = pick("SMTP_HOST", "MAIL_HOST", "host")
    user = pick("SMTP_USER", "MAIL_USERNAME", "MAIL_USER", "user", "username")
    password = pick("SMTP_PASSWORD", "MAIL_PASSWORD", "password")
    if not host or not user or not password:
        return None
    port = pick("SMTP_PORT", "MAIL_PORT", "port") or "587"
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "from_addr": pick("SMTP_FROM", "MAIL_FROM", "from") or DEFAULT_FROM,
        "starttls": pick("SMTP_STARTTLS", "MAIL_STARTTLS", "starttls") or "1",
    }


def send_account_ready_email(
    *,
    to_email: str,
    name: str = "",
    invite_token: str | None = None,
    sender: Callable[[EmailMessage], None] | None = None,
) -> bool:
    """Send the live-app link. Failures never raise to the create-user path."""
    addr = (to_email or "").strip()
    if "@" not in addr:
        return False
    subject, body, _link = account_ready_message(
        to_email=addr, name=name, invite_token=invite_token
    )
    msg = EmailMessage()
    cfg = smtp_config()
    msg["Subject"] = subject
    msg["From"] = (cfg or {}).get("from_addr") or DEFAULT_FROM
    msg["To"] = addr
    msg.set_content(body)
    try:
        if sender is not None:
            sender(msg)
            return True
        if cfg is None:
            logger.warning("Account email skipped — SMTP is not configured")
            return False
        _smtp_send(msg, cfg)
        return True
    except Exception:
        logger.exception("Account email failed for %s", addr)
        return False


def _smtp_send(msg: EmailMessage, cfg: dict[str, str]) -> None:
    port = int(cfg["port"])
    with smtplib.SMTP(cfg["host"], port, timeout=20) as smtp:
        if str(cfg.get("starttls") or "1").strip().lower() not in {"0", "false", "no"}:
            smtp.starttls()
        smtp.login(cfg["user"], cfg["password"])
        smtp.send_message(msg)
