# Working across machines (both Macs + cloud agents)

Goal: any device can pick up the **same code progress and the same catalog data**
with minimal fuss, and the data always matches the live site.

## The split (important)

| What | Source of truth | How it syncs | Why |
|------|-----------------|--------------|-----|
| **Code / progress** | GitHub `faf-pricelist-2.0` (**public**) | normal `git pull` / `git push` | code is fine to be public |
| **Catalog data** (`master_pricebook.db`, ~168MB) | **Fly volume** `/data/master_pricebook.db` (private, this *is* the live site) | `scripts/pull_db_from_fly.sh` / `scripts/push_db_to_fly.sh` | 168MB of PRIVATE pricing — must never touch the public repo |

The DB is gitignored and must **never** be committed to the public repo. Fly is the
live store, so pulling from Fly always gives you exactly what customers see.

## One-time per machine

1. Install flyctl: `curl -L https://fly.io/install.sh | sh`
2. Authenticate one of two ways:
   - `fly auth login`, or
   - create a token at https://fly.io/user/personal_access_tokens (or run `fly tokens create deploy -a "$FLY_APP"`), then `export FLY_API_TOKEN=<value>` (cloud agents: set it as a secret instead)

## Start of a session (any device)

```bash
git pull                          # latest code
./scripts/pull_db_from_fly.sh     # latest live catalog → master_pricebook.db
./run.sh                          # http://127.0.0.1:8501 · login Foothills / Amish
```

## End of a session (any device)

```bash
# code
git add -A && git commit -m "…" && git push

# data (only if you changed the catalog — imports, cleanups, multipliers, phones)
./scripts/push_db_to_fly.sh       # local DB → Fly volume (updates the live site)
```

That is the whole loop. Because both push/pull go through Fly, the other Mac just
runs the start-of-session steps and is instantly in sync with live.

## Optional: extra Git backup of the data (a PRIVATE repo)

If you also want a versioned Git snapshot of the catalog (belt-and-suspenders on top
of Fly), the DB gzips to ~14MB — small enough for a normal git repo (no LFS needed).
This must target a **PRIVATE** repo; the scripts refuse to push data to a public repo.

Setup once:

1. Create a **private** GitHub repo, e.g. `faf-pricebook-backup`.
2. `export FAF_BACKUP_REPO="https://<token>@github.com/<you>/faf-pricebook-backup.git"`
   (cloud agents: provide this via a secret).

Then:

```bash
./scripts/backup_to_github.sh "note about this session"   # gzip DB + manifest → private repo
./scripts/restore_from_github.sh                          # restore DB from the private repo
```

`backup_to_github.sh` verifies the target repo is private (via the `gh` CLI) before
pushing and aborts otherwise.
