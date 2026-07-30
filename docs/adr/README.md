# Architecture Decision Records — FAF Price Book

Locked product/architecture decisions. Skills (`/grill-with-docs`, `/domain-modeling`, `/code-review`) must respect these; reopen only with an explicit ADR update.

| ADR                                                        | Decision                                                         |
| ---------------------------------------------------------- | ---------------------------------------------------------------- |
| [0001](./0001-one-builder-one-vendor.md)                   | One builder = one vendor; replace_vendor on re-import            |
| [0002](./0002-retail-equals-wholesale-times-multiplier.md) | Retail = wholesale × multiplier (2.7 / Genuine Oak 1.7)          |
| [0003](./0003-accuracy-mode-ordertrac-ui-off.md)           | Accuracy mode; OrderTrac UI off                                  |
| [0004](./0004-thin-ui-pricebook-service.md)                | Thin Streamlit; logic in PriceBookService                        |
| [0005](./0005-master-db-never-in-git.md)                   | Master DB / secrets never committed                              |
| [0006](./0006-agent-skills-seeds-own-config.md)            | Setup-skill seeds own FAF agent config; `docs/agents/` is mirror |
| [0007](./0007-thin-catalogs-triage.md)                     | Thin = &lt;150 rows; Judson keep/replace/ignore; Admin+CLI       |
| [0008](./0008-options-are-addon-charges.md)                | Option = addon charges (`line_kind=addon`); not fake retail      |
| [0009](./0009-practical-office-skill-process.md)           | Practical-Office process; keep mattpocock skill packages         |

New ADRs: next number, short slug, see `.agents/skills/domain-modeling/ADR-FORMAT.md`.
