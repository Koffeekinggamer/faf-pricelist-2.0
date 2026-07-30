# Cursor + Matt Pocock skills — FAF operating process

Adapted from [Practical-Office/Cursor-AI-dev](https://github.com/Practical-Office/Cursor-AI-dev) living process (`docs/reference/CURSOR-MATT-SKILLS-PROCESS.md`).  
**Skills packages stay** [mattpocock/skills](https://github.com/mattpocock/skills) (+ [caveman](https://github.com/juliusbrussee/caveman)). That course repo does **not** ship replacement skills — it teaches how to use them.

## Taxonomy

**User-invoked** (you type; primary entry):

`/ask-matt` · `/grill-with-docs` · `/wayfinder` · `/triage` · `/improve-codebase-architecture` · `/setup-matt-pocock-skills` · `/to-spec` · `/to-tickets` · `/implement` · `/caveman`

**Model-invoked** (agent or orchestrator reaches; not a typed primary flow step):

`/prototype` · `/diagnosing-bugs` · `/research` · `/tdd` · `/domain-modeling` · `/codebase-design` · `/code-review` · `/resolving-merge-conflicts`

`/grill-with-docs` reaches `/domain-modeling`. `/implement` reaches `/tdd` and `/code-review`.

## Preferred chain

```
SETUP (once)     /setup-matt-pocock-skills → /setup-pre-commit
TRIAGE FIRST     foggy / >1 session → /wayfinder
                 scoped + codebase → /grill-with-docs
MAIN BUILD       grill → /to-spec → /to-tickets → /implement → /code-review
ROUTER           /ask-matt when unsure which typed skill fits
```

FAF floor work (catalog accuracy) often stays in grill → implement when the change is already scoped (e.g. one importer). Still use `/to-spec` + `/to-tickets` for multi-session or cross-builder work.

## Non-negotiables

1. **Triage before grill** — do not default every item into `/grill-with-docs`.
2. **Three Pillars** on every grill: Context Engineering · Assumption Destruction · Stress Testing.
3. **`/to-spec` is synthesis only** — must include acceptance criteria, non-goals, residual risks.
4. **Vertical tracer-bullet tickets** — binary kill test: one-sentence user-observable behavior + recorded blockers.
5. **Red → Green only inside `/implement`** — refactor is a `/code-review` output, not inside the loop.
6. **Local verification matches CI** — Ruff + pytest (Husky/`npm test`) green before commit is done.
7. **Dual-axis review findings acted on** — must-fix items get a committed fix.
8. **`/prototype` is throwaway** — capture the verdict; never harden prototype code in place.
9. **CONTEXT.md + ADRs mandatory** — vague language rejected (FAF glossary in `CONTEXT.md`, decisions in `docs/adr/`).
10. **Measure real experiments** — no fake Measure/Learn; no self-reported confidence as success.

## Ticket binary kill test

Re-slice if the ticket cannot state, in one sentence, a user-observable behavior change, **or** its blocking edges are missing/circular.

## Spec mandatory sections

1. Acceptance criteria (verifiable)
2. Non-goals
3. Residual risks

Missing any → reject.

## Sources

| Artifact                | Location                                          |
| ----------------------- | ------------------------------------------------- |
| This FAF adaptation     | `docs/agents/skill-process.md`                    |
| Upstream course process | https://github.com/Practical-Office/Cursor-AI-dev |
| Installable skills      | https://github.com/mattpocock/skills              |
