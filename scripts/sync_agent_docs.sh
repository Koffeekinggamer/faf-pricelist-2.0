#!/usr/bin/env bash
# Mirror FAF agent-doc seeds → docs/agents/ (ADR-0006).
# Canonical: .agents/skills/setup-matt-pocock-skills/
# After `npx skills update`, re-apply FAF overlays to the seeds, then run this script.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SEED="$ROOT/.agents/skills/setup-matt-pocock-skills"
DEST="$ROOT/docs/agents"

if [[ ! -d "$SEED" ]]; then
  echo "error: missing seed dir $SEED" >&2
  exit 1
fi

mkdir -p "$DEST"
cp "$SEED/domain.md" "$DEST/domain.md"
cp "$SEED/triage-labels.md" "$DEST/triage-labels.md"
cp "$SEED/issue-tracker-github.md" "$DEST/issue-tracker.md"
echo "Synced docs/agents/ from setup-matt-pocock-skills seeds."
