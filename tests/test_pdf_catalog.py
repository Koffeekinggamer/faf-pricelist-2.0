"""PDF catalog generation smoke test."""

import pandas as pd

from backend.pdf_catalog import catalog_pdf_bytes


def test_catalog_pdf_bytes_nonempty():
    df = pd.DataFrame(
        [
            {
                "part_number": "T-1",
                "description": "Table",
                "species": "Oak",
                "finish_state": "finished",
                "adjusted_price": 270,
            }
        ]
    )
    pdf = catalog_pdf_bytes(df, title="Test Builder Price List")
    assert isinstance(pdf, (bytes, bytearray))
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 200
