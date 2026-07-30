"""Disk-backed Drop parse cache — keep rows off Streamlit session_state."""

from backend.drop_cache import clear, load_parsed, save_parsed, session_meta, sig_key


def test_save_load_roundtrip(tmp_path):
    sig = (("a.xlsx", 100), False)
    parsed = [
        {
            "filename": "a.xlsx",
            "vendor": "FN Chair",
            "rows": [{"part_number": "Abe", "base_price": 1}],
            "row_count": 1,
        }
    ]
    path = save_parsed(sig, parsed, root=tmp_path)
    assert path.is_file()
    loaded = load_parsed(sig, root=tmp_path)
    assert loaded == parsed
    meta = session_meta(path, parsed)
    assert meta["file_count"] == 1
    assert meta["total_rows"] == 1
    assert meta["path"] == str(path)


def test_sig_key_stable():
    sig = (("x.xlsx", 10), True)
    assert sig_key(sig) == sig_key(sig)
    assert sig_key(sig) != sig_key((("y.xlsx", 10), True))


def test_clear(tmp_path):
    sig = (("b.xlsx", 1), False)
    path = save_parsed(sig, [{"filename": "b.xlsx", "rows": [], "row_count": 0}], root=tmp_path)
    assert path.is_file()
    clear(sig, root=tmp_path)
    assert not path.is_file()
    assert load_parsed(sig, root=tmp_path) is None
