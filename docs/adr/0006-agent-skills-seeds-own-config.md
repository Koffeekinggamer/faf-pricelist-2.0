# Setup-skill seeds own FAF agent config; docs/agents is a mirror

FAF agent-tracker / domain / triage config is maintained as overlays inside `.agents/skills/setup-matt-pocock-skills/` (not the generic upstream templates). `docs/agents/*.md` is a synced mirror for skills that read that path. After `npx skills update`, re-apply FAF overlays to the seeds, then run `scripts/sync_agent_docs.sh`. GitLab and local-markdown tracker seeds are deleted on purpose — this repo is GitHub-only.

**Status:** accepted
