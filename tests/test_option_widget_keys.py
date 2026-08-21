"""Streamlit Option checkboxes need a unique key per exact label."""

from backend.option_labels import option_widget_key


def test_trailing_period_does_not_reuse_streamlit_key():
    vendor = "Troyer Design Company"
    a = option_widget_key(vendor, 'For 36"and 42" H')
    b = option_widget_key(vendor, 'For 36"and 42" H.')
    assert a != b


def test_hyphen_vs_space_does_not_reuse_streamlit_key():
    vendor = "Red Barn Woodworking"
    assert option_widget_key(vendor, "2 Tone") != option_widget_key(vendor, "2-Tone")


def test_same_label_is_stable():
    vendor = "Troyer Design Company"
    label = '36" height'
    assert option_widget_key(vendor, label) == option_widget_key(vendor, label)
