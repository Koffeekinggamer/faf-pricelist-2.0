#!/usr/bin/env python3
"""Private local backup / restore of master_pricebook.db (not for GitHub)."""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def db_path() -> Path:
    return project_root() / "master_pricebook.db"


def backup_dir() -> Path:
    return Path(
        os.environ.get(
            "FAF_PRICEBOOK_BACKUP_DIR",
            Path.home() / "Documents" / "FAF-pricebook-backups",
        )
    )


def list_backups(limit: int = 50) -> list[Path]:
    d = backup_dir()
    if not d.is_dir():
        return []
    files = sorted(
        d.glob("master_pricebook-*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[:limit]


def backup_now(*, keep: int = 20) -> Path:
    """Snapshot live DB into backup dir. Returns destination path."""
    db = db_path()
    if not db.is_file():
        raise FileNotFoundError(f"No database at {db}")

    dest_dir = backup_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = dest_dir / f"master_pricebook-{stamp}.db"

    src = sqlite3.connect(str(db))
    dst = sqlite3.connect(str(dest))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    backups = list_backups(limit=9999)
    for old in backups[keep:]:
        old.unlink(missing_ok=True)

    return dest


def restore_from(backup: Path, *, also_backup_current: bool = True) -> Path:
    """
    Replace live DB with a backup file.
    Optionally snapshot the current DB first as safety.
    Returns path to live DB.
    """
    backup = Path(backup)
    if not backup.is_file():
        raise FileNotFoundError(f"Backup not found: {backup}")

    live = db_path()
    if also_backup_current and live.is_file():
        # Safety copy before overwrite
        safety_dir = backup_dir() / "pre-restore"
        safety_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safety = safety_dir / f"pre-restore-{stamp}.db"
        src = sqlite3.connect(str(live))
        dst = sqlite3.connect(str(safety))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()

    # Copy via sqlite backup API into live path (atomic-ish replace)
    tmp = live.with_suffix(".db.restoring")
    if tmp.exists():
        tmp.unlink()
    src = sqlite3.connect(str(backup))
    dst = sqlite3.connect(str(tmp))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    tmp.replace(live)
    return live


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Backup / restore FAF price book DB")
    parser.add_argument(
        "action",
        nargs="?",
        default="backup",
        choices=["backup", "list", "restore"],
        help="backup (default), list, or restore",
    )
    parser.add_argument(
        "--file",
        type=str,
        default="",
        help="Backup file path or name for restore",
    )
    args = parser.parse_args(argv)

    if args.action == "backup":
        try:
            dest = backup_now()
        except FileNotFoundError as e:
            print(e)
            return 1
        size_mb = dest.stat().st_size / (1024 * 1024)
        print(f"Backed up → {dest} ({size_mb:.1f} MB)")
        print(f"Backups in {backup_dir()}: {len(list_backups())} kept (max 20)")
        return 0

    if args.action == "list":
        files = list_backups()
        if not files:
            print(f"No backups in {backup_dir()}")
            return 0
        for p in files:
            age = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            mb = p.stat().st_size / (1024 * 1024)
            print(f"{p.name}  {mb:.1f} MB  {age}")
        return 0

    # restore
    if not args.file:
        print("restore requires --file PATH_OR_NAME")
        return 1
    cand = Path(args.file)
    if not cand.is_file():
        cand = backup_dir() / args.file
    try:
        live = restore_from(cand)
    except FileNotFoundError as e:
        print(e)
        return 1
    print(f"Restored {cand.name} → {live}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
