"""add_builder scaffold: registry + profile + fixture hook, not a real factory.

Kill test: one command plans slug, vendor, CatalogSpec/ReaderEntry, profile,
synthetic Options fixture, and a SETTLED placeholder that is not in SETTLED.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from backend.add_builder import (
    STUB_OPTION_KEYS,
    STUB_PARSER_ID,
    STUB_SETTLED_PLACEHOLDER,
    STUB_VENDOR,
    AddBuilderError,
    plan_builder,
    write_scaffold,
)
from backend.builder_identity import (
    WATCHED_SHORT_TOKENS,
    is_short_token,
    matching_readers,
    token_collisions,
)
from backend.builder_parsers import (
    GENERIC_PARSER_IDS,
    identify_reader,
    preferred_parser_for,
    save_named_parser,
)
from backend.builder_profiles import load_builder_profile, vendor_slug
from backend.builder_reader_registry import DEFAULT_READER_REGISTRY
from backend.catalog_readers import CATALOG_SPECS
from tests.fixture_corpus import STUB_FIXTURE
from tests.test_builder_parser_contract import SETTLED
from wide_import import import_workbook, list_excel_sheets


def _items(df):
    if df is None or getattr(df, "empty", True):
        return df
    if "line_kind" not in df.columns:
        return df
    kind = df["line_kind"].fillna("item").astype(str).str.lower()
    return df[kind != "addon"]


def _addons(df):
    if df is None or getattr(df, "empty", True) or "option_key" not in df.columns:
        return df.iloc[0:0] if df is not None else df
    kind = df["line_kind"].fillna("item").astype(str).str.lower()
    return df[kind == "addon"]


def _option_keys(df) -> set[str]:
    if df is None or getattr(df, "empty", True) or "option_key" not in df.columns:
        return set()
    keys = df["option_key"].dropna().astype(str)
    return {key.strip() for key in keys if key.strip()}


def test_plan_builder_names_slug_parser_and_catalog_spec():
    plan = plan_builder(STUB_VENDOR)
    assert plan.vendor == STUB_VENDOR
    assert plan.slug == "stub-workshop"
    assert plan.parser_id == STUB_PARSER_ID
    assert plan.kind == "catalog"
    assert plan.catalog_spec.parser_id == STUB_PARSER_ID
    assert plan.catalog_spec.vendor == STUB_VENDOR
    assert plan.parser_id not in GENERIC_PARSER_IDS
    assert vendor_slug(plan.vendor) == plan.slug
    assert not any(is_short_token(token) for token in plan.catalog_spec.tokens())
    assert not any(token in WATCHED_SHORT_TOKENS for token in plan.extra_tokens)


def test_plan_builder_reuses_existing_named_parser():
    plan = plan_builder("Patio Kraft", kind="shape")
    assert plan.vendor == "Patio Kraft"
    assert plan.parser_id == "patio_kraft"
    assert plan.kind == "shape"
    assert plan.reader_entry is not None
    assert plan.reader_entry.parser_id == "patio_kraft"
    assert plan.reader_entry.vendor == "Patio Kraft"


def test_plan_builder_refuses_watched_short_tokens():
    with pytest.raises(AddBuilderError, match="ac"):
        plan_builder("Acme Chairs", extra_tokens=("ac",))


def test_plan_builder_refuses_generic_importer():
    with pytest.raises(AddBuilderError, match="generic"):
        plan_builder("Mystery Factory", parser_id="generic")


def test_plan_builder_refuses_to_rekey_an_existing_lock():
    with pytest.raises(AddBuilderError, match="fn_chair"):
        plan_builder("FN Chair", parser_id="mystery_factory")


def test_plan_builder_refuses_download_stem_vendor():
    with pytest.raises(AddBuilderError, match="Download"):
        plan_builder("Download_2027_Pricelist_111")


def test_plan_builder_refuses_token_claimed_by_another_vendor():
    with pytest.raises(AddBuilderError, match="brookside"):
        plan_builder("New Side Chairs", extra_tokens=("brookside",))


def test_scaffold_profile_locks_specific_importer():
    plan = plan_builder(STUB_VENDOR)
    locked = str((plan.profile.get("parser") or {}).get("importer") or "")
    assert locked == STUB_PARSER_ID
    assert locked not in GENERIC_PARSER_IDS
    assert plan.profile.get("stub") is True
    hints = (plan.profile.get("parser") or {}).get("filename_hints") or []
    assert "stub workshop" in hints
    assert not any(is_short_token(str(hint)) for hint in hints)
    assert not any(str(hint) in WATCHED_SHORT_TOKENS for hint in hints)


def test_settled_placeholder_is_not_in_settled():
    assert STUB_SETTLED_PLACEHOLDER[0] == STUB_VENDOR
    assert STUB_SETTLED_PLACEHOLDER[1] == STUB_PARSER_ID
    assert STUB_SETTLED_PLACEHOLDER[1] not in GENERIC_PARSER_IDS
    settled_vendors = {row[0] for row in SETTLED}
    assert STUB_VENDOR not in settled_vendors
    assert plan_builder(STUB_VENDOR).settled_placeholder == STUB_SETTLED_PLACEHOLDER


def test_stub_workshop_is_registered_as_a_catalog_reader():
    spec = next(s for s in CATALOG_SPECS if s.parser_id == STUB_PARSER_ID)
    assert spec.vendor == STUB_VENDOR
    entry = DEFAULT_READER_REGISTRY.get(STUB_PARSER_ID)
    assert entry is not None
    assert entry.vendor == STUB_VENDOR
    assert entry.specific is True
    profile = load_builder_profile(STUB_VENDOR)
    assert str((profile.get("parser") or {}).get("importer") or "") == STUB_PARSER_ID
    assert preferred_parser_for(STUB_VENDOR) == STUB_PARSER_ID


def test_stub_workshop_next_year_filename_has_one_reader():
    next_file = STUB_SETTLED_PLACEHOLDER[2]
    sheets = list(STUB_SETTLED_PLACEHOLDER[3])
    hits = matching_readers(next_file, sheet_names=sheets)
    ids = {hit.parser_id for hit in hits}
    assert ids == {STUB_PARSER_ID}
    vendor, parser_id, source = identify_reader(next_file, sheet_names=sheets)
    assert vendor == STUB_VENDOR
    assert parser_id == STUB_PARSER_ID
    assert source == "saved"


def test_stub_tokens_do_not_collide_with_watched_or_other_vendors():
    plan = plan_builder(STUB_VENDOR)
    tokens = (*plan.catalog_spec.tokens(), *plan.extra_tokens, plan.parser_id)
    for token in tokens:
        assert token not in WATCHED_SHORT_TOKENS
    collisions = token_collisions()
    for token, group in collisions.items():
        vendors = {claim.vendor for claim in group}
        assert STUB_VENDOR not in vendors, f"{token}: {vendors}"


def test_write_scaffold_writes_profile_fixture_and_hook(tmp_path: Path):
    plan = plan_builder("Clone Example Wood")
    written = write_scaffold(plan, repo_root=tmp_path)
    profile = json.loads(written.profile_path.read_text(encoding="utf-8"))
    assert profile["vendor"] == "Clone Example Wood"
    assert profile["parser"]["importer"] == "clone_example_wood"
    assert profile["parser"]["importer"] not in GENERIC_PARSER_IDS
    assert written.fixture_path.is_file()
    assert written.fixture_path.read_bytes()[:2] == b"PK"
    assert written.hook_path.is_file()
    hook = written.hook_path.read_text(encoding="utf-8")
    assert "Clone Example Wood" in hook
    assert "clone_example_wood" in hook
    assert "SETTLED" in hook
    assert "import_workbook" in hook
    assert "empty Options is a capture miss" in hook
    assert "force_layout_guess=True" in hook
    splice = written.splice_path.read_text(encoding="utf-8")
    assert "CatalogSpec(" in splice
    assert "clone_example_wood" in splice
    assert "SETTLED" in splice
    hook_run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(written.hook_path)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert hook_run.returncode == 0, hook_run.stdout + hook_run.stderr


def test_write_scaffold_does_not_overwrite_existing_profile(tmp_path: Path):
    dest = tmp_path / "config" / "builder_profiles" / "clone-example-wood.json"
    dest.parent.mkdir(parents=True)
    dest.write_text('{"vendor": "Clone Example Wood", "keep": true}\n', encoding="utf-8")
    plan = plan_builder("Clone Example Wood")
    with pytest.raises(AddBuilderError, match="exists"):
        write_scaffold(plan, repo_root=tmp_path)


def test_write_scaffold_refuses_overwrite_of_locked_selling_profile(tmp_path: Path):
    dest = tmp_path / "config" / "builder_profiles" / "fn-chair.json"
    dest.parent.mkdir(parents=True)
    dest.write_text(
        json.dumps(
            {
                "vendor": "FN Chair",
                "option_groups": [{"name": "Finish category", "selection": "single"}],
                "parser": {"importer": "fn_chair", "locked": True},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    plan = plan_builder("FN Chair", kind="shape")
    with pytest.raises(AddBuilderError, match="locked profile"):
        write_scaffold(plan, repo_root=tmp_path, overwrite=True)


def test_fallthrough_cannot_downgrade_stub_lock(tmp_path: Path):
    save_named_parser(
        STUB_VENDOR,
        importer=STUB_PARSER_ID,
        source_file=STUB_SETTLED_PLACEHOLDER[2],
        root=tmp_path,
    )
    save_named_parser(
        STUB_VENDOR,
        importer="generic",
        source_file="mystery.xlsx",
        layouts=["long_flat"],
        root=tmp_path,
    )
    assert preferred_parser_for(STUB_VENDOR, root=tmp_path) == STUB_PARSER_ID


def test_stub_fixture_proves_options_from_the_book():
    vendor, importer, filename, path, option_keys = STUB_FIXTURE
    assert vendor == STUB_VENDOR
    assert importer == STUB_PARSER_ID
    assert path.is_file()
    data = path.read_bytes()
    sheets = list_excel_sheets(data)
    assert "Options" in sheets
    assert "Cover" in sheets
    result = import_workbook(
        data, filename=filename, vendor=vendor, preferred_parser=importer
    )
    assert result.detected_importer == importer
    items = _items(result.long_df)
    assert items is not None and not items.empty
    addons = _addons(result.long_df)
    assert addons is not None and not addons.empty, (
        "stub fixture parsed items but no addon Options — capture miss"
    )
    keys = _option_keys(result.long_df)
    missing = [key for key in option_keys if key not in keys]
    assert not missing, f"stub fixture missed Options {missing}; got {sorted(keys)}"
    assert tuple(option_keys) == STUB_OPTION_KEYS


def test_cli_dry_run_prints_the_scaffold():
    script = Path(__file__).resolve().parents[1] / "scripts" / "add_builder.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--vendor", STUB_VENDOR],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert STUB_VENDOR in out
    assert STUB_PARSER_ID in out
    assert "CatalogSpec" in out
    assert "SETTLED" in out
