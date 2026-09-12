"""County selectbox widget identity must rotate on Clear."""

from backend.quote_cart_widgets import bump_quote_county_widget, quote_county_widget_key


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
