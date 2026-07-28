"""Premium wood-tier suffix → option_key."""

from backend.standardize import standardize_row


def test_premium_suffix_moves_to_option_key():
    cleaned = standardize_row(
        {
            "vendor": "Arista Wood",
            "collection": "Servers/Hutches",
            "part_number": "214-36185975",
            "description": "Richmond Server",
            "species": "Barnwood / Brown Maple / Premium",
            "finish_state": "finished",
            "base_price": 1643.35,
            "multiplier": 2.7,
            "source_file": "arista.xlsx",
        }
    )
    assert cleaned is not None
    assert cleaned["species"] == "Barnwood / Brown Maple"
    assert cleaned["option_key"] == "Premium"
    assert cleaned["adjusted_price"] == 4438.0


def test_premium_idempotent():
    once = standardize_row(
        {
            "vendor": "Arista Wood",
            "part_number": "X",
            "description": "X",
            "species": "Red Oak / Wormy Maple / Premium",
            "finish_state": "finished",
            "base_price": 100,
            "multiplier": 2.7,
        }
    )
    twice = standardize_row(once)
    assert twice["species"] == "Red Oak / Wormy Maple"
    assert twice["option_key"] == "Premium"
