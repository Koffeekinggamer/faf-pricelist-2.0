#!/usr/bin/env python3
"""Backup / list master DB for FAF Pricelist 2.0."""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.config import BACKUP_DIR, DB_PATH  # noqa: E402


def list_backups(limit: int = 30) -> list[Path]:
    if not BACKUP_DIR.is_dir():
        return []
    files = sorted(
        BACKUP_DIR.glob("master_pricebook-*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[:limit]


def backup_now() -> Path:
    if not DB_PATH.is_file():
        raise FileNotFoundError(f"No database at {DB_PATH}")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_DIR / f"master_pricebook-{stamp}.db"
    src = sqlite3.connect(str(DB_PATH))
    dst = sqlite3.connect(str(dest))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return dest


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["backup", "list"])
    args = p.parse_args()
    if args.cmd == "backup":
        dest = backup_now()
        print(dest)
    else:
        for f in list_backups():
            print(f.name)


if __name__ == "__main__":
    main()
