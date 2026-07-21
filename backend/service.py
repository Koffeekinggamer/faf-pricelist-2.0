"""Orchestration for FAF Pricelist 2.0."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from . import db
from .config import DB_PATH, DEFAULT_MULTIPLIER
from .import_excel import parse_excel
from .pdf_catalog import catalog_pdf_bytes
from .pricing import retail_from_wholesale


class CatalogService:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or DB_PATH)

    def init(self) -> None:
        db.init_db(self.db_path)

    def stats(self) -> dict:
        return db.stats(self.db_path)

    def list_vendors(self) -> list[str]:
        return db.list_vendors(self.db_path)

    def get_multiplier(self, vendor: str) -> float:
        return db.get_multiplier(vendor, default=DEFAULT_MULTIPLIER, db_path=self.db_path)

    def set_multiplier(self, vendor: str, mult: float, notes: str = "") -> None:
        db.set_multiplier(vendor, mult, notes=notes, db_path=self.db_path)

    def set_phone(self, vendor: str, phone: str) -> None:
        db.set_phone(vendor, phone, db_path=self.db_path)

    def reapply_multiplier(self, vendor: str, mult: float) -> int:
        return db.reapply_multiplier(vendor, mult, db_path=self.db_path)

    def vendor_table(self) -> pd.DataFrame:
        return pd.DataFrame(db.vendor_table(self.db_path))

    def delete_vendor(self, vendor: str) -> int:
        return db.delete_vendor(vendor, db_path=self.db_path)

    def prepare_excel(
        self,
        data: bytes,
        *,
        filename: str,
        vendor: str = "",
        multiplier: Optional[float] = None,
    ) -> dict:
        builder = (vendor or "").strip()
        if not builder:
            # guess first, then check saved mult
            from .import_excel import _guess_builder

            builder = _guess_builder(filename, "")
        mult = multiplier
        if mult is None:
            mult = self.get_multiplier(builder)
        return parse_excel(
            data, filename=filename, vendor=builder, multiplier=float(mult)
        )

    def rows_frame(self, rows: list[dict], mult: float, vendor: str) -> pd.DataFrame:
        out = []
        for r in rows:
            item = dict(r)
            item["vendor"] = vendor
            item["multiplier"] = float(mult)
            bp = item.get("base_price")
            item["adjusted_price"] = retail_from_wholesale(bp, mult)
            out.append(item)
        return pd.DataFrame(out)

    def export_pdf(self, df: pd.DataFrame, title: str) -> bytes:
        return catalog_pdf_bytes(df, title=title)

    def save_builder(
        self, vendor: str, rows: list[dict], mult: float, source_file: str = ""
    ) -> dict:
        prepared = []
        for r in rows:
            item = dict(r)
            item["vendor"] = vendor
            item["multiplier"] = float(mult)
            item["source_file"] = source_file or item.get("source_file")
            item["adjusted_price"] = retail_from_wholesale(
                item.get("base_price"), mult
            )
            prepared.append(item)
        result = db.replace_vendor_rows(vendor, prepared, db_path=self.db_path)
        db.set_multiplier(
            vendor, float(mult), notes="From Drop files", db_path=self.db_path
        )
        return result
