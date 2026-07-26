"""Batch import supplier Excel/PDF files from a folder."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from backend.config import DEFAULT_MULTIPLIER
from backend.import_service import ImportService
from backend.repository import PriceBookRepository


EXCEL_EXT = {".xlsx", ".xls", ".xlsm"}
PDF_EXT = {".pdf"}
SKIP_NAME_BITS = ("~$", ".ds_store")


@dataclass
class BatchFileResult:
    path: str
    vendor: str
    status: str  # ok | skipped | error
    inserted: int = 0
    updated: int = 0
    total: int = 0
    message: str = ""
    markup: Optional[float] = None


@dataclass
class BatchResult:
    files: list[BatchFileResult] = field(default_factory=list)

    @property
    def ok_count(self) -> int:
        return sum(1 for f in self.files if f.status == "ok")

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.files if f.status == "error")

    @property
    def rows_total(self) -> int:
        return sum(f.total for f in self.files)


def _vendor_from_name(path: Path, override: str = "") -> str:
    """One builder = one vendor name (never year/filename twins)."""
    from backend.standardize import resolve_builder_vendor

    if override:
        return resolve_builder_vendor(override) or override.strip()
    return (
        resolve_builder_vendor(path.stem, filename=path.name)
        or path.stem[:80]
        or path.name
    )


class BatchImporter:
    def __init__(
        self,
        repo: PriceBookRepository,
        imports: Optional[ImportService] = None,
    ):
        self.repo = repo
        self.imports = imports or ImportService()

    def discover(self, folder: str | Path, recursive: bool = False) -> list[Path]:
        root = Path(folder)
        if not root.is_dir():
            return []
        pattern = "**/*" if recursive else "*"
        files = []
        for p in sorted(root.glob(pattern)):
            if not p.is_file():
                continue
            name_l = p.name.lower()
            if any(b in name_l for b in SKIP_NAME_BITS):
                continue
            if p.suffix.lower() in EXCEL_EXT | PDF_EXT:
                files.append(p)
        return files

    def run(
        self,
        folder: str | Path,
        *,
        recursive: bool = False,
        mode: str = "upsert",
        multiplier: float = DEFAULT_MULTIPLIER,
        use_workbook_markup: bool = True,
        vendor_override: str = "",
        excel_only: bool = False,
        progress: Optional[Callable[[str], None]] = None,
    ) -> BatchResult:
        result = BatchResult()
        files = self.discover(folder, recursive=recursive)
        if excel_only:
            files = [f for f in files if f.suffix.lower() in EXCEL_EXT]

        # Prefer one file per builder when several map to the same vendor
        # (e.g. MWS 2023 + Millers 2026) — keep the **last** sorted path.
        chosen: dict[str, Path] = {}
        order: list[str] = []
        skipped_dup_files: list[tuple[str, str, str]] = []
        for path in files:
            vendor = _vendor_from_name(path, vendor_override)
            if vendor in chosen:
                # Drop the previous file for this builder; keep this one
                prev = chosen[vendor]
                skipped_dup_files.append((prev.name, path.name, vendor))
            else:
                order.append(vendor)
            chosen[vendor] = path

        for dropped_name, kept_name, vendor in skipped_dup_files:
            result.files.append(
                BatchFileResult(
                    path=dropped_name,
                    vendor=vendor,
                    status="skipped",
                    message=(
                        f"Duplicate builder — using {kept_name} only "
                        f"(one catalog per builder)"
                    ),
                )
            )
            if progress:
                progress(
                    f"Skip {dropped_name} (same builder as {kept_name} → {vendor})"
                )

        for vendor in order:
            path = chosen[vendor]
            if progress:
                progress(f"Importing {path.name} → {vendor}…")
            try:
                data = path.read_bytes()
                if path.suffix.lower() in EXCEL_EXT:
                    prev = self.imports.preview_excel(
                        data,
                        filename=path.name,
                        vendor=vendor,
                        multiplier=multiplier,
                        use_workbook_markup=use_workbook_markup,
                    )
                    rows = prev.rows
                    markup = prev.detected_markup
                    mult_used = prev.multiplier_used
                else:
                    prev_pdf = self.imports.preview_pdf(
                        data,
                        filename=path.name,
                        vendor=vendor,
                        multiplier=multiplier,
                        max_pages=None,
                    )
                    rows = prev_pdf.rows
                    markup = None
                    mult_used = multiplier

                if not rows:
                    result.files.append(
                        BatchFileResult(
                            path=str(path),
                            vendor=vendor,
                            status="skipped",
                            message="0 rows parsed",
                            markup=markup,
                        )
                    )
                    continue

                from backend.pricing import retail_from_wholesale

                for r in rows:
                    r["vendor"] = vendor
                    r["multiplier"] = mult_used
                    if r.get("base_price") is not None:
                        r["adjusted_price"] = retail_from_wholesale(
                            r["base_price"], mult_used
                        )

                # One builder = one catalog. replace_* clears the vendor first.
                use_mode = mode
                if use_mode in (
                    "replace_vendor",
                    "replace_builder",
                    "replace_source",
                ):
                    deleted = self.repo.delete_by_vendor(vendor)
                    n = self.repo.insert_rows(rows)
                    counts = {
                        "inserted": n,
                        "updated": 0,
                        "total": n,
                        "deleted": deleted,
                    }
                elif use_mode == "upsert":
                    counts = self.repo.upsert_rows(rows)
                    counts["deleted"] = 0
                else:
                    n = self.repo.insert_rows(rows)
                    counts = {"inserted": n, "updated": 0, "total": n, "deleted": 0}

                self.repo.set_vendor_multiplier(vendor, float(mult_used))

                result.files.append(
                    BatchFileResult(
                        path=str(path),
                        vendor=vendor,
                        status="ok",
                        inserted=counts.get("inserted", 0),
                        updated=counts.get("updated", 0),
                        total=counts.get("total", 0),
                        message=f"mult={mult_used:g} mode={use_mode}",
                        markup=markup,
                    )
                )
            except Exception as e:
                result.files.append(
                    BatchFileResult(
                        path=str(path),
                        vendor=vendor,
                        status="error",
                        message=str(e)[:300],
                    )
                )
        return result
