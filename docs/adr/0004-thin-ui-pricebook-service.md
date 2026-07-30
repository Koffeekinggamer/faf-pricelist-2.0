# Thin UI; logic in PriceBookService

Streamlit (`pricebook_app.py`) is presentation only. Search, import, vendor mults, Viztech orchestration, and standardization go through `backend.PriceBookService` (and siblings under `backend/`). New features add service methods first, then thin widgets.

**Status:** accepted
