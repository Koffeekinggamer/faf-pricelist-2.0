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
| `settled/ashery-oak.xlsx` | Ashery Oak visible Master wood expand + Products fill + Options&Portal addons | Cover, Markup, Options&Portal, Master, Products |
| `settled/j-and-m-woodworking.xlsx` | J&M Percentage woods + Hampton SKUs + Java Fabric/Crypton/Leather panels + Specialty Finish Options | Cover, Markup, ` Percentage`, Hampton, Java, Specialty Finish Options |
| `settled/artisan-chairs.xlsx` | Artisan Wholesale unfinished/finished matrix + Options block | Retail with MARKUP, Wholesale |
| `settled/criswell-bedroom.xlsx` | Criswell left-pane wholesale + Options tab | Markup, Cover, Bloomfield Collection, `Options ` |
| `wide/genuine-oak-wide-species.xlsx` | Token `genuine_oak` lock on a `wide_species` matrix + a small Options tab | Cover, Options, Pricelist |
| `options/millcraft-options.xlsx` | Token `millcraft` lock + Options **tab** (size %, two-tone, flat $) | Cover, Options, Pricelist |
| `settled/aj-s-furniture.xlsx` | AJ's fabric-tier + OPTIONS band | Cover, Finished Wholesale MARKUP, Options |
| `settled/amish-aspen.xlsx` | Amish Aspen flyer name/price pairs + Hickory/Aspen | Cover, Options, Pricelist |
| `settled/brookside-home-furnishings.xlsx` | Brookside Heritage hutch title-row woods | Cover, Heritage  Hutches, Options, Markup |
| `settled/fredericksburg-furniture.xlsx` | Fredericksburg left-hand wholesale woods | Cover, Bedroom, Options |
| `settled/frog-pond-furniture.xlsx` | Frog Pond title-row wood groups + Options | Cover, `1 Weston `, Options, Markup, Index |
| `settled/hillside-chair.xlsx` | Hillside Unf/Fin under woods on Sheet3 | Cover, Options, Sheet3 |
| `settled/hogback-design-and-finishing.xlsx` | Hogback two wood-group columns | Cover, Pricing, Options |
| `settled/hope-wood.xlsx` | Hope Wood / HW Chair markup calculator | Cover, Markup Calculator, Options |
| `settled/j-troyer-and-company.xlsx` | J. Troyer Item# × wood groups | Cover, Buffet, Options |
| `settled/kidron-woodcraft.xlsx` | Kidron wholesale finish twins, not left retail | Cover, Prices, Options |
| `settled/lamb.xlsx` | LAMB wood matrix + Furniture Options | Cover, Wholesale, Options |
| `settled/maple-lane.xlsx` | Maple Lane CODE + next-row prices + named colors | Cover, Wholesale, Options |
| `settled/patio-kraft.xlsx` | Patio Kraft Item # × color tiers | Cover, Retail, Wholesale, Options |
| `settled/superior-woodcrafts.xlsx` | Superior ITEM # × wood × unf/fin wholesale | Cover, Pricelist, Options |
| `settled/townline-furniture.xlsx` | Townline visible Finished/Unfinished twins | Cover, Finished, Unfinished, Options |
| `settled/troyer-ridge-furniture.xlsx` | Troyer Ridge stacked wood groups | Cover, Bedroom, Options |
| `settled/windy-acres-furniture.xlsx` | Windy Acres ITEM # + finish pairs + in-sheet Options | Cover, Bedroom Collection, Instructions, MarkUp |
| `stubs/stub-workshop.xlsx` | `add_builder` template (`stub_workshop`). Not a selling factory. Not SETTLED. Options tab must emit addons. | Cover, Options, Pricelist |

Regenerate after changing a layout:

```bash
.venv/bin/python tests/fixtures/build_fixtures.py
```

Then commit the new `.xlsx` bytes. Tests read the committed files; they
do not rebuild at collect time. Live Mac Downloads tests remain and
still `skip` when those files are absent.
