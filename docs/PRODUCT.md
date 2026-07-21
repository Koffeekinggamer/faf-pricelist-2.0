# FAF Pricelist 2.0 — product decisions

## Problem

Floor staff need accurate builder pricelists they can **read on a tablet/desktop** after someone drops a vendor Excel file. Parsing everything into a spreadsheet-like grid is noisy. They want a **PDF on screen**.

## Phase 1 (build this first)

1. **Auth** — simple store login (defaults Foothills / Amish; override via env or secrets).
2. **Drop Excel** → convert to a **formatted retail PDF**.
3. **Builder name** control — selecting/editing builder updates the PDF title/header and what is saved.
4. **PDF viewer in-app** (`st.pdf` or equivalent) — primary UI for the team.
5. **Download PDF** optional.
6. **Admin**
   - Backup SQLite (or chosen store) after catalog updates.
   - Per-builder **multiplier** (retail = wholesale × mult). Defaults historically: most builders **2.7**, Genuine Oak often **1.7**.
7. Optional: **Save builder into master DB** after drop (for mults/backup), without showing long-form rows on the floor.

## Explicit non-goals (phase 1)

- OrderTrac quote creation / push UI  
- Full-text search across all builders  
- Pinned builders rail  
- Viztech monthly sync UI  
- Multi-user OrderTrac staff sync UI  

These may return later; v1 code exists under `~/FAF-pricebook` for reference only.

## Design principles

- **Floor-first**: PDF on screen beats tables of parsed rows.
- **One builder = one vendor** when saving to master.
- **Never commit** the master DB or secrets to GitHub.
- **Multipliers** are store policy, not builder wholesale.

## Future (phase 2+)

- Reintroduce OrderTrac as optional backend integration (not blocking phase 1).
- Search across saved masters.
- Fly.io deploy when catalog accuracy is trusted.
