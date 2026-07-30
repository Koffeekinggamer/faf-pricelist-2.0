# Options are addon charges in the master book

Floor **Option** means builder **addon charges** (flat $ or +% over base for woods / specialty changes), not merely finish Cat.N labels. Addons are stored as `pricebook` rows with `line_kind = 'addon'` (optional `addon_pct` for percent adders; `base_price` for flat $). Sellable SKU×wood×finish rows stay `line_kind = 'item'` (default for legacy rows).

Search **results** exclude addon rows so a $23 fabric adder never appears as chair retail. The per-builder Option dropdown lists addon labels (and keeps existing `option_key` finish codes until a separate Finish-tier control exists). Import paths that previously skipped adder columns should write `line_kind=addon` rows instead of dropping them.

**Status:** accepted
