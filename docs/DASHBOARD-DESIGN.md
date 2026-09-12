# Dashboard design — v0.4

**Status:** proposal, 2026-09-12. Supersedes the page layout in PRD 4.5 and the v0.2 panel arrangement.
**Why now:** the product became a measures registry in v0.3, and the two most prominent pages still predate it.

## 1. The mismatch

What Fed Pulse now holds: 55 published measures (plus 23 components), monthly from January 2005, at every level of the org tree, with money by fiscal quarter, surveys by year, and an operational definition for every one of them.

What the site leads with, and where each page's numbers come from:

| Page | Reads | Shows |
|---|---|---|
| Overview (landing) | `overview.json`, `series/gov.json` | One month of headcount and one rolling quarter of money, per agency |
| Agency | `overview.json`, `orgtree.json`, groups | Money cards, FTE, org chart |
| Org chart | `orgtree`, `series`, `mix`, `trend`, `geo`, measures `current` | Navigator, vitals, four panels, query |
| Explore | measures slices + parquet | Everything |
| Catalog | measures catalog | Every definition |

The landing page and the agency page — the two a reader hits first — do not touch the measures table at all. Twenty-one years of history and 55 measures are reachable only from nav item three. The front door still advertises the July 2026 money dashboard we built in week one.

Two smaller findings from the audit:

- **The four v0.2 panels agree with the measures table today.** Labor's September 2025 separation rate is 8.605% computed either way. But it is computed twice, in JavaScript from `series/*.json` and in the evaluator from the catalog, and only one of those has the definition attached. That is a maintenance risk to close, not a defect to fix.
- **`site/js/` contains `explorer 2.js` and `explorer 3.js`**, iCloud conflict copies that are being deployed. Delete.

## 2. Principle

**One source of numbers, one place where a number is defined.** Every figure on every page resolves to a catalog measure and comes from the measures table or its slices. If a reader asks "what is this number," the answer is one click to the catalog entry that defines it.

Corollary: the pre-measures slices (`overview.json`, `series/`, `mix/`, `trend/` — about 10 MB) retire once the pages that read them are re-pointed. `geo/` stays: geography is a view, not a measure.

## 3. Shape

Five destinations instead of six pages.

### 3.1 Pulse (landing, `index.html`)

Three bands, in this order.

**Now and then.** Government-wide headcount from 2005 to the latest month as one wide line, with the 2025–26 decline annotated, and a vitals row beneath it: headcount, twelve-month change, quit rate, separation rate, retirement-eligible share, engagement. Every card is a catalog measure with its period and definition on hover.

**What moved.** The thing a reader actually arrives wanting. Pick a measure, pick a window (3, 12, or 60 months, or since 2005), and get the ten units that rose most and the ten that fell most, with sparklines. Defaults to headcount change over twelve months, which is the current story. Rows click through to the unit page.

**Agencies.** The existing ranked table, re-cut: rows are agencies, columns are chosen measures rather than a fixed money-first set. Default columns: headcount, twelve-month change, quit rate, retirement-eligible share, engagement, intent to leave government, personnel obligations, in-sourcing ratio. A column picker draws from the catalog. Money stops being the organizing principle and becomes two columns among eight.

### 3.2 Unit (`unit.html?code=…`, replaces `org.html` and `agency.html`)

One page for any node, whatever its level. The spine-and-shelf navigator stays as the sticky left column.

- **Vitals strip** — eight measures, survey values inherited from the parent agency and labeled.
- **Trend** — the v0.2 panel, re-pointed at the measures table: measure picker across all 55, breakdown by dimension where one exists, comparison units, range.
- **Flows** — the bar-with-pie chart, unchanged in appearance, reading `accessions` and `separations` and their dimensioned category splits.
- **Composition** — a dimensioned measure for the latest month.
- **Map** — unchanged, from `geo/` plus the browser query for sub-elements.
- **Money** and **Survey** — appear only when the node has them, replacing the separate agency page. An agency node shows its group's obligations, in-sourcing, and FTE; sub-elements show a line saying money stops at agency level and linking up.
- **Data** — the node's rows, the parquet link, and the in-browser query panel.

`agency.html?g=dol` redirects to `unit.html?code=DL`, and group-only measures resolve through the node's group membership. One concept, one URL.

### 3.3 Explore, Catalog, Data, About

Explore is unchanged and gains "open in explorer" links from every panel, seeded with that node and measure. Catalog moves up the nav: it is what makes the numbers trustworthy, and it is the page that distinguishes this from a chart toy. Data keeps downloads, schema, and caveats. About is unchanged.

Nav becomes: **Pulse · Units · Explore · Catalog · Data · About**.

## 4. What this deletes

- `overview.json` and the money-first landing logic
- `series/`, `mix/`, `trend/` slices and the three loaders that read them
- `agency.html` as a separate page
- `trend.js`'s own metric math (the panel keeps its controls, loses its arithmetic)
- two iCloud conflict copies

Net: about 10 MB less committed data per refresh, one fewer page, and no number computed in two places.

## 5. What this does not change

- The measures table, catalog, and evaluator
- The navigator, flows chart, map, and composition chart as visual components
- The pipeline, except deleting the slice builders that become unused
- Privacy posture: still static, still no telemetry, still same-origin data

## 6. Build order

1. **Unit page.** Merge `org.html` and `agency.html`; re-point Trend, Flows, and Composition at the measures slices; add Money and Survey sections; redirect the old URLs.
2. **Pulse.** Rebuild the landing page on the measures table: hero, movers, re-cut agency table with a column picker.
3. **Movers slice.** A small precomputed `movers.json` per measure and window, so the leaderboard paints without reading the parquet.
4. **Retire.** Drop the old slices and their builders; delete the stray files; update the data page.
5. **Verify and deploy.** Tests, live checks, screenshots, report.

## 7. Open decisions

| # | Question | Recommendation |
|---|---|---|
| 1 | Merge the agency page into the unit page, or keep a distinct agency overview? | Merge. A reader thinks "Labor," not "Labor the group and Labor the agency." |
| 2 | Is "what moved" the centerpiece of the landing page, above the agency table? | Yes. It answers the arriving question; the table answers the follow-up. |
| 3 | Retire the pre-measures slices, or keep them for compatibility? | Retire. They are regenerable, nothing external links to them, and they are the second definition of several rates. |
| 4 | Default landing measure and window | Headcount change over twelve months. |
