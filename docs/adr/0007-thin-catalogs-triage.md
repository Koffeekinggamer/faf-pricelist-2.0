# Thin catalogs: threshold and triage process

A **thin catalog** is a builder with fewer than **150** sellable rows in the master price book (after standardize). In-scope starters: Amish Aspen, Hillside Chair, Maple Lane, plus any other builder the scan finds under that threshold. Green Meadows / Simple Living stay on `IGNORE_BUILDERS` and are out of scope for this effort.

For each thin builder, **Judson only** chooses **keep** (accept thin), **replace** (Judson Drop → `replace_vendor` with a fuller file), or **ignore** (explicit add to `IGNORE_BUILDERS`). Agents never auto-ignore or auto-delete. The thin list surfaces via **Admin + CLI** (`PriceBookService.list_thin_catalogs`, `python -m backend.cli thin-catalogs`, `./scripts/ready_catalog.sh`); no floor Search badge in this push. Process per builder: **triage → grill with Judson**. Scan requires a live DB (Fly/Mac pull at `/FAF-pricelist-2.0`) or Dropped files — empty cloud DBs cannot triage.

Out of scope for this effort: leftover phones, FN Chair PL Print re-drop, Fly DB freshness, Search/pin polish, agent-skills docs.

**Status:** accepted
