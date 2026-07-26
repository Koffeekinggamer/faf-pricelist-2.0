#!/usr/bin/env python3
"""
Monthly Viztech → FAF Price Book sync.

1. Log into viztechfurniture.com (Preferred Dealer)
2. Discover builder price-list download links
3. Download Excel catalogs to ~/Documents/viztech-downloads/
4. Import into master_pricebook.db (normalize + replace_vendor)
5. Keep builders that Viztech does not have (never wipe unknown vendors)

Credentials (first match wins):
  - env VIZTECH_USER / VIZTECH_PASSWORD
  - .streamlit/secrets.toml  [viztech] username / password
  - ~/.config/faf-pricebook/viztech.env

Usage:
  python scripts/viztech_sync.py              # full sync
  python scripts/viztech_sync.py --dry-run    # login + list only
  python scripts/viztech_sync.py --download-only
  python scripts/viztech_sync.py --import-only DIR
"""

from __future__ import annotations

import argparse
import concurrent.futures
import html as htmlmod
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import traceback
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

# Project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DOWNLOAD_ROOT = Path.home() / "Documents" / "viztech-downloads"
LOG_DIR = Path.home() / "Documents" / "FAF-pricebook-backups"
STATE_PATH = LOG_DIR / "viztech_sync_state.json"
BASE = "https://viztechfurniture.com"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
EXCEL_EXT = {".xlsx", ".xls", ".xlsm"}

# Same company labels → existing FAF vendor names (not true variants)
SAME_COMPANY = {
    "hopewood inc": "Hope Wood",
    "hopewood": "Hope Wood",
    "genuine oak designs": "Genuine Oak",
    "fn chairs llc": "FN Chair",
    "fn chairs": "FN Chair",
    "windy acres": "Windy Acres Furniture",
    "patiokraft": "Patio Kraft",
    "patio kraft": "Patio Kraft",
    "lamb woodworking": "LAMB",
}

# Builders we do not want in the book (PDF-only / not needed on floor).
# Match on Viztech slug or display title (normalized: lower, &→and, non-alnum → space).
IGNORE_BUILDERS = {
    "green meadows",
    "green-meadows",
    "simple living",
    "simple-living",
}


def _norm_builder_key(s: str) -> str:
    s = (s or "").lower().replace("&", "and")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def is_ignored_builder(*, slug: str = "", title: str = "", vendor: str = "") -> bool:
    for raw in (slug, title, vendor):
        key = _norm_builder_key(raw)
        if not key:
            continue
        if key in IGNORE_BUILDERS:
            return True
        # hyphen form of multi-word keys
        if key.replace(" ", "-") in IGNORE_BUILDERS:
            return True
    return False


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def load_credentials() -> tuple[str, str]:
    user = os.environ.get("VIZTECH_USER", "").strip()
    pwd = os.environ.get("VIZTECH_PASSWORD", "").strip()
    if user and pwd:
        return user, pwd

    # streamlit secrets.toml
    secrets = ROOT / ".streamlit" / "secrets.toml"
    if secrets.exists():
        text = secrets.read_text(encoding="utf-8", errors="replace")
        # crude TOML section parse for [viztech]
        section = None
        data: dict[str, str] = {}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1].strip().lower()
                continue
            if "=" in line and section in ("viztech", "auth"):
                k, v = line.split("=", 1)
                k = k.strip().lower()
                v = v.strip().strip('"').strip("'")
                if section == "viztech":
                    data[k] = v
                # only use auth as fallback if no viztech section values yet
        if data.get("username") and data.get("password"):
            return data["username"], data["password"]
        # re-parse for [viztech] only more carefully
        in_v = False
        vu, vp = "", ""
        for line in text.splitlines():
            s = line.strip()
            if s.lower() == "[viztech]":
                in_v = True
                continue
            if s.startswith("["):
                in_v = False
                continue
            if in_v and "=" in s and not s.startswith("#"):
                k, v = s.split("=", 1)
                k, v = k.strip().lower(), v.strip().strip('"').strip("'")
                if k in ("username", "user", "log"):
                    vu = v
                if k in ("password", "pwd", "pass"):
                    vp = v
        if vu and vp:
            return vu, vp

    env_file = Path.home() / ".config" / "faf-pricebook" / "viztech.env"
    if env_file.exists():
        vals: dict[str, str] = {}
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
        user = vals.get("VIZTECH_USER") or vals.get("username") or ""
        pwd = vals.get("VIZTECH_PASSWORD") or vals.get("password") or ""
        if user and pwd:
            return user, pwd

    raise SystemExit(
        "Viztech credentials not found. Set VIZTECH_USER / VIZTECH_PASSWORD, "
        "or add [viztech] username/password to .streamlit/secrets.toml, "
        "or ~/.config/faf-pricebook/viztech.env"
    )


def http_session():
    import requests

    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    return s


def login(session, user: str, password: str) -> None:
    import requests

    session.get(f"{BASE}/wp-login.php", timeout=60)
    r = session.post(
        f"{BASE}/wp-login.php",
        data={
            "log": user,
            "pwd": password,
            "wp-submit": "Log In",
            "redirect_to": f"{BASE}/",
            "testcookie": "1",
        },
        headers={"Referer": f"{BASE}/wp-login.php"},
        timeout=60,
        allow_redirects=True,
    )
    cookies = session.cookies.get_dict()
    if not any(k.startswith("wordpress_logged_in") for k in cookies):
        raise RuntimeError(
            f"Viztech login failed (HTTP {r.status_code}). Check credentials."
        )
    log(f"Logged in as {user}")


def list_builder_slugs(session) -> list[str]:
    r = session.get(f"{BASE}/all-builders/", timeout=120)
    r.raise_for_status()
    slugs = sorted(
        set(
            re.findall(
                r"https?://viztechfurniture\.com/builders/([a-z0-9\-]+)/?",
                r.text,
                re.I,
            )
        )
    )
    slugs = [s for s in slugs if s and s != "builders"]
    log(f"Found {len(slugs)} builders on all-builders")
    return slugs


def parse_price_tab(html: str, slug: str) -> dict[str, Any]:
    title_m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
    title = re.sub(r"\s+", " ", title_m.group(1)).strip() if title_m else slug
    title = re.sub(r"\s*\|\s*VIZTECH.*$", "", title, flags=re.I).strip()
    title = htmlmod.unescape(title)

    files: list[dict[str, str]] = []
    seen: set[str] = set()
    for href, inner in re.findall(
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>', html, re.I
    ):
        text = re.sub(r"<[^>]+>", " ", inner)
        text = re.sub(r"\s+", " ", text).strip()
        href = href.replace("&amp;", "&")
        if "wpdmdl" not in href.lower() and "/download/" not in href.lower():
            continue
        if href in seen:
            continue
        seen.add(href)
        url = href if href.startswith("http") else urljoin(BASE, href)
        files.append({"label": text or "download", "url": url})

    for m in re.finditer(
        r'https?://viztechfurniture\.com/download/[^"\']+\?wpdmdl=\d+[^"\']*',
        html,
        re.I,
    ):
        u = m.group(0).replace("&amp;", "&")
        if u not in seen:
            seen.add(u)
            files.append({"label": "file", "url": u})

    return {"slug": slug, "title": title, "files": files}


def fetch_catalog(session, slugs: list[str], workers: int = 6) -> list[dict]:
    catalog: list[dict] = []

    def one(slug: str) -> dict:
        url = f"{BASE}/builders/{slug}/?tab=price_list"
        try:
            r = session.get(url, timeout=90)
            if r.status_code != 200 or len(r.text) < 500:
                return {"slug": slug, "title": slug, "files": [], "error": f"HTTP {r.status_code}"}
            return parse_price_tab(r.text, slug)
        except Exception as e:
            return {"slug": slug, "title": slug, "files": [], "error": str(e)}

    # sequential is safer for session cookies; small pool of threads with session is often OK
    # for requests.Session, use sequential to avoid cookie races
    for i, slug in enumerate(slugs, 1):
        if i % 25 == 0 or i == 1:
            log(f"  price tabs {i}/{len(slugs)}")
        catalog.append(one(slug))
    with_files = sum(1 for c in catalog if c.get("files"))
    log(f"Builders with download links: {with_files}/{len(catalog)}")
    return catalog


def safe_name(s: str, max_len: int = 80) -> str:
    s = re.sub(r"[^\w.\-]+", "_", s, flags=re.U).strip("_")
    return (s or "file")[:max_len]


def detect_ext(path: Path) -> str:
    data = path.read_bytes()[:8]
    if data[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
                if any(n.startswith("xl/") for n in names):
                    return (
                        ".xlsm"
                        if any("vbaProject" in n for n in names)
                        else ".xlsx"
                    )
                return ".zip"
        except Exception:
            return ".zip"
    if data[:4] == b"%PDF":
        return ".pdf"
    if data[:4] == b"\xd0\xcf\x11\xe0":
        return ".xls"
    head = path.read_bytes()[:200].lower()
    if b"<html" in head or b"<!doctype" in head:
        return ".html"
    return ".bin"


def download_catalog(
    session, catalog: list[dict], out_dir: Path
) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    jobs: list[dict] = []
    ignored = 0
    for c in catalog:
        if is_ignored_builder(slug=c.get("slug") or "", title=c.get("title") or ""):
            ignored += 1
            continue
        for i, f in enumerate(c.get("files") or []):
            jobs.append(
                {
                    "title": c.get("title") or c["slug"],
                    "slug": c["slug"],
                    "label": f.get("label") or f"file{i}",
                    "url": f["url"].replace("&amp;", "&"),
                    "idx": i,
                }
            )
    if ignored:
        log(f"Ignored {ignored} builders (IGNORE_BUILDERS)")
    log(f"Download jobs: {len(jobs)}")

    for n, job in enumerate(jobs, 1):
        if n % 20 == 0 or n == 1:
            log(f"  download {n}/{len(jobs)}")
        vendor_dir = out_dir / safe_name(job["title"])
        vendor_dir.mkdir(parents=True, exist_ok=True)
        base = safe_name(job["label"]) or f"file{job['idx']}"
        m = re.search(r"wpdmdl=(\d+)", job["url"])
        if m:
            base = f"{base}_{m.group(1)}"
        existing = [
            e
            for e in vendor_dir.glob(f"{base}.*")
            if e.suffix not in {".part", ".html"} and e.stat().st_size > 1000
        ]
        if existing:
            results.append(
                {
                    "ok": True,
                    "skipped": True,
                    "path": str(existing[0]),
                    "title": job["title"],
                    "bytes": existing[0].stat().st_size,
                }
            )
            continue
        tmp = vendor_dir / f"{base}.part"
        try:
            r = session.get(
                job["url"],
                timeout=180,
                headers={"Referer": BASE + "/"},
                allow_redirects=True,
            )
            if r.status_code != 200 or len(r.content) < 50:
                results.append(
                    {
                        "ok": False,
                        "title": job["title"],
                        "error": f"HTTP {r.status_code} size={len(r.content)}",
                        "url": job["url"],
                    }
                )
                continue
            tmp.write_bytes(r.content)
            ext = detect_ext(tmp)
            final = vendor_dir / f"{base}{ext}"
            tmp.rename(final)
            ok = ext not in {".html", ".bin"} and final.stat().st_size > 500
            results.append(
                {
                    "ok": ok,
                    "path": str(final),
                    "title": job["title"],
                    "slug": job["slug"],
                    "ext": ext,
                    "bytes": final.stat().st_size,
                }
            )
        except Exception as e:
            results.append(
                {
                    "ok": False,
                    "title": job["title"],
                    "error": str(e),
                    "url": job["url"],
                }
            )

    # unzip archives
    for zpath in out_dir.rglob("*.zip"):
        dest = zpath.parent / (zpath.stem + "_unzipped")
        dest.mkdir(exist_ok=True)
        try:
            with zipfile.ZipFile(zpath) as z:
                z.extractall(dest)
        except Exception as e:
            log(f"  unzip fail {zpath.name}: {e}")

    ok_n = sum(1 for r in results if r.get("ok"))
    log(f"Downloads OK {ok_n}/{len(results)}")
    return results


def clean_folder_title(name: str) -> str:
    """Folder / HTML title → display vendor name (fix entity leftovers)."""
    raw = name.replace("_", " ")
    raw = htmlmod.unescape(raw)
    # leftovers when &amp; / &#039; were partially stripped earlier
    raw = re.sub(r"\s+amp\s+", " & ", raw, flags=re.I)
    raw = re.sub(r"\s+039\s+s\b", "'s", raw, flags=re.I)
    raw = re.sub(r"\s+039\s+", "'", raw, flags=re.I)
    raw = re.sub(r"\s+", " ", raw).strip()
    return re.sub(r"\s*&\s*", " & ", raw)


def vendor_from_folder(folder_name: str) -> str:
    title = clean_folder_title(folder_name)
    key = title.lower().strip()
    key2 = re.sub(r"\s+(inc\.?|llc\.?|co\.?|company|designs)$", "", key).strip()
    if key in SAME_COMPANY:
        return SAME_COMPANY[key]
    if key2 in SAME_COMPANY:
        return SAME_COMPANY[key2]
    return title  # variants stay separate


def rank_file(p: Path, vendor: str) -> tuple:
    name = p.name.lower()
    score = 0
    if vendor == "FN Chair":
        if re.search(r"level.?one|one.?blue", name):
            score += 1000
        if re.search(r"level.?two|two.?orange", name):
            score -= 1000
    if "wholesale" in name:
        score += 50
    if "2026" in name or re.search(r"20\d{2}", name):
        score += 30
    if "master" in name:
        score += 20
    if re.search(r"level.?one", name):
        score += 15
    if re.search(r"level.?two", name):
        score -= 20
    if "retail" in name and "wholesale" not in name:
        score -= 10
    if "footer" in name:
        score -= 8
    size = p.stat().st_size
    ext_pref = {".xlsx": 3, ".xlsm": 2, ".xls": 1}.get(p.suffix.lower(), 0)
    return (-score, -ext_pref, -size, p.name)


def backup_db() -> None:
    try:
        from scripts.backup_db import backup_now

        path = backup_now()
        log(f"DB backup → {path}")
    except Exception:
        # fallback CLI
        py = ROOT / ".venv" / "bin" / "python"
        if py.exists():
            subprocess.run(
                [str(py), "-m", "backend.cli", "backup-db"],
                cwd=str(ROOT),
                check=False,
            )
            log("DB backup via CLI")


def import_folder(out_dir: Path) -> dict[str, Any]:
    from backend import PriceBookService

    db = ROOT / "master_pricebook.db"
    con = sqlite3.connect(str(db))
    svc = PriceBookService(db_path=str(db))
    svc.init()

    plan: list[tuple[str, Path, list[Path]]] = []
    for d in sorted(out_dir.iterdir()):
        if not d.is_dir():
            continue
        vendor = vendor_from_folder(d.name)
        if is_ignored_builder(vendor=vendor, title=d.name, slug=d.name):
            log(f"  ignore builder folder: {d.name}")
            continue
        files = [
            p
            for p in d.rglob("*")
            if p.is_file()
            and p.suffix.lower() in EXCEL_EXT
            and not p.name.startswith("~$")
            and "__MACOSX" not in str(p)
            and p.stat().st_size > 2000
        ]
        if not files:
            continue
        if vendor == "FN Chair":
            one = [
                p
                for p in files
                if re.search(r"level.?one|one.?blue", p.name, re.I)
            ]
            if one:
                files = one
        files = sorted(set(files), key=lambda p: rank_file(p, vendor))
        plan.append((vendor, files[0], files[1:]))

    log(f"Import plan: {len(plan)} builders")
    report: list[dict] = []
    ok = err = skip = 0

    for i, (vendor, best, extras) in enumerate(plan, 1):
        mult = 1.7 if vendor == "Genuine Oak" else 2.7
        log(f"[{i}/{len(plan)}] {vendor} ← {best.name}")
        entry: dict[str, Any] = {
            "vendor": vendor,
            "file": str(best),
            "mult": mult,
            "extras": [str(e) for e in extras],
        }
        try:
            data = best.read_bytes()
            prev = svc.preview_excel(
                data,
                filename=best.name,
                vendor=vendor,
                multiplier=mult,
                use_workbook_markup=False,
            )
            rows = prev.rows or []
            if len(rows) < 5:
                prev = svc.preview_excel(
                    data,
                    filename=best.name,
                    vendor=vendor,
                    multiplier=mult,
                    use_workbook_markup=True,
                )
                rows = prev.rows or []
                entry["used_markup"] = True
            entry["preview_rows"] = len(rows)
            if len(rows) < 5:
                entry["status"] = "error"
                entry["error"] = f"too few rows ({len(rows)})"
                err += 1
                log(f"  ERR few rows {len(rows)}")
                report.append(entry)
                continue
            existing = con.execute(
                "select count(*) from pricebook where vendor=?", (vendor,)
            ).fetchone()[0]
            # Never wipe a large catalog with a tiny parse
            if existing > 200 and len(rows) < max(30, int(existing * 0.05)):
                entry["status"] = "skipped_keep_existing"
                entry["error"] = f"existing={existing} new={len(rows)}"
                skip += 1
                log(f"  SKIP keep existing {existing}")
                report.append(entry)
                continue
            result = svc.add_rows(rows, mode="replace_vendor")
            try:
                svc.set_vendor_multiplier(vendor, mult)
            except Exception:
                pass
            entry["status"] = "ok"
            entry["result"] = result
            ok += 1
            log(f"  OK total={result.get('total')}")
        except Exception as e:
            entry["status"] = "error"
            entry["error"] = f"{type(e).__name__}: {e}"
            entry["trace"] = traceback.format_exc()[-400:]
            err += 1
            log(f"  ERR {e}")
        report.append(entry)

    stats = svc.stats()
    con.close()
    summary = {
        "ok": ok,
        "err": err,
        "skip": skip,
        "stats": stats,
        "details": report,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    return summary


def save_state(state: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Viztech → FAF monthly sync")
    ap.add_argument("--dry-run", action="store_true", help="Login + list builders only")
    ap.add_argument("--download-only", action="store_true")
    ap.add_argument("--import-only", metavar="DIR", help="Import from existing download dir")
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args(argv)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    log(f"=== Viztech sync start {run_id} ===")

    if args.import_only:
        out_dir = Path(args.import_only)
        if not out_dir.is_dir():
            log(f"Not a directory: {out_dir}")
            return 1
        if not args.no_backup:
            backup_db()
        summary = import_folder(out_dir)
        report_path = DOWNLOAD_ROOT / f"import_report_{run_id}.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(summary, indent=2, default=str))
        log(f"Import report → {report_path}")
        log(f"DONE ok={summary['ok']} err={summary['err']} skip={summary['skip']} stats={summary['stats']}")
        save_state(
            {
                "last_run": run_id,
                "last_success": datetime.now(timezone.utc).isoformat(),
                "mode": "import-only",
                "summary": {
                    k: summary[k] for k in ("ok", "err", "skip", "stats")
                },
            }
        )
        return 0 if summary["err"] < summary["ok"] or summary["ok"] > 0 else 1

    user, password = load_credentials()
    session = http_session()
    login(session, user, password)
    slugs = list_builder_slugs(session)

    if args.dry_run:
        log(f"Dry-run OK — {len(slugs)} builders visible")
        save_state(
            {
                "last_run": run_id,
                "last_check": datetime.now(timezone.utc).isoformat(),
                "mode": "dry-run",
                "builders_seen": len(slugs),
            }
        )
        return 0

    catalog = fetch_catalog(session, slugs)
    out_dir = DOWNLOAD_ROOT / f"sync-{run_id}"
    dl_results = download_catalog(session, catalog, out_dir)
    cat_path = out_dir / "catalog.json"
    cat_path.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    (out_dir / "download_results.json").write_text(
        json.dumps(dl_results, indent=2), encoding="utf-8"
    )

    if args.download_only:
        log(f"Download-only complete → {out_dir}")
        save_state(
            {
                "last_run": run_id,
                "last_download": datetime.now(timezone.utc).isoformat(),
                "mode": "download-only",
                "dir": str(out_dir),
            }
        )
        return 0

    if not args.no_backup:
        backup_db()

    summary = import_folder(out_dir)
    report_path = out_dir / "import_report.json"
    report_path.write_text(json.dumps(summary, indent=2, default=str))
    # also copy to backups for easy finding
    (LOG_DIR / f"viztech_sync_report_{run_id}.json").write_text(
        json.dumps(summary, indent=2, default=str)
    )
    log(f"Import report → {report_path}")
    log(
        f"DONE ok={summary['ok']} err={summary['err']} skip={summary['skip']} "
        f"stats={summary['stats']}"
    )
    save_state(
        {
            "last_run": run_id,
            "last_success": datetime.now(timezone.utc).isoformat(),
            "mode": "full",
            "dir": str(out_dir),
            "summary": {k: summary[k] for k in ("ok", "err", "skip", "stats")},
            "next_due_hint": "Scheduled every 30 days via LaunchAgent",
        }
    )
    # Streamlit reads DB live; restart not required. Touch state for ops.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
