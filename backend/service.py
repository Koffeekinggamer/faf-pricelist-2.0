"""
Public facade for the Price Book backend.

UI and scripts should prefer this over touching repository/importers directly.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable, Optional, Sequence, Union

import pandas as pd

from backend.batch import BatchImporter, BatchResult
from backend.builder_parsers import (
    identify_reader,
    infer_importer,
    list_locked_parsers,
    preferred_parser_for,
    save_named_parser,
)
from backend.builder_profiles import (
    apply_finish_as_option,
    category_matches_override,
    effective_finish_as_option,
    finish_option_label,
    load_builder_profile,
    override_applies,
    resolve_option_groups,
    single_select_group,
)
from backend.config import (
    DATA_DIR,
    DB_PATH,
    DEFAULT_MULTIPLIER,
    DEFAULT_SEARCH_LIMIT,
    THIN_CATALOG_MAX_ROWS,
)
from backend.db import init_db
from backend.export import to_csv_bytes, to_excel_bytes, to_pdf_bytes
from backend.import_service import ExcelImportPreview, ImportService, PdfImportPreview
from backend.normalize import map_columns, read_excel_bytes
from backend.option_fit import (
    filter_options_for_kinds,
    furniture_kinds_from_text,
    order_search_options,
)
from backend.quotes import QuoteRepository
from backend.repository import PriceBookRepository
from backend.users import UserRepository


def _wholesale_fingerprint(rows: list[dict]) -> str:
    """ADR-0010: sorted item/addon identities + wholesale after Standardize."""
    identities = []
    for row in rows:
        line_kind = str(row.get("line_kind") or "item").strip().lower()
        identities.append(
            (
                line_kind,
                str(row.get("collection") or ""),
                str(row.get("part_number") or ""),
                str(row.get("description") or ""),
                str(row.get("species") or ""),
                str(row.get("finish_state") or ""),
                str(row.get("option_key") or ""),
                round(float(row.get("base_price") or 0), 4),
                round(float(row.get("addon_pct") or 0), 4),
            )
        )
    raw = json.dumps(sorted(identities), separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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
        self._builder_profile_root: Optional[Path] = None

    def _christina_watch(self, out: dict) -> dict:
        """Christina records every Drop. Failures here must never block parse."""
        try:
            from dataclasses import asdict

            from backend.christina import observe_drop
            from backend.drop_parse_session import evaluate_readiness

            out["readiness"] = asdict(evaluate_readiness(out))
            observe_drop(out, path=self.db_path.parent / "christina_lessons.jsonl")
        except Exception:
            pass
        return out

    def _christina_log_path(self) -> Path:
        return self.db_path.parent / "christina_lessons.jsonl"

    def _christina_observe_load(self, **kwargs) -> None:
        try:
            from backend.christina import observe_load

            kwargs.setdefault("path", self._christina_log_path())
            observe_load(**kwargs)
        except Exception:
            pass

    def _christina_observe_lock(self, **kwargs) -> None:
        try:
            from backend.christina import observe_lock

            kwargs.setdefault("path", self._christina_log_path())
            observe_lock(**kwargs)
        except Exception:
            pass

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
        part_number: Optional[str] = None,
        finish_state: Optional[str] = None,
        species: Optional[str] = None,
        option_key: Optional[Union[str, Sequence[str]]] = None,
        option_qty: Optional[dict[str, int]] = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> pd.DataFrame:
        self.ensure_ready()
        opts = self._normalize_option_keys(option_key)
        profile = self._search_profile(vendor)
        finish_state, opts = apply_finish_as_option(profile, opts, finish_state)
        if opts and vendor and vendor != "All":
            opts = resolve_option_groups(profile, opts)
        if opts and vendor and vendor != "All":
            upcharged = self._search_with_item_option_upcharge(
                query,
                vendor=vendor,
                collection=collection,
                part_number=part_number,
                finish_state=finish_state,
                species=species,
                option_keys=opts,
                option_qty=option_qty or {},
                limit=limit,
            )
            if upcharged is not None:
                return self._with_catalog_images(upcharged)
        # Repo accepts a single key or a list (IN filter).
        repo_opt: Optional[Union[str, Sequence[str]]] = None
        if len(opts) == 1:
            repo_opt = opts[0]
        elif len(opts) > 1:
            repo_opt = opts
        return self._with_catalog_images(
            self.repo.search(
                query,
                collection=collection,
                vendor=vendor,
                part_number=part_number,
                finish_state=finish_state,
                species=species,
                option_key=repo_opt,
                limit=limit,
            )
        )

    def vendors_with_catalog_images(self) -> set[str]:
        """Builders that have catalog photos, so the UI can keep the column."""
        return self.repo.vendors_with_catalog_images()

    def _with_catalog_images(self, df: pd.DataFrame) -> pd.DataFrame:
        """Attach ``image_path`` from catalog_images for each row's vendor+SKU."""
        if df is None or df.empty:
            if df is not None and "image_path" not in df.columns:
                df = df.copy()
                df["image_path"] = pd.Series(dtype=object)
            return df
        if "vendor" not in df.columns or "part_number" not in df.columns:
            out = df.copy()
            out["image_path"] = None
            return out
        pairs = list(
            zip(
                df["vendor"].fillna("").astype(str),
                df["part_number"].fillna("").astype(str),
            )
        )
        paths = self.repo.catalog_image_paths(pairs)
        out = df.copy()
        out["image_path"] = [paths.get((v, p)) for v, p in pairs]
        return out

    def ingest_single_catalog_image(
        self,
        *,
        vendor: str,
        items: Sequence[str],
        image_bytes: bytes,
        filename: str = "",
        descriptor: str = "",
        notes: str = "",
        image_root: Optional[Path] = None,
    ) -> dict:
        """R7: bind one operator photo to exact builder item keys. Draft until Christina."""
        from datetime import datetime, timezone

        from backend.builder_profiles import vendor_slug
        from backend.catalog_images import relative_image_path
        from backend.christina import observe_image, review_image_alignment
        from backend.image_alignment import (
            normalize_catalog_key,
            viztech_image_policy,
        )

        vend = (vendor or "").strip()
        keys = [str(i).strip() for i in items if str(i).strip()]
        if not vend or not keys:
            return {"ok": False, "error": "Builder and item(s) are required."}
        if not image_bytes:
            return {"ok": False, "error": "Image file is required."}

        known = self.repo.list_part_numbers_for_vendor(vend)
        known_ci = {normalize_catalog_key(k): k for k in known}
        resolved: list[str] = []
        unknown: list[str] = []
        for raw in keys:
            canon = known_ci.get(normalize_catalog_key(raw))
            if canon:
                resolved.append(canon)
            else:
                unknown.append(raw)
        if not resolved:
            return {"ok": False, "error": "No matching catalog item for this builder."}

        extra = [k for k in resolved[1:]]
        desc = (descriptor or "").strip() or (notes or "").strip() or Path(filename).stem
        slug = vendor_slug(vend)
        root = Path(image_root) if image_root else DATA_DIR
        policy = viztech_image_policy(vend)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        reviews = []
        first_path = ""
        for part in resolved:
            self.repo.delete_catalog_image(vend, part)
            rel = relative_image_path(part, slug)
            dest = root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(image_bytes)
            prior = self.repo.catalog_image_row(vend, part)
            prior_hero = (prior or {}).get("image_path")
            review = review_image_alignment(
                builder=vend,
                part_number=part,
                item_number="",
                extracted_keys=[part],
                descriptor=desc,
                source="single",
                asset_key=rel,
                prior_hero=prior_hero,
                vision_available=False,
                extra_attaches=extra if part == resolved[0] else [],
            )
            observe_image(review, path=self._christina_log_path())
            self.repo.upsert_catalog_image(
                vendor=vend,
                part_number=part,
                image_path=rel,
                source_file=filename or Path(rel).name,
                match_method="operator_descriptor",
                updated_at=now,
                status="draft",
                descriptor=desc,
                source="single",
                christina_verdict=review["verdict"],
                christina_score=review["score"],
                christina_findings="; ".join(review["findings"]),
                christina_run_id=review["raw_run_id"],
            )
            reviews.append(review)
            if not first_path:
                first_path = rel
        return {
            "ok": True,
            "status": "draft",
            "vendor": vend,
            "items": resolved,
            "unknown": unknown,
            "image_path": first_path,
            "descriptor": desc,
            "reviews": reviews,
            "viztech": policy,
        }

    def override_catalog_image(
        self,
        *,
        vendor: str,
        part_number: str,
        reason: str,
    ) -> dict:
        reason = (reason or "").strip()
        if not reason:
            return {"ok": False, "error": "Override requires a reason."}
        row = self.repo.catalog_image_row(vendor, part_number)
        if not row:
            return {"ok": False, "error": "No catalog photo for that SKU."}
        from datetime import datetime, timezone

        self.repo.upsert_catalog_image(
            vendor=vendor,
            part_number=part_number,
            image_path=row["image_path"],
            source_file=row.get("source_file"),
            page=row.get("page"),
            match_method=row.get("match_method"),
            updated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            status="override",
            descriptor=row.get("descriptor"),
            source=row.get("source"),
            override_reason=reason,
            christina_verdict=row.get("christina_verdict"),
            christina_score=row.get("christina_score"),
            christina_findings=row.get("christina_findings"),
            christina_run_id=row.get("christina_run_id"),
        )
        return {"ok": True, "status": "override"}

    def remove_catalog_image(self, *, vendor: str, part_number: str) -> dict:
        self.repo.delete_catalog_image(vendor, part_number)
        return {"ok": True}

    def ingest_catalog_pdf_images(
        self,
        *,
        vendor: str,
        pdf_bytes: bytes,
        filename: str = "",
        image_root: Optional[Path] = None,
    ) -> dict:
        """R5/R6: extract keyed product figures from a catalog PDF."""
        from datetime import datetime, timezone
        from io import BytesIO

        from backend.builder_profiles import vendor_slug
        from backend.catalog_images import (
            captions_from_words,
            match_captions_to_images,
            plan_upserts,
            product_images_from_page,
            relative_image_path,
        )
        from backend.christina import observe_image, review_image_alignment
        from backend.image_alignment import (
            extract_sku_keys_from_text,
            page_is_skipped_figure,
            viztech_image_policy,
        )

        vend = (vendor or "").strip()
        if not vend:
            return {"ok": False, "error": "Builder is required."}
        if not pdf_bytes:
            return {"ok": False, "error": "PDF is required."}
        try:
            import pdfplumber
        except ImportError:
            return {"ok": False, "error": "pdfplumber is not installed."}

        known = self.repo.list_part_numbers_for_vendor(vend)
        slug = vendor_slug(vend)
        root = Path(image_root) if image_root else DATA_DIR
        policy = viztech_image_policy(vend)
        matched = []
        skipped_pages = []
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                if page_is_skipped_figure(text) and not extract_sku_keys_from_text(text):
                    skipped_pages.append(i)
                    continue
                words = page.extract_words() or []
                caps = captions_from_words(words)
                imgs = product_images_from_page(page.images or [], page_number=i)
                matched.extend(match_captions_to_images(caps, imgs))

        plan = plan_upserts(
            matched,
            known_part_numbers=known,
            vendor=vend,
            vendor_slug=slug,
            source_file=filename,
        )
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        reviews = []
        # Persist matched rasters when pdfplumber exposes them.
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            by_page: dict[int, list] = {}
            for row in plan["upserts"]:
                by_page.setdefault(int(row["page"]), []).append(row)
            for page_no, rows in by_page.items():
                page = pdf.pages[page_no - 1]
                page_images = product_images_from_page(page.images or [], page_number=page_no)
                name_to_im = {im.name: im for im in page_images}
                for row in rows:
                    rel = relative_image_path(row["part_number"], slug)
                    dest = root / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    hit = name_to_im.get(row.get("_image_name") or "")
                    raw = None
                    if hit is not None:
                        for src in page.images or []:
                            if str(src.get("name") or "") == hit.name and src.get("stream"):
                                try:
                                    raw = src["stream"].get_data()
                                except Exception:
                                    raw = None
                                break
                    if raw:
                        dest.write_bytes(raw)
                    prior = self.repo.catalog_image_row(vend, row["part_number"])
                    review = review_image_alignment(
                        builder=vend,
                        part_number=row["part_number"],
                        extracted_keys=[row["part_number"]],
                        descriptor=f"{vend} {row['part_number']}",
                        source="pdf",
                        asset_key=rel,
                        prior_hero=(prior or {}).get("image_path"),
                        vision_available=False,
                    )
                    observe_image(review, path=self._christina_log_path())
                    self.repo.upsert_catalog_image(
                        vendor=vend,
                        part_number=row["part_number"],
                        image_path=rel,
                        source_file=filename,
                        page=row.get("page"),
                        match_method="nearest_caption",
                        updated_at=now,
                        status="draft",
                        descriptor=f"{vend} {row['part_number']}",
                        source="pdf",
                        christina_verdict=review["verdict"],
                        christina_score=review["score"],
                        christina_findings="; ".join(review["findings"]),
                        christina_run_id=review["raw_run_id"],
                    )
                    reviews.append(review)
                    row["image_path"] = rel
        return {
            "ok": True,
            "vendor": vend,
            "matched_count": plan["matched_count"],
            "unknown_count": plan["unknown_count"],
            "skipped_pages": skipped_pages,
            "reviews": reviews,
            "viztech": policy,
        }

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

        Countable hardware/openings use a quantity after the Option is checked.
        A printed fixed bundle (``2 Glass Shelves``) stays one Option; labels
        saying additional/extra/per/each may be repeated on the same piece.
        """
        o = (option_key or "").lower()
        if not o:
            return False
        if re.search(r"\b(set of|options?:)\s*\d+\b", o):
            return False
        if re.search(r"\b\d+\s*[- ]?\s*(?:glass\s+)?shel(?:f|ves)\b", o):
            return False
        if re.search(r"^\s*\d+\s+drawer\b", o):
            return False
        if re.search(r"drawer\s+unit", o):
            return False
        if re.search(r"\bwithout\s+drawers?\b|\bdrawer\s+in\s+drawer\b", o):
            return False
        if re.search(r"\b(?:usb|port|charger)\b.*\bdrawer\b", o):
            return False
        if any(token in o for token in ("drawer", "slide", "knob", "kick plate")):
            return True
        if re.search(r"\b(?:additional|extra|add)\b.*\b(?:door|shel(?:f|ves)|lea(?:f|ves))\b", o):
            return True
        if re.search(r"\bper\s+(?:door|drawer|shel(?:f|ves)|knob|pull|light|opening)\b", o):
            return True
        if re.search(
            r"\b(?:door|drawer|shel(?:f|ves)|knob|pull|light|opening)\b.*\b(?:each|per)\b", o
        ):
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
        option_key: str = "",
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
            from backend.pricing import is_no_markup_option

            if is_no_markup_option(option_key) and base_add is not None:
                amount = float(base_add)
                return amount, amount, None
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

    @staticmethod
    def _locked_flat_option_has_item_evidence(
        items: pd.DataFrame,
        option_key: str,
        profile: dict,
    ) -> bool:
        """Whether a locked builder proves a flat Option belongs to these items."""
        if single_select_group(profile, option_key) is not None:
            return True
        for pattern in profile.get("global_option_patterns") or []:
            try:
                if re.search(str(pattern), option_key, re.IGNORECASE):
                    return True
            except re.error:
                continue
        label = re.sub(r"\s+", " ", str(option_key or "").strip()).casefold()
        if not label:
            return False
        text = (
            items.get("description", pd.Series("", index=items.index)).fillna("").astype(str)
            + " | "
            + items.get("notes", pd.Series("", index=items.index)).fillna("").astype(str)
        ).map(lambda value: re.sub(r"\s+", " ", value).casefold())
        if text.str.contains(re.escape(label), regex=True).any():
            return True

        # Printed titles often shorten the stored label ("Leather Seat") to
        # "Leather $40". A priced OPTIONS/ADD phrase plus a distinctive shared
        # word is still item-level evidence.
        stop = {"add", "added", "available", "option", "options", "seat", "seats"}

        def evidence_terms(value: str) -> set[str]:
            words = re.findall(r"[a-z]{4,}", value.casefold())
            return {word[:-1] if word.endswith("s") else word for word in words if word not in stop}

        label_terms = evidence_terms(label)
        if not label_terms:
            return False
        for value in text:
            if not re.search(r"(?i)\boptions?\s*:|\badd\s*\$|\$\s*\d", value):
                continue
            if label_terms & evidence_terms(value):
                return True
        return False

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
        parser_locked = bool((profile.get("parser") or {}).get("locked"))

        text = (
            df.get("description").fillna("").astype(str)
            + " | "
            + df.get("collection").fillna("").astype(str)
            + " | "
            + df.get("part_number").fillna("").astype(str)
        ).str.lower()

        df = df.copy()
        applied = pd.Series(False, index=df.index)
        notes = df.get("notes").fillna("").astype(str)

        item_scoped = [a for a in addons if a.get("is_item_scoped")]
        if item_scoped:
            # Some factory books print add-on columns directly on each SKU
            # (LuxHome). Those charges are exact-item data, not categories and
            # never a builder-wide fallback. Identity is builder (caller) +
            # part_number + collection.
            by_item = {
                (
                    str(a.get("part_number") or "").strip().casefold(),
                    str(a.get("collection") or "").strip().casefold(),
                ): a
                for a in item_scoped
                if str(a.get("part_number") or "").strip()
            }
            for idx in df.index:
                part = str(df.at[idx, "part_number"] or "").strip().casefold()
                coll = str(df.at[idx, "collection"] or "").strip().casefold()
                addon = by_item.get((part, coll))
                if addon is None:
                    continue
                r = df.loc[idx]
                b, a, pct_tag = self._addon_dollar_or_pct(
                    addon,
                    item_base=r.get("base_price"),
                    item_retail=r.get("adjusted_price"),
                    option_key=option_key,
                )
                if a is not None:
                    df.at[idx, "adjusted_price"] = float(r.get("adjusted_price") or 0.0) + float(a)
                if b is not None:
                    df.at[idx, "base_price"] = float(r.get("base_price") or 0.0) + float(b)
                amount = f" ({pct_tag})" if pct_tag else (f" (+${float(a):,.0f})" if a is not None else "")
                tag = f"+ {option_key}{amount}"
                n = notes.at[idx] if idx in notes.index else ""
                df.at[idx, "notes"] = f"{n} · {tag}".strip(" ·") if n else tag
                applied.at[idx] = True
            return df, applied

        if is_drawer_door and flat:
            eligible = text.apply(
                lambda s: (
                    any(k in s for k in drawer_keywords) and not any(x in s for x in drawer_exclude)
                )
            )
            if not eligible.any():
                return df, applied
            for idx in df.index[eligible]:
                r = df.loc[idx]
                b, a, pct_tag = self._addon_dollar_or_pct(
                    flat[0],
                    item_base=r.get("base_price"),
                    item_retail=r.get("adjusted_price"),
                    option_key=option_key,
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

        if parser_locked and flat:
            flat = (
                flat
                if self._locked_flat_option_has_item_evidence(df, option_key, profile)
                else []
            )
            if not flat and not cats:
                return df, applied

        # Finish / per-category (or non-drawer flat): every physical WOOD item.
        # Qty does not apply to finish options — only extras.
        has_wood = df.get("species").fillna("").astype(str).str.strip() != ""
        if not has_wood.any():
            return df, applied

        rc = sorted(
            a["adjusted_price"]
            for a in cats
            if a.get("adjusted_price") is not None and float(a["adjusted_price"] or 0) != 0
        )
        bc = sorted(
            a["base_price"]
            for a in cats
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
                if m is None and flat:
                    # A flat row is the default price; category rows override it
                    # for named collections (for example AC Asher/Lenova/Martin).
                    m, confident = flat[0], True
            else:
                m, confident = (flat[0], True) if flat else (None, False)
            op = r.get("adjusted_price")
            ob = r.get("base_price")
            pct_tag = None
            if m is not None:
                b, a, pct_tag = self._addon_dollar_or_pct(
                    m, item_base=ob, item_retail=op, option_key=option_key
                )
                label = None if m.get("is_flat") else m.get("category")
                approx = not confident
            elif med_addon is not None and not parser_locked:
                b, a, pct_tag = self._addon_dollar_or_pct(
                    med_addon,
                    item_base=ob,
                    item_retail=op,
                    option_key=option_key,
                )
                label, approx = None, True
            else:
                if parser_locked:
                    continue
                b, a, label, approx = med_base, med_retail, None, True
            if qty > 1:
                if a is not None:
                    a = float(a) * qty
                if b is not None:
                    b = float(b) * qty
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
            if qty > 1:
                inner = f"{inner} ×{qty}".strip()
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
        collection: Optional[str],
        part_number: Optional[str],
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
        item_options: list[str] = []
        for opt in keys:
            addons = self.repo.get_addon_rows(vendor, opt)
            if addons:
                addon_by_opt.append((opt, addons))
            else:
                # Item-native options (FN Cat.N, size variants, etc.) select
                # the priced base rows before additive options are applied.
                item_options.append(opt)
        if not addon_by_opt:
            return None

        df = self.repo.search(
            query,
            collection=collection,
            vendor=vendor,
            part_number=part_number,
            finish_state=finish_state,
            species=species,
            option_key=item_options or None,
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
        # Label with item-native and additive selections in stable UI order.
        label_bits = []
        addon_keys = {opt for opt, _ in addon_by_opt}
        for opt in keys:
            q = (
                self._clamp_option_qty(qtys.get(opt, 1))
                if opt in addon_keys and self._option_qty_allowed(opt)
                else 1
            )
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

    def list_option_keys(
        self,
        vendor: Optional[str] = None,
        *,
        query: str = "",
        collection: Optional[str] = None,
        part_number: Optional[str] = None,
        species: Optional[str] = None,
    ) -> list[str]:
        """Live Options for one builder, optionally narrowed to matching items.

        With a product query, item-native variants come only from those rows
        and addon charges must actually apply to at least one matching item.
        This keeps per-SKU option columns from becoming builder-wide choices.
        """
        self.ensure_ready()
        keys = self.repo.list_option_keys(vendor=vendor)
        profile = self._search_profile(vendor)
        label = finish_option_label(profile)
        if label and label not in keys:
            keys = [label, *keys]
        if not query.strip() or not vendor or vendor == "All":
            return order_search_options(keys)

        items = self.repo.search(
            query,
            vendor=vendor,
            collection=collection,
            part_number=part_number,
            species=species,
            finish_state=None,
            limit=max(DEFAULT_SEARCH_LIMIT * 6, 400),
        )
        if items.empty:
            return []

        native = {
            str(value).strip()
            for column in ("option_key", "species")
            if column in items.columns
            for value in items[column].dropna()
            if str(value).strip()
        }
        applicable: list[str] = []
        for key in keys:
            if key == label:
                selects = str((profile.get("finish_as_option") or {}).get("selects") or "")
                states = set(items.get("finish_state", pd.Series(dtype=str)).dropna().astype(str))
                if not selects or selects in states:
                    applicable.append(key)
                continue
            addons = self.repo.get_addon_rows(vendor, key)
            if addons:
                _priced, mask = self._apply_one_option_upcharge(
                    items,
                    option_key=key,
                    addons=addons,
                    profile=profile,
                )
                if mask.any():
                    applicable.append(key)
            elif key in native:
                applicable.append(key)
        return order_search_options(applicable)

    def options_for_search(
        self,
        vendor: Optional[str],
        query: str,
        options: Optional[Sequence[str]] = None,
        *,
        species: Optional[str] = None,
    ) -> list[str]:
        """Builder Options that fit the piece named in Search (all builders)."""
        self.ensure_ready()
        keys = (
            list(options)
            if options is not None
            else self.list_option_keys(vendor, query=query, species=species)
        )
        blob = str(query or "").strip()
        if not blob:
            return order_search_options(filter_options_for_kinds(keys, set(), text=""))
        query_kinds = furniture_kinds_from_text(blob)
        drawer_kinds = {"casegood", "nightstand", "wardrobe"}
        if "bed" in query_kinds and not (query_kinds & drawer_kinds):
            return order_search_options(filter_options_for_kinds(keys, query_kinds, text=blob))
        kinds_blob = blob
        if vendor and vendor not in ("All", ""):
            hits = self.repo.search(
                blob,
                vendor=vendor,
                species=None if not species or species == "All" else species,
                limit=40,
            )
            if hits is not None and not hits.empty:
                parts = []
                for _, row in hits.head(25).iterrows():
                    parts.append(
                        " ".join(
                            str(row.get(col) or "")
                            for col in ("description", "collection", "part_number")
                        )
                    )
                kinds_blob = f"{blob} {' '.join(parts)}"
        return order_search_options(
            filter_options_for_kinds(keys, furniture_kinds_from_text(kinds_blob), text=blob)
        )

    def _search_profile(self, vendor: Optional[str]) -> dict:
        if not vendor or vendor == "All":
            return {}
        profile = dict(load_builder_profile(vendor) or {})
        spec = effective_finish_as_option(
            profile,
            finish_states=self.repo.list_finish_states(vendor),
        )
        if spec:
            profile["finish_as_option"] = spec
        return profile

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

    def list_upload_quality(self) -> list[dict]:
        """0–100% quality rating for every builder currently in the book."""
        self.ensure_ready()
        from backend.upload_quality import list_upload_quality

        return list_upload_quality(self)

    def rate_drop_parse(self, payload: dict) -> dict:
        """0–100% quality rating for one Drop file parse."""
        from backend.upload_quality import rate_drop_parse

        rating = rate_drop_parse(payload)
        return {"percent": rating.percent, "deductions": list(rating.deductions)}

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

        # Canonical vendor on every row (prevents filename twins).
        # An explicit builder name wins over a filename hint so a new Drop
        # cannot retarget J&M / Hope Wood / etc. by accident.
        vend_raw = rows[0].get("vendor") or ""
        source = rows[0].get("source_file") or ""
        vend_from_name = resolve_builder_vendor(vend_raw) or ""
        vend_from_file = resolve_builder_vendor(vend_raw, filename=str(source)) or ""
        hinted = resolve_builder_vendor("", filename=str(source)) or ""
        if vend_from_name and vend_from_file and vend_from_name != vend_from_file:
            vend = vend_from_name
        else:
            vend = vend_from_file or vend_from_name or vend_raw
        for r in rows:
            r["vendor"] = vend

        existed = False
        if vend:
            try:
                existed = vend in set(self.repo.list_vendors())
            except Exception:
                existed = False

        if mode in ("replace_source", "replace_vendor", "replace_builder"):
            # One builder = one book: wipe + load in a single transaction
            if vend:
                result = self.repo.replace_vendor_rows(vend, rows)
            elif source:
                result = self.repo.replace_source_rows(source, rows)
            else:
                n = self.repo.insert_rows(rows)
                result = {
                    "inserted": n,
                    "updated": 0,
                    "deleted": 0,
                    "total": n,
                }
            if "total" not in result:
                n = result.get("inserted", 0)
                result = {
                    "inserted": n,
                    "updated": 0,
                    "deleted": result.get("deleted", 0),
                    "total": n,
                }
        elif mode == "upsert":
            result = self.repo.upsert_rows(rows)
            result["deleted"] = 0
        else:
            n = self.repo.insert_rows(rows)
            result = {"inserted": n, "updated": 0, "deleted": 0, "total": n}

        self._christina_observe_load(
            builder=str(vend or ""),
            filename=str(source or ""),
            mode=mode,
            inserted=int(result.get("inserted") or 0),
            deleted=int(result.get("deleted") or 0),
            existed=existed,
            hinted_builder=str(hinted or ""),
        )
        return result

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
        vendor_override: str = "",
    ) -> dict:
        """Single-pass parse → post-Standardize wholesale rows + suggested mult metadata."""
        from backend.drop_parse_session import wholesale_row
        from backend.smart_parse import summarize_parse_variants, variants_caption

        name = filename or "upload"
        typed = (vendor_override or "").strip()
        kind = "pdf" if name.lower().endswith(".pdf") else "excel"
        vend, selected_parser, source = identify_reader(
            name,
            data=data if kind == "excel" else None,
            vendor_override=typed,
            root=self._builder_profile_root,
            allow_guess=kind == "excel",
        )
        profile_parser = preferred_parser_for(
            vend,
            filename=name,
            root=self._builder_profile_root,
        )
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
            "variants": {},
            "detected_importer": selected_parser or ("pdf" if kind == "pdf" else ""),
            "parser_source": source,
            "locked_parser": profile_parser,
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
                    return self._christina_watch(out)
                if not prev.results and not prev.rows:
                    out["error"] = "No prices found in PDF."
                    out["notes"] = str(prev.stats)
                    return self._christina_watch(out)
                rows = [wholesale_row(r) for r in (prev.rows or [])]
                for r in rows:
                    r["vendor"] = vend
                    r["source_file"] = name
                    r["price_basis"] = r.get("price_basis") or "wholesale"
                out["rows"] = rows
                out["row_count"] = len(rows)
                out["priced_option_count"] = int(getattr(prev, "priced_option_count", 0) or 0)
                out["expected_finish_states"] = list(
                    getattr(prev, "expected_finish_states", []) or []
                )
                out["variants"] = summarize_parse_variants(
                    rows, vendor=vend, sheets_tried=[{"layout": "pdf"}]
                )
                out["detected_importer"] = selected_parser or "pdf"
                out["parser_source"] = "saved" if profile_parser else "guessed"
                cap = variants_caption(out["variants"])
                out["notes"] = f"PDF strategy · {len(rows)} rows" + (f" · {cap}" if cap else "")
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
                    preferred_parser=profile_parser,
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
                out["priced_option_count"] = int(getattr(prev, "priced_option_count", 0) or 0)
                out["expected_finish_states"] = list(
                    getattr(prev, "expected_finish_states", []) or []
                )
                out["hidden_product_candidates"] = list(
                    getattr(prev, "hidden_product_candidates", []) or []
                )
                out["variants"] = summarize_parse_variants(
                    rows,
                    vendor=vend,
                    sheets_tried=getattr(prev, "sheets_tried", None),
                )
                out["detected_importer"] = infer_importer(
                    getattr(prev, "detected_importer", "") or selected_parser,
                    out["variants"].get("layouts"),
                )
                out["parser_source"] = (
                    "saved"
                    if profile_parser and out["detected_importer"] == profile_parser
                    else (getattr(prev, "parser_source", "") or "guessed")
                )
                cap = variants_caption(out["variants"])
                if cap:
                    out["notes"] = (out["notes"] + " · " if out["notes"] else "") + cap
                if out["hidden_product_candidates"]:
                    # Hidden stays hidden. Naming the tabs lets Judson ask the
                    # factory for a visible copy instead of guessing.
                    named = ", ".join(out["hidden_product_candidates"][:6])
                    out["notes"] = (
                        out["notes"] + " · " if out["notes"] else ""
                    ) + f"Hidden tabs that look like product (not imported): {named}"
                if not rows:
                    out["error"] = "0 rows parsed — check file layout."
        except Exception as e:
            out["error"] = str(e)[:400]
        return self._christina_watch(out)

    def ensure_drop_parse_session(
        self,
        uploads: Sequence[Any],
        *,
        session_id: Optional[str] = None,
        prefer_workbook_markup: bool = False,
        force: bool = False,
        progress: Optional[Callable[[float, str], None]] = None,
        vendor_overrides: Optional[dict[str, str]] = None,
    ):
        """
        Create or reuse a Drop parse session for one upload batch.

        Returns DropParseSessionView (opaque id + per-file preview metadata).
        Full rows stay on disk; UI must not hold them.
        """
        from backend.drop_parse_session import (
            DropFileOutcome,
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
                vendor_override=(vendor_overrides or {}).get(up.filename, ""),
            )
            files_payload.append(DropFileOutcome.from_payload(parsed).to_payload())
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

    def list_builder_parsers(self, *, root: Optional[Path] = None) -> list[dict[str, str]]:
        """Named parsers locked after a perfected Drop (ADR-0011)."""
        return list_locked_parsers(root=root)

    def lock_builder_parser(
        self,
        vendor: str,
        *,
        importer: str = "",
        source_file: str = "",
        layouts: Optional[list] = None,
        root: Optional[Path] = None,
    ) -> Optional[Path]:
        """Persist this builder's parser after a successful Drop Load."""
        from backend.standardize import resolve_builder_vendor

        vend = resolve_builder_vendor(vendor) or (vendor or "").strip()
        if not vend:
            return None
        saved = save_named_parser(
            vend,
            importer=importer,
            source_file=source_file,
            layouts=list(layouts or []),
            root=root if root is not None else self._builder_profile_root,
        )
        self._christina_observe_lock(
            builder=vend,
            importer=importer,
            source_file=source_file,
        )
        return saved

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

    def commit_drop_load(
        self,
        session_id: str,
        bindings,
        *,
        mode: str = "replace_vendor",
    ):
        """Commit confirmed Drop bindings; each Builder succeeds or blocks independently."""
        from backend.builder_profiles import profile_writes_allowed
        from backend.drop_parse_session import (
            DropBuilderLoadResult,
            DropLoadBatchResult,
            DropSessionGone,
            _lock_fields_from_payload,
            _readiness_from_payload,
        )

        store = self._drop_parse_store()
        payload = store.load(session_id)
        if not payload:
            raise DropSessionGone(session_id)
        files = list(payload.get("files") or [])

        # One builder = one catalog. Multiple files for the same name concatenate.
        grouped: dict[str, list[tuple[Any, dict]]] = {}
        for binding in bindings:
            index = int(binding.file_index)
            if index < 0 or index >= len(files):
                continue
            builder = str(binding.builder or "").strip()
            if not builder:
                continue
            grouped.setdefault(builder, []).append((binding, files[index]))

        results = []
        warnings: list[str] = []
        any_success = False
        for builder, parts in grouped.items():
            binding = parts[0][0]
            mult = float(binding.multiplier)
            ready: list[tuple[Any, dict]] = []
            skipped: list[str] = []
            for _binding, file_payload in parts:
                readiness = _readiness_from_payload(file_payload)
                if not readiness.load_ready:
                    skipped.append(
                        "{0}: {1}".format(
                            file_payload.get("filename") or "file",
                            readiness.block_message or "not ready",
                        )
                    )
                    continue
                ready.append((_binding, file_payload))
            if not ready:
                lock_fields = _lock_fields_from_payload(parts[0][1])
                results.append(
                    DropBuilderLoadResult(
                        builder=builder,
                        filename=" + ".join(str(item[1].get("filename") or "") for item in parts),
                        status="blocked",
                        multiplier=mult,
                        catalog={},
                        parser_id=lock_fields.importer,
                        block_message="; ".join(skipped),
                    )
                )
                continue

            rows = []
            filenames: list[str] = []
            lock_fields = _lock_fields_from_payload(ready[0][1])
            for _binding, file_payload in ready:
                filename = str(file_payload.get("filename") or "")
                filenames.append(filename)
                next_lock = _lock_fields_from_payload(file_payload)
                if next_lock.importer and next_lock.importer not in {"generic", "pdf"}:
                    lock_fields = next_lock
                for source_row in file_payload.get("rows") or []:
                    row = dict(source_row)
                    row["vendor"] = builder
                    row["source_file"] = filename
                    row["multiplier"] = mult
                    row.pop("adjusted_price", None)
                    rows.append(row)
            filename = " + ".join(filenames)
            if skipped:
                warnings.append(
                    "{0}: loaded {1} file(s), skipped {2}".format(
                        builder, len(ready), "; ".join(skipped)
                    )
                )
            if not rows:
                results.append(
                    DropBuilderLoadResult(
                        builder=builder,
                        filename=filename,
                        status="blocked",
                        multiplier=mult,
                        catalog={},
                        parser_id=lock_fields.importer,
                        block_message="0 rows parsed",
                    )
                )
                continue

            fingerprint = _wholesale_fingerprint(rows)
            unchanged = (
                bool(fingerprint)
                and self.repo.get_vendor_import_fingerprint(builder) == fingerprint
            )
            try:
                if unchanged:
                    catalog = {
                        "inserted": 0,
                        "updated": 0,
                        "deleted": 0,
                        "total": 0,
                    }
                else:
                    catalog = self.add_rows(rows, mode=mode)
                self.set_vendor_multiplier(
                    builder,
                    mult,
                    notes=f"Set from drop import of {filename}",
                )
                self.reapply_multiplier(mult, vendor=builder)
                self.repo.set_vendor_import_fingerprint(
                    builder,
                    fingerprint,
                    source_file=filename,
                )
            except Exception as exc:
                results.append(
                    DropBuilderLoadResult(
                        builder=builder,
                        filename=filename,
                        status="error",
                        multiplier=mult,
                        catalog={},
                        parser_id=lock_fields.importer,
                        block_message=str(exc)[:400],
                    )
                )
                continue

            profile_saved = False
            profile_warning = ""
            from backend.builder_reader_registry import DEFAULT_READER_REGISTRY

            existing_imp = (
                str(
                    (
                        load_builder_profile(builder, root=self._builder_profile_root).get("parser")
                        or {}
                    ).get("importer")
                    or ""
                )
                .strip()
                .lower()
            )
            lock_importer = lock_fields.importer
            if existing_imp in DEFAULT_READER_REGISTRY.specific_ids:
                lock_importer = existing_imp
            lock_layouts: list[str] = []
            for _binding, file_payload in ready:
                lock_layouts.extend(_lock_fields_from_payload(file_payload).layouts)
            if not lock_layouts:
                lock_layouts = list(lock_fields.layouts)
            lock_layouts = list(dict.fromkeys(str(x) for x in lock_layouts if x))
            try:
                parser_path = self.lock_builder_parser(
                    builder,
                    importer=lock_importer,
                    source_file=filename,
                    layouts=lock_layouts,
                )
                profile_saved = bool(parser_path)
                # Fly intentionally reads shipped profiles and does not write.
                if parser_path is None and profile_writes_allowed():
                    profile_warning = "Builder Profile parser lock was not saved"
            except Exception as exc:
                profile_warning = str(exc)[:400]
            if profile_warning:
                warning = f"{builder}: catalog loaded but parser lock failed — {profile_warning}"
                warnings.append(warning)

            any_success = True
            results.append(
                DropBuilderLoadResult(
                    builder=builder,
                    filename=filename,
                    status="unchanged" if unchanged else "loaded",
                    multiplier=mult,
                    catalog=catalog,
                    parser_id=lock_importer,
                    profile_saved=profile_saved,
                    profile_warning=profile_warning,
                )
            )

        if any_success:
            store.delete(session_id)
        return DropLoadBatchResult(
            session_id=session_id,
            results=tuple(results),
            blocking_warnings=tuple(warnings),
            master_row_count=self.row_count(),
            session_cleared=any_success,
        )

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
