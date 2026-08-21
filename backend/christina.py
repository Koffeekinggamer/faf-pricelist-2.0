"""Christina — Holt's child in this price book.

She watches each step Judson takes (Drop, name, Load, lock), keeps a lesson log,
and tells Holt the next useful move. Judson never talks to her.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.config import APP_DIR, DB_PATH


def lessons_path(root: Optional[Path] = None) -> Path:
    if root is not None:
        return Path(root) / "christina_lessons.jsonl"
    return DB_PATH.parent / "christina_lessons.jsonl"


def _write(lesson: dict, *, path: Optional[Path] = None) -> dict:
    dest = path or lessons_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    prior = load_lessons(path=dest, limit=1)
    if prior and _same_signal(prior[-1], lesson):
        return prior[-1]
    with dest.open("a") as handle:
        handle.write(json.dumps(lesson) + "\n")
    return lesson


def _same_signal(left: dict, right: dict) -> bool:
    keys = ("step", "builder", "filename", "needs_fix", "issues", "learned")
    return all(left.get(k) == right.get(k) for k in keys)


def _item_rows(rows: list) -> list:
    return [r for r in rows or [] if str(r.get("line_kind") or "item").strip().lower() != "addon"]


def _gate_block(result: dict) -> tuple[bool, str]:
    """Read the Drop gate's verdict off the parse payload, if it ran."""
    raw = result.get("readiness")
    if raw is None:
        from backend.drop_parse_session import evaluate_readiness

        verdict = evaluate_readiness(result)
        return (not verdict.load_ready, str(verdict.block_message or ""))
    if isinstance(raw, dict):
        return (not bool(raw.get("load_ready")), str(raw.get("block_message") or ""))
    return (
        not bool(getattr(raw, "load_ready", True)),
        str(getattr(raw, "block_message", "") or ""),
    )


def observe_drop(result: dict, *, path: Optional[Path] = None) -> dict:
    """Watch a Drop parse. Addon rows without species are not a wood bug."""
    rows = result.get("rows") or []
    items = _item_rows(rows)
    empty_species = sum(1 for r in items if not str(r.get("species") or "").strip())
    error = str(result.get("error") or "").strip()
    row_count = int(result.get("row_count") or len(rows) or 0)
    item_count = len(items)
    parser = str(result.get("detected_importer") or "")
    source = str(result.get("parser_source") or "")
    builder = str(result.get("suggested_builder") or result.get("vendor") or "")
    filename = str(result.get("filename") or "")
    variants = result.get("variants") or {}
    sheets = variants.get("sheets_tried") or result.get("sheets_tried") or []

    needs_fix = False
    issues: list[str] = []
    if error:
        needs_fix = True
        issues.append(error)
    if row_count == 0 and not error:
        needs_fix = True
        issues.append("0 rows parsed")
    if item_count and empty_species == item_count:
        needs_fix = True
        issues.append("every sellable row is missing species — wood dropdown will not attach")
    elif item_count and empty_species / item_count >= 0.5:
        needs_fix = True
        issues.append("{0}/{1} sellable rows missing species".format(empty_species, item_count))
    if parser in ("", "generic") and not error:
        issues.append("no locked named parser for {0}".format(builder or filename))
        if source != "saved":
            needs_fix = True

    # A settled builder whose own reader could not read this book. Never let
    # this pass as a normal Load — the lock would degrade to a layout guess.
    locked = str(result.get("locked_parser") or "").strip().lower()
    lock_missed = bool(locked) and locked not in ("generic", "pdf") and parser != locked
    if lock_missed:
        needs_fix = True
        issues.append(
            "{0} parser {1} did not read this book (fell through to {2}) — "
            "check the workbook before Load".format(
                builder or filename, locked, parser or "nothing"
            )
        )

    # The Drop gate is the authority on Load-ready. Christina reports its
    # verdict; she never talks Holt past a block she did not re-derive.
    blocked, block_message = _gate_block(result)
    if blocked:
        needs_fix = True
        if block_message and not any(block_message in issue for issue in issues):
            issues.append(block_message)

    next_step = "Fix parse before Load" if needs_fix else "Confirm builder name, then Load"
    if lock_missed:
        next_step = "Do not Load {0} yet — {1} must read this book first".format(
            builder or filename, locked
        )
    if parser not in ("", "generic") and not needs_fix:
        next_step = "Load {0} — parser {1} is ready".format(builder or filename, parser)

    lesson = {
        "at": datetime.now(timezone.utc).isoformat(),
        "step": "drop",
        "builder": builder,
        "filename": filename,
        "parser": parser,
        "parser_source": source,
        "locked_parser": locked,
        "row_count": row_count,
        "empty_species": empty_species,
        "sheet_count": len(sheets) if isinstance(sheets, list) else 0,
        "needs_fix": needs_fix,
        "issues": issues,
        "next_step": next_step,
        "learned": (
            "Drop of {0} via {1} ({2} rows)".format(builder or filename, parser or "unknown", row_count)
        ),
    }
    return _write(lesson, path=path)


def observe_load(
    *,
    builder: str,
    filename: str = "",
    mode: str = "replace_vendor",
    inserted: int = 0,
    deleted: int = 0,
    existed: bool = False,
    hinted_builder: str = "",
    multiplier: Optional[float] = None,
    path: Optional[Path] = None,
) -> dict:
    """Watch a Load. Name overrides and add-vs-replace are the useful signal."""
    renamed = bool(hinted_builder and builder and hinted_builder != builder)
    replaced = existed or deleted > 0
    issues: list[str] = []
    needs_fix = inserted == 0
    if needs_fix:
        issues.append("Load wrote 0 rows")
    if renamed:
        issues.append("loaded as {0} (file hinted {1})".format(builder, hinted_builder))

    if needs_fix:
        next_step = "Re-parse {0} — Load wrote nothing".format(builder or filename)
    elif replaced:
        next_step = "Leave {0} unless the book changed".format(builder)
    else:
        next_step = "Drop the next selling builder. Do not re-drop {0}.".format(builder)

    learned = "Loaded {0} ({1} rows{2})".format(
        builder,
        inserted,
        ", replaced" if replaced else ", added",
    )
    if renamed:
        learned += " — Judson named it, did not take the filename"

    lesson = {
        "at": datetime.now(timezone.utc).isoformat(),
        "step": "load",
        "builder": builder,
        "filename": filename,
        "mode": mode,
        "inserted": inserted,
        "deleted": deleted,
        "existed": replaced,
        "renamed": renamed,
        "hinted_builder": hinted_builder,
        "multiplier": multiplier,
        "needs_fix": needs_fix,
        "issues": issues,
        "next_step": next_step,
        "learned": learned,
    }
    return _write(lesson, path=path)


def observe_lock(
    *,
    builder: str,
    importer: str,
    source_file: str = "",
    path: Optional[Path] = None,
) -> dict:
    """Watch a named-parser lock. Next Drop of this factory should reuse it."""
    lesson = {
        "at": datetime.now(timezone.utc).isoformat(),
        "step": "lock",
        "builder": builder,
        "filename": source_file,
        "parser": importer,
        "needs_fix": not bool(importer),
        "issues": [] if importer else ["lock wrote no importer"],
        "next_step": "Next {0} book reuses {1}".format(builder, importer or "generic"),
        "learned": "Locked {0} → {1}".format(builder, importer or "unknown"),
    }
    return _write(lesson, path=path)


def load_lessons(*, path: Optional[Path] = None, limit: int = 40) -> list[dict[str, Any]]:
    dest = path or lessons_path()
    if not dest.exists():
        return []
    lines = dest.read_text().splitlines()
    selected = lines[-limit:]
    out = []
    for line in selected:
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def unique_fixes(*, path: Optional[Path] = None) -> list[dict[str, Any]]:
    seen: set[tuple] = set()
    resolved_parser_builders: set[str] = set()
    out: list[dict[str, Any]] = []
    for lesson in reversed(load_lessons(path=path)):
        builder = str(lesson.get("builder") or lesson.get("filename") or "")
        if lesson.get("step") in ("load", "lock") and not lesson.get("needs_fix"):
            if lesson.get("step") == "load" or lesson.get("parser"):
                resolved_parser_builders.add(builder)
            continue
        if not lesson.get("needs_fix"):
            continue
        if builder in resolved_parser_builders:
            continue
        issues = [str(issue) for issue in (lesson.get("issues") or [])]
        key = (
            builder,
            tuple(issues),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(lesson)
    out.reverse()
    return out


def needs_fix(*, path: Optional[Path] = None) -> list[dict[str, Any]]:
    return unique_fixes(path=path)


def next_step(*, path: Optional[Path] = None) -> str:
    lessons = load_lessons(path=path, limit=20)
    fixes = unique_fixes(path=path)
    if fixes:
        last = fixes[-1]
        return str(last.get("next_step") or "Fix {0}".format(last.get("builder") or "the last Drop"))
    # Lock is learning for the next Drop of *this* factory. Holt's move after a
    # clean upload is still the last Load: Drop the next selling builder.
    for lesson in reversed(lessons):
        if lesson.get("step") == "lock" and not lesson.get("needs_fix"):
            continue
        step = str(lesson.get("next_step") or "").strip()
        if step:
            return step
    return "Drop the next selling builder. Confirm the name before Load."


def report_for_holt(*, path: Optional[Path] = None) -> str:
    fixes = unique_fixes(path=path)
    lessons = load_lessons(path=path, limit=8)
    lines = ["CHRISTINA", "Next: {0}".format(next_step(path=path)), "Fixes Holt should see:"]
    if not fixes:
        lines.append("None open.")
    else:
        for lesson in fixes[-8:]:
            builder = lesson.get("builder") or lesson.get("filename") or "unknown builder"
            issues = lesson.get("issues") or ["needs a look"]
            lines.append("- {0}: {1}".format(builder, "; ".join(issues)))
    distinct: list[str] = []
    for lesson in reversed(lessons):
        learned = str(lesson.get("learned") or "").strip()
        if learned and learned not in distinct:
            distinct.append(learned)
        if len(distinct) >= 3:
            break
    if distinct:
        lines.append("Recent learning:")
        for item in reversed(distinct):
            lines.append("- {0}".format(item))
    return "\n".join(lines)


CHRISTINA_HOME = APP_DIR
