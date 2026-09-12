"""One explicit registry for Builder reader identity, detection, and dispatch."""

from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass
from typing import Any, Optional, Sequence


@dataclass(frozen=True)
class ReaderEntry:
    parser_id: str
    vendor: str
    detector: str = ""
    reader: str = ""
    layouts: tuple[str, ...] = ()
    specific: bool = True
    detect_fn: Any = None
    reader_fn: Any = None


def _symbol(path: str):
    module_name, symbol_name = path.rsplit(":", 1)
    return getattr(importlib.import_module(module_name), symbol_name)


class BuilderReaderRegistry:
    """Deep in-process module for all workbook reader routing."""

    def __init__(self, entries: Sequence[ReaderEntry]):
        self.entries = tuple(entries)
        ids = [entry.parser_id for entry in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate Builder reader id")
        self._by_id = {entry.parser_id: entry for entry in self.entries}

    @property
    def parser_ids(self) -> tuple[str, ...]:
        return tuple(self._by_id)

    @property
    def specific_ids(self) -> frozenset[str]:
        return frozenset(e.parser_id for e in self.entries if e.specific)

    @property
    def generic_ids(self) -> frozenset[str]:
        return frozenset(e.parser_id for e in self.entries if not e.specific)

    def get(self, parser_id: str) -> Optional[ReaderEntry]:
        return self._by_id.get((parser_id or "").strip().lower())

    def infer(self, detected: str = "", layouts: Optional[Sequence[str]] = None) -> str:
        raw = (detected or "").strip().lower()
        if raw in self._by_id:
            return raw
        for layout in layouts or ():
            key = str(layout or "").strip().lower()
            for entry in self.entries:
                if any(key == tag or key.startswith(tag) for tag in entry.layouts):
                    return entry.parser_id
        return "generic"

    def _detector_hits(
        self,
        filename: str = "",
        *,
        sheet_names: Optional[list[str]] = None,
        data: Optional[bytes] = None,
    ) -> list[tuple[str, str]]:
        names = list(sheet_names or [])
        hits: list[tuple[str, str]] = []
        for entry in self.entries:
            if not entry.specific:
                continue
            detector = entry.detect_fn
            if detector is None:
                if not entry.detector:
                    continue
                detector = _symbol(entry.detector)
            kwargs = {
                "filename": filename,
                "sheet_names": names,
                "data": data,
            }
            params = inspect.signature(detector).parameters
            accepted = {key: value for key, value in kwargs.items() if key in params}
            try:
                matched = bool(detector(**accepted))
            except (TypeError, ValueError, OSError):
                matched = False
            if matched:
                hits.append((entry.vendor, entry.parser_id))
        return hits

    def detect(
        self,
        filename: str = "",
        *,
        sheet_names: Optional[list[str]] = None,
        data: Optional[bytes] = None,
    ) -> tuple[str, str]:
        hits = self._detector_hits(filename, sheet_names=sheet_names, data=data)
        return hits[0] if hits else ("", "")

    def detect_all(
        self,
        filename: str = "",
        *,
        sheet_names: Optional[list[str]] = None,
        data: Optional[bytes] = None,
    ) -> tuple[tuple[str, str], ...]:
        """Every specific reader that claims this file. Empty if none.

        ``detect`` stays first-win. Collision tests use this so a later
        factory cannot hide behind registry order.
        """
        return tuple(self._detector_hits(filename, sheet_names=sheet_names, data=data))

    def run(
        self,
        parser_id: str,
        data: bytes,
        *,
        vendor: str = "",
        default_collection: str = "",
        sheet_filter: Optional[list[str]] = None,
        filename: str = "",
    ):
        entry = self.get(parser_id)
        if entry is None or not entry.specific:
            return None
        reader = entry.reader_fn
        if reader is None:
            if not entry.reader:
                return None
            reader = _symbol(entry.reader)
        return reader(
            data,
            vendor=vendor,
            default_collection=default_collection,
            sheet_filter=sheet_filter,
            filename=filename,
        )


from backend.catalog_readers import catalog_reader_entries

DEFAULT_READER_REGISTRY = BuilderReaderRegistry(
    (
        ReaderEntry(
            "fn_chair",
            "FN Chair",
            "backend.fn_chair_import:looks_like_fn_level_one",
            "backend.fn_chair_import:import_fn_chair_workbook",
            ("fn_chair", "fn_level_one_pl_print"),
        ),
        ReaderEntry(
            "artisan_chairs",
            "Artisan Chairs",
            "backend.artisan_chairs_import:looks_like_artisan_chairs",
            "backend.artisan_chairs_import:import_artisan_chairs_workbook",
            ("artisan_chairs",),
        ),
        ReaderEntry(
            "criswell",
            "Criswell Bedroom",
            "backend.criswell_import:looks_like_criswell",
            "backend.criswell_import:import_criswell_workbook",
            ("criswell",),
        ),
        ReaderEntry(
            "jmw",
            "J & M Woodworking",
            "backend.jmw_import:looks_like_jmw",
            "backend.jmw_import:import_jmw_workbook",
            ("jmw", "jmw_br_maple_expand"),
        ),
        ReaderEntry(
            "ashery_oak",
            "Ashery Oak",
            "backend.ashery_oak_import:looks_like_ashery_oak",
            "backend.ashery_oak_import:import_ashery_oak_workbook",
            ("ashery_oak", "ashery_oak_master_wood_expand", "ao_master_wood_expand"),
        ),
        ReaderEntry(
            "patio_kraft",
            "Patio Kraft",
            "backend.patio_kraft_import:looks_like_patio_kraft",
            "backend.patio_kraft_import:import_patio_kraft_workbook",
            ("patio_kraft",),
        ),
        ReaderEntry(
            "amish_aspen",
            "Amish Aspen",
            "backend.amish_aspen_import:looks_like_amish_aspen",
            "backend.amish_aspen_import:import_amish_aspen_workbook",
            ("amish_aspen",),
        ),
        ReaderEntry(
            "hillside_chair",
            "Hillside Chair",
            "backend.hillside_chair_import:looks_like_hillside_chair",
            "backend.hillside_chair_import:import_hillside_chair_workbook",
            ("hillside_chair",),
        ),
        ReaderEntry(
            "maple_lane",
            "Maple Lane",
            "backend.maple_lane_import:looks_like_maple_lane",
            "backend.maple_lane_import:import_maple_lane_workbook",
            ("maple_lane",),
        ),
        ReaderEntry(
            "hw_chair_markup",
            "Hope Wood",
            "backend.hw_chair_import:looks_like_hw_chair_markup",
            "backend.hw_chair_import:import_hw_chair_workbook",
            ("hw_chair", "hw_chair_markup"),
        ),
        ReaderEntry(
            "lamb",
            "LAMB",
            "backend.lamb_import:looks_like_lamb",
            "backend.lamb_import:import_lamb_workbook",
            ("lamb",),
        ),
        ReaderEntry(
            "luxhome",
            "LuxHome",
            "backend.luxhome_import:looks_like_luxhome",
            "backend.luxhome_import:import_luxhome_workbook",
            ("luxhome",),
        ),
        ReaderEntry(
            "windy_acres",
            "Windy Acres Furniture",
            "backend.windy_acres_import:looks_like_windy_acres",
            "backend.windy_acres_import:import_windy_acres_workbook",
            ("windy_acres",),
        ),
        *catalog_reader_entries(),
        ReaderEntry("generic", "", "", "", ("wide_species", "wide_finish", "long_flat"), False),
        ReaderEntry("pdf", "", "", "", ("pdf",), False),
    )
)
