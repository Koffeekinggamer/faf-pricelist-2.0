from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from backend.drop_parse_session import evaluate_readiness

from backend.christina import (
    needs_fix,
    next_step,
    observe_drop,
    observe_load,
    observe_lock,
    report_for_holt,
)


def test_christina_never_recommends_load_when_the_gate_blocks(tmp_path: Path) -> None:
    """Christina reads the Drop gate's verdict; she does not re-derive it."""
    log = tmp_path / "christina_lessons.jsonl"
    payload = {
        "filename": "AC_2026_Pricelist_0226.xlsx",
        "suggested_builder": "Artisan Chairs",
        "detected_importer": "artisan_chairs",
        "parser_source": "saved",
        "locked_parser": "artisan_chairs",
        "priced_option_count": 30,
        "row_count": 1,
        "rows": [
            {
                "vendor": "Artisan Chairs",
                "part_number": "C1",
                "species": "Oak",
                "base_price": 100.0,
                "line_kind": "item",
            }
        ],
    }
    payload["readiness"] = asdict(evaluate_readiness(payload))

    lesson = observe_drop(payload, path=log)

    assert lesson["needs_fix"] is True
    assert not lesson["next_step"].startswith("Load ")
    assert any("option" in issue.lower() for issue in lesson["issues"])


def test_observe_drop_flags_missing_species_on_sellable_rows(tmp_path: Path) -> None:
    log = tmp_path / "christina_lessons.jsonl"
    lesson = observe_drop(
        {
            "filename": "AO_Pricelist.xlsx",
            "suggested_builder": "Ashery Oak",
            "detected_importer": "generic",
            "parser_source": "guessed",
            "row_count": 2,
            "rows": [
                {"species": "", "line_kind": "item"},
                {"species": "", "line_kind": "item"},
            ],
        },
        path=log,
    )
    assert lesson["needs_fix"] is True
    assert any("species" in i for i in lesson["issues"])
    assert "Next:" in report_for_holt(path=log)
    assert needs_fix(path=log)


def test_addon_rows_without_species_are_not_a_wood_bug(tmp_path: Path) -> None:
    log = tmp_path / "christina_lessons.jsonl"
    lesson = observe_drop(
        {
            "filename": "AO_Pricelist.xlsx",
            "suggested_builder": "Ashery Oak",
            "detected_importer": "ashery_oak",
            "parser_source": "saved",
            "row_count": 2,
            "rows": [
                {"species": "Oak", "line_kind": "item"},
                {"species": "", "line_kind": "addon"},
            ],
        },
        path=log,
    )
    assert lesson["needs_fix"] is False
    assert needs_fix(path=log) == []


def test_named_parser_success_is_learning_not_a_fix(tmp_path: Path) -> None:
    log = tmp_path / "christina_lessons.jsonl"
    lesson = observe_drop(
        {
            "filename": "AO_Pricelist.xlsx",
            "suggested_builder": "Ashery Oak",
            "detected_importer": "ashery_oak",
            "parser_source": "saved",
            "row_count": 1,
            "rows": [{"species": "Oak"}],
        },
        path=log,
    )
    assert lesson["needs_fix"] is False
    assert "Load Ashery Oak" in lesson["next_step"]


def test_repeat_drop_does_not_spam_the_log(tmp_path: Path) -> None:
    log = tmp_path / "christina_lessons.jsonl"
    payload = {
        "filename": "AO_Pricelist.xlsx",
        "suggested_builder": "Ashery Oak",
        "detected_importer": "ashery_oak",
        "parser_source": "saved",
        "row_count": 1,
        "rows": [{"species": "Oak"}],
    }
    observe_drop(payload, path=log)
    observe_drop(payload, path=log)
    assert log.read_text().count("\n") == 1


def test_load_and_lock_drive_the_next_step(tmp_path: Path) -> None:
    log = tmp_path / "christina_lessons.jsonl"
    load = observe_load(
        builder="FN Chair",
        filename="FN_LevelOne.xlsx",
        inserted=40,
        existed=False,
        hinted_builder="FN Chair",
        path=log,
    )
    assert load["needs_fix"] is False
    assert "next selling builder" in load["next_step"]
    observe_lock(builder="FN Chair", importer="fn_chair", source_file="FN_LevelOne.xlsx", path=log)
    text = report_for_holt(path=log)
    assert "Next:" in text
    assert "FN Chair" in text
    assert "next selling builder" in next_step(path=log)
    assert "Locked FN Chair" in text


def test_successful_named_lock_resolves_first_drop_no_parser_fix(tmp_path: Path) -> None:
    log = tmp_path / "christina_lessons.jsonl"
    observe_drop(
        {
            "filename": "AC_2026_Pricelist.xlsx",
            "suggested_builder": "Artisan Chairs",
            "detected_importer": "generic",
            "parser_source": "guessed",
            "row_count": 1,
            "rows": [{"species": "Oak", "line_kind": "item"}],
        },
        path=log,
    )
    assert needs_fix(path=log)

    observe_load(
        builder="Artisan Chairs",
        filename="AC_2026_Pricelist.xlsx",
        inserted=40,
        path=log,
    )
    observe_lock(
        builder="Artisan Chairs",
        importer="artisan_chairs",
        source_file="AC_2026_Pricelist.xlsx",
        path=log,
    )

    assert needs_fix(path=log) == []
    assert "next selling builder" in next_step(path=log)


def test_successful_reload_clears_a_prior_species_block(tmp_path: Path) -> None:
    log = tmp_path / "christina_lessons.jsonl"
    observe_drop(
        {
            "filename": "Living Rooms Price List.xlsx",
            "suggested_builder": "Criswell Bedroom",
            "detected_importer": "generic",
            "parser_source": "guessed",
            "row_count": 2,
            "rows": [
                {"species": "", "line_kind": "item"},
                {"species": "", "line_kind": "item"},
            ],
        },
        path=log,
    )
    assert needs_fix(path=log)

    observe_drop(
        {
            "filename": "Living Rooms Price List.xlsx",
            "suggested_builder": "Criswell Bedroom",
            "detected_importer": "criswell",
            "parser_source": "saved",
            "row_count": 2,
            "rows": [
                {"species": "Oak", "line_kind": "item"},
                {"species": "Cherry", "line_kind": "item"},
            ],
        },
        path=log,
    )
    observe_load(
        builder="Criswell Bedroom",
        filename="Living Rooms Price List.xlsx",
        inserted=80,
        existed=True,
        deleted=10,
        path=log,
    )
    observe_lock(
        builder="Criswell Bedroom",
        importer="criswell",
        source_file="Living Rooms Price List.xlsx",
        path=log,
    )

    assert needs_fix(path=log) == []
    assert "Leave Criswell Bedroom" in next_step(path=log)
