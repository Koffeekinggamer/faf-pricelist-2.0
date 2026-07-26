#!/usr/bin/env python3
"""
Push a FAF quote (by id) or sample dining set to OrderTrac as a QUOTE.

  python scripts/ordertrac_push_quote.py --quote-id 1
  python scripts/ordertrac_push_quote.py --faf-ids 479060,482875 --qtys 1,4
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quote-id", type=int, default=None)
    ap.add_argument("--faf-ids", default="", help="Comma-separated pricebook ids")
    ap.add_argument("--qtys", default="", help="Comma-separated qtys matching faf-ids")
    ap.add_argument("--user", default="Miller, Judson")
    ap.add_argument("--location", default="Landrum")
    ap.add_argument("--wood", default="Red Oak")
    ap.add_argument("--stain", default="Michael's Cherry (OCS-113)")
    args = ap.parse_args()

    from backend.service import PriceBookService

    svc = PriceBookService()
    svc.init()

    if args.quote_id:
        result = svc.push_quote_to_ordertrac(
            args.quote_id,
            ot_user_display=args.user,
            location=args.location,
            mode="create",
        )
    elif args.faf_ids:
        ids = [int(x.strip()) for x in args.faf_ids.split(",") if x.strip()]
        qtys = [float(x.strip()) for x in args.qtys.split(",") if x.strip()] if args.qtys else None
        rows = []
        for i in ids:
            r = svc.get_row(i)
            if not r:
                print(f"Missing FAF id {i}", file=sys.stderr)
                return 1
            rows.append(r)
        result = svc.push_rows_to_ordertrac(
            rows,
            qtys=qtys,
            wood=args.wood,
            stain=args.stain,
            ot_user_display=args.user,
            location=args.location,
            project="FAF CLI push",
        )
    else:
        print("Provide --quote-id or --faf-ids", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
