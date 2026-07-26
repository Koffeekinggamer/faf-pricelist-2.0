#!/usr/bin/env python3
"""
Sync OrderTrac sales users → FAF Price Book app_users.

Requires a live Playwright session:
  python scripts/ordertrac_login.py

Usage:
  .venv/bin/python scripts/ordertrac_sync_users.py
  .venv/bin/python scripts/ordertrac_sync_users.py --check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync OrderTrac users into FAF")
    ap.add_argument(
        "--check",
        action="store_true",
        help="Only check OrderTrac session + list users (no write)",
    )
    ap.add_argument(
        "--role",
        default="sales",
        choices=["admin", "sales", "floor"],
        help="Role for newly created FAF users (default sales)",
    )
    args = ap.parse_args()

    from backend.db import init_db
    from backend.ordertrac_connect import (
        check_session,
        connection_status,
        fetch_ordertrac_users,
        sync_users_to_faf,
    )
    from backend.auth import ensure_seed_admin

    init_db()
    ensure_seed_admin()

    print("Connection:", json.dumps(connection_status(), indent=2))
    sess = check_session(headless=True)
    print("Session:", json.dumps(sess, indent=2))
    if not sess.get("ok"):
        print("\nRe-login:  .venv/bin/python scripts/ordertrac_login.py")
        return 1

    if args.check:
        fetched = fetch_ordertrac_users(headless=True)
        print(json.dumps(fetched, indent=2))
        return 0 if fetched.get("ok") else 1

    result = sync_users_to_faf(headless=True, default_role=args.role)
    print(json.dumps(result, indent=2))
    if result.get("created"):
        print("\n=== NEW ACCOUNTS (share temp passwords once) ===")
        for c in result["created"]:
            print(
                f"  {c['username']:20}  temp={c.get('temp_password', '')}  "
                f"({c.get('user_id')})"
            )
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
