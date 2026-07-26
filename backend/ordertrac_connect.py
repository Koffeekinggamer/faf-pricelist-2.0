"""
OrderTrac connection helpers for FAF Price Book.

Uses existing Playwright session (~/Documents/ordertrac-session/storage_state.json)
and credentials from .streamlit/secrets.toml [ordertrac].

Does not store OrderTrac passwords in the SQLite DB.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
SESSION_DIR = Path.home() / "Documents" / "ordertrac-session"
STORAGE = SESSION_DIR / "storage_state.json"
BASE_DEFAULT = "https://app.ordertracinventory.com"


def map_ordertrac_role_to_faf(ot_role: str) -> str:
    """Map OrderTrac permission labels → FAF app roles."""
    r = (ot_role or "").strip().lower()
    if not r:
        return "sales"
    if "admin" in r:
        return "admin"
    if "warehouse" in r:
        return "floor"
    if "sales" in r:
        return "sales"
    return "sales"


def load_ordertrac_creds() -> dict[str, str]:
    """Load [ordertrac] block from secrets.toml or env."""
    import os

    user = (os.environ.get("ORDERTRAC_USER") or "").strip()
    pw = os.environ.get("ORDERTRAC_PASSWORD") or ""
    base = (os.environ.get("ORDERTRAC_BASE_URL") or BASE_DEFAULT).rstrip("/")

    secrets = ROOT / ".streamlit" / "secrets.toml"
    if secrets.is_file():
        text = secrets.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"\[ordertrac\](.*?)(?=\n\[|\Z)", text, re.S | re.I)
        if m:
            block = m.group(1)
            um = re.search(r'username\s*=\s*"([^"]+)"', block)
            pm = re.search(r'password\s*=\s*"([^"]+)"', block)
            bm = re.search(r'base_url\s*=\s*"([^"]+)"', block)
            if um:
                user = um.group(1)
            if pm:
                pw = pm.group(1)
            if bm:
                base = bm.group(1).rstrip("/")
    return {"username": user, "password": pw, "base_url": base}


def connection_status() -> dict[str, Any]:
    """Non-browser status of configured connection + session file."""
    creds = load_ordertrac_creds()
    return {
        "configured": bool(creds.get("username") and creds.get("password")),
        "username": creds.get("username") or "",
        "base_url": creds.get("base_url") or BASE_DEFAULT,
        "session_file": str(STORAGE),
        "session_exists": STORAGE.is_file(),
    }


def _launch_page(headless: bool = True):
    from playwright.sync_api import sync_playwright

    if not STORAGE.is_file():
        raise RuntimeError(
            "No OrderTrac session — run: python scripts/ordertrac_login.py"
        )
    creds = load_ordertrac_creds()
    base = creds["base_url"]
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.launch(
            channel="chrome",
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
    except Exception:
        browser = pw.chromium.launch(headless=headless)
    context = browser.new_context(storage_state=str(STORAGE))
    page = context.new_page()
    return pw, browser, context, page, base


def check_session(*, headless: bool = True) -> dict[str, Any]:
    """Hit OrderTrac home; refresh storage_state if alive."""
    try:
        pw, browser, context, page, base = _launch_page(headless=headless)
    except Exception as e:
        return {"ok": False, "error": str(e), "users": []}
    try:
        page.goto(base + "/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)
        title = page.title()
        url = page.url
        ok = "Login" not in title and "/Account/Login" not in url
        if ok:
            context.storage_state(path=str(STORAGE))
        return {
            "ok": ok,
            "title": title,
            "url": url,
            "error": None if ok else "Session expired — re-run ordertrac_login.py",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        browser.close()
        pw.stop()


def fetch_ordertrac_users(*, headless: bool = True) -> dict[str, Any]:
    """
    Scrape OrderTrac sales users (UserGUID dropdown on New Quote form).

    Returns {ok, users: [{guid, display_name, label}], error?, count}.
    """
    try:
        pw, browser, context, page, base = _launch_page(headless=headless)
    except Exception as e:
        return {"ok": False, "error": str(e), "users": [], "count": 0}

    users: list[dict[str, str]] = []
    try:
        page.goto(base + "/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1200)
        if "Login" in page.title() or "/Account/Login" in page.url:
            return {
                "ok": False,
                "error": "Session expired — run scripts/ordertrac_login.py",
                "users": [],
                "count": 0,
            }

        # Open New Quote form (has UserGUID select with all sales users)
        page.goto(
            base + "/SalesOrders/SalesOrder?newSalesOrderType=QUOTE",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        page.wait_for_timeout(2500)

        raw = page.evaluate(
            """() => {
          const sel = document.querySelector('select[name="UserGUID"]');
          if (!sel) {
            // fallback: any select whose options look like "Last, First"
            const sels = Array.from(document.querySelectorAll('select'));
            for (const s of sels) {
              const texts = Array.from(s.options).map(o => o.text.trim());
              if (texts.filter(t => /,/.test(t)).length >= 3) {
                return Array.from(s.options).map(o => ({
                  value: o.value || '',
                  text: (o.text || '').trim()
                }));
              }
            }
            return null;
          }
          return Array.from(sel.options).map(o => ({
            value: o.value || '',
            text: (o.text || '').trim()
          }));
        }"""
        )

        if not raw:
            # Try Settings / users page paths
            for path in (
                "/Settings/Users",
                "/Account/Users",
                "/Admin/Users",
                "/users",
            ):
                try:
                    page.goto(base + path, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(1500)
                    if "Login" in page.title():
                        break
                    raw = page.evaluate(
                        """() => {
                      const sel = document.querySelector('select[name="UserGUID"]');
                      if (sel) {
                        return Array.from(sel.options).map(o => ({
                          value: o.value||'', text: (o.text||'').trim()
                        }));
                      }
                      // table of users
                      const rows = Array.from(document.querySelectorAll('tr, .list-item, .user-row'));
                      const out = [];
                      for (const r of rows) {
                        const t = (r.innerText||'').trim().split('\\n')[0];
                        if (t && /,/.test(t) && t.length < 60) {
                          out.push({value: '', text: t});
                        }
                      }
                      return out.length ? out : null;
                    }"""
                    )
                    if raw:
                        break
                except Exception:
                    continue

        if not raw:
            return {
                "ok": False,
                "error": "Could not find UserGUID list on OrderTrac",
                "users": [],
                "count": 0,
            }

        skip = {"", "select", "select a user", "—", "-"}
        for o in raw:
            text = (o.get("text") or "").strip()
            val = (o.get("value") or "").strip()
            if not text or text.lower() in skip:
                continue
            if not val and not re.search(r"[A-Za-z]", text):
                continue
            # Table scrapes look like: "Miller, Judson\tAdministrator\t05/26/2026\t…"
            parts = re.split(r"[\t|]+|\s{2,}", text)
            parts = [p.strip() for p in parts if p and p.strip()]
            display = parts[0] if parts else text
            # Keep only "Last, First" style names
            if not re.search(r"[A-Za-z]", display):
                continue
            ot_role = parts[1] if len(parts) > 1 else ""
            # Drop date-only fragments as role
            if re.match(r"\d{1,2}/\d{1,2}/\d{2,4}", ot_role or ""):
                ot_role = ""
            users.append(
                {
                    "guid": val,
                    "display_name": display,
                    "label": display,
                    "ordertrac_role": ot_role,
                    "faf_role": map_ordertrac_role_to_faf(ot_role),
                }
            )

        # de-dupe by guid or name
        seen = set()
        deduped = []
        for u in users:
            key = u["guid"] or u["display_name"].lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(u)

        context.storage_state(path=str(STORAGE))
        return {
            "ok": True,
            "users": deduped,
            "count": len(deduped),
            "error": None,
            "base_url": base,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "users": [], "count": 0}
    finally:
        browser.close()
        pw.stop()


def sync_users_to_faf(
    db_path: Optional[Path] = None,
    *,
    headless: bool = True,
    default_role: str = "sales",
    skip_names: Optional[list[str]] = None,
) -> dict[str, Any]:
    """
    Fetch OrderTrac users and upsert into FAF app_users.
    Returns summary with created/updated lists (temp passwords for created).
    """
    from backend.db import init_db
    from backend.users import UserRepository

    init_db(db_path)
    repo = UserRepository(db_path)
    # Ensure admin seed exists first
    from backend.auth import ensure_seed_admin

    ensure_seed_admin(db_path)

    fetched = fetch_ordertrac_users(headless=headless)
    if not fetched.get("ok"):
        repo.set_integration(
            "ordertrac",
            status="error",
            last_error=fetched.get("error") or "fetch failed",
            ok=False,
        )
        return {
            "ok": False,
            "error": fetched.get("error"),
            "created": [],
            "updated": [],
            "skipped": [],
        }

    skip = {s.lower() for s in (skip_names or ["Commission, No"])}
    created, updated, skipped = [], [], []

    for u in fetched["users"]:
        name = (u.get("display_name") or "").strip()
        if not name or name.lower() in skip:
            skipped.append(name or "(blank)")
            continue
        # Heuristic: "Commission, No" style placeholders
        if re.match(r"^commission", name, re.I):
            skipped.append(name)
            continue
        role = u.get("faf_role") or default_role
        try:
            result = repo.upsert_from_ordertrac(
                display_name=name,
                ordertrac_user_guid=u.get("guid") or "",
                role=role,
            )
            if result["action"] == "created":
                created.append(result)
            else:
                updated.append(result)
        except Exception as e:
            skipped.append(f"{name} ({e})")

    repo.set_integration(
        "ordertrac",
        status="connected",
        last_error="",
        meta={
            "user_count_ot": fetched["count"],
            "created": len(created),
            "updated": len(updated),
            "base_url": fetched.get("base_url"),
        },
        ok=True,
    )

    return {
        "ok": True,
        "error": None,
        "ot_count": fetched["count"],
        "created": created,
        "updated": updated,
        "skipped": skipped,
    }
