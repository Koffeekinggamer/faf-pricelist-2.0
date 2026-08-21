"""Load Criswell Bedroom from its locked parser after the wood-column fix.

Criswell's header band runs footnotes and drawer-unit callouts down the same
columns as the wood names, so the stored species strings were unrecoverable by
a text pass. This reparses the four locked source books and replaces that one
builder. Read-only by default; pass ``--apply`` to write.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from backend import PriceBookService
from backend.builder_reader_registry import DEFAULT_READER_REGISTRY
from backend.normalize import long_df_to_rows

VENDOR = "Criswell Bedroom"
SOURCE_DIR = Path(
    "/Users/lordjudsonmiller/Documents/Judson's old mac book pro/Downloads/"
    "CWF_Pricelists_2025_1224"
)
SOURCE_FILES = (
    "Beds A-F.xlsx",
    "Beds H-W.xlsx",
    "Wholesale Price List.xlsx",
    "Living Rooms Price List.xlsx",
)
MIN_RATIO = 0.95


def parse_sources(cache: Path) -> pd.DataFrame:
    if cache.is_file():
        print(f"using cached parse {cache}")
        return pd.read_pickle(cache)
    frames = []
    for name in SOURCE_FILES:
        path = SOURCE_DIR / name
        if not path.is_file():
            raise SystemExit(f"missing locked source: {path}")
        print(f"parsing {name} ({path.stat().st_size / 1e6:.0f} MB)", flush=True)
        result = DEFAULT_READER_REGISTRY.run(
            "criswell", path.read_bytes(), vendor=VENDOR, filename=name
        )
        if result is None:
            raise SystemExit(f"criswell parser did not read {name}")
        print(f"  rows: {len(result.long_df):,}")
        frames.append(result.long_df)
    parsed = pd.concat(frames, ignore_index=True)
    parsed.to_pickle(cache)
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--cache", default="/tmp/criswell_reparse.pkl")
    args = parser.parse_args()

    parsed = parse_sources(Path(args.cache))
    rows = long_df_to_rows(
        parsed,
        source_file="CWF_Pricelists_2025_1224",
        multiplier=2.7,
        vendor=VENDOR,
        default_collection="",
    )
    svc = PriceBookService()
    before = len(svc.repo.search("", vendor=VENDOR, limit=1_000_000))
    print(f"\nparsed {len(rows):,} rows · live {before:,}")

    if before and len(rows) < before * MIN_RATIO:
        raise SystemExit(
            f"refused: parsed {len(rows):,} is under {MIN_RATIO:.0%} of live {before:,}"
        )
    if not args.apply:
        print("dry run — no changes written. Pass --apply to write.")
        return 0

    print("replace:", svc.repo.replace_vendor_rows(VENDOR, rows, multiplier=2.7))
    after = svc.repo.search("", vendor=VENDOR, limit=1_000_000)
    print(f"live {before:,} -> {len(after):,}\n")
    print("wood column now:")
    print(after["species"].fillna("(none)").value_counts().head(10).to_string())
    print("\nsample rows:")
    for _, row in after.head(6).iterrows():
        print(
            f"  part={row['part_number']!r} "
            f"desc={str(row['description'])[:60]!r} wood={row['species']!r}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
