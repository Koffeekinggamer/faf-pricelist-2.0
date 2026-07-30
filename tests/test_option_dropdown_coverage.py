"""Feedback loop: every builder with catalog rows has Option dropdown choices.

User symptom: expected all builders to have some items in the Options dropdown.
"""

import pytest

from backend.db import init_db
from backend.repository import PriceBookRepository


def _row(vendor: str, *, species: str, option_key: str | None = None, part: str = "P1"):
    return {
        "vendor": vendor,
        "collection": "Casegoods",
        "part_number": part,
        "description": part,
        "option_key": option_key,
        "species": species,
        "finish_state": "finished",
        "base_price": 100,
        "multiplier": 2.7,
        "adjusted_price": 270,
        "price_basis": "wholesale",
        "source_file": "t.xlsx",
    }


@pytest.mark.xfail(
    reason=(
        "Product gap: Option should mean addon/upcharge charges, but import "
        "skips adder lines and list_option_keys only surfaces option_key / "
        "option-like species — wood-only builders correctly return []. "
        "Remove xfail when addon import + Option dropdown are implemented."
    ),
    strict=True,
)
def test_wood_only_builder_has_option_dropdown_choices(tmp_path):
    """Desired: builders with only woods still expose Option when addons exist.

    Today: empty Option for wood-only catalogs (no option_key / option-species).
    """
    db = tmp_path / "t.db"
    init_db(db)
    repo = PriceBookRepository(db)
    repo.insert_rows(
        [
            _row("Wood Only Co", species="Oak"),
            _row("Wood Only Co", species="Cherry", part="P2"),
        ]
    )
    woods = repo.list_species(vendor="Wood Only Co")
    opts = repo.list_option_keys("Wood Only Co")
    assert woods, "sanity: Wood dropdown should list woods"
    assert opts, (
        "expected Option dropdown to list something for wood-only builders; "
        f"got woods={woods!r} options={opts!r}"
    )


def test_fn_chair_still_lists_cats(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    repo = PriceBookRepository(db)
    repo.insert_rows(
        [
            _row("FN Chair", species="Oak", option_key="Cat. 1"),
            _row("FN Chair", species="Oak", option_key="Cat. 2", part="P2"),
        ]
    )
    assert repo.list_option_keys("FN Chair") == ["Cat. 1", "Cat. 2"]
