# DEPRECATED — not an identity source

> **Do not use this file.** The 2026-07-18 snapshot below is historical. It conflicts with the live book: wrong remote (`pricebook-system`), stale counts (**155 vendors / ~476k rows**), and outdated next-work (Windy Acres as generic fall-through).
>
> Read instead:
>
> - [`AGENTS.md`](./AGENTS.md) — identity, Load path, non-negotiables
> - [`docs/PRICEBOOK_AGENT_AUDIT.md`](./docs/PRICEBOOK_AGENT_AUDIT.md) — completeness, forbidden moves
> - [`docs/CURSOR_AGENT_KICKOFF.md`](./docs/CURSOR_AGENT_KICKOFF.md) — ordered first jobs
> - [`HANDOFF.md`](./HANDOFF.md) — dated catalog facts
>
> Re-import is `replace_vendor` (ADR-0001). Everyday `upsert` / `append` is forbidden. Holt owns Fly app `faf-pricebook` only — never `pricebook-system`.

---

## Archived snapshot (2026-07-18) — historical only

The block below is kept so history is not lost. **Do not treat any count, remote, or next-work item as current.**

# FAF Pricebook — LIVE

**Updated:** 2026-07-18  
**Folder:** `~/FAF-pricelist-2.0`  
**GitHub (STALE):** https://github.com/Koffeekinggamer/pricebook-system (`origin`) — canonical remote is `Koffeekinggamer/faf-pricelist-2.0`  
**Status:** snapshot only — not live identity  
**Book size (STALE):** ~476,824 rows · 155 vendors · 3,104 collections — do not cite

> **Full agent handoff:** [HANDOFF.md](./HANDOFF.md) — dated facts win over this archive.

## Run (still valid commands; prefer `./run.sh`)

```bash
cd ~/FAF-pricelist-2.0
source .venv/bin/activate
streamlit run pricebook_app.py --server.port 8501
# http://127.0.0.1:8501
# Login: Foothills / Amish
```

Public tunnel (ephemeral): `~/Documents/FAF-pricebook-backups/CURRENT_PUBLIC_URL.txt`

## Backup (local only — never GitHub)

```bash
.venv/bin/python -m backend.cli backup-db
# → ~/Documents/FAF-pricebook-backups/master_pricebook-YYYYMMDD-HHMMSS.db
```

## CLI

```bash
.venv/bin/python -m backend.cli stats
.venv/bin/python -m backend.cli vendors
.venv/bin/python -m backend.cli search "nightstand" --vendor "Genuine Oak"
.venv/bin/python -m backend.cli standardize
.venv/bin/python -m backend.cli backup-db
.venv/bin/python scripts/viztech_sync.py --dry-run
.venv/bin/python scripts/viztech_sync.py
```

## Decisions locked in (still true; see CONTEXT.md / ADRs)

- One builder = one vendor (`replace_vendor` default)
- Mult: default **2.7**; Genuine Oak **1.7**
- FN Chair = **Level One only** on Viztech import
- Viztech sync keeps builders not on Viztech
- Local DB gitignored; backup to Documents only
- Search: boolean; Collection column first; sidebar collapsed by default
- Vendors: Phone + Multiplier editable; Items/Collections locked

## Next work (priority) — SUPERSEDED

Do not pick these up from this archive. First jobs: [`docs/CURSOR_AGENT_KICKOFF.md`](./docs/CURSOR_AGENT_KICKOFF.md). Windy Acres is locked `windy_acres`, not generic fall-through.

1. **Do not build yet — per-user auth / invite / billing (resale prep).** Still Judson-gated (audit §6 / kickoff).
2. **Drop parser coverage** — superseded by named-parser lock + audit completeness tiers.
3. Fix ~26 Viztech files that import as 0 rows (formula sheets) — class of failure; Load gate catches `zero_rows`.
4. Commit/push product code (no DB/secrets) if user wants
5. Fill builder phones / better scrape
6. Confirm hosted deploy strategy — live path is Fly `faf-pricebook`, not Streamlit Cloud.

## Next prompt (copy-paste)

```
You are Holt on faf-pricelist-2.0 only.
Read AGENTS.md → CONTEXT.md → HANDOFF.md → STANDARDS.md → docs/adr → docs/PRICEBOOK_AGENT_AUDIT.md → docs/CURSOR_AGENT_KICKOFF.md.
Do the next unchecked first job. Do not use CONTINUE.md as identity.
```
