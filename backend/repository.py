"""Data access for pricebook + vendors tables."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Union  # noqa: F401 — Optional used throughout

import pandas as pd

from backend.config import DEFAULT_MULTIPLIER, DEFAULT_SEARCH_LIMIT, IDENTITY_FIELDS
from backend.db import get_connection
from backend.models import PRICEBOOK_COLS, SELECT_COLS


def _norm_key_val(v) -> str:
    if v is None:
        return ""
    s = str(v).strip().lower()
    if s in {"none", "nan", "null"}:
        return ""
    return s


def identity_key(row: dict) -> tuple:
    return tuple(_norm_key_val(row.get(f)) for f in IDENTITY_FIELDS)


class PriceBookRepository:
    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        self.db_path = db_path

    def _conn(self):
        return get_connection(self.db_path)

    # ------------------------------------------------------------------ stats
    def row_count(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM pricebook").fetchone()[0]

    def stats(self) -> dict:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM pricebook").fetchone()[0]
            vendors = conn.execute(
                "SELECT COUNT(DISTINCT vendor) FROM pricebook "
                "WHERE vendor IS NOT NULL AND vendor != ''"
            ).fetchone()[0]
            collections = conn.execute(
                "SELECT COUNT(DISTINCT collection) FROM pricebook "
                "WHERE collection IS NOT NULL AND collection != ''"
            ).fetchone()[0]
            sources = conn.execute(
                "SELECT COUNT(DISTINCT source_file) FROM pricebook "
                "WHERE source_file IS NOT NULL AND source_file != ''"
            ).fetchone()[0]
        return {
            "rows": total,
            "vendors": vendors,
            "collections": collections,
            "source_files": sources,
        }

    # ------------------------------------------------------------------ lists
    def list_vendors(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT vendor FROM pricebook "
                "WHERE vendor IS NOT NULL AND vendor != '' "
                "ORDER BY vendor"
            ).fetchall()
        return [r[0] for r in rows]

    def list_collections(self, vendor: Optional[str] = None) -> list[str]:
        with self._conn() as conn:
            if vendor:
                rows = conn.execute(
                    "SELECT DISTINCT collection FROM pricebook "
                    "WHERE collection IS NOT NULL AND collection != '' "
                    "AND vendor = ? ORDER BY collection",
                    (vendor,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT DISTINCT collection FROM pricebook "
                    "WHERE collection IS NOT NULL AND collection != '' "
                    "ORDER BY collection"
                ).fetchall()
        return [r[0] for r in rows]

    # Core woods always offered in the dropdown (even if rare in current filter)
    _CORE_WOODS = (
        "Oak",
        "Red Oak",
        "White Oak",
        "Brown Maple",
        "Hard Maple",
        "Soft Maple",
        "Maple",
        "Cherry",
        "Sap Cherry",
        "Walnut",
        "Hickory",
        "Elm",
        "QSWO",
        "Quarter Sawn White Oak",
        "Rustic Cherry",
        "Rustic Hickory",
        "Rustic Walnut",
        "Rustic QSWO",
        "Wormy Maple",
        "Birch",
        "Ash",
        "Alder",
        "Pine",
        "Cedar",
        "Barnwood",
    )
    _WOOD_DROPDOWN_RE = re.compile(
        r"(?i)\b("
        r"oak|maple|cherry|walnut|hickory|elm|birch|ash|poplar|pine|alder|"
        r"beech|mahogany|qswo|pswo|qsw|wormy|rustic|brown\s*maple|hard\s*maple|"
        r"soft\s*maple|white\s*oak|red\s*oak|sap\s*cherry|quarter\s*sawn|"
        r"rough\s*sawn|ruff\s*sawn|barnwood|cedar|poly|woodgrain|fabric|leather|"
        r"paint|black|white\s*maple|grey\s*elm|gray\s*elm"
        r")\b"
    )
    _WOOD_DROPDOWN_JUNK = re.compile(
        r"(?i)^("
        r"[\d$#+%.\-\"']+|"
        r"and|or|the|with|also|add|option|species|stain|part|number|color|"
        r"r\.?|combo|standard|premium|unf\.?|fin\.?|wood|tier|quarter"
        r")$"
    )

    def list_species(self, vendor: Optional[str] = None) -> list[str]:
        """
        Distinct wood / option labels for the floor Wood dropdown.

        When *vendor* is set, only woods that appear in that builder's
        catalog are returned (multi-wood tiers are split into atoms).
        When vendor is All/None, woods are collected across all builders.
        """
        scoped = bool(vendor and vendor not in ("All", "", None))
        atomic: set[str] = set()
        try:
            with self._conn() as conn:
                if scoped:
                    rows = conn.execute(
                        "SELECT DISTINCT species FROM pricebook "
                        "WHERE species IS NOT NULL AND TRIM(species) != '' "
                        "AND vendor = ?",
                        (vendor,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT DISTINCT species FROM pricebook "
                        "WHERE species IS NOT NULL AND TRIM(species) != ''"
                    ).fetchall()
            for (raw,) in rows:
                s = str(raw).strip()
                if not s:
                    continue
                # Split multi-wood tiers on " / " or "/"
                if " / " in s or (s.count("/") >= 1 and not re.search(r"\d/\d", s)):
                    parts = [p.strip() for p in re.split(r"\s*/\s*", s) if p.strip()]
                else:
                    parts = [s]
                for p in parts:
                    if self._is_wood_dropdown_label(p):
                        atomic.add(p)
        except Exception:
            if not scoped:
                atomic.update(self._CORE_WOODS)

        # All-builders only: seed common woods if DB parse was empty
        if not scoped and not atomic:
            atomic.update(self._CORE_WOODS)

        # Prefer Title Case for duplicates that only differ by case
        by_low: dict[str, str] = {}
        for p in atomic:
            k = p.lower()
            if k not in by_low or (p[:1].isupper() and not by_low[k][:1].isupper()):
                by_low[k] = p
        return sorted(by_low.values(), key=lambda x: x.lower())

    def _is_wood_dropdown_label(self, p: str) -> bool:
        if not p or len(p) < 2 or len(p) > 48:
            return False
        if re.fullmatch(r"\d+(\.\d+)?", p):
            return False
        if self._WOOD_DROPDOWN_JUNK.match(p.strip()):
            return False
        if re.search(r"[@$%]|\+\d|option:|stain part", p, re.I):
            return False
        if self._WOOD_DROPDOWN_RE.search(p):
            return True
        return False

    def list_source_files(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT source_file FROM pricebook "
                "WHERE source_file IS NOT NULL AND source_file != '' "
                "ORDER BY source_file"
            ).fetchall()
        return [r[0] for r in rows]

    # ------------------------------------------------------------------ search
    # Columns searched for every boolean term (anywhere in the pricelist row)
    _SEARCH_FIELDS = (
        "vendor",
        "collection",
        "part_number",
        "description",
        "species",
        "dimensions",
        "notes",
        "source_file",
        "finish_state",
        "option_key",
        "unit",
    )

    @staticmethod
    def _like_escape(term: str) -> str:
        """Escape LIKE wildcards so user input is literal (%, _, \\)."""
        return (
            (term or "")
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )

    def _term_match_sql(self, term: str) -> tuple[str, list]:
        """One term → SQL that matches if the term appears in ANY pricelist field."""
        term = (term or "").strip().lower()
        if not term:
            return "1=1", []
        like = f"%{self._like_escape(term)}%"
        parts = [
            f"lower(coalesce({col},'')) LIKE ? ESCAPE '\\'"
            for col in self._SEARCH_FIELDS
        ]
        # Also match cast of base_price as text (e.g. "1250")
        parts.append("cast(base_price as text) LIKE ? ESCAPE '\\'")
        parts.append("cast(adjusted_price as text) LIKE ? ESCAPE '\\'")
        return "(" + " OR ".join(parts) + ")", [like] * (len(self._SEARCH_FIELDS) + 2)
    @staticmethod
    def _tokenize_boolean(query: str) -> list:
        """
        Tokenize boolean query into: WORD, PHRASE, AND, OR, NOT, LPAREN, RPAREN.

        Supported syntax:
          oak nightstand          → AND (default between words)
          oak AND nightstand      → AND
          oak OR maple            → OR
          oak | maple             → OR
          nightstand NOT dust     → NOT
          -dust                   → NOT dust
          \"bar stool\"           → phrase
          (oak OR maple) chair    → grouping
        """
        q = (query or "").strip()
        if not q:
            return []
        tokens: list[tuple[str, str]] = []
        i = 0
        n = len(q)
        while i < n:
            ch = q[i]
            if ch.isspace():
                i += 1
                continue
            if ch in "()":
                tokens.append(("LPAREN" if ch == "(" else "RPAREN", ch))
                i += 1
                continue
            if ch in "|\u2228":  # | or ∨
                tokens.append(("OR", "OR"))
                i += 1
                continue
            if ch == "-" and (i + 1 < n) and not q[i + 1].isspace():
                # leading -term as NOT (when not mid-SKU like GO-AVNNS)
                # Only if at start or after space/operator
                prev_ok = i == 0 or q[i - 1].isspace() or q[i - 1] in "()"
                if prev_ok:
                    tokens.append(("NOT", "NOT"))
                    i += 1
                    continue
            if ch in "\"'":
                quote = ch
                i += 1
                start = i
                while i < n and q[i] != quote:
                    i += 1
                phrase = q[start:i]
                if i < n:
                    i += 1
                tokens.append(("PHRASE", phrase.strip()))
                continue
            # word
            start = i
            while i < n and (not q[i].isspace()) and q[i] not in "()|\"'":
                i += 1
            word = q[start:i]
            up = word.upper()
            if up == "AND":
                tokens.append(("AND", "AND"))
            elif up == "OR":
                tokens.append(("OR", "OR"))
            elif up == "NOT":
                tokens.append(("NOT", "NOT"))
            else:
                tokens.append(("WORD", word))
        return tokens

    def _boolean_to_sql(self, query: str) -> tuple[str, list, list[str]]:
        """
        Parse boolean query → (sql_clause, params, bare_terms_for_ranking).
        Empty query → ("", [], []).
        """
        tokens = self._tokenize_boolean(query)
        if not tokens:
            return "", [], []

        # Insert implicit AND between adjacent terms / groups
        # e.g. WORD WORD → WORD AND WORD ; ) WORD → ) AND WORD ; NOT is unary
        expanded: list[tuple[str, str]] = []
        prev_end = False  # previous token ends a value/group
        for typ, val in tokens:
            is_start = typ in ("WORD", "PHRASE", "NOT", "LPAREN")
            if expanded and prev_end and is_start:
                expanded.append(("AND", "AND"))
            expanded.append((typ, val))
            prev_end = typ in ("WORD", "PHRASE", "RPAREN")

        bare_terms: list[str] = []

        # Shunting-yard → RPN
        prec = {"OR": 1, "AND": 2, "NOT": 3}
        right_assoc = {"NOT"}
        output: list[tuple[str, str]] = []
        stack: list[tuple[str, str]] = []
        for typ, val in expanded:
            if typ in ("WORD", "PHRASE"):
                output.append((typ, val))
                bare_terms.append(val)
            elif typ == "NOT":
                stack.append((typ, val))
            elif typ in ("AND", "OR"):
                while stack and stack[-1][0] in prec:
                    top = stack[-1][0]
                    if (prec[top] > prec[typ]) or (
                        prec[top] == prec[typ] and typ not in right_assoc
                    ):
                        output.append(stack.pop())
                    else:
                        break
                stack.append((typ, val))
            elif typ == "LPAREN":
                stack.append((typ, val))
            elif typ == "RPAREN":
                while stack and stack[-1][0] != "LPAREN":
                    output.append(stack.pop())
                if stack and stack[-1][0] == "LPAREN":
                    stack.pop()
        while stack:
            if stack[-1][0] != "LPAREN":
                output.append(stack.pop())
            else:
                stack.pop()

        # RPN → SQL
        sql_stack: list[tuple[str, list]] = []
        for typ, val in output:
            if typ in ("WORD", "PHRASE"):
                sql_stack.append(self._term_match_sql(val))
            elif typ == "NOT":
                if not sql_stack:
                    continue
                clause, p = sql_stack.pop()
                sql_stack.append((f"(NOT {clause})", p))
            elif typ in ("AND", "OR"):
                if len(sql_stack) < 2:
                    continue
                right_c, right_p = sql_stack.pop()
                left_c, left_p = sql_stack.pop()
                op = " AND " if typ == "AND" else " OR "
                sql_stack.append(
                    (f"({left_c}{op}{right_c})", left_p + right_p)
                )

        if not sql_stack:
            return "", [], bare_terms
        clause, params = sql_stack[-1]
        return clause, params, bare_terms

    def search(
        self,
        query: str = "",
        *,
        collection: Optional[str] = None,
        vendor: Optional[str] = None,
        finish_state: Optional[str] = None,
        species: Optional[str] = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> pd.DataFrame:
        """
        Boolean floor search across the full pricelist row.

        Operators: AND (default between words), OR / |, NOT / -term,
        \"phrases\", (parentheses).

        Each term matches if found in any field: part #, description, collection,
        builder, wood/option, dimensions, finish, notes, source file, prices.

        species: exact match, or multi-wood tier containing that wood
        (e.g. filter "Cherry" matches "Elm / Cherry / Maple / QSWO").

        Ranking (best first):
          1. Exact part_number match
          2. Part number starts with query / term
          3. Part contains term
          4. Description match
          Prefer finished; demote dust covers / -DC accessories.
        """
        clauses: list[str] = []
        params: list = []
        q = (query or "").strip()
        q_lower = q.lower()

        bare_terms: list[str] = []
        if q:
            bool_sql, bool_params, bare_terms = self._boolean_to_sql(q)
            if bool_sql:
                clauses.append(bool_sql)
                params.extend(bool_params)
            else:
                # User typed something that parsed to no real terms (e.g. "AND OR NOT")
                # — do not return the whole catalog.
                clauses.append("1=0")

        if collection and collection != "All":
            clauses.append("collection = ?")
            params.append(collection)
        if vendor and vendor != "All":
            clauses.append("vendor = ?")
            params.append(vendor)
        if finish_state and finish_state.lower() in ("finished", "unfinished", "glazed"):
            clauses.append("finish_state = ?")
            params.append(finish_state.lower())
        if species and species != "All":
            # Exact tier/label, or multi-wood tier that includes this wood as a token
            sp = species.strip()
            clauses.append(
                "("
                "trim(coalesce(species,'')) = ? OR "
                "trim(coalesce(species,'')) LIKE ? ESCAPE '\\' OR "
                "trim(coalesce(species,'')) LIKE ? ESCAPE '\\' OR "
                "trim(coalesce(species,'')) LIKE ? ESCAPE '\\'"
                ")"
            )
            esc = self._like_escape(sp)
            params.extend(
                [
                    sp,
                    esc + " / %",  # "Cherry / …"
                    "% / " + esc + " / %",  # "… / Cherry / …"
                    "% / " + esc,  # "… / Cherry"
                ]
            )

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        cols = ", ".join(SELECT_COLS)

        # Ranking: prefer matches on the full query string, then first term
        rank_key = q_lower
        if bare_terms:
            # Prefer longest bare term (often the SKU) for ranking
            rank_key = max((t.lower() for t in bare_terms), key=len)

        order_params: list = []
        if rank_key and bare_terms:
            rk = self._like_escape(rank_key)
            order_sql = """
            ORDER BY
              CASE
                WHEN lower(trim(coalesce(part_number,''))) = ? THEN 0
                WHEN lower(trim(coalesce(part_number,''))) LIKE ? ESCAPE '\\' THEN 1
                WHEN lower(trim(coalesce(part_number,''))) LIKE ? ESCAPE '\\' THEN 2
                WHEN lower(coalesce(description,'')) LIKE ? ESCAPE '\\' THEN 3
                WHEN lower(coalesce(collection,'')) LIKE ? ESCAPE '\\' THEN 4
                WHEN lower(coalesce(species,'')) LIKE ? ESCAPE '\\' THEN 5
                ELSE 6
              END,
              CASE lower(coalesce(finish_state,''))
                WHEN 'finished' THEN 0
                WHEN 'unfinished' THEN 1
                ELSE 2
              END,
              CASE
                WHEN lower(coalesce(part_number,'')) LIKE '%-dc'
                  OR lower(coalesce(description,'')) LIKE '%dust cover%'
                THEN 1 ELSE 0
              END,
              length(coalesce(part_number,'')),
              vendor, collection, part_number, species_tier, description
            """
            order_params = [
                rank_key,
                rk + "%",
                "%" + rk + "%",
                "%" + rk + "%",
                "%" + rk + "%",
                "%" + rk + "%",
            ]
        else:
            # No rank terms (empty query, or operators-only)
            order_sql = """
            ORDER BY vendor, collection, part_number, species_tier, description
            """

        sql = f"""
            SELECT {cols}
            FROM pricebook
            {where}
            {order_sql}
            LIMIT ?
        """
        params.extend(order_params)
        params.append(int(limit))

        with self._conn() as conn:
            return pd.read_sql_query(sql, conn, params=params)

    # ------------------------------------------------------------------ write
    def insert_rows(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        placeholders = ",".join("?" * len(PRICEBOOK_COLS))
        sql = (
            f"INSERT INTO pricebook ({','.join(PRICEBOOK_COLS)}) "
            f"VALUES ({placeholders})"
        )
        values = [tuple(r.get(c) for c in PRICEBOOK_COLS) for r in rows]
        with self._conn() as conn:
            conn.executemany(sql, values)
            conn.commit()
            return len(values)

    def delete_by_source(self, source_file: str) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM pricebook WHERE source_file = ?", (source_file,)
            )
            conn.commit()
            return cur.rowcount

    def delete_by_vendor(self, vendor: str) -> int:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM pricebook WHERE vendor = ?", (vendor,))
            conn.commit()
            return cur.rowcount

    def upsert_rows(self, rows: list[dict]) -> dict:
        """
        Insert new configs; update base_price/multiplier/adjusted when identity matches.

        Identity = vendor + collection + part_number + species + finish_state
                    + option_key + dimensions (null-safe).

        Returns counts: inserted, updated, skipped.
        """
        if not rows:
            return {"inserted": 0, "updated": 0, "skipped": 0, "total": 0}

        # Load existing keys for vendors present in batch (scoped for speed)
        vendors = {r.get("vendor") for r in rows if r.get("vendor")}
        existing: dict[tuple, int] = {}
        with self._conn() as conn:
            if vendors:
                for vend in vendors:
                    cur = conn.execute(
                        f"SELECT id, {', '.join(IDENTITY_FIELDS)} FROM pricebook "
                        "WHERE vendor = ?",
                        (vend,),
                    )
                    for row in cur.fetchall():
                        d = {f: row[f] for f in IDENTITY_FIELDS}
                        d["id"] = row["id"]
                        existing[identity_key(d)] = row["id"]
            else:
                cur = conn.execute(
                    f"SELECT id, {', '.join(IDENTITY_FIELDS)} FROM pricebook"
                )
                for row in cur.fetchall():
                    d = {f: row[f] for f in IDENTITY_FIELDS}
                    existing[identity_key(d)] = row["id"]

            to_insert = []
            updated = 0
            skipped = 0
            for r in rows:
                key = identity_key(r)
                # require at least part or description + price
                if r.get("base_price") is None and not (
                    r.get("part_number") or r.get("description")
                ):
                    skipped += 1
                    continue
                if key in existing and any(key):  # empty key still inserts
                    # all-empty identity → always insert to avoid mass collision
                    if not any(key):
                        to_insert.append(r)
                        continue
                    rid = existing[key]
                    conn.execute(
                        """
                        UPDATE pricebook SET
                            description = COALESCE(?, description),
                            base_price = ?,
                            price_basis = COALESCE(?, price_basis),
                            multiplier = ?,
                            adjusted_price = ?,
                            unit = COALESCE(?, unit),
                            notes = COALESCE(?, notes),
                            source_file = ?,
                            imported_at = ?,
                            species_tier = COALESCE(?, species_tier)
                        WHERE id = ?
                        """,
                        (
                            r.get("description"),
                            r.get("base_price"),
                            r.get("price_basis"),
                            r.get("multiplier"),
                            r.get("adjusted_price"),
                            r.get("unit"),
                            r.get("notes"),
                            r.get("source_file"),
                            r.get("imported_at"),
                            r.get("species_tier"),
                            rid,
                        ),
                    )
                    updated += 1
                else:
                    to_insert.append(r)
                    # prevent dupes within same batch
                    if any(key):
                        existing[key] = -1

            inserted = 0
            if to_insert:
                placeholders = ",".join("?" * len(PRICEBOOK_COLS))
                sql = (
                    f"INSERT INTO pricebook ({','.join(PRICEBOOK_COLS)}) "
                    f"VALUES ({placeholders})"
                )
                values = [tuple(r.get(c) for c in PRICEBOOK_COLS) for r in to_insert]
                conn.executemany(sql, values)
                inserted = len(values)

            conn.commit()

        return {
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
            "total": inserted + updated,
        }

    def find_duplicate_groups(self, limit: int = 100) -> pd.DataFrame:
        """Groups sharing the same identity key with count > 1."""
        fields = ", ".join(IDENTITY_FIELDS)
        coalesce_parts = [
            f"COALESCE(LOWER(TRIM({f})), '')" for f in IDENTITY_FIELDS
        ]
        group_expr = " || '|' || ".join(coalesce_parts)
        sql = f"""
            SELECT {fields}, COUNT(*) AS dup_count
            FROM pricebook
            GROUP BY {group_expr}
            HAVING COUNT(*) > 1
            ORDER BY dup_count DESC
            LIMIT ?
        """
        with self._conn() as conn:
            return pd.read_sql_query(sql, conn, params=(limit,))

    def cleanup_duplicates(self, *, dry_run: bool = True) -> dict:
        """
        Keep newest imported_at (then highest id) per identity group; delete rest.

        Returns counts and optional sample of deleted ids when dry_run.
        """
        fields = ", ".join(IDENTITY_FIELDS)
        coalesce_parts = [
            f"COALESCE(LOWER(TRIM({f})), '')" for f in IDENTITY_FIELDS
        ]
        group_expr = " || '|' || ".join(coalesce_parts)

        with self._conn() as conn:
            groups = conn.execute(
                f"""
                SELECT {group_expr} AS gkey, COUNT(*) AS c
                FROM pricebook
                GROUP BY gkey
                HAVING c > 1
                """
            ).fetchall()

            to_delete: list[int] = []
            for g in groups:
                # empty identity keys — skip mass delete
                if not g["gkey"] or set(g["gkey"].split("|")) <= {""}:
                    continue
                rows = conn.execute(
                    f"""
                    SELECT id, imported_at FROM pricebook
                    WHERE {group_expr} = ?
                    ORDER BY
                        CASE WHEN imported_at IS NULL OR imported_at = '' THEN 0 ELSE 1 END DESC,
                        imported_at DESC,
                        id DESC
                    """,
                    (g["gkey"],),
                ).fetchall()
                # keep first
                for r in rows[1:]:
                    to_delete.append(int(r["id"]))

            if dry_run:
                return {
                    "dry_run": True,
                    "groups": len(groups),
                    "would_delete": len(to_delete),
                    "sample_ids": to_delete[:30],
                }

            deleted = 0
            # chunk deletes
            chunk = 500
            for i in range(0, len(to_delete), chunk):
                batch = to_delete[i : i + chunk]
                placeholders = ",".join("?" * len(batch))
                cur = conn.execute(
                    f"DELETE FROM pricebook WHERE id IN ({placeholders})", batch
                )
                deleted += cur.rowcount
            conn.commit()
            return {
                "dry_run": False,
                "groups": len(groups),
                "deleted": deleted,
            }

    def get_row_by_id(self, row_id: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                f"SELECT {', '.join(SELECT_COLS)} FROM pricebook WHERE id = ?",
                (row_id,),
            ).fetchone()
            return dict(row) if row else None

    def vendor_summary(self) -> pd.DataFrame:
        with self._conn() as conn:
            return pd.read_sql_query(
                """
                SELECT
                    p.vendor,
                    COUNT(*) AS rows,
                    COUNT(DISTINCT p.collection) AS collections,
                    COUNT(DISTINCT p.source_file) AS source_files,
                    MIN(p.base_price) AS min_base,
                    MAX(p.base_price) AS max_base,
                    AVG(p.multiplier) AS avg_mult,
                    v.multiplier AS saved_mult,
                    v.phone AS phone,
                    v.updated_at AS mult_updated
                FROM pricebook p
                LEFT JOIN vendors v ON v.name = p.vendor
                WHERE p.vendor IS NOT NULL AND p.vendor != ''
                GROUP BY p.vendor
                ORDER BY rows DESC
                """,
                conn,
            )

    # ------------------------------------------------------------------ pricing bulk
    def reapply_multiplier(
        self,
        new_mult: float,
        *,
        vendor: Optional[str] = None,
    ) -> int:
        """Set mult and recompute retail (even whole dollars)."""
        # 2 * CEIL((base * mult) / 2) — next even dollar up
        retail_expr = "2 * CEIL((base_price * ?) / 2.0 - 1e-12)"
        with self._conn() as conn:
            if vendor:
                cur = conn.execute(
                    f"""
                    UPDATE pricebook
                    SET multiplier = ?,
                        adjusted_price = {retail_expr}
                    WHERE base_price IS NOT NULL AND vendor = ?
                    """,
                    (new_mult, new_mult, vendor),
                )
            else:
                cur = conn.execute(
                    f"""
                    UPDATE pricebook
                    SET multiplier = ?,
                        adjusted_price = {retail_expr}
                    WHERE base_price IS NOT NULL
                    """,
                    (new_mult, new_mult),
                )
            conn.commit()
            return cur.rowcount

    def recompute_adjusted(self, vendor: Optional[str] = None) -> int:
        """Recompute retail from each row's own multiplier (even whole dollars)."""
        retail_expr = "2 * CEIL((base_price * multiplier) / 2.0 - 1e-12)"
        with self._conn() as conn:
            if vendor:
                cur = conn.execute(
                    f"""
                    UPDATE pricebook
                    SET adjusted_price = {retail_expr}
                    WHERE base_price IS NOT NULL AND multiplier IS NOT NULL
                      AND vendor = ?
                    """,
                    (vendor,),
                )
            else:
                cur = conn.execute(
                    f"""
                    UPDATE pricebook
                    SET adjusted_price = {retail_expr}
                    WHERE base_price IS NOT NULL AND multiplier IS NOT NULL
                    """
                )
            conn.commit()
            return cur.rowcount

    # ------------------------------------------------------------------ vendors table
    def get_vendor_multiplier(
        self, vendor: str, default: float = DEFAULT_MULTIPLIER
    ) -> float:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT multiplier FROM vendors WHERE name = ?", (vendor,)
            ).fetchone()
        if row and row[0] is not None:
            return float(row[0])
        return default

    def set_vendor_multiplier(
        self, vendor: str, multiplier: float, notes: str = ""
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO vendors (name, multiplier, notes, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    multiplier = excluded.multiplier,
                    notes = COALESCE(excluded.notes, vendors.notes),
                    updated_at = excluded.updated_at
                """,
                (vendor, multiplier, notes or None, now),
            )
            conn.commit()

    def set_vendor_phone(self, vendor: str, phone: str = "") -> None:
        """Upsert builder phone; preserves existing multiplier when inserting."""
        now = datetime.now().isoformat(timespec="seconds")
        phone_clean = (phone or "").strip() or None
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO vendors (name, multiplier, phone, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    phone = excluded.phone,
                    updated_at = excluded.updated_at
                """,
                (vendor, DEFAULT_MULTIPLIER, phone_clean, now),
            )
            conn.commit()

    def get_vendor_phone(self, vendor: str) -> str:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT phone FROM vendors WHERE name = ?", (vendor,)
            ).fetchone()
        if row and row[0]:
            return str(row[0])
        return ""

    def list_vendor_settings(self) -> pd.DataFrame:
        with self._conn() as conn:
            return pd.read_sql_query(
                "SELECT name, multiplier, notes, phone, updated_at FROM vendors ORDER BY name",
                conn,
            )

    def standardize_all(self, *, default_multiplier: float = DEFAULT_MULTIPLIER) -> dict:
        """
        Rewrite every pricebook row through backend.standardize rules.
        Drops unrecoverable junk rows. Recomputes adjusted_price.
        """
        from backend.standardize import standardize_row, VENDOR_CANON

        with self._conn() as conn:
            cur = conn.execute(f"SELECT {', '.join(SELECT_COLS)} FROM pricebook")
            cols = [d[0] for d in cur.description]
            raw_rows = [dict(zip(cols, r)) for r in cur.fetchall()]

            kept = 0
            dropped = 0
            updated = 0
            to_delete: list[int] = []
            updates: list[tuple] = []

            for r in raw_rows:
                rid = r.get("id")
                mult = r.get("multiplier") or default_multiplier
                cleaned = standardize_row(r, default_multiplier=float(mult))
                if cleaned is None:
                    if rid is not None:
                        to_delete.append(int(rid))
                    dropped += 1
                    continue
                kept += 1
                # Detect change
                changed = False
                for k in PRICEBOOK_COLS:
                    old, new = r.get(k), cleaned.get(k)
                    if old != new and not (
                        old is None and new is None
                    ) and not (
                        isinstance(old, float)
                        and isinstance(new, float)
                        and abs(old - new) < 1e-9
                    ):
                        # string normalize compare
                        if str(old or "") != str(new or ""):
                            changed = True
                            break
                if changed and rid is not None:
                    updates.append(
                        tuple(cleaned.get(c) for c in PRICEBOOK_COLS) + (int(rid),)
                    )
                    updated += 1

            if to_delete:
                # sqlite variable limit — chunk
                for i in range(0, len(to_delete), 400):
                    chunk = to_delete[i : i + 400]
                    placeholders = ",".join("?" * len(chunk))
                    conn.execute(
                        f"DELETE FROM pricebook WHERE id IN ({placeholders})", chunk
                    )

            if updates:
                set_clause = ", ".join(f"{c}=?" for c in PRICEBOOK_COLS)
                conn.executemany(
                    f"UPDATE pricebook SET {set_clause} WHERE id=?",
                    updates,
                )

            # Normalize vendor table names
            for old_key, canon in VENDOR_CANON.items():
                # rename any vendor row matching key
                conn.execute(
                    """
                    UPDATE vendors SET name = ?
                    WHERE lower(name) = ? AND name != ?
                    """,
                    (canon, old_key, canon),
                )
            # drop vendor settings with no pricebook rows
            conn.execute(
                """
                DELETE FROM vendors WHERE name NOT IN (
                    SELECT DISTINCT vendor FROM pricebook WHERE vendor IS NOT NULL
                )
                """
            )
            conn.commit()

        return {
            "scanned": len(raw_rows),
            "kept": kept,
            "updated": updated,
            "dropped": dropped,
            "remaining": self.row_count(),
        }
