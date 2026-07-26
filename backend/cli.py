"""
Price Book backend CLI.

  python -m backend.cli stats
  python -m backend.cli search "oak nightstand"
  python -m backend.cli import-xlsx path.xlsx --vendor "Genuine Oak" --use-markup
  python -m backend.cli batch /path/to/folder --excel-only
  python -m backend.cli dups
  python -m backend.cli cleanup-dups --execute
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from backend import PriceBookService

    p = argparse.ArgumentParser(description="Price Book backend CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_db(sp_):
        sp_.add_argument("--db", default=None, help="SQLite path override")

    sp_stats = sub.add_parser("stats", help="Row / vendor / quote counts")
    add_db(sp_stats)

    sp = sub.add_parser("search", help="Search master")
    add_db(sp)
    sp.add_argument("query", nargs="?", default="")
    sp.add_argument("--vendor", default=None)
    sp.add_argument("--limit", type=int, default=20)

    ip = sub.add_parser("import-xlsx", help="Import Excel workbook")
    add_db(ip)
    ip.add_argument("path")
    ip.add_argument("--vendor", default="")
    ip.add_argument("--multiplier", type=float, default=2.7)
    ip.add_argument(
        "--mode",
        choices=["append", "upsert", "replace_source", "replace_vendor"],
        default="replace_vendor",
        help="replace_vendor = one catalog per builder (default)",
    )
    ip.add_argument("--use-markup", action="store_true")

    bp = sub.add_parser("batch", help="Import all price files in a folder")
    add_db(bp)
    bp.add_argument("folder")
    bp.add_argument("--recursive", action="store_true")
    bp.add_argument("--excel-only", action="store_true", default=True)
    bp.add_argument("--include-pdf", action="store_true")
    bp.add_argument("--multiplier", type=float, default=2.7)
    bp.add_argument("--use-markup", action="store_true", default=True)
    bp.add_argument(
        "--mode",
        choices=["append", "upsert", "replace_source", "replace_vendor"],
        default="replace_vendor",
        help="replace_vendor = wipe+reload each builder (default; no twins)",
    )
    bp.add_argument("--vendor", default="", help="Force one vendor name")

    dp = sub.add_parser("dups", help="Show duplicate identity groups")
    add_db(dp)
    dp.add_argument("--limit", type=int, default=20)

    cp = sub.add_parser("cleanup-dups", help="Remove older duplicate rows")
    add_db(cp)
    cp.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete (default is dry-run)",
    )

    mp = sub.add_parser("set-multiplier", help="Save per-vendor multiplier")
    add_db(mp)
    mp.add_argument("vendor")
    mp.add_argument("multiplier", type=float)

    vp = sub.add_parser("vendors", help="Vendor summary table")
    add_db(vp)

    sp_std = sub.add_parser(
        "standardize",
        help="Rewrite master rows to canonical vendor/species/finish/collection shape",
    )
    add_db(sp_std)

    sp_bak = sub.add_parser(
        "backup-db",
        help="Copy master_pricebook.db to ~/Documents/FAF-pricebook-backups (local only)",
    )
    add_db(sp_bak)

    args = p.parse_args(argv)
    svc = PriceBookService(db_path=getattr(args, "db", None))
    svc.init()

    if args.cmd == "stats":
        print(svc.stats())
        return 0

    if args.cmd == "search":
        df = svc.search(args.query, vendor=args.vendor, limit=args.limit)
        if df.empty:
            print("(no rows)")
        else:
            cols = [
                c
                for c in [
                    "id",
                    "vendor",
                    "part_number",
                    "description",
                    "species",
                    "base_price",
                    "adjusted_price",
                ]
                if c in df.columns
            ]
            print(df[cols].to_string(index=False))
            print(f"\n{len(df)} rows")
        return 0

    if args.cmd == "import-xlsx":
        from backend.standardize import resolve_builder_vendor

        path = Path(args.path)
        data = path.read_bytes()
        vendor = resolve_builder_vendor(
            args.vendor or path.stem, filename=path.name
        ) or (args.vendor or path.stem)
        preview = svc.preview_excel(
            data,
            filename=path.name,
            vendor=vendor,
            multiplier=args.multiplier,
            use_workbook_markup=args.use_markup,
        )
        print(preview.notes)
        print(
            f"Builder: {vendor} (one catalog) · "
            f"Preview rows: {len(preview.rows)} · mult={preview.multiplier_used} · mode={args.mode}"
        )
        result = svc.add_rows(preview.rows, mode=args.mode)
        svc.set_vendor_multiplier(vendor, preview.multiplier_used)
        print(result)
        print("stats:", svc.stats())
        return 0

    if args.cmd == "batch":
        excel_only = not args.include_pdf
        print(f"Batch → {args.folder} (excel_only={excel_only}, mode={args.mode})")
        result = svc.batch_import(
            args.folder,
            recursive=args.recursive,
            mode=args.mode,
            multiplier=args.multiplier,
            use_workbook_markup=args.use_markup,
            vendor_override=args.vendor,
            excel_only=excel_only,
            progress=lambda m: print(" ", m),
        )
        for f in result.files:
            print(
                f"  [{f.status:7}] {Path(f.path).name:50} "
                f"in={f.inserted} up={f.updated} · {f.message}"
            )
        print(
            f"\nOK {result.ok_count} · errors {result.error_count} · "
            f"rows {result.rows_total} · master {svc.row_count()}"
        )
        return 0 if result.error_count == 0 else 1

    if args.cmd == "dups":
        df = svc.find_duplicates(limit=args.limit)
        if df.empty:
            print("No duplicate groups.")
        else:
            print(df.to_string(index=False))
        return 0

    if args.cmd == "cleanup-dups":
        report = svc.cleanup_duplicates(dry_run=not args.execute)
        print(report)
        return 0

    if args.cmd == "set-multiplier":
        svc.set_vendor_multiplier(args.vendor, args.multiplier)
        print(f"Saved {args.vendor} → {args.multiplier}")
        return 0

    if args.cmd == "vendors":
        df = svc.vendor_summary()
        if df.empty:
            print("(no vendors)")
        else:
            print(df.to_string(index=False))
        return 0

    if args.cmd == "standardize":
        report = svc.standardize_master()
        print("Standardize complete:", report)
        print("stats:", svc.stats())
        # optional: collapse dups created by name normalization
        dups = svc.cleanup_duplicates(dry_run=False)
        print("post-standardize dup cleanup:", dups)
        print("final stats:", svc.stats())
        print(svc.vendor_summary().to_string(index=False))
        return 0

    if args.cmd == "backup-db":
        import subprocess

        script = Path(__file__).resolve().parent.parent / "scripts" / "backup_db.py"
        return subprocess.call([sys.executable, str(script)])

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
