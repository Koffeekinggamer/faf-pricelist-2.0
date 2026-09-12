"""County selectbox widget identity must rotate on Clear."""

from backend.quote_cart_widgets import (
    QUOTE_CART_REFRESH_KEY,
    bump_quote_county_widget,
    clear_quote_cart_line_widgets,
    mark_quote_cart_widgets_dirty,
    quote_county_widget_key,
)


def test_county_widget_key_includes_nonce():
    session = {"cart_county_nonce_5": 2}
    assert quote_county_widget_key(5, session) == "cart_county_5_2"


def test_bump_county_widget_invalidates_prior_selection():
    session = {
        "cart_county_nonce_5": 0,
        "cart_county_5_0": "Spartanburg County, SC — 7%",
        "cart_name_5": "Quote",
    }
    new_key = bump_quote_county_widget(5, session)
    assert new_key == "cart_county_5_1"
    assert session["cart_county_nonce_5"] == 1
    assert "cart_county_5_0" not in session
    assert new_key not in session
    # Unrelated cart keys stay put.
    assert session["cart_name_5"] == "Quote"


def test_after_merge_add_stale_cart_qty_widget_is_cleared_before_sidebar_sync():
    """Regression: second Add merges DB qty to 2, but Streamlit still holds 1.

    Without clearing cart_qty_*, sidebar write-back overwrites the merge.
    """
    session = {
        "cart_qty_10_12": 1,  # stale widget after merge wrote qty 2 to DB
        "cart_notes_10_12": "",
        "cart_name_10": "Quote",
        "cart_county_nonce_10": 0,
        "other_key": True,
    }
    mark_quote_cart_widgets_dirty(session)
    assert session[QUOTE_CART_REFRESH_KEY] is True

    # Sidebar consumes the flag then clears keys (same order as production).
    assert session.pop(QUOTE_CART_REFRESH_KEY, False) is True
    clear_quote_cart_line_widgets(session, 10)

    assert "cart_qty_10_12" not in session
    assert "cart_notes_10_12" not in session
    assert "cart_name_10" not in session
    assert session["cart_county_nonce_10"] == 0
    assert session["other_key"] is True
