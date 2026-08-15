# Builder Profiles — per-builder learned rules, not hardcoded

Builders differ in how their price lists express options, categories, and parse quirks. Rather than hardcode one builder's conventions in the repository/search helper, each builder gets a **Builder Profile**: a persistent record of what we've learned about that builder, consumed by two places — the **Drop files** import (so re-importing/updating a builder is seamless and consistent) and the **search/upcharge helper** (so option upcharges use that builder's real vocabulary).

A profile holds the builder-specific bits that vary: option **charge shapes** (flat `$`, `%` via `addon_pct`, or per-category), **category synonyms**, **item→category overrides** (to resolve the `approx` matches from ADR-0008 follow-up), and **parse hints** (which columns are options/addons, markup/multiplier rules, finish handling). Values are auto-learned on import where derivable and hand-tunable for the rest.

**What lives where (locked):** the profile stores **only durable rules** — category synonyms, item→category overrides, per-option eligibility, parse hints, and charge *shapes* (flat `$` / `%` / per-category). **Actual dollar amounts and the live category/charge list stay in the DB** and refresh on every re-import, so git never holds stale prices and search/upcharge always reads current charges from SQLite.

**Drop write (locked):** on a successful Drop-files Load, newly learned durable rules **auto-update** that builder's profile JSON. Charges themselves are never written into the profile. **Where:** auto-update runs on **local/Mac** Drop only → commit the JSON → deploy; production Drop on Fly **reads** shipped profiles and never writes (container FS is ephemeral; Fly volume stays catalog-only per ADR-0005).

**Storage:** versioned JSON in the repo at `config/builder_profiles/<vendor>.json`, keyed by the canonical vendor name (`standardize.resolve_builder_vendor`). Chosen over a DB table because it is flexible, diffable/reviewable in git, survives DB resets, and onboarding a builder never requires a code change. The private catalog itself stays in the gitignored DB / on Fly (ADR-0005) — only the *rules* live in the repo.

J&M Woodworking is the first profile: today's hardcoded J&M option/category vocabulary migrates into it unchanged, so search-upcharge behavior does not regress while the system generalizes.

**Named parser (locked):** after a builder is uploaded and the Drop looks right, Load writes `parser.importer` (plus filename hints and layouts seen) onto that builder's profile, keyed by the canonical vendor name. The next Drop for that factory runs the named parser first; zero rows falls through to the layout guesser and Load refreshes the lock. Fly Drop reads shipped profiles and does not write.

**First slice (shipped):** search/upcharge reads `config/builder_profiles/j-and-m-woodworking.json`. **Drop read/write of the named parser is now live** — kill test: lock a parser on Load, re-drop a file that resolves to that builder, same importer runs without hand-picking a layout.

**Status:** accepted
