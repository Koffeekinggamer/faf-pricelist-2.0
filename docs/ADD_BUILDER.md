# Add builder N — clone this stub

Adding a factory is a known path. Do not hand-wire a 49th detector. Run the
scaffold, splice the printed registry line, commit the profile + Options
fixture, and leave SETTLED as a placeholder until a shape test exists.

**This is not a selling-factory Drop.** Confirm the canonical name with Judson
before a real Load. Never unhide sheets. Never commit `master_pricebook.db`.
Never lock `generic` / `pdf` over a specific importer. Empty Search Options is
a capture miss.

## Command

```bash
# Plan only — prints slug, parser id, CatalogSpec / ReaderEntry, SETTLED placeholder
.venv/bin/python scripts/add_builder.py --vendor "Canonical Name"

# Write profile JSON + synthetic Options fixture + test hook + splice notes
.venv/bin/python scripts/add_builder.py --vendor "Canonical Name" --write
```

Shape-specific first lock (Tier B / job 5):

```bash
.venv/bin/python scripts/add_builder.py --vendor "Patio Kraft" --kind shape
```

`--token` adds an extra detect token. The command refuses watched short tokens
(`ac` / `ao` / `fnc` / `jmw` / …), tokens another vendor already claims, a
`generic`/`pdf` importer, and `--write --overwrite` of a locked selling /
SETTLED profile. Only a `stub: true` template may be overwritten.

## What the stub already did (clone these files)

| Piece | Stub Workshop (template) | Real factory (later job) |
| ----- | ------------------------ | ------------------------ |
| Canonical name | `Stub Workshop` | Judson-confirmed display name |
| Slug / parser id | `stub-workshop` / `stub_workshop` | `scripts/add_builder.py` prints both |
| Registry | `CatalogSpec("stub_workshop", "Stub Workshop")` in `CATALOG_SPECS` | Splice the printed `CatalogSpec` **or** `ReaderEntry` |
| Profile | `config/builder_profiles/stub-workshop.json` (`stub: true`, locked, not generic) | Commit `config/builder_profiles/<slug>.json` |
| Fixture + Options | `tests/fixtures/stubs/stub-workshop.xlsx` | Commit the written xlsx; prove addon rows |
| Test hook | `tests/test_add_builder.py` | Generated `tests/test_<slug>_builder_scaffold.py` |
| SETTLED | `STUB_SETTLED_PLACEHOLDER` — **not** in `SETTLED` | Promote only after a shape test (kickoff job 5) |

## After `--write`

1. Splice the CatalogSpec into `backend/catalog_readers.py` `CATALOG_SPECS` (token lock) **or** the ReaderEntry into `DEFAULT_READER_REGISTRY` (shape). Do not add both for the same id.
2. Optional: add `VENDOR_CANON` + a filename hint in `backend/standardize.py` when the stem is messy. Never hint a Viztech `Download_*` stem.
3. Commit the profile JSON and the Options fixture. Profile may say `stub: true` only for the template.
4. Parse the fixture. Addon rows and the planned `option_keys` must be present. Empty Options ≠ no Options.
5. Keep identity collision tests green (`tests/test_builder_identity.py`). New tokens must not collide with `ac` / `ao` / `fnc` / …
6. Leave the SETTLED placeholder out of `tests/test_builder_parser_contract.py` until job 5 has a shape test and fixture bytes.
7. Do not edit `pricebook_app.py`. Do not Fly deploy. Do not touch the volume.

## Checked-in example

`Stub Workshop` is the reusable tracer: a catalog-token reader, a locked
profile, and a synthetic Options workbook. It is **not** one of the 48 selling
factories and it is **not** SETTLED.
