"""Load AJ's Furniture from its named reader now that the Options are captured.

The generic wide-species layout kept only the three wood price columns. It lost
the fabric tier, all five option charges, the Roughsawn Brown Maple column, the
occasional-table and accessory sections, and it tagged the Unfinished book as
``finished`` — so the floor saw one chair twice at two prices and no Options.

Read-only by default; pass ``--apply`` to write.
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

VENDOR = "AJ's Furniture"
MULTIPLIER = 2.7
SOURCE_DIR = Path(
    "/Users/lordjudsonmiller/Documents/viztech-downloads/all-20260717/AJ_039_s_Furniture"
)
SOURCE_FILES = (
    "Download_2026_Pricelist_Finished_301390.xls",
    "Download_2026_Pricelist_Unfinished_301389.xls",
    "Download_2026_LuxHome_Pricelist_648810.xls",
)
SOURCE_LABEL = "AJ_039_s_Furniture"


def parse_sources() -> pd.DataFrame:
    frames = []
    for name in SOURCE_FILES:
        path = SOURCE_DIR / name
        if not path.is_file():
            raise SystemExit(f"missing locked source: {path}")
        result = DEFAULT_READER_REGISTRY.run(
            "ajs_furniture", path.read_bytes(), vendor=VENDOR, filename=name
        )
        if result is None or result.long_df.empty:
            raise SystemExit(f"ajs reader did not read {name}")
        addons = int((result.long_df["line_kind"] == "addon").sum())
        print(f"{name}: {len(result.long_df):,} rows · {addons:,} option lines")
        frames.append(result.long_df)
    return pd.concat(frames, ignore_index=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    parsed = parse_sources()
    rows = long_df_to_rows(
        parsed,
        source_file=SOURCE_LABEL,
        multiplier=MULTIPLIER,
        vendor=VENDOR,
        default_collection="",
    )
    option_rows = sum(1 for row in rows if (row.get("option_key") or "").strip())
    if not option_rows:
        raise SystemExit("refused: no Option lines survived standardization")

    svc = PriceBookService()
    before = svc.repo.search("", vendor=VENDOR, limit=1_000_000)
    print(f"\nparsed {len(rows):,} rows · {option_rows:,} carry an Option")
    print(
        f"live {len(before):,} rows · options today "
        f"{int(before['option_key'].fillna('').astype(str).str.strip().ne('').sum()):,}"
    )

    if not args.apply:
        print("\ndry run — no changes written. Pass --apply to write.")
        return 0

    print("replace:", svc.repo.replace_vendor_rows(VENDOR, rows, multiplier=MULTIPLIER))
    after = svc.repo.search("", vendor=VENDOR, limit=1_000_000)
    print(f"\nlive {len(before):,} -> {len(after):,}")
    print("\nfinish_state:")
    print(after["finish_state"].fillna("(none)").value_counts().to_string())
    print("\noptions now:")
    print(after["option_key"].fillna("(none)").value_counts().to_string())
    print("\nwood now:")
    print(after["species"].fillna("(none)").value_counts().to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
