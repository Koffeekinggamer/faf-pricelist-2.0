# CI parser fixtures

Synthetic Office Open XML workbooks so GitHub Actions can prove named
parsers without Judson’s Mac `Downloads` tree.

These are **not** dealer books. Layouts are copied from the in-memory
minis already used by `tests/test_fn_pl_print_import.py`,
`tests/test_ashery_oak_import.py`, `tests/test_jmw_import.py`,
`tests/test_artisan_chairs.py`, `tests/test_criswell.py`,
`tests/test_import_excel.py`, and `tests/test_book_options.py`. SKUs and
prices are the same synthetic values those tests already assert. No
customer names, addresses, emails, or other PII. No secrets. Visible
tabs only — nothing is hidden.

| File | Proves | Visible tabs |
| ---- | ------ | ------------ |
| `settled/fn-chair.xlsx` | FN Chair `fn_chair` PL Print + fabric addon | Cover Page, PCL Color List, PL Print, PL With Markup, PL To Export |
| `settled/ashery-oak.xlsx` | Ashery Oak Master/Products wood expand + Options&Portal addons | Cover, Markup, Options&Portal, Products |
| `settled/j-and-m-woodworking.xlsx` | J&M Percentage woods + Hampton SKUs + Specialty Finish Options | Cover, Markup, ` Percentage`, Hampton, Specialty Finish Options |
| `settled/artisan-chairs.xlsx` | Artisan Wholesale unfinished/finished matrix + Options block | Retail with MARKUP, Wholesale |
| `settled/criswell-bedroom.xlsx` | Criswell left-pane wholesale + Options tab | Markup, Cover, Bloomfield Collection, `Options ` |
| `wide/genuine-oak-wide-species.xlsx` | Token `genuine_oak` lock on a `wide_species` matrix | Cover, Pricelist |
| `options/millcraft-options.xlsx` | Token `millcraft` lock + Options **tab** (size %, two-tone, flat $) | Cover, Options, Pricelist |

Regenerate after changing a layout:

```bash
.venv/bin/python tests/fixtures/build_fixtures.py
```

Then commit the new `.xlsx` bytes. Tests read the committed files; they
do not rebuild at collect time. Live Mac Downloads tests remain and
still `skip` when those files are absent.
