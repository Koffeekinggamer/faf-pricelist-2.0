"""
Price Book backend — data layer and services used by the Streamlit UI
(and any future CLI / API).

    from backend import PriceBookService
    svc = PriceBookService()
    svc.init()
    results = svc.search("oak nightstand", vendor="Schrock's")
"""

from backend.service import PriceBookService

__all__ = ["PriceBookService"]
