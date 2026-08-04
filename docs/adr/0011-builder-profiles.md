# Builder Profiles — per-builder learned rules, not hardcoded

Builders differ in how their price lists express options, categories, and parse quirks. Rather than hardcode one builder's conventions in the repository/search helper, each builder gets a **Builder Profile**: a persistent record of what we've learned about that builder, consumed by two places — the **Drop files** import (so re-importing/updating a builder is seamless and consistent) and the **search/upcharge helper** (so option upcharges use that builder's real vocabulary).

A profile holds the builder-specific bits that vary: option **charge shapes** (flat `$`, `%` via `addon_pct`, or per-category), **category synonyms**, **item→category overrides** (to resolve the `approx` matches from ADR-0008 follow-up), and **parse hints** (which columns are options/addons, markup/multiplier rules, finish handling). Values are auto-learned on import where derivable and hand-tunable for the rest.

**Storage:** versioned JSON in the repo at `config/builder_profiles/<vendor>.json`, keyed by the canonical vendor name (`standardize.resolve_builder_vendor`). Chosen over a DB table because it is flexible, diffable/reviewable in git, survives DB resets, and onboarding a builder never requires a code change. The private catalog itself stays in the gitignored DB / on Fly (ADR-0005) — only the *rules* live in the repo.

J&M Woodworking is the first profile: today's hardcoded J&M option/category vocabulary migrates into it unchanged, so search-upcharge behavior does not regress while the system generalizes.

**Status:** accepted
