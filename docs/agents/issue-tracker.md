# Issue tracker: GitHub (FAF Price Book)

Issues and specs for **Foothills Amish Furniture Price Book** live in GitHub Issues on `Koffeekinggamer/faf-pricelist-2.0`. Use the `gh` CLI for all operations.

## Product framing for tickets

Prefer titles and bodies that use FAF vocabulary from `CONTEXT.md`:

- Catalog / import / Search / Vendors / Viztech / multipliers / builder names
- Tag the surface when useful: `Search`, `Drop`, `Vendors`, `Admin`, `import`, `Viztech`
- Call out builder name when the ticket is about one factory (e.g. `FN Chair`, `Genuine Oak`)

Do **not** file tickets that require committing `*.db` or secrets. Catalog data stays on Fly / local volume (see ADR-0005).

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --comments`
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` / `--state` filters
- **Comment**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v` — `gh` does this inside a clone.

## Pull requests as a triage surface

**PRs as a request surface: no.** Cloud-agent / Cursor PRs are the normal delivery path; they are not treated as external feature requests for `/triage`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue. For specs from `/to-spec`, include acceptance criteria in FAF terms (builder, retail, replace_vendor, which tab). For `/to-tickets`, keep each ticket a vertical slice that an agent can finish without needing the private DB committed.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`. Also skim `HANDOFF.md` known issues if the ticket mentions catalog thinness, Viztech, or FN Chair.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets.

- **Map**: a single issue labelled `wayfinder:map`, holding Notes / Decisions-so-far / Fog. `gh issue create --label wayfinder:map`.
- **Child ticket**: GitHub sub-issue when available; else task-list link in the map body + `Part of #<map>` on the child. Labels: `wayfinder:<type>` (`research` / `prototype` / `grilling` / `task`).
- **Blocking**: native issue dependencies when available; else `Blocked by: #<n>` at the top of the child body.
- **Claim**: `gh issue edit <n> --add-assignee @me`
- **Resolve**: comment the answer, close the child, append a pointer to the map’s Decisions-so-far.
