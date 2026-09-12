# Fed Pulse — Product Requirements Document

**Version:** 2.0
**Status:** active
**Name:** Fed Pulse, at [fedpulse.awrylabs.com](https://fedpulse.awrylabs.com). Repo `rhoekstr/federal-workforce-explorer`.
**Created:** 2026-09-09 · **Rewritten:** 2026-09-12
**Author:** Robert Hoekstra, with Claude

Version 2 replaces version 1.3 and folds in the three design documents that had overtaken it: `docs/MEASURES-MODEL.md` (the data model), `docs/DASHBOARD-DESIGN.md` (the v0.4 information architecture), and `docs/FEVS-EXPLORATION.md` (the survey source study). Those stay as the detailed references; this is the one document to read first. Every number here was measured against the live build on 2026-09-12.

---

## 1. What Fed Pulse is

OPM publishes record-level data on the entire executive-branch civilian workforce every month, going back to 2005. It is public, free, and almost unusable: 1.7 GB of pipe-delimited text per month behind an undocumented endpoint. Fed Pulse turns it into **a registry of organizational-health measures with two decades of history at every level of the federal org tree**, puts money and survey data beside it, and serves the whole thing as a static site that runs in the reader's browser.

The thing that makes it worth building is not the dashboard. It is that every number on the site resolves to a catalog entry with an operational definition, a source, a cadence, and a date from which it can honestly be computed. The measures are the product; the pages are views onto them.

**Who it is for:** federal employees who want to see their own agency's trajectory, journalists covering the workforce, researchers who need a cleaned reproducible cut, and the general public.

## 2. What it does and does not do

### Does

1. **Measures over time.** 85 measures, 12.2 million values, 984 nodes, January 2005 to July 2026 monthly, with money by fiscal quarter and surveys by survey year.
2. **A real data dictionary.** Every measure carries an operational definition. Derived measures generate theirs from their calculation. An undescribed measure is a pipeline error.
3. **Any measure, any unit, any span,** trended against any other, with native cadences respected and mixed units indexed.
4. **Leadership.** The statutory PLUM list as a searchable directory and a roster on every unit page.
5. **Reproducibility.** The measures table and the raw-extract archive are published to GitHub Releases; anyone can rebuild the site from them.
6. **Privacy by construction.** No backend, no analytics, no cookies. Queries run in the reader's browser.

### Does not

1. **No individual workforce lookup.** OPM's files carry no names and Fed Pulse adds none.
2. **No record-level linkage between PLUM and the workforce files.** Measured on the July 2026 file: using only keys PLUM also carries, 23% of SES rows are unique and 46% sit in cells of five or fewer, before salary. Joining them would deterministically re-identify a large share of career executives and attach to them the age, education, veteran status, and service date that OPM deliberately withholds. A test enforces this: no workforce field may appear on a PLUM row.
3. **No pay analysis below the band.** Exact salary is dropped; averages survive through summed measures.
4. **No general query builder.** OPM has one. Fed Pulse has a small number of well-chosen views plus a downloadable table.

## 3. The data model

Full detail in `docs/MEASURES-MODEL.md`. It is a simplification of the Evince measurement model (`~/Desktop/Code/Evince`), keeping four things and discarding the rest.

**Kept from Evince:** base and derived measure tiers with dimensionality orthogonal to composition; three derived patterns (additive, ratio, time offset) composed by layering rather than nesting, which makes extensiveness decidable and definitions generatable; lagged results dated to the period they describe; incomplete periods notated rather than silently summed; and the data dictionary as the thing that drives validation.

**Discarded:** the append-only value ledger with as-of reconstruction, targets, status, certification, drafts, tenancy, and the recompute ledger. Fed Pulse is a dashboard, not a system of record. Every run recomputes everything and replaces the table; `source_ref` records which source version produced each value.

### Objects

| Object | Where | Notes |
|---|---|---|
| Measure | `catalog/measures.json` | 85 entries: code, definition, unit, aggregation, extensiveness, category, cadence, since-date, levels, dimensions, sources, calculation |
| Node | `catalog/nodes.json` | 984: government, department, agency, sub-element, and overview group |
| Value | `data/work/measures.parquet` | measure, node, period, dim, value, n, notation, source_ref |
| Calculation | inside the measure | exactly one of additive, ratio, time offset |
| Dimension | `catalog/dimensions.json` | 10, with top-8 value capping per node |

### Period types

`month` (workforce), `quarter` (money, fiscal, rolling four), `fiscal_year` (OMB FTE), `survey_year` (FEVS). The site's as-of date is anchored on headcount, not on the end of the period axis, because PLUM publishes a month or two ahead of OPM's snapshot.

## 4. Sources

All unauthenticated. Verified 2026-09-12.

| Source | Coverage | Access |
|---|---|---|
| OPM Federal Workforce Data | employment, accessions, separations; 2005 onward; 725 files | metadata API for discovery, undocumented blob path for the pipe-delimited files |
| USAspending File B | object-class obligations, FY2017 Q2 onward | bulk account download by period; aggregates committed to the repo |
| OMB Analytical Perspectives Table 5-1 | civilian FTE by agency | annual spreadsheet, manual refresh |
| OPM FEVS | indices and intent to leave, 2019 to 2023 | public respondent files; indices validated to ±0.00 against OPM's published values |
| OPM PLUM | 15,661 leadership positions, 9,816 individuals | undocumented endpoint; needs a browser user agent; snapshot history committed |

**Era awareness is structural.** The 2005 files carry 31 columns; today's carry 64. Every measure declares the period from which its inputs exist, and the extractor emits a measure only where its columns are present. Employment is quarterly before mid-2011 and monthly after, so monthly rates carry the prior snapshot forward up to two months, stated in the definitions.

## 5. The site

Six pages, described in full in `docs/DASHBOARD-DESIGN.md`.

- **Pulse** (`index.html`): the 21-year government-wide story, six vitals, a movers leaderboard rankable by size or percent over 3, 12, or 60 months, and an agency table whose columns are any measure.
- **Units** (`unit.html`): one page for any node. Spine-and-shelf navigator, vitals, then Trend, Flows, Composition, Money, Survey, Leadership, and Map. Money and survey sections appear only where the node has them, and an agency with no obligations says why.
- **Executives** (`executives.html`): the PLUM directory, searchable by name, title, agency, and appointment type, with a card and position timeline per person.
- **Explore** (`explore.html`): any measures against any units over any span.
- **Catalog** (`catalog.html`): the dictionary, rendered. Every number on the site links here.
- **Data** (`data.html`): downloads, schema, methodology, caveats.

Every chart has a data-table alternative, selection state lives in the URL, and the pages carry no third-party requests beyond pinned CDN scripts.

## 6. Architecture

Static site, no build step. Python and DuckDB pipeline, parquet on GitHub Releases, DuckDB-WASM in the browser for record-level queries, Observable Plot for charts, GitHub Actions for the monthly refresh.

```
sources → era-aware extractors → catalog validation → derived evaluator → measures.parquet → slices → publish
```

**Guards that exist because something went wrong:**

- The build refuses to run when it sees fewer than 80% of the extracts the last published build used. This exists because a manifest key was being overwritten, CI silently built from 57 months instead of 725, and published a 2018-onward table over the 21-year one.
- Every header is checked against a committed reference; a mismatch stops that dataset and reports.
- Sync and publish never run concurrently, because both write the manifest.
- Every pipeline command sweeps iCloud conflict copies first, because the repo lives in iCloud Drive and iCloud races itself when hundreds of slice files are rewritten. It has produced over 2,000 stray files and corrupted the git index once. **Moving the repo out of iCloud remains the real fix and is deliberately not done.**

## 7. What the data says

As of the July 2026 snapshot:

| | |
|---|---|
| Employees | 2,020,230 |
| Peak | 2,313,562 in October 2024 |
| Change since peak | −293,332 |
| Separations, 2025 | 497,032, of which 140,481 deferred resignations |
| Quit rate, 2006 to 2024 | 3.6% to 4.9% annually |
| Quit rate, 2025 | 7.4% |
| Location withheld by OPM | 47% of employees |

## 8. Open items

| # | Item | State |
|---|---|---|
| 1 | OSHA injury and illness rates, EEOC complaint rates | Designed, not built. Both are annual per-agency tables published only as reports; they need hand transcription against the source documents, which is better done with a human reading the PDFs than by a scraper guessing. |
| 2 | VA All Employee Survey | Investigated 2026-09-12 and deliberately deferred. VA is the largest survey gap (446k people, never in a public FEVS file). `data.va.gov` has two shapes: `mpkr-yv95` carries FEVS-comparable **named** items but only one year per group across 18 groups, which is a comparison table rather than a series; the per-year `*-FEVS Percents` datasets (e.g. `rdpw-mtbs` for 2024) carry item-level response distributions by VA administration keyed by AES item number (`f03`, `f04`, …) with no published mapping to FEVS items. Percent-positive is mechanical once the mapping exists. Building the index without it would be a guess. |
| 3 | FEVS below agency level | Blocked on OPM. The 2024 respondent file is corrupt as published (87k rows then null bytes); the 2019 file is intact and carries a sub-agency field. Its codes are FWD sub-element codes only for Defense, Treasury, and Transportation; elsewhere FEVS uses its own numbering and colliding codes can name different units. Needs a curated crosswalk of about 130 rows. Never join on code. |
| 4 | Historical org names | 186 pre-2012 sub-element codes render as codes because the name history starts where our lookups do. |
| 5 | Repo location | In iCloud Drive by explicit decision. The sweep mitigates; it does not fix. |
| 6 | Product surface | No sharing, no saved views, no alerting. Deliberate. |

## 9. Decisions worth not relitigating

1. **Measures, not fact tables, are the product.** The 18-dimension monthly fact tables continue for 2025 onward as the researcher download and the engine behind the map and in-browser query, and stop there.
2. **Money is direct obligations only.** Reimbursable obligations double count across government.
3. **In-sourcing means labor substitution:** personnel over personnel plus contracted services from non-federal sources. Services bought from other federal agencies are shown and never in the ratio.
4. **Actions are attributed to their effective month,** which means recent months revise upward as later files arrive.
5. **Redaction is a measure, not a footnote.** The disclosed share is itself published, and every geographic view states it.
6. **Nodes are not stitched across reorganizations.** A code that disappears ends its series; the tree shows it.
7. **PLUM organizations that sit below OPM's reporting level roll up to their agency** rather than inventing a node.
