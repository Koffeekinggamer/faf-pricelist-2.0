"""Import orchestration: Excel workbooks + PDF price lists → row dicts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from backend.config import DEFAULT_MULTIPLIER
from backend.normalize import long_df_to_rows, normalize_dataframe, read_excel_bytes


@dataclass
class ExcelImportPreview:
    long_df: pd.DataFrame
    sheets_tried: list[dict] = field(default_factory=list)
    detected_markup: Optional[float] = None
    sheet_names: list[str] = field(default_factory=list)
    notes: str = ""
    rows: list[dict] = field(default_factory=list)
    multiplier_used: float = DEFAULT_MULTIPLIER


@dataclass
class PdfImportPreview:
    results: list  # ParseResult-like from pdf_import
    stats: dict
    chosen_name: str = ""
    long_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    rows: list[dict] = field(default_factory=list)


class ImportService:
    """Parse supplier files into normalized master rows (does not write DB)."""

    def preview_excel(
        self,
        data: bytes,
        *,
        filename: str = "",
        vendor: str = "",
        default_collection: str = "",
        multiplier: float = DEFAULT_MULTIPLIER,
        sheet_filter: Optional[list[str]] = None,
        use_workbook_markup: bool = False,
        species_keep: Optional[list[str]] = None,
    ) -> ExcelImportPreview:
        from wide_import import import_workbook

        wb = import_workbook(
            data,
            vendor=vendor,
            default_collection=default_collection,
            sheet_filter=sheet_filter,
            filename=filename,
        )
        mult = float(multiplier)
        if use_workbook_markup and wb.detected_markup:
            mult = float(wb.detected_markup)

        long_df = wb.long_df
        if species_keep and not long_df.empty and "species" in long_df.columns:
            long_df = long_df[
                long_df["species"].isna() | long_df["species"].isin(species_keep)
            ].copy()

        rows = long_df_to_rows(
            long_df,
            source_file=filename,
            multiplier=mult,
            vendor=vendor,
            default_collection=default_collection,
        )
        return ExcelImportPreview(
            long_df=long_df,
            sheets_tried=wb.sheets_tried,
            detected_markup=wb.detected_markup,
            sheet_names=wb.sheet_names,
            notes=wb.notes,
            rows=rows,
            multiplier_used=mult,
        )

    def preview_excel_manual(
        self,
        data: bytes,
        *,
        filename: str = "",
        vendor: str = "",
        default_collection: str = "",
        multiplier: float = DEFAULT_MULTIPLIER,
        column_map: Optional[dict[str, str]] = None,
    ) -> list[dict]:
        df = read_excel_bytes(data)
        return normalize_dataframe(
            df,
            source_file=filename,
            default_collection=default_collection,
            multiplier=multiplier,
            column_map=column_map,
            vendor=vendor,
        )

    def preview_pdf(
        self,
        data: bytes,
        *,
        filename: str = "",
        vendor: str = "",
        default_collection: str = "",
        multiplier: float = DEFAULT_MULTIPLIER,
        max_pages: Optional[int] = None,
        strategy_index: int = 0,
        species_mode: str = "all",
        species_keep: Optional[list[str]] = None,
    ) -> PdfImportPreview:
        from pdf_import import (
            expand_species_choice,
            parse_pdf_pricelist,
            result_to_import_df,
        )

        results, stats = parse_pdf_pricelist(data, max_pages=max_pages)
        if not results:
            return PdfImportPreview(results=[], stats=stats)

        idx = max(0, min(strategy_index, len(results) - 1))
        chosen = results[idx]
        df = result_to_import_df(chosen)
        if "species" in df.columns and not df["species"].dropna().empty:
            df = expand_species_choice(df, mode=species_mode, species_keep=species_keep)

        if chosen.name == "tables":
            rows = normalize_dataframe(
                df,
                source_file=filename,
                default_collection=default_collection,
                multiplier=multiplier,
                vendor=vendor,
            )
        else:
            col_map = {
                c: c
                for c in (
                    "part_number",
                    "description",
                    "base_price",
                    "species",
                    "collection",
                    "unit",
                    "notes",
                )
                if c in df.columns
            }
            rows = normalize_dataframe(
                df,
                source_file=filename,
                default_collection=default_collection,
                multiplier=multiplier,
                column_map=col_map,
                vendor=vendor,
            )
            if default_collection:
                for r in rows:
                    if not r.get("collection"):
                        r["collection"] = default_collection
            if vendor:
                for r in rows:
                    if not r.get("vendor"):
                        r["vendor"] = vendor

        return PdfImportPreview(
            results=results,
            stats=stats,
            chosen_name=chosen.name,
            long_df=df,
            rows=rows,
        )
