"""
Public facade for the Price Book backend.

UI and scripts should prefer this over touching repository/importers directly.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Optional, Sequence, Union

import pandas as pd

from backend.batch import BatchImporter, BatchResult
from backend.builder_profiles import (
    category_matches_override,
    load_builder_profile,
    override_applies,
)
from backend.config import (
    DB_PATH,
    DEFAULT_MULTIPLIER,
    DEFAULT_SEARCH_LIMIT,
    THIN_CATALOG_MAX_ROWS,
)
from backend.db import init_db
from backend.export import to_csv_bytes, to_excel_bytes, to_pdf_bytes
from backend.import_service import ExcelImportPreview, ImportService, PdfImportPreview
from backend.normalize import map_columns, read_excel_bytes
from backend.quotes import QuoteRepository
from backend.repository import PriceBookRepository
from backend.users import UserRepository


class PriceBookService:
    """Single entry point: catalog, import, pricing, quotes, users, batch, export."""

    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.repo = PriceBookRepository(self.db_path)
        self.quotes = QuoteRepository(self.db_path)
        self.users = UserRepository(self.db_path)
        self.imports = ImportService()
        self.batch = BatchImporter(self.repo, self.imports)
        self._ready = False
        # Injectable Drop parse session store root (tests / Fly temp).
        self._drop_parse_root: Optional[Path] = None

    # ------------------------------------------------------------------ lifecycle
    def init(self) -> Path:
        path = init_db(self.db_path)
        # Seed admin if empty (OrderTrac sync builds the rest)
        try:
            from backend.auth import ensure_seed_admin

            ensure_seed_admin(self.db_path)
        except Exception:
            pass
        self._ready = True
        return path

    def ensure_ready(self) -> None:
        if not self._ready:
            self.init()

    @property
    def path(self) -> Path:
        return self.db_path

    # ------------------------------------------------------------------ read
    def stats(self) -> dict:
        self.ensure_ready()
        s = self.repo.stats()
        s["quotes"] = self.quotes.quote_count()
        return s

    def row_count(self) -> int:
        self.ensure_ready()
        return self.repo.row_count()

    def search(
        self,
        query: str = "",
        *,
        collection: Optional[str] = None,
        vendor: Optional[str] = None,
        finish_state: Optional[str] = None,
        species: Optional[str] = None,
        option_key: Optional[Union[str, Sequence[str]]] = None,
        option_qty: Optional[dict[str, int]] = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> pd.DataFrame:
        self.ensure_ready()
        opts = self._normalize_option_keys(option_key)
        if (
            opts
            and vendor
            and vendor != "All"
        ):
            upcharged = self._search_with_item_option_upcharge(
                query,
                vendor=vendor,
                finish_state=finish_state,
                species=species,
                option_keys=opts,
                option_qty=option_qty or {},
                limit=limit,
            )
            if upcharged is not None:
                return upcharged
        # Repo accepts a single key or a list (IN filter).
        repo_opt: Optional[Union[str, Sequence[str]]] = None
        if len(opts) == 1:
            repo_opt = opts[0]
        elif len(opts) > 1:
            repo_opt = opts
        return self.repo.search(
            query,
            collection=collection,
            vendor=vendor,
            finish_state=finish_state,
            species=species,
            option_key=repo_opt,
            limit=limit,
        )

    @staticmethod
    def _normalize_option_keys(
        option_key: Optional[Union[str, Sequence[str]]],
    ) -> list[str]:
        """Flatten UI/API option selection into a de-duped list (no All/blank)."""
        if option_key is None:
            return []
        if isinstance(option_key, str):
            raw = [option_key]
        else:
            raw = list(option_key)
        out: list[str] = []
        seen: set[str] = set()
        for o in raw:
            s = (o or "").strip()
            if not s or s.lower() == "all":
                continue
            if s not in seen:
                seen.add(s)
                out.append(s)
        return out

    @staticmethod
    def _option_qty_allowed(option_key: str) -> bool:
        """True when floor may pick how many of this option to stack.

        Extra drawers/doors and undermount slides are per-opening charges on
        casegoods that may have more than one drawer or door.
        """
        o = (option_key or "").lower()
        if "extra" in o and ("drawer" in o or "door" in o):
            return True
        if "slide" in o and "drawer" in o:
            return True
        return False

    @staticmethod
    def _clamp_option_qty(qty: Any, *, default: int = 1) -> int:
        try:
            n = int(qty)
        except (TypeError, ValueError):
            return default
        return max(1, min(n, 20))

    # Options whose upcharge modifies the price of eligible ITEMS (drawered /
    # doored goods) rather than showing a standalone addon row. Vocabulary for
    # keywords / synonym overrides lives in Builder Profiles (ADR-0011); the
    # default profile preserves pre-profile search behaviour.

    @staticmethod
    def _addon_dollar_or_pct(
        addon: dict,
        *,
        item_base: Any,
        item_retail: Any,
    ) -> tuple[Optional[float], Optional[float], Optional[str]]:
        """Resolve flat $ or addon_pct into (base_add, retail_add, pct_tag).

        Percent adders apply to the item's own wholesale/retail (ADR-0008).
        When both pct and dollar amounts exist, dollars win (legacy flat rows).
        """
        base_add = addon.get("base_price")
        retail_add = addon.get("adjusted_price")
        pct = addon.get("addon_pct")
        has_dollar = (base_add is not None and float(base_add) != 0.0) or (
            retail_add is not None and float(retail_add) != 0.0
        )
        if has_dollar:
            return (
                float(base_add) if base_add is not None else None,
                float(retail_add) if retail_add is not None else None,
                None,
            )
        if pct is not None:
            p = float(pct)
            b = round(float(item_base or 0.0) * p / 100.0, 2)
            a = round(float(item_retail or 0.0) * p / 100.0, 2)
            return b, a, f"+{p:g}%"
        return (
            float(base_add) if base_add is not None else None,
            float(retail_add) if retail_add is not None else None,
            None,
        )

    def _is_item_upcharge_option(self, option_key: str, profile: Optional[dict] = None) -> bool:
        o = (option_key or "").lower()
        profile = profile or load_builder_profile(None)
        keys = profile.get("item_upcharge_option_keywords") or []
        return any(k in o for k in keys)

    def _match_addon_category(
        self,
        item_text: str,
        categories: list[dict],
        profile: Optional[dict] = None,
    ) -> tuple[Optional[dict], bool]:
        """Best-matching addon category for an item, and whether it's confident.

        Heuristic (ADR-0008 follow-up): distinctive-synonym overrides first, then
        furniture-type token scoring. `confident` is False for ambiguous ties
        (plain "Dresser", generic "Chest") and compound goods ("5 Piece Set"), so
        the caller can flag the charge as approximate rather than imply certainty.
        Returns (None, False) when nothing matches.
        """
        profile = profile or load_builder_profile(None)
        low = (item_text or "").lower()

        def find(pred) -> Optional[dict]:
            for c in categories:
                if pred((c.get("category") or "").lower()):
                    return c
            return None

        for rule in profile.get("category_synonym_overrides") or []:
            if not override_applies(low, rule):
                continue
            c = find(lambda cat: category_matches_override(cat, rule))
            if c is not None:
                return c, True

        t = " " + re.sub(r"[^a-z0-9\"/ ]+", " ", low) + " "
        if "nightstand" in low:
            t += " night stand "
        words = set(t.split())
        scored: list[tuple[int, dict]] = []
        for cat in categories:
            toks = [w for w in re.split(r"[^a-z0-9\"]+", (cat.get("category") or "").lower()) if w]
            score = 0
            for w in toks:
                if w in words:
                    score += 1 if w.isdigit() else 2
                elif len(w) > 3 and w in t:
                    score += 1
            scored.append((score, cat))
        scored.sort(key=lambda x: x[0], reverse=True)
        if not scored or scored[0][0] == 0:
            return None, False
        best_score, best = scored[0]
        second = scored[1][0] if len(scored) > 1 else 0
        confident = best_score > second
        for marker in profile.get("compound_item_markers") or []:
            if marker in low:
                confident = False  # compound: upcharge would be the sum of several categories
                break
        return best, confident

    def _apply_one_option_upcharge(
        self,
        df: pd.DataFrame,
        *,
        option_key: str,
        addons: list[dict],
        profile: dict,
        qty: int = 1,
    ) -> tuple[pd.DataFrame, pd.Series]:
        """Stack one Option's charge onto eligible rows. Returns (df, applied_mask).

        Ineligible rows are left unchanged (needed so multi-select can stack
        paint onto a bed while drawer slides only hit drawered goods).
        `qty` multiplies flat drawer/door extras (casegoods with several openings).
        """
        if df.empty or not addons:
            return df, pd.Series(False, index=df.index)

        qty = self._clamp_option_qty(qty)
        flat = [a for a in addons if a.get("is_flat")]
        cats = [a for a in addons if not a.get("is_flat")]
        is_drawer_door = self._is_item_upcharge_option(option_key, profile)
        drawer_keywords = profile.get("drawer_door_item_keywords") or []
        drawer_exclude = profile.get("drawer_door_exclude_keywords") or []

        text = (
            df.get("description").fillna("").astype(str) + " | "
            + df.get("collection").fillna("").astype(str) + " | "
            + df.get("part_number").fillna("").astype(str)
        ).str.lower()

        df = df.copy()
        applied = pd.Series(False, index=df.index)
        notes = df.get("notes").fillna("").astype(str)

        if is_drawer_door and flat:
            eligible = text.apply(
                lambda s: any(k in s for k in drawer_keywords)
                and not any(x in s for x in drawer_exclude)
            )
            if not eligible.any():
                return df, applied
            for idx in df.index[eligible]:
                r = df.loc[idx]
                b, a, pct_tag = self._addon_dollar_or_pct(
                    flat[0],
                    item_base=r.get("base_price"),
                    item_retail=r.get("adjusted_price"),
                )
                if a is not None:
                    a = float(a) * qty
                    cur = r.get("adjusted_price")
                    df.at[idx, "adjusted_price"] = (float(cur) if cur is not None else 0.0) + a
                if b is not None:
                    b = float(b) * qty
                    cur = r.get("base_price")
                    df.at[idx, "base_price"] = (float(cur) if cur is not None else 0.0) + b
                tag = f"+ {option_key}"
                if qty > 1:
                    tag += f" ×{qty}"
                if pct_tag:
                    tag += f" ({pct_tag}"
                    if a is not None:
                        tag += f" +${float(a):,.0f}"
                    tag += ")"
                elif a is not None:
                    tag += f" (+${float(a):,.0f})"
                n = notes.at[idx] if idx in notes.index else ""
                df.at[idx, "notes"] = f"{n} · {tag}".strip(" ·") if n else tag
                applied.at[idx] = True
            return df, applied

        # Finish / per-category (or non-drawer flat): every physical WOOD item.
        # Qty does not apply to finish options — only extras.
        has_wood = df.get("species").fillna("").astype(str).str.strip() != ""
        if not has_wood.any():
            return df, applied

        rc = sorted(
            a["adjusted_price"] for a in cats
            if a.get("adjusted_price") is not None and float(a["adjusted_price"] or 0) != 0
        )
        bc = sorted(
            a["base_price"] for a in cats
            if a.get("base_price") is not None and float(a["base_price"] or 0) != 0
        )
        med_retail = rc[len(rc) // 2] if rc else (flat[0].get("adjusted_price") if flat else None)
        med_base = bc[len(bc) // 2] if bc else (flat[0].get("base_price") if flat else None)
        med_addon = None
        if not rc and not bc:
            for a in cats + flat:
                if a.get("addon_pct") is not None:
                    med_addon = a
                    break

        for idx in df.index[has_wood]:
            r = df.loc[idx]
            itext = f"{r.get('description') or ''} {r.get('collection') or ''} {r.get('part_number') or ''}"
            if cats:
                m, confident = self._match_addon_category(itext, cats, profile)
            else:
                m, confident = (flat[0], True) if flat else (None, False)
            op = r.get("adjusted_price")
            ob = r.get("base_price")
            pct_tag = None
            if m is not None:
                b, a, pct_tag = self._addon_dollar_or_pct(m, item_base=ob, item_retail=op)
                label = None if m.get("is_flat") else m.get("category")
                approx = not confident
            elif med_addon is not None:
                b, a, pct_tag = self._addon_dollar_or_pct(
                    med_addon, item_base=ob, item_retail=op
                )
                label, approx = None, True
            else:
                b, a, label, approx = med_base, med_retail, None, True
            if a is not None:
                df.at[idx, "adjusted_price"] = (float(op) if op is not None else 0.0) + float(a)
            if b is not None:
                df.at[idx, "base_price"] = (float(ob) if ob is not None else 0.0) + float(b)
            if pct_tag and a is not None:
                amt = f" {pct_tag} +${float(a):,.0f}"
            elif pct_tag:
                amt = f" {pct_tag}"
            elif a is not None:
                amt = f" +${float(a):,.0f}"
            else:
                amt = ""
            if approx:
                inner = f"approx: {label}{amt}" if label else f"approx{amt}"
            elif label:
                inner = f"{label}{amt}"
            else:
                inner = amt.strip(" +")
            tag = f"+ {option_key} ({inner})" if inner else f"+ {option_key}"
            n = str(df.at[idx, "notes"] or "") if "notes" in df.columns else ""
            df.at[idx, "notes"] = f"{n} · {tag}".strip(" ·") if n else tag
            applied.at[idx] = True
        return df, applied

    def _search_with_item_option_upcharge(
        self,
        query: str,
        *,
        vendor: str,
        finish_state: Optional[str],
        species: Optional[str],
        option_keys: Sequence[str],
        limit: int,
        option_qty: Optional[dict[str, int]] = None,
    ) -> Optional[pd.DataFrame]:
        """Show eligible items with retail raised by selected Option charge(s).

        Multiple Options stack: each adder applies only to items eligible for it
        (drawer slides → drawered goods; finish options → every wood item).

        Returns None (caller falls back to normal search) when none of the
        Options have addon charge rows for this builder.
        """
        keys = [k for k in option_keys if k]
        if not keys:
            return None

        qtys = option_qty or {}
        profile = load_builder_profile(vendor)
        addon_by_opt: list[tuple[str, list[dict]]] = []
        for opt in keys:
            addons = self.repo.get_addon_rows(vendor, opt)
            if addons:
                addon_by_opt.append((opt, addons))
        if not addon_by_opt:
            return None

        df = self.repo.search(
            query,
            vendor=vendor,
            finish_state=finish_state,
            species=species,
            option_key=None,
            limit=max(int(limit) * 6, 400),
        )
        if df.empty:
            return df

        any_applied = pd.Series(False, index=df.index)
        for opt, addons in addon_by_opt:
            q = self._clamp_option_qty(qtys.get(opt, 1)) if self._option_qty_allowed(opt) else 1
            df, mask = self._apply_one_option_upcharge(
                df, option_key=opt, addons=addons, profile=profile, qty=q
            )
            any_applied = any_applied | mask.reindex(df.index, fill_value=False)

        if not any_applied.any():
            return df.iloc[0:0].copy()

        df = df.loc[any_applied].copy()
        # Label with all selected upcharge options (stable order from UI).
        label_bits = []
        for opt, _ in addon_by_opt:
            q = self._clamp_option_qty(qtys.get(opt, 1)) if self._option_qty_allowed(opt) else 1
            label_bits.append(f"{opt} ×{q}" if q > 1 else opt)
        df["option_key"] = ", ".join(label_bits)
        return df.head(int(limit)).reset_index(drop=True)

    def get_row(self, row_id: int) -> Optional[dict]:
        self.ensure_ready()
        return self.repo.get_row_by_id(row_id)

    def list_vendors(self) -> list[str]:
        self.ensure_ready()
        return self.repo.list_vendors()

    def list_collections(self, vendor: Optional[str] = None) -> list[str]:
        self.ensure_ready()
        return self.repo.list_collections(vendor=vendor)

    def list_species(self, vendor: Optional[str] = None) -> list[str]:
        """Selectable wood names for the floor Wood dropdown (all builders)."""
        self.ensure_ready()
        return self.repo.list_species(vendor=vendor)

    def list_option_keys(self, vendor: Optional[str] = None) -> list[str]:
        """Selectable Option values for a builder — addon charges + finish codes (ADR-0008)."""
        self.ensure_ready()
        return self.repo.list_option_keys(vendor=vendor)

    def add_addon_charge(
        self,
        *,
        vendor: str,
        label: str,
        flat_wholesale: Optional[float] = None,
        addon_pct: Optional[float] = None,
        species: Optional[str] = None,
        notes: Optional[str] = None,
        source_file: Optional[str] = None,
    ) -> dict:
        """Insert one addon charge row (not sellable Search retail)."""
        self.ensure_ready()
        label = (label or "").strip()
        if not vendor or not label:
            raise ValueError("vendor and label are required for addon charges")
        if flat_wholesale is None and addon_pct is None:
            raise ValueError("provide flat_wholesale and/or addon_pct")
        row = {
            "vendor": vendor,
            "collection": "Addons",
            "part_number": label,
            "description": label,
            "option_key": label,
            "species": species,
            "finish_state": None,
            "base_price": flat_wholesale,
            "price_basis": "wholesale",
            "multiplier": None,
            "adjusted_price": None,
            "line_kind": "addon",
            "addon_pct": addon_pct,
            "notes": notes,
            "source_file": source_file or "addon",
        }
        n = self.repo.insert_rows([row])
        return {"inserted": n, "label": label, "vendor": vendor}

    def list_source_files(self) -> list[str]:
        self.ensure_ready()
        return self.repo.list_source_files()

    def vendor_summary(self) -> pd.DataFrame:
        self.ensure_ready()
        return self.repo.vendor_summary()

    def list_thin_catalogs(self, *, max_rows: int = THIN_CATALOG_MAX_ROWS) -> pd.DataFrame:
        """Builders with fewer than max_rows sellable rows (ADR-0007).

        Read-only. Sorted ascending by row count. Does not mutate IGNORE_BUILDERS.
        """
        self.ensure_ready()
        summary = self.repo.vendor_summary()
        if summary.empty:
            return summary
        thin = summary[summary["rows"] < int(max_rows)].copy()
        return thin.sort_values("rows", ascending=True).reset_index(drop=True)

    def find_duplicates(self, limit: int = 100) -> pd.DataFrame:
        self.ensure_ready()
        return self.repo.find_duplicate_groups(limit=limit)

    def cleanup_duplicates(self, *, dry_run: bool = True) -> dict:
        self.ensure_ready()
        return self.repo.cleanup_duplicates(dry_run=dry_run)

    # ------------------------------------------------------------------ write
    def add_rows(self, rows: list[dict], *, mode: str = "append") -> dict:
        """
        Commit rows to master.

        Modes:
          - replace_vendor / replace_builder / replace_source:
              delete ALL rows for this builder, then insert (one catalog per builder)
          - upsert: update matching identities, insert new
          - append: always insert
        """
        self.ensure_ready()
        if not rows:
            return {"inserted": 0, "updated": 0, "deleted": 0, "total": 0}

        from backend.standardize import resolve_builder_vendor

        # Canonical vendor on every row (prevents filename twins)
        vend_raw = rows[0].get("vendor") or ""
        source = rows[0].get("source_file") or ""
        vend = resolve_builder_vendor(vend_raw, filename=str(source)) or vend_raw
        for r in rows:
            r["vendor"] = vend

        if mode in ("replace_source", "replace_vendor", "replace_builder"):
            # One builder = one book: wipe + load in a single transaction
            if vend:
                result = self.repo.replace_vendor_rows(vend, rows)
            elif source:
                result = self.repo.replace_source_rows(source, rows)
            else:
                n = self.repo.insert_rows(rows)
                return {
                    "inserted": n,
                    "updated": 0,
                    "deleted": 0,
                    "total": n,
                }
            n = result.get("inserted", 0)
            return {
                "inserted": n,
                "updated": 0,
                "deleted": result.get("deleted", 0),
                "total": n,
            }

        if mode == "upsert":
            result = self.repo.upsert_rows(rows)
            result["deleted"] = 0
            return result

        n = self.repo.insert_rows(rows)
        return {"inserted": n, "updated": 0, "deleted": 0, "total": n}

    def delete_by_source(self, source_file: str) -> int:
        self.ensure_ready()
        return self.repo.delete_by_source(source_file)

    def delete_by_vendor(self, vendor: str) -> int:
        self.ensure_ready()
        return self.repo.delete_by_vendor(vendor)

    # ------------------------------------------------------------------ pricing
    def get_vendor_multiplier(self, vendor: str, default: float = DEFAULT_MULTIPLIER) -> float:
        self.ensure_ready()
        return self.repo.get_vendor_multiplier(vendor, default=default)

    def set_vendor_multiplier(self, vendor: str, multiplier: float, notes: str = "") -> None:
        self.ensure_ready()
        self.repo.set_vendor_multiplier(vendor, multiplier, notes=notes)

    def set_vendor_phone(self, vendor: str, phone: str = "") -> None:
        self.ensure_ready()
        self.repo.set_vendor_phone(vendor, phone)

    def get_vendor_phone(self, vendor: str) -> str:
        self.ensure_ready()
        return self.repo.get_vendor_phone(vendor)

    def list_vendor_settings(self) -> pd.DataFrame:
        self.ensure_ready()
        return self.repo.list_vendor_settings()

    def reapply_multiplier(self, new_mult: float, *, vendor: Optional[str] = None) -> int:
        self.ensure_ready()
        return self.repo.reapply_multiplier(new_mult, vendor=vendor)

    def recompute_adjusted(self, vendor: Optional[str] = None) -> int:
        self.ensure_ready()
        return self.repo.recompute_adjusted(vendor=vendor)

    def standardize_master(self) -> dict:
        """Apply canonical field rules to every master row (in place)."""
        self.ensure_ready()
        return self.repo.standardize_all()

    def resolve_multiplier(
        self,
        vendor: str = "",
        sidebar_mult: float = DEFAULT_MULTIPLIER,
        detected_markup: Optional[float] = None,
        prefer_workbook: bool = False,
        prefer_saved_vendor: bool = True,
    ) -> float:
        if prefer_workbook and detected_markup:
            return float(detected_markup)
        if prefer_saved_vendor and vendor:
            saved = self.get_vendor_multiplier(vendor, default=-1.0)
            if saved > 0:
                return float(saved)
        return float(sidebar_mult)

    # ------------------------------------------------------------------ Drop parse session
    def _drop_parse_store(self):
        from backend.drop_parse_session import DiskDropParseStore

        return DiskDropParseStore(self._drop_parse_root)

    def _parse_drop_file_wholesale(
        self,
        data: bytes,
        *,
        filename: str,
        prefer_workbook_markup: bool = False,
        default_collection: str = "",
        pdf_max_pages: Optional[int] = None,
        pdf_strategy_index: int = 0,
    ) -> dict:
        """Single-pass parse → post-Standardize wholesale rows + suggested mult metadata."""
        from backend.drop_parse_session import wholesale_row
        from backend.standardize import resolve_builder_vendor

        name = filename or "upload"
        vend = resolve_builder_vendor(name, filename=name) or Path(name).stem
        kind = "pdf" if name.lower().endswith(".pdf") else "excel"
        out: dict = {
            "filename": name,
            "kind": kind,
            "suggested_builder": vend,
            "suggested_mult": float(DEFAULT_MULTIPLIER),
            "detected_markup": None,
            "rows": [],
            "notes": "",
            "error": "",
            "row_count": 0,
        }
        try:
            if kind == "pdf":
                mult_hint = self.get_vendor_multiplier(vend, default=DEFAULT_MULTIPLIER)
                prev = self.imports.preview_pdf(
                    data,
                    filename=name,
                    vendor=vend,
                    default_collection=default_collection,
                    multiplier=float(mult_hint),
                    max_pages=pdf_max_pages,
                    strategy_index=pdf_strategy_index,
                )
                if prev.stats.get("likely_scanned"):
                    out["error"] = "Scanned PDF — little extractable text. Prefer Excel."
                    out["notes"] = str(prev.stats)
                    return out
                if not prev.results and not prev.rows:
                    out["error"] = "No prices found in PDF."
                    out["notes"] = str(prev.stats)
                    return out
                rows = [wholesale_row(r) for r in (prev.rows or [])]
                for r in rows:
                    r["vendor"] = vend
                    r["source_file"] = name
                    r["price_basis"] = r.get("price_basis") or "wholesale"
                out["rows"] = rows
                out["row_count"] = len(rows)
                out["notes"] = f"PDF strategy · {len(rows)} rows"
                out["suggested_mult"] = float(mult_hint)
            else:
                # One Excel pass — markup detection piggybacks; no second parse.
                prev = self.imports.preview_excel(
                    data,
                    filename=name,
                    vendor=vend,
                    default_collection=default_collection,
                    multiplier=DEFAULT_MULTIPLIER,
                    use_workbook_markup=False,
                )
                detected = prev.detected_markup
                out["detected_markup"] = detected
                out["notes"] = prev.notes or ""
                suggested = self.resolve_multiplier(
                    vend,
                    sidebar_mult=DEFAULT_MULTIPLIER,
                    detected_markup=detected if prefer_workbook_markup else None,
                    prefer_workbook=prefer_workbook_markup,
                    prefer_saved_vendor=True,
                )
                out["suggested_mult"] = float(suggested)
                rows = [wholesale_row(r) for r in (prev.rows or [])]
                for r in rows:
                    r["vendor"] = vend
                    r["source_file"] = name
                    r["price_basis"] = r.get("price_basis") or "wholesale"
                out["rows"] = rows
                out["row_count"] = len(rows)
                if not rows:
                    out["error"] = "0 rows parsed — check file layout."
        except Exception as e:
            out["error"] = str(e)[:400]
        return out

    def ensure_drop_parse_session(
        self,
        uploads: Sequence[Any],
        *,
        session_id: Optional[str] = None,
        prefer_workbook_markup: bool = False,
        force: bool = False,
        progress: Optional[Callable[[float, str], None]] = None,
    ):
        """
        Create or reuse a Drop parse session for one upload batch.

        Returns DropParseSessionView (opaque id + per-file preview metadata).
        Full rows stay on disk; UI must not hold them.
        """
        from backend.drop_parse_session import (
            DropUpload,
            batch_key,
            new_session_id,
            view_from_payload,
        )

        self.ensure_ready()
        force = bool(force)
        upload_list: list[DropUpload] = []
        for u in uploads:
            if isinstance(u, DropUpload):
                upload_list.append(u)
            else:
                raise TypeError("uploads must be DropUpload instances")
        if not upload_list:
            raise ValueError("uploads must not be empty")

        key = batch_key(upload_list, prefer_workbook_markup=prefer_workbook_markup)
        store = self._drop_parse_store()
        store.purge_expired()

        if session_id and not force:
            payload = store.load(session_id)
            if payload and store.is_fresh(payload, batch=key):
                return view_from_payload(payload)
            if payload:
                store.delete(session_id)

        # Build new session — need file bytes (UI may probe with empty data for reuse).
        if any(not up.data for up in upload_list):
            raise ValueError("upload data required to parse Drop session")

        if session_id and force:
            store.delete(session_id)
        sid = new_session_id()
        files_payload: list[dict] = []
        n = max(len(upload_list), 1)
        for i, up in enumerate(upload_list):
            if progress:
                try:
                    progress(i / n, f"Parsing {up.filename}…")
                except Exception:
                    pass
            parsed = self._parse_drop_file_wholesale(
                up.data,
                filename=up.filename,
                prefer_workbook_markup=prefer_workbook_markup,
            )
            files_payload.append(parsed)
        if progress:
            try:
                progress(1.0, "Done parsing")
            except Exception:
                pass

        import time

        payload = {
            "session_id": sid,
            "batch_key": key,
            "prefer_workbook_markup": bool(prefer_workbook_markup),
            "saved_at": time.time(),
            "files": files_payload,
        }
        store.save(sid, payload)
        return view_from_payload(payload)

    def clear_drop_parse_session(self, session_id: Optional[str]) -> None:
        """Discard a Drop parse session (Load / Clear). Idempotent."""
        if not session_id:
            return
        self._drop_parse_store().delete(session_id)

    def wholesale_from_drop_parse_session(self, session_id: str):
        """Read post-Standardize wholesale rows for commit binding (outside this module)."""
        from backend.drop_parse_session import (
            DropSessionGone,
            wholesale_from_payload,
        )

        if not session_id:
            raise DropSessionGone("missing session_id")
        store = self._drop_parse_store()
        payload = store.load(session_id)
        if not payload:
            raise DropSessionGone(session_id)
        # TTL-only check (batch already bound to this session_id).
        saved = float(payload.get("saved_at") or 0)
        import time as _time

        from backend.drop_parse_session import DEFAULT_TTL_SECONDS

        if _time.time() - saved > DEFAULT_TTL_SECONDS:
            store.delete(session_id)
            raise DropSessionGone(session_id)
        return wholesale_from_payload(payload)

    def prepare_drop_file(
        self,
        data: bytes,
        *,
        filename: str,
        vendor: str = "",
        multiplier: Optional[float] = None,
        use_workbook_markup: bool = False,
        default_collection: str = "",
        pdf_max_pages: Optional[int] = None,
        pdf_strategy_index: int = 0,
    ) -> dict:
        """
        Parse one dropped Excel/PDF into standardized long-form rows.

        Returns dict:
          vendor, multiplier, detected_markup, rows, notes, error, row_count,
          sample (list of dicts), sheets_tried
        """
        from backend.standardize import resolve_builder_vendor

        self.ensure_ready()
        name = filename or "upload"
        vend = (
            resolve_builder_vendor(vendor or name, filename=name)
            or (vendor or "").strip()
            or Path(name).stem
        )
        out: dict = {
            "filename": name,
            "vendor": vend,
            "multiplier": float(DEFAULT_MULTIPLIER),
            "detected_markup": None,
            "rows": [],
            "notes": "",
            "error": "",
            "row_count": 0,
            "sample": [],
            "sheets_tried": [],
            "kind": "pdf" if name.lower().endswith(".pdf") else "excel",
        }

        try:
            if name.lower().endswith(".pdf"):
                prev = self.imports.preview_pdf(
                    data,
                    filename=name,
                    vendor=vend,
                    default_collection=default_collection,
                    multiplier=float(
                        multiplier
                        if multiplier is not None
                        else self.get_vendor_multiplier(vend, default=DEFAULT_MULTIPLIER)
                    ),
                    max_pages=pdf_max_pages,
                    strategy_index=pdf_strategy_index,
                )
                if prev.stats.get("likely_scanned"):
                    out["error"] = "Scanned PDF — little extractable text. Prefer Excel."
                    out["notes"] = str(prev.stats)
                    return out
                if not prev.results and not prev.rows:
                    out["error"] = "No prices found in PDF."
                    out["notes"] = str(prev.stats)
                    return out
                rows = list(prev.rows or [])
                detected = None
                notes = f"PDF strategy · {len(rows)} rows"
            else:
                # First pass: detect markup without forcing mult
                probe = self.imports.preview_excel(
                    data,
                    filename=name,
                    vendor=vend,
                    default_collection=default_collection,
                    multiplier=DEFAULT_MULTIPLIER,
                    use_workbook_markup=False,
                )
                detected = probe.detected_markup
                out["sheets_tried"] = probe.sheets_tried or []
                out["notes"] = probe.notes or ""

                if multiplier is not None:
                    mult = float(multiplier)
                else:
                    mult = self.resolve_multiplier(
                        vend,
                        sidebar_mult=DEFAULT_MULTIPLIER,
                        detected_markup=detected if use_workbook_markup else None,
                        prefer_workbook=use_workbook_markup,
                        prefer_saved_vendor=True,
                    )

                prev = self.imports.preview_excel(
                    data,
                    filename=name,
                    vendor=vend,
                    default_collection=default_collection,
                    multiplier=mult,
                    use_workbook_markup=False,
                )
                rows = list(prev.rows or [])
                notes = prev.notes or notes
                out["sheets_tried"] = prev.sheets_tried or out["sheets_tried"]
                out["detected_markup"] = detected

            # Resolve final mult after we know detected
            if multiplier is not None:
                mult = float(multiplier)
            else:
                mult = self.resolve_multiplier(
                    vend,
                    sidebar_mult=DEFAULT_MULTIPLIER,
                    detected_markup=out.get("detected_markup") if use_workbook_markup else None,
                    prefer_workbook=use_workbook_markup,
                    prefer_saved_vendor=True,
                )

            # Apply builder-specific mult + ensure standardization already on rows
            for r in rows:
                r["vendor"] = vend
                r["source_file"] = name
                r["multiplier"] = mult
                r["price_basis"] = r.get("price_basis") or "wholesale"
                bp = r.get("base_price")
                if bp is not None:
                    try:
                        from backend.pricing import retail_from_wholesale

                        r["adjusted_price"] = retail_from_wholesale(bp, mult)
                    except (TypeError, ValueError):
                        pass

            out["vendor"] = vend
            out["multiplier"] = mult
            out["rows"] = rows
            out["row_count"] = len(rows)
            out["notes"] = notes
            out["sample"] = rows[:8]
            if not rows:
                out["error"] = out["error"] or "0 rows parsed — check file layout."
        except Exception as e:
            out["error"] = str(e)[:400]
        return out

    def preview_excel(self, data: bytes, **kwargs) -> ExcelImportPreview:
        return self.imports.preview_excel(data, **kwargs)

    def preview_excel_manual(self, data: bytes, **kwargs) -> list[dict]:
        return self.imports.preview_excel_manual(data, **kwargs)

    def preview_pdf(self, data: bytes, **kwargs) -> PdfImportPreview:
        return self.imports.preview_pdf(data, **kwargs)

    def map_columns(self, df: pd.DataFrame) -> dict[str, str]:
        return map_columns(df)

    def read_excel_bytes(self, data: bytes) -> pd.DataFrame:
        return read_excel_bytes(data)

    def batch_import(
        self,
        folder: str | Path,
        *,
        recursive: bool = False,
        mode: str = "upsert",
        multiplier: float = DEFAULT_MULTIPLIER,
        use_workbook_markup: bool = True,
        vendor_override: str = "",
        excel_only: bool = True,
        progress: Optional[Callable[[str], None]] = None,
    ) -> BatchResult:
        self.ensure_ready()
        return self.batch.run(
            folder,
            recursive=recursive,
            mode=mode,
            multiplier=multiplier,
            use_workbook_markup=use_workbook_markup,
            vendor_override=vendor_override,
            excel_only=excel_only,
            progress=progress,
        )

    def discover_batch_files(self, folder: str | Path, recursive: bool = False) -> list[Path]:
        return self.batch.discover(folder, recursive=recursive)

    # ------------------------------------------------------------------ quotes
    def create_quote(self, **kwargs) -> int:
        self.ensure_ready()
        return self.quotes.create_quote(**kwargs)

    def update_quote(self, quote_id: int, **kwargs) -> None:
        self.ensure_ready()
        self.quotes.update_quote(quote_id, **kwargs)

    def delete_quote(self, quote_id: int) -> None:
        self.ensure_ready()
        self.quotes.delete_quote(quote_id)

    def get_quote(self, quote_id: int) -> Optional[dict]:
        self.ensure_ready()
        return self.quotes.get_quote(quote_id)

    def list_quotes(self, limit: int = 100) -> pd.DataFrame:
        self.ensure_ready()
        return self.quotes.list_quotes(limit=limit)

    def quote_lines(self, quote_id: int) -> pd.DataFrame:
        self.ensure_ready()
        return self.quotes.list_lines(quote_id)

    def quote_totals(self, quote_id: int) -> dict[str, Any]:
        self.ensure_ready()
        return self.quotes.totals(quote_id)

    def add_quote_line_from_id(
        self,
        quote_id: int,
        pricebook_id: int,
        *,
        qty: float = 1.0,
        line_discount_pct: float = 0.0,
        notes: str = "",
        species_override: Optional[str] = None,
        stain: str = "",
        finish_override: Optional[str] = None,
    ) -> int:
        """Add a catalog row to a quote; optional wood/stain/finish for the line."""
        self.ensure_ready()
        row = self.repo.get_row_by_id(pricebook_id)
        if not row:
            raise ValueError(f"No pricebook row id={pricebook_id}")
        row = dict(row)
        if species_override:
            row["species"] = species_override
        if finish_override:
            row["finish_state"] = finish_override
        note_bits = [n for n in (notes, f"Stain: {stain}" if stain else "") if n]
        return self.quotes.add_line_from_pricebook(
            quote_id,
            row,
            qty=qty,
            line_discount_pct=line_discount_pct,
            notes=" · ".join(note_bits) if note_bits else "",
        )

    def add_quote_line_from_row(self, quote_id: int, pricebook_row: dict, **kwargs) -> int:
        self.ensure_ready()
        return self.quotes.add_line_from_pricebook(quote_id, pricebook_row, **kwargs)

    def add_custom_quote_line(self, quote_id: int, **kwargs) -> int:
        self.ensure_ready()
        return self.quotes.add_custom_line(quote_id, **kwargs)

    def update_quote_line(self, line_id: int, **kwargs) -> None:
        self.ensure_ready()
        self.quotes.update_line(line_id, **kwargs)

    def delete_quote_line(self, line_id: int) -> None:
        self.ensure_ready()
        self.quotes.delete_line(line_id)

    # ------------------------------------------------------------------ users / OrderTrac
    def list_app_users(self, *, active_only: bool = False) -> pd.DataFrame:
        self.ensure_ready()
        return self.users.list_users(active_only=active_only)

    def create_app_user(self, **kwargs) -> int:
        self.ensure_ready()
        return self.users.create_user(**kwargs)

    def update_app_user(self, user_id: int, **kwargs) -> None:
        self.ensure_ready()
        self.users.update_user(user_id, **kwargs)

    def set_app_user_password(
        self, user_id: int, password: str, *, must_change: bool = False
    ) -> None:
        self.ensure_ready()
        self.users.set_password(user_id, password, must_change=must_change)

    def ordertrac_connection_status(self) -> dict:
        """Secrets + session file status (no browser)."""
        from backend.ordertrac_connect import connection_status

        st = connection_status()
        self.ensure_ready()
        integ = self.users.get_integration("ordertrac") or {}
        st["integration"] = integ
        st["faf_user_count"] = self.users.count()
        return st

    def ordertrac_check_session(self) -> dict:
        from backend.ordertrac_connect import check_session

        self.ensure_ready()
        result = check_session(headless=True)
        self.users.set_integration(
            "ordertrac",
            status="connected" if result.get("ok") else "error",
            last_error=result.get("error") or "",
            meta={"check": result},
            ok=bool(result.get("ok")),
        )
        return result

    def sync_users_from_ordertrac(self, *, default_role: str = "sales") -> dict:
        """Pull OrderTrac sales users into app_users."""
        from backend.ordertrac_connect import sync_users_to_faf

        self.ensure_ready()
        return sync_users_to_faf(self.db_path, headless=True, default_role=default_role)

    def push_quote_to_ordertrac(
        self,
        quote_id: int,
        *,
        ot_user_display: str = "Miller, Judson",
        location: str = "Landrum",
        headless: bool = True,
        mode: str = "create",
    ) -> dict:
        """
        Send FAF quote lines to OrderTrac as a QUOTE (never a sale).

        mode:
          - "create": always open a new OrderTrac quote with all FAF lines
          - "append": open the linked OrderTrac quote (if any) and add lines
            that are not already present (by FAF #id / SKU)
        """
        from datetime import datetime

        from backend.ordertrac_push import (
            build_payload_from_faf_quote,
            push_quote_to_ordertrac,
        )

        self.ensure_ready()
        q = self.quotes.get_quote(quote_id)
        if not q:
            raise ValueError(f"No FAF quote id={quote_id}")
        lines = self.quotes.list_lines(quote_id)
        if lines is None or lines.empty:
            return {
                "ok": False,
                "error": "Quote has no lines — add items from Search first",
            }

        existing_guid = (q.get("ordertrac_guid") or "").strip()
        mode = (mode or "create").lower().strip()
        if mode == "append":
            if not existing_guid:
                return {
                    "ok": False,
                    "error": "No linked OrderTrac quote yet — use Create first",
                }
            use_guid = existing_guid
            skip_existing = True
        else:
            use_guid = None
            skip_existing = False

        payload = build_payload_from_faf_quote(
            q,
            lines,
            ot_user_display=ot_user_display,
            location=location,
            project=q.get("quote_number") or f"FAF-{quote_id}",
        )
        if q.get("customer_name"):
            payload["customer_name"] = q["customer_name"]
        if q.get("customer_phone"):
            payload["customer_phone"] = q["customer_phone"]
        if q.get("customer_email"):
            payload["customer_email"] = q["customer_email"]

        result = push_quote_to_ordertrac(
            payload,
            headless=headless,
            sales_order_guid=use_guid,
            skip_existing_lines=skip_existing,
        )
        if result.get("ok") or result.get("guid"):
            self.quotes.update_quote(
                quote_id,
                ordertrac_guid=result.get("guid") or existing_guid,
                ordertrac_so_id=str(result.get("sales_order_id") or q.get("ordertrac_so_id") or "")
                or None,
                ordertrac_url=result.get("url") or q.get("ordertrac_url"),
                ordertrac_pushed_at=datetime.now().isoformat(timespec="seconds"),
                status="sent" if result.get("ok") else q.get("status") or "draft",
            )
        self.users.set_integration(
            "ordertrac",
            status="connected" if result.get("ok") else "error",
            last_error=result.get("error") or "",
            meta={"last_push": result, "faf_quote_id": quote_id, "mode": mode},
            ok=bool(result.get("ok")),
        )
        result["faf_quote_id"] = quote_id
        result["faf_quote_number"] = q.get("quote_number")
        result["mode"] = mode
        return result

    def push_rows_to_ordertrac(
        self,
        rows: list[dict],
        *,
        qtys: Optional[list[float]] = None,
        wood: str = "",
        stain: str = "",
        finish: str = "",
        project: str = "FAF Price Book push",
        notes: str = "",
        ot_user_display: str = "Miller, Judson",
        location: str = "Landrum",
        customer_name: str = "FAF Floor Quote",
        headless: bool = True,
    ) -> dict:
        """Push selected pricebook rows as a new OrderTrac QUOTE."""
        from backend.ordertrac_push import line_from_pricebook_row, push_quote_to_ordertrac

        self.ensure_ready()
        if not rows:
            return {"ok": False, "error": "No rows"}
        qtys = qtys or [1.0] * len(rows)
        lines = []
        for i, row in enumerate(rows):
            q = qtys[i] if i < len(qtys) else 1.0
            lines.append(line_from_pricebook_row(row, qty=q, wood=wood, stain=stain, finish=finish))
        payload = {
            "type": "QUOTE",
            "customer_name": customer_name,
            "project": project,
            "notes": notes
            or "Pushed from FAF Price Book. DO NOT convert to sale unless authorized.",
            "user_display": ot_user_display,
            "location": location,
            "lines": lines,
        }
        result = push_quote_to_ordertrac(payload, headless=headless)
        self.users.set_integration(
            "ordertrac",
            status="connected" if result.get("ok") else "error",
            last_error=result.get("error") or "",
            meta={"last_push": result},
            ok=bool(result.get("ok")),
        )
        return result

    def export_quote_excel(self, quote_id: int) -> bytes:
        self.ensure_ready()
        return self.quotes.export_excel(quote_id)

    def export_quote_pdf(self, quote_id: int) -> bytes:
        self.ensure_ready()
        return self.quotes.export_pdf(quote_id)

    # ------------------------------------------------------------------ export catalog
    def export_excel(self, df: pd.DataFrame) -> bytes:
        return to_excel_bytes(df)

    def export_csv(self, df: pd.DataFrame) -> bytes:
        return to_csv_bytes(df)

    def export_pdf(self, df: pd.DataFrame, title: str = "Price Book Export") -> bytes:
        return to_pdf_bytes(df, title=title)
