#!/usr/bin/env python3
"""
OrderTrac agent access helpers (Foothills Amish Furniture — company-owned account).

Session dir: ~/Documents/ordertrac-session/
  storage_state.json  — Playwright auth (reuse this)
  cookies.json
  test-quote.json

Credentials: .streamlit/secrets.toml [ordertrac] (gitignored)
  username / password / base_url

Re-login if session expires:
  .venv/bin/python scripts/ordertrac_login.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
SESSION_DIR = Path.home() / "Documents" / "ordertrac-session"
STORAGE = SESSION_DIR / "storage_state.json"
BASE_DEFAULT = "https://app.ordertracinventory.com"


def load_creds() -> dict[str, str]:
    user = pw = ""
    base = BASE_DEFAULT
    secrets = ROOT / ".streamlit" / "secrets.toml"
    if secrets.is_file():
        text = secrets.read_text()
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


def ensure_session(*, relogin: bool = False) -> Path:
    """Return path to storage_state.json; optionally force interactive re-login."""
    import subprocess

    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    if relogin or not STORAGE.is_file():
        login = ROOT / "scripts" / "ordertrac_login.py"
        py = ROOT / ".venv" / "bin" / "python"
        cmd = [str(py if py.is_file() else sys.executable), str(login), "--wait", "300"]
        rc = subprocess.call(cmd, cwd=str(ROOT))
        if rc != 0 or not STORAGE.is_file():
            raise RuntimeError("OrderTrac login failed — run scripts/ordertrac_login.py")
    return STORAGE


def browser_page(headless: bool = True):
    """Context manager-ish: returns (playwright, browser, context, page, base)."""
    from playwright.sync_api import sync_playwright

    creds = load_creds()
    base = creds["base_url"]
    state = ensure_session()
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.launch(
            channel="chrome",
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
    except Exception:
        browser = pw.chromium.launch(headless=headless)
    context = browser.new_context(storage_state=str(state))
    page = context.new_page()
    return pw, browser, context, page, base


def session_alive() -> bool:
    try:
        pw, browser, context, page, base = browser_page(headless=True)
        try:
            page.goto(base + "/", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1500)
            ok = "Login" not in page.title() and "/Account/Login" not in page.url
            if ok:
                context.storage_state(path=str(STORAGE))
            return ok
        finally:
            browser.close()
            pw.stop()
    except Exception:
        return False


def create_test_quote(
    *,
    first: str = "Grok",
    last: str = "TestQuote",
    org: str = "Agent Test Co",
    phone: str = "8645550199",
    email: str = "grok-test@example.com",
    user_label: str = "Miller, Judson",
    location: str = "Landrum",
    notes: str = "Test quote — Grok agent. Safe to delete.",
) -> dict[str, Any]:
    """Create a new Quote with a new customer; return ids + url."""
    from playwright.sync_api import sync_playwright

    creds = load_creds()
    base = creds["base_url"]
    state = ensure_session()
    result: dict[str, Any] = {}

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                channel="chrome",
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
        except Exception:
            browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(state))
        page = context.new_page()

        page.goto(f"{base}/SalesOrders", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        page.get_by_text("New Quote", exact=True).click()
        page.wait_for_url(re.compile(r"salesOrderGUID="), timeout=30000)
        page.wait_for_timeout(2500)
        m = re.search(r"salesOrderGUID=([^&]+)", page.url)
        guid = m.group(1) if m else ""
        result["guid"] = guid

        page.locator("select[name='UserGUID']").select_option(label=user_label)
        page.locator("#sales-order-location-guid").select_option(label=location)
        page.locator("textarea[name='Notes']").fill(notes)

        page.get_by_text("Select", exact=True).first.click()
        page.wait_for_timeout(1000)
        page.get_by_text("New Customer", exact=True).click()
        page.wait_for_timeout(1200)

        for name, val in [
            ("Customer.FirstName", first),
            ("Customer.LastName", last),
            ("Customer.Organization", org),
            ("Customer.Email", email),
            ("Customer.Phone1", phone),
        ]:
            page.locator(f"input[name='{name}']").last.fill(val, force=True)

        page.locator("#add-customer-btn").click()
        page.wait_for_timeout(3000)
        page.locator("button").filter(has_text=re.compile(r"^Save$")).first.click(
            timeout=8000
        )
        page.wait_for_timeout(3000)

        body = page.inner_text("body")
        mid = re.search(r"SALES ORDER ID\s*\n?\s*(\d+)", body)
        so_id = mid.group(1) if mid else None
        result.update(
            {
                "sales_order_id": so_id,
                "type": "QUOTE",
                "url": f"{base}/SalesOrders/SalesOrder?salesOrderGUID={guid}",
                "customer": f"{first} {last}",
                "organization": org,
                "user": user_label,
                "location": location,
                "notes": notes,
            }
        )
        context.storage_state(path=str(state))
        Path(SESSION_DIR / "test-quote.json").write_text(json.dumps(result, indent=2))
        browser.close()
    return result


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="OrderTrac agent session tools")
    ap.add_argument("cmd", choices=["check", "quote"], help="check session | create test quote")
    args = ap.parse_args()
    if args.cmd == "check":
        ok = session_alive()
        print("session_alive" if ok else "session_dead")
        raise SystemExit(0 if ok else 1)
    if args.cmd == "quote":
        print(json.dumps(create_test_quote(), indent=2))
