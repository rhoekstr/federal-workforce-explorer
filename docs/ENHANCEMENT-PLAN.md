# Overnight enhancement plan — Fed Pulse v0.2

Written 2026-09-10 after Robert's review of the MVP. Same contract as `RUNBOOK.md`: execute milestones in order, verify each against its acceptance checks, commit at each boundary, and finish with a build report. Read `CLAUDE.md` first. The hard rules there still apply, especially no individuals, no telemetry, no build step.

## What Robert asked for, and the design that answers it

| Ask | Design |
|---|---|
| Org chart is hard to use, too much scrolling | Replace the wide tree with a **spine and shelf**: the path from government to the selected node runs down the left as a vertical spine of boxes; the selected node's children sit to the right as a wrapping grid of boxes sorted by headcount, with connectors from the parent. No horizontal scroll. On desktop the navigator is a sticky left column and the detail is the right column, so selecting a node never means scrolling back up. |
| The map is missing | County choropleth for any node. Precomputed for government and agencies; computed in the browser with DuckDB for sub-elements. Disclosure share stated on the map itself. |
| Stacked hires-and-separations chart is too messy | One bar per month: blue above the axis for all accessions, red below for all separations. Hover a bar to get a tooltip with a pie of the categories and their counts. Deferred resignations shown as a hatched slice of the red bar. |
| Too many charts; want one good trend with configuration | Two configurable panels replace the pile: **Trend** (metric, breakdown, comparison, range) and **Composition** (one dimension at a time for the latest month). Plus the hires-and-separations bar and the map. Four panels per node, all driven by controls, state in the URL. |

## Milestones

### E0 — Housekeeping (15 minutes)

- Confirm HTTPS on fedpulse.awrylabs.com is enforced (`gh api repos/rhoekstr/federal-workforce-explorer/pages`). If the certificate is still missing, re-PUT the cname and leave a note; do not block on it.
- Create the `pipeline` and `crosswalk` issue labels so the workflow's failure step can open issues.
- Bump `PRD.md` to 1.3: name, domain, fact-only Releases, and move "Geography" from Phase 2 into this plan. Add the four designs above to Section 4.5.

**Accept:** labels exist; PRD committed.

### E1 — Trend data: monthly breakdowns per node (pipeline)

The trend panel needs, for each node and month, headcount broken down by a dimension. Precompute it rather than querying 19 parquet files in the browser.

- New `pipeline/trends.py` writing `data/slices/trend/{code}.json`:
  ```json
  {"code":"DLLS","months":[...],
   "headcount":{"202501":1863,...},
   "accessions":{"202501":{"AC":12,"AE":3},...},   "separations":{...,"DRP":n},
   "by":{"grade":{"12":{"202501":640,...},"13":{...},"_other":{...}},
         "age_bracket":{...},"supervisory_code":{...},"appointment_type_code":{...},
         "pay_band":{...},"work_schedule_code":{...},"series_code":{...},"step_code":{...}}}
  ```
  Keep the top 8 values per dimension (by latest-month headcount) plus `_other`. Series and step top 8 only.
- Scope: government, departments, agencies, and sub-elements with 500 or more employees in the latest month (245 of 541 today). Smaller sub-elements get headcount and actions only (the existing series file) and the Composition panel for the latest month.
- Budget: each file under 60 KB; total under 15 MB in the repo. Measure and report. If over, drop `series_code` and `step_code` from sub-elements.
- Derived metrics computed client-side from these files: net change, separation rate (separations ÷ prior-month headcount), accession rate, DRP share.
- Wire into `cli.py slices`. Tests: sums by dimension equal the node headcount for every month; file count and size budget.

**Accept:** `data/slices/trend/DL.json` and `DLLS.json` exist, pass the sum test, and the total is under budget.

### E2 — Geography data (pipeline)

- `pipeline/geo.py` writing:
  - `data/slices/geo/{code}.json` for government, departments, agencies: `{"month":"202607","n":..., "disclosed":..., "counties":{"11001":523,...}, "states":{"DC":...}}`. Counties keyed by 5-digit FIPS from the duty station lookup (`fips` field). Non-US and invalid go to `"_abroad"` and `"_invalid"`.
  - `data/geo/counties-10m.json`: US Atlas TopoJSON (us-atlas@3 `counties-10m.json`, ~650 KB) committed to the repo so nothing is fetched from a third party at runtime. Record the source and license in `data/geo/README.md`.
- Sub-elements are not precomputed: the browser runs `SELECT duty_station_code, sum(n) ... WHERE org_code LIKE 'X%' GROUP BY 1` on the latest fact parquet and maps codes to FIPS with the duty station lookup, which the query panel already loads.
- Tests: county counts plus not-disclosed plus abroad plus invalid equal the node headcount; every FIPS in a geo slice exists in the TopoJSON or is flagged.

**Accept:** Labor's geo slice sums to 11,074 with the disclosed share matching the mix summary.

### E3 — Hires-and-separations bar with hover breakdown (site)

- New `site/js/flows.js`: hand-rolled SVG (no Plot) so the tooltip is ours. One bar per effective month: accessions up in blue, separations down in red, DRP as a hatched slice of the red bar. Y axis symmetric or independent (independent by default; toggle).
- Hover or focus a bar: a tooltip card with month, totals, net, and a small pie per side (accession categories, separation categories) with a legend of names and counts. Keyboard: arrow keys move the focused month; tooltip content is also written to an `aria-live` region.
- Replace `actionsChart` and `separationsByCategory` on the landing, agency, and org pages with this one panel. Keep the data table alternative.

**Accept:** on the org page for BLS, hovering July 2026 shows the pie with quits, retirements, and the counts that match `series/DLLS.json`.

### E4 — Trend and Composition panels (site)

- `site/js/trend.js`: one chart with controls:
  - **Metric:** headcount · net change · accessions · separations · separation rate · accession rate.
  - **Breakdown:** none · grade · age · supervisory · appointment type · pay band · work schedule · series · step (stacked areas or lines; areas for shares, lines for counts; a toggle).
  - **Compare:** add up to three other nodes by name (typeahead from the org tree) as lines on the same axes; default comparison is the parent node, shown as an index (100 = first month) so a bureau can sit beside its department.
  - **Range:** all · 12 months · since a chosen month.
  - State in the URL (`?code=DLLS&metric=headcount&by=grade&cmp=DL,gov&range=12`).
  - Falls back gracefully for nodes without a trend file: metric and compare still work from `series/`, breakdown control is disabled with a note.
- `site/js/composition.js`: one horizontal bar chart with a dimension selector for the latest month, replacing the eight mix charts. Includes the disclosure and average-pay summary line.
- Org page and agency page use: Trend, Flows (E3), Composition, Map (E5). Landing page: Trend (government, metric and breakdown only), Flows, the agency table.

**Accept:** the org page shows four panels and no more; changing any control updates the URL; reloading the URL restores the view; the data-table alternative reflects the current configuration.

### E5 — Map panel (site)

- `site/js/map.js` on Observable Plot geo marks plus `topojson-client` (pinned, jsdelivr) to unpack the committed TopoJSON.
- County choropleth with a quantized log color scale (counties range from 1 to tens of thousands), state outlines, and a hover tooltip with county name, state, and count. Toggle to states. Abroad and not-disclosed shown as two counters beside the map, with the disclosure share in the caption in words: "62% of this unit's employees have a disclosed location; the map shows those."
- For sub-elements, the map queries the parquet through the existing DuckDB-WASM module. Show a loading state; cache the result per node in memory.
- Mobile: the map keeps its aspect ratio and the tooltip becomes tap.

**Accept:** Labor's map paints from the precomputed slice; BLS's map paints from a DuckDB query; a Defense sub-element shows the map greyed with "0% disclosed" rather than an empty map.

### E6 — Org navigator: spine and shelf (site)

- `site/js/orgnav.js` replaces `orgchart.js`:
  - **Spine:** vertical stack of boxes for the path (government → department → agency → selected), each with headcount and sparkline, connected by a single vertical line. Clicking a spine box selects it.
  - **Shelf:** the selected node's children as a wrapping grid of boxes (CSS grid, `minmax(160px, 1fr)`), sorted by headcount, connected to the spine by one elbow. Show 24 by default with "show all". "Small agencies" stays as a group box at the government level. Boxes keep the sparkline, change since first month, and the "gone since" marker.
  - **Search** stays; result selection scrolls the shelf, not the page.
  - **Layout:** desktop is a two-column grid, navigator sticky in the left column (max height = viewport, scrolls internally), detail in the right column. Mobile stacks them with the navigator collapsible.
  - Keyboard: arrow keys move within the shelf, Enter selects, Backspace goes to the parent. `aria-tree` semantics preserved.
- Remove the old orgchart CSS.

**Accept:** with BLS selected, the whole navigator fits in one viewport at 1280 px wide with no horizontal scroll; selecting a sibling changes the detail without the page scrolling; the mobile screenshot shows the collapsed navigator above the detail.

### E7 — Verification, screenshots, deploy

- `pytest` green. Headless-Chrome screenshots of landing, Labor agency, BLS org page (desktop and mobile widths) into `docs/screenshots/v0.2/`.
- Assemble, dispatch the workflow, confirm the deploy is green, and probe https://fedpulse.awrylabs.com for the new panels.
- `docs/BUILD-REPORT-v0.2.md` in the same format as the first report.

## Guardrails

- No new third-party runtime requests except pinned scripts from jsdelivr. The TopoJSON is committed, not fetched.
- Repo growth from slices under 20 MB total. Report the number.
- Keep the old pages working until the new panels pass their checks; swap in one commit per page.
- If E1's budget cannot be met, reduce scope (fewer dimensions for sub-elements), do not raise the budget.
- Do not touch the crosswalk, money, or PLUM.

## Kickoff prompt

```
Execute docs/ENHANCEMENT-PLAN.md in this repo, unattended: milestones E0 through E7 in order, acceptance checks after each, one commit per milestone named for it. Read CLAUDE.md first; its hard rules override everything. Take the designs in the plan as decided; where the plan leaves a detail open, choose the simpler option and record it in the build report. Deploy through the existing workflow at the end and confirm fedpulse.awrylabs.com serves the result. Finish with docs/BUILD-REPORT-v0.2.md and put its summary in your final message.
```
