"""Collapse size-pair Options into one checkbox plus a size prompt."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

_SIZE_PROMPT = "What size bed is it for?"
_SIZE_PLACEHOLDER = "Select size"

PLATFORM_DISPLAY = "Platform for all beds"
DRAWER_UNIT_DISPLAY = "drawer unit on all bed sizes"


@dataclass(frozen=True)
class SizePromptFamily:
    display: str
    sizes: tuple[tuple[str, re.Pattern[str]], ...]
    always_prompt: bool = False

    def members(self, options: list[str]) -> dict[str, str]:
        found: dict[str, str] = {}
        for label in options:
            raw = str(label or "").strip()
            for size, pattern in self.sizes:
                if size not in found and pattern.search(raw):
                    found[size] = raw
                    break
        return found


PLATFORM_FAMILY = SizePromptFamily(
    display=PLATFORM_DISPLAY,
    sizes=(
        ("Queen", re.compile(r"(?i)^queen\s+platform\b")),
        ("King", re.compile(r"(?i)^king\s+platform\b")),
    ),
)
DRAWER_UNIT_FAMILY = SizePromptFamily(
    display=DRAWER_UNIT_DISPLAY,
    sizes=(
        ("Queen", re.compile(r"(?i)^queen\s+drawer\s+unit\b")),
        ("King", re.compile(r"(?i)^king\s+drawer\s+unit\b")),
    ),
    always_prompt=True,
)
SIZE_PROMPT_FAMILIES: tuple[SizePromptFamily, ...] = (
    PLATFORM_FAMILY,
    DRAWER_UNIT_FAMILY,
)


def _family_for_display(label: str) -> Optional[SizePromptFamily]:
    raw = str(label or "").strip()
    for family in SIZE_PROMPT_FAMILIES:
        if raw == family.display:
            return family
    return None


def platform_size_members(options: list[str]) -> dict[str, str]:
    return PLATFORM_FAMILY.members(options)


def collapse_size_prompt_options(options: list[str]) -> list[str]:
    """Replace size-pair checkboxes with one display Option per family."""
    out = list(options)
    for family in SIZE_PROMPT_FAMILIES:
        out = _collapse_family(out, family)
    return out


def collapse_platform_options(options: list[str]) -> list[str]:
    return _collapse_family(list(options), PLATFORM_FAMILY)


def _collapse_family(options: list[str], family: SizePromptFamily) -> list[str]:
    members = family.members(options)
    hide = set(members.values())
    if len(members) < 2:
        return list(options)
    out: list[str] = []
    inserted = False
    for label in options:
        if label == family.display:
            if not inserted:
                out.append(family.display)
                inserted = True
            continue
        if label in hide:
            if not inserted:
                out.append(family.display)
                inserted = True
            continue
        out.append(label)
    return out


def resolve_size_choice(
    options: list[str],
    display: str,
    *,
    selected: bool,
    size: str,
) -> Optional[str]:
    """Catalog option_key for the chosen bed size, or None until a size is picked."""
    if not selected:
        return None
    pick = str(size or "").strip()
    if pick in {"", _SIZE_PLACEHOLDER}:
        return None
    family = _family_for_display(display)
    if family is None:
        return None
    members = family.members(options)
    if pick in members:
        return members[pick]
    if family.always_prompt and pick in {size_name for size_name, _ in family.sizes}:
        if family.display in options:
            return family.display
    return None


def resolve_platform_choice(
    options: list[str],
    *,
    selected: bool,
    size: str,
) -> Optional[str]:
    return resolve_size_choice(options, PLATFORM_DISPLAY, selected=selected, size=size)


def size_prompt_choices(options: list[str], display: str) -> list[str]:
    family = _family_for_display(display)
    if family is None:
        return []
    members = family.members(options)
    if len(members) >= 2:
        return [
            _SIZE_PLACEHOLDER,
            *(size for size, _ in family.sizes if size in members),
        ]
    if family.always_prompt and family.display in options:
        return [_SIZE_PLACEHOLDER, *(size for size, _ in family.sizes)]
    return []


def platform_size_choices(options: list[str]) -> list[str]:
    return size_prompt_choices(options, PLATFORM_DISPLAY)


def is_size_prompt_display(label: str) -> bool:
    return _family_for_display(label) is not None


def is_platform_display(label: str) -> bool:
    return str(label or "").strip() == PLATFORM_DISPLAY


def platform_prompt_label() -> str:
    return _SIZE_PROMPT


def size_by_resolved_label(options: list[str]) -> dict[str, str]:
    """Map catalog option_key → size name for selected-summary wording."""
    out: dict[str, str] = {}
    for family in SIZE_PROMPT_FAMILIES:
        for size, label in family.members(options).items():
            out[label] = size
    return out
