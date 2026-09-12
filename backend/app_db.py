"""Sibling SQLite for users, quotes, and activity — never the catalog dump."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from backend.config import resolve_app_db_path

# 90-day retention job comes later. Do not auto-delete activity_log rows.

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    name TEXT,
    role TEXT NOT NULL DEFAULT 'sales',
    active INTEGER NOT NULL DEFAULT 1,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by INTEGER,
    last_login_at TEXT,
    failed_login_count INTEGER NOT NULL DEFAULT 0,
    failed_window_started_at TEXT,
    locked_until TEXT,
    must_change_password INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

CREATE TABLE IF NOT EXISTS invites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    name TEXT,
    role TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    token_last4 TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    accepted_at TEXT,
    created_by INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS password_resets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    email TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    token_last4 TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    client_name TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    tax_county TEXT,
    tax_state TEXT,
    tax_rate REAL,
    tax_exempt INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_quotes_owner ON quotes (owner_id, updated_at);

CREATE TABLE IF NOT EXISTS quote_lines (
    id TEXT PRIMARY KEY,
    quote_id INTEGER NOT NULL,
    product_id TEXT,
    sku TEXT,
    name TEXT NOT NULL,
    options_snapshot TEXT NOT NULL,
    default_options TEXT NOT NULL,
    unit_price REAL NOT NULL,
    qty INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (quote_id) REFERENCES quotes(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_quote_lines_quote ON quote_lines (quote_id);

CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    actor_id INTEGER,
    actor_email TEXT,
    actor_role TEXT,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    resource_type TEXT,
    resource_id TEXT,
    summary TEXT,
    metadata TEXT,
    ip TEXT,
    user_agent TEXT,
    path TEXT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_activity_created ON activity_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_actor_id ON activity_log (actor_id, created_at);
CREATE INDEX IF NOT EXISTS idx_activity_actor_email ON activity_log (actor_email, created_at);
CREATE INDEX IF NOT EXISTS idx_activity_action ON activity_log (action, created_at);
CREATE INDEX IF NOT EXISTS idx_activity_status ON activity_log (status, created_at);
CREATE INDEX IF NOT EXISTS idx_activity_resource ON activity_log (resource_type, resource_id);

CREATE TABLE IF NOT EXISTS app_kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def get_app_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else resolve_app_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_app_db(db_path: Path | None = None) -> Path:
    path = Path(db_path) if db_path is not None else resolve_app_db_path()
    with get_app_connection(path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    return path


def sqlite_path_from_url(url: str) -> str:
    text = (url or "").strip()
    if text.startswith("sqlite:///"):
        return text[len("sqlite:///") :]
    return text


def env_is_fly() -> bool:
    return bool(os.environ.get("FLY_APP_NAME") or os.environ.get("FLY_ALLOC_ID"))
