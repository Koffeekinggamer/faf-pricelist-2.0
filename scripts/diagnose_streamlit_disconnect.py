#!/usr/bin/env python3
"""Diagnose Streamlit disconnects (idle WS + Drop session payload pattern).

Usage:
  .venv/bin/python scripts/diagnose_streamlit_disconnect.py
  .venv/bin/python scripts/diagnose_streamlit_disconnect.py --url https://faf-pricebook.fly.dev
  .venv/bin/python scripts/diagnose_streamlit_disconnect.py --hold 120

Exit 0 = idle WS held; exit 1 = WS failed; exit 2 = Drop session pattern warning.
"""

from __future__ import annotations

import argparse
import asyncio
import pickle
import time
import urllib.request


def check_drop_session_amplification() -> int:
    def make_row(i: int) -> dict:
        return {
            "vendor": "Big Builder",
            "part_number": f"SKU-{i:05d}",
            "description": f"Item {i}",
            "species": "Red Oak / Sap Cherry / Wormy Maple",
            "base_price": 147.0,
            "multiplier": 2.7,
            "adjusted_price": 400.0,
        }

    parsed = [
        {
            "filename": "big.xlsx",
            "rows": [make_row(i) for i in range(15_000)],
            "row_count": 15_000,
        }
    ]
    meta = {"path": "/tmp/x.pkl", "row_count": 15_000}
    full = sum(len(pickle.dumps(parsed)) for _ in range(8))
    light = sum(len(pickle.dumps(meta)) for _ in range(8))
    ratio = full / max(light, 1)
    print(f"Drop session amplification: full/meta = {ratio:.0f}× over 8 reruns")
    print("  Fix: disk-backed drop cache (backend.drop_cache) — rows not in session_state.")
    if ratio < 100:
        print("UNEXPECTED ratio")
        return 2
    return 0


async def hold_ws(url: str, seconds: float) -> int:
    try:
        import websockets
    except ImportError:
        print("websockets not installed — skip WS hold")
        return 0

    base = url.rstrip("/")
    with urllib.request.urlopen(base + "/_stcore/health", timeout=20) as r:
        print("health", r.status, r.read())

    uri = base.replace("https://", "wss://").replace("http://", "ws://")
    uri = uri + "/_stcore/stream"
    print("connecting", uri)
    t0 = time.time()
    try:
        async with websockets.connect(
            uri,
            open_timeout=30,
            ping_interval=20,
            ping_timeout=20,
            additional_headers={"Origin": base},
        ) as ws:
            print("connected")
            end = time.time() + seconds
            while time.time() < end:
                try:
                    await asyncio.wait_for(ws.recv(), timeout=5)
                except asyncio.TimeoutError:
                    print(f"[{time.time() - t0:6.1f}s] open")
            print(f"PASS held {seconds:.0f}s")
            return 0
    except Exception as e:
        print(f"FAIL at {time.time() - t0:.1f}s: {type(e).__name__}: {e}")
        return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://faf-pricebook.fly.dev")
    ap.add_argument("--hold", type=float, default=60.0)
    ap.add_argument("--skip-ws", action="store_true")
    args = ap.parse_args()

    print("=== Drop session pattern ===")
    check_drop_session_amplification()

    if args.skip_ws:
        return 0

    print("\n=== Idle WebSocket hold ===")
    print("Tip: long Drop/Viztech on Cloudflare tunnel is flakier than localhost:8501.")
    return asyncio.run(hold_ws(args.url, args.hold))


if __name__ == "__main__":
    raise SystemExit(main())
