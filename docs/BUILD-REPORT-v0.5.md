# Build report — Fed Pulse v0.5

Run of `docs/OVERNIGHT-v0.5.md`, 2026-09-12 into 2026-09-13.

## Milestones

| Milestone | Result | Notes |
|---|---|---|
| N0 preflight | passed | 44 tests, clean tree, prior CI run green with all three markers present. |
| N1 historical names | passed | All 165 nameless units named from 13 employment files. |
| N2 sub-agency FEVS 2019 | passed | 117 of 238 units mapped; every Labor value reproduces the exploration document exactly. |
| N3 OSHA | passed | 16 fiscal years, 27 agencies, through the validation gate. |
| N3 EEOC | **not shipped** | Does not clear the gate. Blocker below. |
| N4 reconciliation | passed | Found a real defect in the money measures on its first run. |
| N5 accessibility and weight | passed | Unit page 6.4 MB → 4.0 MB; three charts gained the data tables they lacked. |
| N6 deploy and verify | passed | Deployed, verified live, report written. |

## What each milestone produced

### N1 — 165 units that had no name

Sub-elements rendered as their own code (`ARXR`, `DLES`, `AM**`) because the org lookup only learns names from the months the fact pipeline processes, which is 2025 onward, while the measures history runs to 2005. Their headcount series were real and their labels were not.

A greedy covering set found **13 employment files** that name all 165. Each was downloaded, read for two columns, and deleted before the next. Acceptance targets all resolved:

| Code | Name |
|---|---|
| ARXR | U.S. Army Research, Development and Engineering Command |
| NV33 | Military Sealift Command |
| ARG6 | U.S. Army Network Enterprise Technology Command |
| DLES | Employment Standards Administration |

Codes OPM itself recorded as `INVALID` now read "Unrecorded sub-element", which is what they are.

**Deviation from the plan.** The plan said to merge names into the org lookup. That was wrong: these units are not in the lookup at all, which is *why* they had no name. The first run harvested all 165 and merged 0. The names are now committed as `data/reference/historical_names.json` and the node builder reads them.

### N2 — Sub-agency FEVS, 2019

2019 is the only public FEVS year with a sub-agency field. 117 of 238 units map to org nodes, **matched by name and never by code**, because FEVS codes coincide with OPM sub-element codes only for Defense, Treasury and Transportation, and a collision can name a different unit.

Validation against `docs/FEVS-EXPLORATION.md` section 10, computed independently here:

| Unit | Expected | Computed |
|---|---|---|
| Bureau of Labor Statistics, engagement | 76.4 | 76.4 |
| Mine Safety and Health, engagement | 61.5 | 61.5 |
| BLS, considering leaving | 35.8 | 35.8 |
| BLS, leaving government | 5.2 | 5.2 |

Unmapped units are left out rather than rolled into their agency: the agency already carries its own directly measured value, and a partial roll-up would corrupt it.

### N3 — OSHA shipped, EEOC blocked

**OSHA** publishes recordable and lost-time injury rates per 100 employees, per agency, per fiscal year. 860 facts, 27 agencies, FY2004 through FY2019. Labor's recordable rate falls from 2.35 to 1.39 across the series.

The gate the plan required was that each agency's published rate be recomputed from its own case count and employment. Worst year was 99.4% agreement; most were 100%. That is what proves the columns are aligned, which is what actually goes wrong in a scrape. Two parsing faults it caught: alias keys were not normalised the way the lookup normalises, and OSHA appends footnote digits to agency names that vary by year.

**OSHA has published nothing after FY2019**, so both measures carry an `until` and the catalog says the series ended.

**EEOC ships nothing.** Its per-agency complaint statistics live inside annual report PDFs. The profiles page and the Form 462 resources page both return 200 and carry no tables and no downloadable dataset. There is no artefact to parse, so there was nothing to put through the gate.

### N4 — Reconciliation, which found a real defect

The report compares sources that measure different things, so divergence is expected; the point is that an *unexplained* divergence becomes visible. On its first run it showed spending per employee at **$1.2M at Defense and $2.6M at OPM**.

The cause was a defect in the measure definition. `personnel_obligations` swept in:

- **11.7 and 12.2, military personnel and their benefits** — $157B at Defense, none of it civilian.
- **13.0, benefits for former personnel** — $455B at Defense, $3.7B at OPM. Retiree annuities, not pay.

Both pay populations this site's headcount does not contain. Personnel is now civilian current-employee compensation; military pay is its own measure; retiree annuities count as administered, which is what they are. Defense now reads **$127k per employee**.

Remaining flags carry a stated cause where one is known: State and USAID exclude Foreign Service personnel, GSA is paid from revolving funds this site excludes, OPM's object class 25.2 is health-benefit carrier payments rather than contracted labour. Eleven small agencies remain unexplained and are listed in the report.

The agency-sum invariant — agency headcount must equal the government total — is exact for every month.

### N5 — Accessibility and weight

- The unit page transferred **6.4 MB** because the query panel eagerly loaded a 2.7 MB duty-station table that a reader only needs after running a record-level query. Deferred: **4.0 MB**, under the 5 MB target. Pulse is 1.2 MB.
- Three charts had no data-table alternative: the Pulse hero, the two money split bars, and the survey chart. All now have one. The hero lists September of each year plus the endpoints rather than 259 rows.
- Every sortable table header is keyboard focusable; heading order is correct. The two figures that still report no data table are Observable Plot's own colour legends, not charts.

## Deviations from the plan

1. **N1's merge target was wrong** in the plan and in the first implementation. Described above.
2. **Three sources had to be committed as reference tables** rather than computed at build time: VA, OSHA, and 2019 sub-agency FEVS. Their source files live outside the repo, and CI silently dropped each one until it was committed. The 2019 case was caught by comparing row counts between the local and CI builds, which differed by exactly 585.
3. **N3 is half-shipped**, by design of the gate rather than by accident.

## The recurring failure, now three times

A source the build reads that CI cannot see gets silently dropped, and a green deploy is not evidence against it. It happened with PLUM, with VA, and again with sub-agency FEVS in this run. The pattern that catches it is comparing the CI build's row count to the local one; the pattern that prevents it is committing derived values as reference data. Every source now does the latter.

## Numbers

| | |
|---|---|
| Measures | 96 |
| Values | 12,220,956 |
| Nodes | 984, none unnamed |
| Earliest period | October 2003 (OSHA FY2004) |
| Sources | OPM workforce, USAspending, OMB, FEVS, PLUM, VA survey, OSHA |
| Tests | 44 passing, 2 skipped |

## Still open

- **EEOC complaint rates.** No machine-readable artefact exists; the data is narrative inside annual report PDFs.
- **FEVS after 2019 below agency level.** Blocked on OPM republishing an intact 2024 respondent file.
- **VA 2024 survey.** Tabular but keyed by unpublished item numbers.
- **Eleven unexplained reconciliation flags**, all small agencies.
- **The repo is in iCloud** by explicit decision. The sweep now runs before every command and before the test suite.
