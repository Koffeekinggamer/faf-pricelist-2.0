#!/usr/bin/env python3
"""
OrderTrac login helper.

reCAPTCHA blocks pure API login. This opens real Chrome, fills credentials,
clicks Sign In, retries on failure, and waits for a successful session.

Usage:
  .venv/bin/python scripts/ordertrac_login.py
  .venv/bin/python scripts/ordertrac_login.py --headless   # often fails captcha
  .venv/bin/python scripts/ordertrac_login.py --wait 600  # seconds

Saves on success:
  ~/Documents/ordertrac-session/storage_state.json
  ~/Documents/ordertrac-session/cookies.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path.home() / "Documents" / "ordertrac-session"
DEFAULT_BASE = "https://app.ordertracinventory.com"


def load_creds() -> tuple[str, str, str]:
    user = os.environ.get("ORDERTRAC_USER", "").strip()
    pw = os.environ.get("ORDERTRAC_PASSWORD", "").strip()
    base = os.environ.get("ORDERTRAC_BASE", DEFAULT_BASE).strip()
    secrets = ROOT / ".streamlit" / "secrets.toml"
    if secrets.is_file():
        text = secrets.read_text()
        m = re.search(r"\[ordertrac\](.*?)(?=\n\[|\Z)", text, re.S | re.I)
        if m:
            block = m.group(1)
            um = re.search(r'username\s*=\s*"([^"]+)"', block)
            pm = re.search(r'password\s*=\s*"([^"]+)"', block)
            bm = re.search(r'base_url\s*=\s*"([^"]+)"', block)
            if um and not user:
                user = um.group(1)
            if pm and not pw:
                pw = pm.group(1)
            if bm:
                base = bm.group(1)
    # defaults from session
    if not user:
        user = "judson@foothillsamishfurniture.com"
    if not pw:
        pw = "1115"
    return user, pw, base.rstrip("/")


def logged_in(url: str) -> bool:
    u = url.lower()
    if "/account/login" in u:
        return False
    if any(
        x in u
        for x in (
            "continuetohomepage",
            "/home",
            "dashboard",
            "/inventory",
            "/sales",
            "/item",
            "/report",
        )
    ):
        return True
    # any non-login account path after auth often redirects home
    if "ordertracinventory.com" in u and "/account/login" not in u:
        if u.rstrip("/").endswith("ordertracinventory.com"):
            return True
        if "/account/" not in u or "continue" in u:
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--wait", type=int, default=600, help="max seconds to wait")
    ap.add_argument("--retries", type=int, default=8, help="auto Sign In clicks")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    user, pw, base = load_creds()
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"OrderTrac login as {user}", flush=True)
    print(f"Browser will open — complete reCAPTCHA if asked.", flush=True)
    print(f"Waiting up to {args.wait}s… session → {OUT}/storage_state.json", flush=True)

    with sync_playwright() as p:
        launch_kwargs = {
            "headless": args.headless,
            "slow_mo": 80 if not args.headless else 0,
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        browser = None
        for channel in ("chrome", None):
            try:
                kw = dict(launch_kwargs)
                if channel:
                    kw["channel"] = channel
                browser = p.chromium.launch(**kw)
                print(f"launched chromium channel={channel}", flush=True)
                break
            except Exception as e:
                print(f"launch fail channel={channel}: {e}", flush=True)
        if browser is None:
            return 1

        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            "window.chrome = { runtime: {} };"
        )
        page = context.new_page()

        login_bodies: list = []

        def on_resp(r):
            if "UserLogIn" in r.url:
                try:
                    body = r.json()
                except Exception:
                    body = {"raw": r.text()[:300]}
                login_bodies.append(body)
                print(f"UserLogIn: {body}", flush=True)

        page.on("response", on_resp)

        page.goto(f"{base}/Account/Login", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("#username", timeout=30000)
        page.fill("#username", user)
        page.fill("#password", pw)
        page.wait_for_timeout(1500)

        clicks = 0
        deadline = time.time() + args.wait
        last_click = 0.0

        while time.time() < deadline:
            url = page.url
            if logged_in(url):
                print(f"Logged in at {url}", flush=True)
                break

            # auto-click Sign In every ~25s up to retries
            if clicks < args.retries and (time.time() - last_click) > 25:
                try:
                    # re-fill in case page reset
                    if page.locator("#username").count():
                        page.fill("#username", user)
                        page.fill("#password", pw)
                    btn = page.locator("button.g-recaptcha, button:has-text('Sign In')").first
                    if btn.count():
                        btn.click(timeout=5000)
                        clicks += 1
                        last_click = time.time()
                        print(f"Sign In click #{clicks}", flush=True)
                except Exception as e:
                    print(f"click err: {e}", flush=True)

            # if success payload without nav yet
            if login_bodies and login_bodies[-1].get("Success") is True:
                print("API Success — navigating home", flush=True)
                try:
                    page.goto(
                        f"{base}/Account/ContinueToHomePage",
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )
                except Exception:
                    pass
                break

            page.wait_for_timeout(1000)
        else:
            page.screenshot(path=str(OUT / "login-timeout.png"), full_page=True)
            print("TIMEOUT — still not logged in. See login-timeout.png", flush=True)
            print("Last bodies:", login_bodies[-3:] if login_bodies else None, flush=True)
            browser.close()
            return 1

        # stabilize on app home
        try:
            if "Login" in page.url:
                page.goto(
                    f"{base}/Account/ContinueToHomePage",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
            page.wait_for_timeout(2500)
        except Exception:
            pass

        context.storage_state(path=str(OUT / "storage_state.json"))
        Path(OUT / "cookies.json").write_text(json.dumps(context.cookies(), indent=2))
        page.screenshot(path=str(OUT / "home.png"), full_page=True)
        print("LOGIN OK", flush=True)
        print("url:", page.url, flush=True)
        print("title:", page.title(), flush=True)
        print("saved:", OUT / "storage_state.json", flush=True)

        # quick nav map
        for a in page.locator("a[href]").all()[:40]:
            try:
                href = a.get_attribute("href") or ""
                txt = (a.inner_text() or "").strip().replace("\n", " ")[:50]
                if href.startswith("/") and txt:
                    print(f"  {txt!r} -> {href}", flush=True)
            except Exception:
                pass

        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
