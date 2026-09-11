#!/usr/bin/env python3
"""Scaffold registry + profile + fixture + SETTLED placeholder for builder N.

Tracer only — does not invent a selling factory. Clone for a real factory:

    .venv/bin/python scripts/add_builder.py --vendor "Canonical Name"
    .venv/bin/python scripts/add_builder.py --vendor "Canonical Name" --write

Then splice the printed CatalogSpec (or ReaderEntry) and commit the profile
JSON plus Options fixture. Do not add the SETTLED placeholder to SETTLED
until a shape test exists. Never lock generic. Empty Options is a miss.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from backend.add_builder import (
        AddBuilderError,
        format_plan,
        plan_builder,
        write_scaffold,
    )

    parser = argparse.ArgumentParser(
        description="Plan or write an add_builder scaffold (not a selling factory)."
    )
    parser.add_argument("--vendor", required=True, help="Canonical builder display name")
    parser.add_argument(
        "--kind",
        choices=("catalog", "shape"),
        default="catalog",
        help="catalog = CatalogSpec token lock; shape = ReaderEntry + import module",
    )
    parser.add_argument(
        "--token",
        action="append",
        default=[],
        help="Optional extra detect token (repeatable). Refuses ac/ao/fnc/…",
    )
    parser.add_argument("--parser-id", default="", help="Override importer id (never generic/pdf)")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write profile JSON, Options fixture, test hook, and splice notes",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing generated profile (never used to downgrade a lock)",
    )
    parser.add_argument("--repo", type=Path, default=root, help="Repo root for --write")
    args = parser.parse_args(argv)

    try:
        plan = plan_builder(
            args.vendor,
            kind=args.kind,
            extra_tokens=args.token,
            parser_id=args.parser_id,
        )
    except AddBuilderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(format_plan(plan))
    if args.write:
        try:
            written = write_scaffold(plan, repo_root=args.repo, overwrite=args.overwrite)
        except AddBuilderError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"wrote {written.profile_path}")
        print(f"wrote {written.fixture_path}")
        print(f"wrote {written.hook_path}")
        print(f"wrote {written.splice_path}")
        print("Next: splice CatalogSpec/ReaderEntry, prove Options, leave SETTLED as placeholder.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
