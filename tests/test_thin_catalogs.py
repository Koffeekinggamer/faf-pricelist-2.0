"""Thin catalog listing (ADR-0007)."""

from backend.config import THIN_CATALOG_MAX_ROWS
from backend.service import PriceBookService


def _rows(vendor: str, n: int, collection: str = "Seating") -> list[dict]:
    return [
        {
            "vendor": vendor,
            "collection": collection,
            "part_number": f"{vendor[:4]}-{i}",
            "description": f"{vendor} {i}",
            "species": "Oak",
            "finish_state": "finished",
            "base_price": 50.0,
            "price_basis": "wholesale",
            "multiplier": 2.7,
            "adjusted_price": 135.0,
        }
        for i in range(n)
    ]


def _seed(svc: PriceBookService) -> None:
    svc.init()
    # add_rows canonicalizes vendor from rows[0] — one builder per call
    svc.add_rows(
        _rows("Fat Builder", THIN_CATALOG_MAX_ROWS, collection="Casegoods"),
        mode="append",
    )
    for vendor, n in (("Amish Aspen", 16), ("Hillside Chair", 5), ("Maple Lane", 6)):
        svc.add_rows(_rows(vendor, n), mode="append")


def test_list_thin_catalogs_threshold(tmp_path):
    db = tmp_path / "t.db"
    svc = PriceBookService(db_path=db)
    _seed(svc)
    thin = svc.list_thin_catalogs()
    names = set(thin["vendor"].tolist())
    assert names == {"Amish Aspen", "Hillside Chair", "Maple Lane"}
    assert "Fat Builder" not in names
    assert thin.iloc[0]["rows"] <= thin.iloc[-1]["rows"]
    assert all(thin["rows"] < THIN_CATALOG_MAX_ROWS)


def test_list_thin_catalogs_custom_max(tmp_path):
    db = tmp_path / "t.db"
    svc = PriceBookService(db_path=db)
    _seed(svc)
    thin = svc.list_thin_catalogs(max_rows=6)
    assert set(thin["vendor"].tolist()) == {"Hillside Chair"}
