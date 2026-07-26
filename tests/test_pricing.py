"""Even-dollar retail rounding."""

from backend.pricing import retail_from_wholesale, round_up_even_dollar


def test_round_up_even_dollar_examples():
    assert round_up_even_dollar(337.50) == 338.0
    assert round_up_even_dollar(3010.50) == 3012.0
    assert round_up_even_dollar(100.00) == 100.0
    assert round_up_even_dollar(101.00) == 102.0
    assert round_up_even_dollar(0) == 0.0
    assert round_up_even_dollar(None) is None


def test_retail_from_wholesale():
    # 100 * 2.7 = 270 → even stays
    assert retail_from_wholesale(100, 2.7) == 270.0
    # 111 * 2.7 = 299.7 → 300
    assert retail_from_wholesale(111, 2.7) == 300.0
    # Genuine Oak-ish 1.7
    assert retail_from_wholesale(200, 1.7) == 340.0
