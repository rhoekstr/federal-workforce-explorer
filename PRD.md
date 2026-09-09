# Federal Workforce Explorer — Product Requirements Document

**Working title:** Federal Workforce Explorer (repo: `opm_search`; Awry Labs name TBD)
**Version:** 1.1
**Status:** draft
**Created:** 2026-09-09
**Updated:** 2026-09-09 (v1.1: agency overview from USAspending and OMB; MVP defined; runbook added)
**Author:** Robert Hoekstra, with Claude (workshop session 2026-09-09)

Every number in this document was measured against the July 2026 OPM files on 2026-09-09 unless stated otherwise. Re-verify before relying on them in code.

---

## 1. Overview / Problem Statement

OPM publishes record-level data on the entire executive-branch civilian workforce every month, and a separate statutory list of every executive and political appointee. Both are public, free, and almost nobody can use them. The workforce files are 1.7 GB of pipe-delimited text per month behind an interactive Blazor page. The PLUM list is a ten-row-at-a-time search box. OPM's own dashboards answer OPM's questions, not a reader's.

In 2025 and 2026 the federal workforce changed faster than at any point since the 1990s: reductions in force, the deferred resignation program, agency eliminations, and reorganizations. The record of that change exists, monthly, in these files. There is no place a journalist, a federal employee, a researcher, or a curious citizen can go to see it as a trend, drill into their own agency, and understand what moved.

This project builds that place. It is a static, privacy-first, browser-only dashboard over OPM's Federal Workforce Data (FWD) and PLUM releases, published under Awry Labs, that lets anyone explore headcount, hires, and separations over time for any part of the federal government, navigate the organizational tree, see who leads each unit, and download the cleaned data.

**Who has this problem:** federal employees who want to see their own agency's trajectory; journalists covering the workforce; researchers who need a cleaned, versioned, reproducible cut of the FWD releases; the general public.

**Why it matters:** the workforce is the government. Making its changes legible is a transparency function the source agency has chosen not to perform beyond the raw release.

## 2. Goals and Non-Goals

### Goals

1. **Trends, not snapshots.** Headcount, accessions, and separations as monthly time series for any node of the organizational tree, with separations broken out by category (quit, retirement, RIF, DRP, and so on).
2. **The org chart is the index.** A classic collapsed org chart is the primary selector. Selecting a node re-scopes every view.
3. **Leadership in context.** PLUM executives and political appointees appear on the org chart nodes they lead, and a searchable executive directory with per-person timelines sits alongside.
4. **Geography that is honest about redaction.** A county choropleth with a persistent "N% of this selection has no disclosed location" indicator, because 47% of the workforce is redacted.
5. **Reproducible, downloadable data.** Every published month is a versioned parquet on GitHub Releases, with lookups and a data dictionary. Anyone can rebuild the site from the releases.
6. **Zero backend, zero telemetry.** Static site on GitHub Pages. All queries run in the visitor's browser. Nothing leaves the visitor's machine except range requests to GitHub.
7. **Runs itself.** A monthly GitHub Actions cron discovers new OPM files, rebuilds, publishes, and opens an issue only when a human needs to look at something.
8. **People next to money.** A cross-government overview and a per-agency overview that put FWD headcount beside official OMB FTE, personnel compensation, contracted services, and the split between dollars the agency administers and dollars it runs on, from USAspending. The entry point is government-wide, then agency, then down the org chart into personnel detail alone.

### Non-Goals

1. **No individual lookup.** The product does not identify, search for, or display any non-executive employee. FWD contains no names and the product does not try to add them.
2. **No record-level linkage between PLUM and FWD.** Measured on July 2026: using only keys PLUM also carries (sub-element, duty station, pay plan, series), 23% of SES rows are unique and 46% sit in cells of five or fewer, before salary. A "fuzzy" match would be a deterministic re-identification for a large share of career executives, attaching age bracket, education, veteran status, and service computation date to a named person. Those are exactly the fields OPM de-identifies. Not doing it, under any framing.
3. **No pay analysis beyond what aggregation supports.** Exact salary is dropped from the fact table. Averages survive through summed measures; distributions survive through $10k bands.
4. **No competition with OPM's table builder.** The dashboard has a small number of well-chosen views. The general query surface is the downloadable parquet.
5. **Not a FOIA-named-data product.** FederalPay and FedsDataCenter exist. This is not that.

## 3. User Stories

- As a **federal employee**, I want to select my sub-element on the org chart and see headcount over the last 18 months with separations by category, so I can see what actually happened to my bureau rather than what I heard.
- As a **journalist**, I want to compare separation rates across cabinet departments month by month, filter to RIF and DRP, and export the underlying rows, so I can report a number with a citation.
- As a **researcher**, I want to download every month's fact table as parquet with a stable schema and a data dictionary, so I can run my own analysis without scraping OPM.
- As a **reader**, I want to click an agency on the org chart and see who runs it, their appointment type, and when they started, so I know whether the leadership is career or political.
- As a **reader**, I want a map of where an agency's employees are, with a clear statement of how much of the agency is missing from the map.
- As a **reader**, I want to look up an executive by name and see every PLUM position they have held, so I can trace a career across agencies.
- As a **reader**, I want to see, for every agency on one page, how many people it has, what it spends on them, how much of its service work is contracted out, and how much money it administers versus runs on, so I can tell a benefits-paying agency from an operating one before I drill in.
- As the **maintainer**, I want the site to update itself monthly and tell me only when a mapping needs my attention.

## 4. Technical Architecture

### 4.1 Shape

Three parts, all in one GitHub repository:

1. **Pipeline** (Python, runs in GitHub Actions on a monthly cron and on manual dispatch). Discovers, downloads, aggregates, and publishes.
2. **Data** (GitHub Releases for parquet; small JSON in the repo). The published, versioned artifact.
3. **Site** (static HTML, ES modules, no build step; GitHub Pages). Reads data from the repo and from Releases.

### 4.2 Stack decisions and why

| Choice | Decision | Why |
|---|---|---|
| Site framework | None. Static HTML, ES modules from pinned CDN URLs. | Six views and a tree do not need routing or state management. Matches the Embedding Playground and Mosaic pattern. Keeps the privacy claim auditable: view source. |
| In-browser query | DuckDB-WASM | Queries parquet directly over HTTP range requests from GitHub Releases. No server. Handles 1M-row fact tables comfortably. |
| Charts | Observable Plot (pinned) | Grammar-of-graphics API; small; SVG output is accessible and printable. |
| Map | County choropleth over Census TIGER (simplified TopoJSON in repo) | Duty station lookup carries state and county FIPS, so no geocoding is needed. City points are a later layer requiring a one-time geocode of ~10k city-state pairs. |
| Org chart | Plain HTML boxes with CSS connectors in a horizontally scrolling container | Classic look without a layout library. Collapses to an indented list on mobile. |
| Pipeline language | Python with DuckDB | The July employment file loads and aggregates in seconds in DuckDB. Fits `code-python` conventions and the existing loader pattern in `code-apis`. |
| Data format | Parquet, ZSTD | Dictionary encoding does most of the compression work; DuckDB-WASM reads it natively with range requests. |
| Storage | GitHub Releases for parquet; repo for JSON slices and lookups | Releases have a 2 GB per-file limit and do not count toward repo size. Repo stays small and fast to clone. |
| Hosting | GitHub Pages, path under awrylabs.com | Consistent with the other Awry Labs web apps. |

### 4.3 Data flow

```
OPM FWD metadata API ──► discover new (dataset, year, month, version)
        │
        ▼
OPM FWD blob path ──► download .txt (employment ~1.7 GB, actions ~15 MB)
        │
        ▼
DuckDB ──► raw parquet (kept on Releases, ~55 MB/month, for reproducibility)
        │
        ├──► fact_employment_YYYYMM.parquet  (~15 MB)
        ├──► fact_accessions_YYYYMM.parquet  (small)
        ├──► fact_separations_YYYYMM.parquet (small)
        ├──► lookups/*.json (merged with prior months; first_seen / last_seen)
        └──► slices/*.json (pre-computed dashboard series, a few KB each)
        
OPM PLUM download endpoint ──► plum_YYYYMMDD.csv (~3 MB)
        │
        ├──► plum/positions.parquet (current + historical rows, deduplicated across snapshots)
        ├──► plum/people.json (unique ID → timeline)
        ├──► crosswalk apply + auto-match + drift report
        └──► leadership overlay per org node

GitHub Release (tag = data-YYYYMM) ◄── parquet
Repo commit ◄── JSON slices, lookups, crosswalk additions, manifest.json
GitHub Issue ◄── only if the drift report is non-empty or a download failed
```

### 4.4 Source access (verified 2026-09-09)

**FWD metadata API.** `GET https://data.opm.gov/api/v1/files/{employment|accessions|separations}` with optional `year`, `month`, `version`, `current`, `publishedAfter`, `publishedBefore`. No auth. Returns JSON like:

```json
[{"filename":"employment_202607_1","publishDate":"2026-09-02T13:44:22.923Z","version":1,"current":true,"month":"07","year":"2026"}]
```

Filenames carry a version suffix. OPM re-publishes files, so the pipeline keys on `(dataset, year, month, version)` and treats a new version of an old month as a rebuild of that month.

**FWD file download.** The API page describes parquet downloads but no parquet URL works. The site's download button calls:

```
GET https://data.opm.gov/data/blob/download/chunked/{filename}.txt
```

which streams pipe-delimited text with a header row and no quoting. This is not a documented contract. The pipeline must verify the header row against the expected schema and fail loudly on drift.

**PLUM.** The page at opm.gov/about-us/open-government/plum-reporting/plum-data/ calls an unpublished JSON API at `https://escs.opm.gov/escs-net/api/pbpub`. `GET /download-data` with an empty JSON body returns the full CSV (15,777 rows, 2.8 MB, June 15 2026 as-of). Also present and worth probing in Phase 3: `get-historical-incumbencies`, `get-historical-positions`, `filter-records`. Same caveat: undocumented, verify the header.

**Legacy FedScope.** Quarterly cubes back to 1998 exist under opm.gov/data with a different schema. Out of scope until Phase 4.

**USAspending, agency list.** `GET https://api.usaspending.gov/api/v2/references/toptier_agencies/` returns 111 toptier agencies with `toptier_code` (CGAC-style, e.g. `1601` Labor, `097` Defense, `096` Corps of Engineers civil works), `agency_id`, abbreviation, budget authority, obligations, outlays, and the active fiscal year and quarter. No auth. Saved to `data/reference/usaspending_toptier_agencies.json`.

**USAspending, object class by period (File B).** The per-agency `object_class` endpoint returns names only, no codes, and annual totals only. The bulk account download does carry codes and periods:

```
POST https://api.usaspending.gov/api/v2/download/accounts/
{"account_level":"treasury_account",
 "filters":{"fy":"2026","quarter":"3","submission_types":["object_class_program_activity"],"agency":"all"},
 "file_format":"csv"}
```

Returns a status URL and a zip URL; the job finishes in under a minute. FY2026 through P09 is a 92 MB CSV with 137k rows: one row per treasury account, program activity, object class code, and funding source, with `obligations_incurred` cumulative fiscal-year-to-date as of the submission period. Agency is `agency_identifier_code` (three-digit, e.g. `016` Labor) plus `agency_identifier_name`. The `agency` filter by id did not work for Labor; pulling all agencies per quarter is simpler and only three pulls are needed for a rolling four quarters. Saved sample: `data/raw/usaspending_fileB_FY2026_P01-P09.csv`.

**FEVS (Federal Employee Viewpoint Survey).** Last administered 2024; none in 2025. Two usable products, both unauthenticated:

- *Agency-level index reports* (small xlsx, one row per agency, five survey years of history). Employee Engagement Index: `https://www.opm.gov/fevs/reports/data-reports/index-results-by-agency/employee-engagement-index-results-by-agency/2024/2024-ee-report-excel.xlsx`. Global Satisfaction, Performance Confidence, and Employee Experience follow the same path pattern. 93 rows including size-group subtotals; Labor is present; Defense is split into Air Force, Army, Navy, and OSD/agencies, which matches the overview groups.
- *Report by Agency* (`.../data-reports/report-by-agency/2024/2024-agency-report-excel.xlsx`): one sheet per item, 50 agencies, weighted percentages per response option. No sub-agency rows.
- *Public Release Data File* (respondent-level, weighted, at `https://www.opm.gov/media/xywc4uyy/2024_opm_fevs_prdf_revised.zip`). **The 2024 file as published on 2026-09-09 is corrupt**: 87,320 rows for Agriculture, Air Force, and Army, then 127 MB of null bytes. Its codebook shows the intended `level1` field uses OPM sub-element codes (e.g. `AG05`, `HS04`, `DD07`), the same keys as our org tree. The 2023 file is intact (625,568 rows, 31 agencies) but has no `level1`. The intent-to-leave item is `DLEAVING` (no / yes other / yes within government / yes outside government). Saved: `data/reference/fevs/`.

**OMB FTE.** FY2027 Analytical Perspectives, Table 5-1 "Federal Civilian Employment in the Executive Branch", FTE in thousands by agency, FY2024 and FY2025 actual, FY2026 and FY2027 estimate. Published as `https://www.whitehouse.gov/wp-content/uploads/2026/04/ap_5_tables_1-3_fy2027.xlsx`, sheet `Table 5-1`, agency label in column A, four year columns, cabinet agencies then other agencies then totals. About 60 rows. Refreshed once a year when the budget drops; the URL pattern changes each cycle, so this is a manual annual update with the file committed to `data/reference/`. Saved: `data/reference/omb_ap_fy2027_tables_5-1_to_5-3.xlsx`.

### 4.5 Site structure

The navigation is a funnel: government, then agency, then org chart, with money present at the first two levels and personnel detail alone below.

- `/` — cross-government overview: one row per agency (overview group) with headcount, OMB FTE, personnel compensation, contracted services, in-sourcing ratio, dollars administered, dollars for operations, and twelve-month headcount change. Sortable. Government-wide totals and the headcount, accessions, and separations series above it.
- `/agency/{group}` — agency overview: the same measures as a card set with rolling-four-quarter money and monthly people, the object class split as a bar, the FTE series from OMB beside the FWD headcount series, and the agency's org chart collapsed below. Leads into the tree.
- `/org` — the org chart, full screen, with search. Selecting a node routes to `/org/{code}`.
- `/org/{code}` — the node page, personnel only: trend lines, separations by category, grade and step mix, age mix, map, leadership box, and a download link for the filtered rows. No money below agency level, because USAspending has no payroll below toptier.
- `/map` — county choropleth for the current selection with the disclosure indicator.
- `/executives` — PLUM directory: search by name, title, agency, appointment type; person timeline pages.
- `/data` — every release, schema, data dictionary, methodology, caveats.
- `/about` — what this is, what it is not, privacy statement.

Selection state lives in the URL so every view is linkable.

## 5. Data Model

### 5.1 Principles

- **Star schema.** One fact table per dataset per month. Small lookups keyed by code. Labels never appear in fact tables.
- **Strict coarsening of the source.** Everything published is derivable from OPM's public release by dropping or bucketing columns. The product never adds information about an individual.
- **Codes are stable, names drift.** Lookups keep a name history by month. Sub-element codes embed their agency code as a prefix (verified on all 516), so node selection is a prefix filter on one column.
- **The tree is time-varying.** Every org node carries `first_seen` and `last_seen`. Nodes that vanish stay in the tree, marked.

### 5.2 Fact table: `fact_employment_YYYYMM`

Grain: one row per distinct combination of the 18 dimensions below within a monthly snapshot.

| Column | Type | Source | Notes |
|---|---|---|---|
| snapshot_yyyymm | string | snapshot_yyyymm | |
| org_code | string | agency_subelement_code | Prefix-filterable. 516 values. |
| duty_station_code | string | duty_station_code | 15,562 values plus sentinel `NDS` for "not disclosed". Resolves city, county, state, country, CBSA, CSA, locality via lookup. |
| series_code | string | occupational_series_code | 665 values. Resolves group, PATCO category, STEM via lookup. |
| pay_plan_code | string | pay_plan_code | 177 values. |
| grade | string | grade | 214 values, pay-plan-specific. |
| step_code | string | step_or_rate_type_code | 91 values. |
| pay_band | string | derived | floor(annualized_adjusted_basic_pay / 10000) × 10, as `"120"`; `"R"` if redacted. |
| supervisory_code | string | supervisory_status_code | 7 values. |
| work_schedule_code | string | work_schedule_code | 11 values. |
| appointment_type_code | string | appointment_type_code | 20 values. |
| position_occupied_code | string | position_occupied_code | 5 values. Not determined by appointment type; kept separately. |
| tenure_code | string | tenure_code | 5 values. Same. |
| age_bracket | string | age_bracket | 12 values. |
| education_bracket | string | education_level_bracket | 6 values. |
| veteran | string | veteran_indicator | Y/N. |
| flsa_code | string | flsa_category_code | 3 values. |
| pay_basis_code | string | pay_basis_code | 7 values. |
| n | int | sum(count) | Headcount. |
| pay_sum | double | sum(annualized_adjusted_basic_pay) | Over disclosed rows only. |
| pay_n | int | count of disclosed pay | Denominator for average pay. |
| los_sum | double | sum(length_of_service_years) | Denominator is n. |

Measured on July 2026 at this grain minus pay band: 1,410,836 rows, 14.9 MB parquet. With pay band the estimate is roughly 1.6M rows and 18 MB. Dropped from the source: exact pay, service computation date, length of service in tenths, bargaining unit (3 fields), personnel office identifier, CFO Act flag (derivable from org lookup), and every label column.

### 5.3 Fact tables: `fact_accessions_YYYYMM`, `fact_separations_YYYYMM`

Same dimensions and measures, with these changes:

- `snapshot_yyyymm` is replaced by `file_yyyymm` (the OPM file the action came from) and `effective_yyyymm` (personnel_action_effective_date_yyyymm). Both are kept so either attribution can be used. See Open Question 3.
- Accessions add `accession_category_code` (4 values) and `pathways_group`.
- Separations add `separation_category_code` (9 values) and `drp_indicator`.
- `appointment_not_to_exceed_date` is dropped.

Measured on July 2026: accessions 19,024 records, separations 16,681 records, before aggregation. The July separations file contains actions with effective months spanning 25 distinct months; 78% are July, 13% June.

### 5.4 Lookups (JSON in repo, merged across months)

| Lookup | Key | Fields | Rows |
|---|---|---|---|
| `org` | org_code | agency_code, department_code, name (current), name_history[{yyyymm, name}], cfo_act, first_seen, last_seen, headcount_latest | 516 + parents |
| `duty_station` | duty_station_code | city, county_fips, state, country, cbsa_code, csa_code, locality_code, first_seen, last_seen | 15,562 + `NDS` |
| `series` | series_code | name, group_code, group_name, category_code, category_name, stem, stem_type | 665 |
| `pay_plan` | pay_plan_code | name | 177 |
| `step` | step_code | name | 91 |
| `codes` | (table, code) | name for every small enumerated dimension | few hundred |
| `cbsa`, `county` | code | name, state, and TopoJSON id | for the map |

All lookups were verified as functional dependencies of their key on July 2026 with zero violations, so the decomposition is lossless.

### 5.5 Org tree

Built from the `org` lookup. Node = department → agency → sub-element, except that 124 of 125 departments contain exactly one agency, so those two levels collapse to one node in the UI. Defense is the exception (four agencies, 172 sub-elements). 104 agencies have a single sub-element and render as leaves under a "small agencies" group.

Each node carries: code, name, parent, children, first_seen, last_seen, headcount series (18 months), and a leadership list from PLUM.

### 5.6 PLUM

`plum/positions.parquet`: one row per (position id, individual unique id, begin date), deduplicated across monthly snapshots, with `first_snapshot` and `last_snapshot`. Fields as delivered: agency, organization, title, status, appointment type, expiration, level/grade/pay, duty location, first name, last name, individual unique id, pay plan, tenure, begin date, vacate date.

`plum/people.json`: individual unique id → ordered list of positions held. June 2026 file: 9,816 individuals, 2,287 with more than one row.

`crosswalk/plum_org.json`: normalized (agency, organization) → org_code, with `method` (exact | normalized | auto | manual), `confidence`, `matched_on`, `note`. Unmapped organizations roll up to the agency node. June 2026: 1,442 distinct pairs, 322 exact matches to sub-element names before normalization.

`crosswalk/review.json`: the current drift queue. Non-empty means an issue is open.

### 5.7 Pre-computed slices (JSON in repo)

Small series so the landing page paints before DuckDB-WASM loads:

- government-wide headcount, accessions, separations by category, by month
- the same per agency (top level) and per sub-element
- grade mix, age mix, step mix per node for the latest month
- disclosure share per node

Target: every slice under 50 KB; the full set under 5 MB.

### 5.8 Agency overview

**Overview group.** The unit of the overview is a group, because the three sources disagree on what an agency is. FWD splits Defense into Army, Navy, Air Force, and other; USAspending has `097` Defense and `096` Corps of Engineers civil works; OMB has "War, military programs" and "Corps of Engineers, civil works". `crosswalk/agency_groups.json` defines each group once:

```json
{"group":"dol","name":"Department of Labor",
 "fwd_agency_codes":["DL"],"usaspending_toptier_codes":["1601"],"usaspending_aid_codes":["016"],
 "omb_ap_labels":["Labor"]}
```

About 60 groups cover every agency OMB lists; the remaining small FWD agencies map to USAspending where a toptier code exists and carry no FTE. Curated once; drift is rare and surfaces as an unmapped FWD agency or toptier code in the build log.

**`overview/agency_period.parquet`** (also emitted as JSON for the landing page): one row per group per period.

| Column | Definition |
|---|---|
| group | from agency_groups |
| period | fiscal quarter label, e.g. `FY2026Q3` |
| headcount | FWD `n` summed over the group at the quarter's last month |
| headcount_latest | FWD at the latest published month |
| headcount_change_12m | headcount minus headcount twelve months earlier |
| fte_omb | OMB Table 5-1 value × 1,000 for the fiscal year (actual if available, else estimate, flagged) |
| personnel | rolling four quarters of object classes 11.1 through 11.9, 12.1, 12.2, 13.0 |
| contracted_services | rolling four quarters of 25.1 (advisory and assistance) plus 25.2 (other services from non-federal sources) |
| federal_services | rolling four quarters of 25.3, shown but excluded from the ratio |
| insourcing_ratio | personnel ÷ (personnel + contracted_services) |
| administered | rolling four quarters of 41 grants, 42 insurance claims and indemnities, 43 interest, 44 refunds, 33 investments and loans, 94 financial transfers |
| operations | rolling four quarters of 11 through 13, 21 through 26, 31, 32 |
| other | everything else (91, 99, and any code not classified) |
| personnel_per_head | personnel ÷ headcount |

**Rolling four quarters.** File B obligations are cumulative fiscal-year-to-date. For a quarter ending at period P of fiscal year Y:

```
rolling(Y, P) = YTD(Y, P) + [ YTD(Y-1, 12) − YTD(Y-1, P) ]
```

Three File B pulls per refresh: current year through P, prior year full, prior year through P. Negative obligations (deobligations) are kept as delivered.

**Definition of in-sourcing ratio.** Labor substitution only: employee compensation and benefits against services bought from non-federal parties. Object class 25.3 (services from other federal agencies) is excluded because it is neither in-house nor contractor labor. Class 25.4 through 25.8 (facilities, equipment, research, medical care, subsistence) are excluded because they buy things, not labor substitution. The page states this definition next to the number.

### 5.9 FEVS beside staffing (Phase 2)

FEVS is a leading indicator; separations are the outcome. The product puts them side by side at the agency level and says plainly that the survey is from 2024 and the separations are from 2025 and 2026.

**`overview/fevs_agency.parquet`** (and JSON): one row per overview group per survey year, 2020 through 2024: engagement index, global satisfaction, performance confidence, employee experience, response rate, and, from the Report by Agency, the weighted share answering "considering leaving" by reason. Joined to the group through `omb_ap_labels`-style name matching in `agency_groups.json` (`fevs_labels`).

**Views.** On the agency page: the 2020 to 2024 engagement and satisfaction lines, the 2024 intent-to-leave split, and beside them the 2025 to 2026 monthly separation rate by category. On the landing table: 2024 engagement and intent-to-leave as two sortable columns next to twelve-month headcount change, so the reader can see whether the agencies that said they were leaving are the ones that left.

**Sub-element level** only if OPM re-publishes an intact 2024 respondent file with `level1`. Then intent-to-leave and engagement can be computed per sub-element for units with 500 or more respondents, joined on code, and shown on node pages. Until then, FEVS stops at the agency.

**Caveats the page must carry.** Weighted percentages, not counts. Response rates vary by agency. No 2025 survey. The 2024 survey fielded before the 2025 reductions, which is exactly why it is useful as a baseline and useless as a description of the current workforce.

### 5.10 Manifest

`manifest.json`: list of published months per dataset with OPM version, publish date, release tag, row counts, and checksums. The site reads this first.

## 6. Dependencies and Constraints

- **OPM endpoints are undocumented or partially documented.** Both file paths were captured from page behavior. Expect breakage; design for loud failure and manual re-run.
- **OPM re-publishes months.** Version numbers exist in filenames. The pipeline rebuilds a month when a new version appears and records both in the manifest.
- **Redaction is structural.** 47% of employees have location, pay, locality, and bargaining unit withheld as a block. Defense is 100%, DHS 76%, Justice 66%, Treasury 17%. Every geographic and pay view must carry the disclosure share for the current selection.
- **Department of War data gap.** June and July 2026 files are missing some DOW components. OPM says they will republish. The manifest and the site must be able to flag a month as "incomplete per OPM".
- **Naming drift.** The July file says "Department of Defense"; the site says "Department of War". Names are display attributes with history, never keys.
- **PLUM cadence.** Agencies must update at least annually. Freshness varies by agency. The directory shows the as-of date per row.
- **GitHub Actions runner.** 7 GB RAM, 14 GB disk, 6-hour job limit. The 1.7 GB employment download plus DuckDB aggregation fits with streaming. Do not load the text file into pandas.
- **GitHub limits.** 100 MB per file in the repo, 2 GB per Release asset, 1 GB soft Pages limit. Parquet goes to Releases; the repo stays under 100 MB.
- **Unknown OPM rate limit.** The API documents a 429 response. Be polite: one download per file, retries with backoff, no parallel fetches.
- **Browser memory.** DuckDB-WASM over an 18 MB parquet is fine on desktop and modern phones; the slices cover mobile-first views so WASM is optional there.
- **Privacy.** No analytics, no third-party requests except pinned CDN scripts and GitHub. Fonts self-hosted or system.
- **Accessibility.** Charts get text alternatives and data tables; the org chart is keyboard navigable; color is never the only encoding.

## 7. Open Questions

| # | Question | Status | Default if unresolved |
|---|---|---|---|
| 1 | Executive directory scope: all PLUM positions (including Schedule C, PAS, PA) or SES only? | open 2026-09-09 | All. Schedule C is where the 2025–2026 churn is and it is not visible anywhere else. |
| 2 | Show exact salary on executive person pages? PLUM publishes it by name under statute. | open 2026-09-09 | Show it in the position row, not in headline. It is public by design of the PLUM Act. |
| 3 | Action time attribution: effective month (restates history as late actions arrive) or file month (never restates, smears events)? | open 2026-09-09 | Effective month for charts, with a "revised since last release" marker; file month kept in the fact table. |
| 4 | History depth: start at January 2026 or backfill legacy FedScope quarterly cubes (different schema, 1998 onward)? | open 2026-09-09 | Start 2026. Backfill is Phase 4 and only at the coarse grain the cubes support. |
| 5 | Product name under Awry Labs. | open 2026-09-09 | "Federal Workforce Explorer" as a descriptive working title. |
| 6 | Hosting path: awrylabs.com/{name} in the site repo, or a separate repo with a custom subpath? | open 2026-09-09 | Separate repo (pipeline, releases, and issues need their own home), published to a subpath of awrylabs.com via Pages. |
| 7 | Whether PLUM's `get-historical-incumbencies` endpoint carries more than the CSV's Historical rows. | open 2026-09-09 | Probe in Phase 3. |
| 8 | Whether to keep raw (unaggregated) parquet on Releases for reproducibility, ~55 MB/month. | open 2026-09-09 | Yes. Cheap, and it means re-aggregation never requires re-downloading from OPM. |
| 9 | Suppression of small cells? The source publishes record level, so the fact table adds no exposure, but a k-threshold on displayed cells (not stored) may be wise for the UI. | open 2026-09-09 | No suppression in data; UI displays "fewer than 5" for cells under 5 in any view that names a duty station. |
| 10 | In-sourcing ratio definition. | **resolved 2026-09-09** | Labor substitution: personnel (11–13) ÷ (personnel + 25.1 + 25.2). See 5.8. |
| 11 | Dollars administered vs operations. | **resolved 2026-09-09** | Two numbers, split by object class as in 5.8. |
| 12 | Time alignment of money and people. | **resolved 2026-09-09** | Rolling four fiscal quarters of obligations against headcount at the quarter's last month, plus latest-month headcount. |
| 13 | FTE source. | **resolved 2026-09-09** | OMB Analytical Perspectives Table 5-1, refreshed annually by hand. FWD headcount shown beside it, never blended. |
| 14 | Where the overview lives. | **resolved 2026-09-09** | Landing page is the cross-government table; agency page carries the card set; org nodes below agency are personnel-only. |
| 15 | OMB's FY2026 and FY2027 FTE are estimates and reflect the administration's plan, not actuals. How to label them. | open 2026-09-09 | Show actuals as solid and estimates as hollow points, with "OMB estimate" in the tooltip. Never compute a ratio on an estimate. |
| 16 | FEVS in conversation with staffing. | **resolved 2026-09-09** | Agency level, Phase 2, per 5.9. Sub-element level contingent on OPM fixing the 2024 respondent file. Worth emailing OPMDataHelp about the null-byte file. |

## 8. Implementation Phases

Each phase ships something usable on its own.

**MVP is Phase 0 plus Phase 1.** It is the funnel from government to agency to org node with people and money at the top two levels and personnel detail below, running on the monthly cron, with the data downloadable. It does not include the map, PLUM, or legacy history. The autonomous build plan for the MVP is `RUNBOOK.md`.

### Phase 0 — Pipeline and data (one month)

- Repo scaffold, Python project, DuckDB loader for one employment file and both action files.
- Schema validation against the expected header. Fail loudly.
- Aggregation to the Section 5 grain; lookups; manifest.
- Publish parquet to a Release; commit lookups, slices, manifest.
- `/data` page listing what exists, with the data dictionary.
- **Deliverable:** a versioned, documented, downloadable clean cut of July 2026.

### Phase 1 — Dashboard MVP

- Agency groups crosswalk (FWD ↔ USAspending ↔ OMB), curated.
- USAspending File B pulls (three per refresh), classification to personnel, contracted, federal services, administered, operations, other; rolling four quarters.
- OMB Table 5-1 loader.
- `overview/agency_period` table and JSON.
- Landing page: cross-government table plus government-wide series.
- Agency page: overview cards, object class split, FTE beside headcount, collapsed org chart.
- Org chart, classic collapsed tree, FWD nodes only, search, URL state.
- Node page: headcount, accessions, separations by category, grade and step mix, age mix, download.
- DuckDB-WASM filter panel over the fact table.
- Monthly cron with discovery, rebuild, publish, and failure issue.
- **Deliverable:** live site covering every month since January 2026 and the last rolling four quarters of money, government to agency to node.

### Phase 2 — Geography and FEVS

- County choropleth from TIGER TopoJSON; disclosure indicator everywhere geography appears.
- Duty station lookup with FIPS; CBSA view.
- FEVS agency-level indices and intent-to-leave (5.9) on the agency page and landing table.
- **Deliverable:** map view for any node with honest coverage; survey baseline beside separations.

### Phase 3 — PLUM

- PLUM download, snapshot, dedupe, people timelines.
- Crosswalk: auto-match, one-time manual curation, drift report, issue automation.
- Leadership overlay on org nodes (rolled up to nearest mapped node).
- Executive directory with search and person pages.
- Aggregate PLUM-to-FWD reconciliation by agency: filled vs vacant, career vs political, ES headcount comparison.
- **Deliverable:** who leads what, and how the executive layer moved.

### Phase 4 — History and polish

- Legacy FedScope backfill at coarse grain, if Open Question 4 resolves yes.
- City points layer.
- Reorganization view: nodes appearing and vanishing over time.
- Performance pass, accessibility audit, methodology write-up.

## 9. Security and Privacy Considerations

- The site makes no requests except to its own origin, GitHub Releases, and pinned CDN script URLs. No analytics, no cookies, no local storage beyond UI preferences.
- The published data is a strict coarsening of OPM's public release. No field is added, no record is linked to a name, and the three most identifying continuous fields are dropped or bucketed.
- PLUM data is published by statute for the express purpose of identifying these office-holders. The product displays it as delivered and does not enrich it from FWD at the record level.
- The crosswalk maps organizations to org codes. It never maps people.
- The pipeline runs with a GitHub token scoped to the repository. No OPM credentials exist.

## 10. Testing Strategy

- **Schema tests:** header of every downloaded file matches the expected column set; fail the run otherwise.
- **Invariant tests on every build:** sum of `n` equals the source row count; pay_n ≤ n; every fact `org_code` exists in the lookup; every `duty_station_code` exists in the lookup or is `NDS`; functional dependencies still hold (a violation means OPM changed something).
- **Golden-month test:** July 2026 aggregates to the recorded row count and checksum.
- **Crosswalk tests:** every mapped target exists in the current org lookup; no organization maps to two codes.
- **Site tests:** slices load without WASM; every node URL resolves; keyboard traversal of the org chart; chart text alternatives present.
- **Acceptance for Phase 1:** a user can go from the landing page to a Labor sub-element, see 18 months of headcount with separations by category, and download the rows behind it, in under three clicks.

## 11. Launch Plan

- Phase 0 and 1 ship to a subpath of awrylabs.com with a "beta" mark and a methodology page.
- Announce on the Awry Labs blog with the July 2026 numbers as the worked example.
- Monitoring is the cron's failure issue. No uptime service; it is a static site.
- Rollback is a Pages redeploy of the previous commit; data releases are immutable.

---

## Appendix A — Measured facts, July 2026 employment file

| Fact | Value |
|---|---|
| Rows / employees | 2,020,230 |
| Columns | 64 |
| Text size | 1.69 GB |
| Raw parquet (ZSTD) | 55 MB |
| Departments / agencies / sub-elements | 125 / 128 / 516 |
| Duty stations / cities / counties / states | 15,562 / 10,405 / 1,789 / 54 |
| Occupational series / groups | 665 / 60 |
| Pay plans / grades / steps | 177 / 214 / 91 |
| Distinct exact salaries | 99,206 |
| Distinct service computation dates | 19,131 |
| Location and pay redacted | 47% (DOD 100%, DHS 76%, DOJ 66%, Treasury 17%, VA 1%) |
| Aggregation, 16 dims (base + duty station) | 1,136,425 rows, 12.0 MB |
| Aggregation, 17 dims (+ step) | 1,410,836 rows, 14.9 MB |
| Aggregation, 17 dims (+ pay band, no step) | 1,227,175 rows, 13.3 MB |
| Aggregation, 19 dims (+ step, pay band, LOS band) | 1,592,627 rows, 18.2 MB |
| SES headcount (pay plan ES) | 6,647 |

## Appendix B — Measured facts, PLUM June 15 2026 file

| Fact | Value |
|---|---|
| Rows | 15,777 (Filled 6,846; Vacant 2,951; Historical 5,980) |
| Distinct individuals | 9,816 (2,287 with more than one row) |
| Appointment types | CA 6,285; SC 3,861; NA 2,056; PAS 1,447; XS 1,372; PA 502; TA 125; CG 118 |
| Pay plans | ES 8,546; GS 3,761; OT 1,171; EX 938; AD 568; SL 219 |
| Filled ES positions | 6,457 (FWD ES headcount 6,647) |
| Agencies / organizations | 174 / 1,442 pairs |
| Organizations matching an FWD sub-element name exactly | 322 |
| Begin date filled / vacate date filled | 15,777 / 5,980 |

## Appendix D — Measured facts, USAspending and OMB (2026-09-09)

| Fact | Value |
|---|---|
| USAspending toptier agencies | 111 |
| File B FY2026 P01–P09, all agencies | 137,390 rows, 92 MB CSV, generated in under a minute |
| Labor FY2026 YTD P09, insurance claims (42.0) | $41.1B |
| Labor, grants (41.0) | $10.0B |
| Labor, full-time permanent comp (11.1) | $1.27B |
| Labor, civilian benefits (12.1) | $0.52B |
| Labor, services from non-federal sources (25.2) | $1.06B |
| Labor, advisory and assistance (25.1) | $0.20B |
| Labor, services from federal sources (25.3) | $1.26B |
| Labor budgetary resources FY2022–FY2026 | $73.3B, $64.1B, $71.3B, $76.0B, $92.6B |
| OMB Table 5-1 rows | ~60 agencies; FY2024, FY2025 actual; FY2026, FY2027 estimate |
| OMB Labor FTE (thousands) | 15.4, 14.8, 13.0, 10.7 |
| OMB Agriculture FTE (thousands) | 91.2, 88.6, 78.1, 59.1 |

Sanity check on the in-sourcing definition for Labor, FY2026 YTD: personnel ≈ $1.8B, contracted (25.1 + 25.2) ≈ $1.26B, ratio ≈ 0.59. Including 25.3 would drop it to 0.42 and misstate purchases from other agencies as contractor labor.

## Appendix E — Measured facts, FEVS (2026-09-09)

| Fact | Value |
|---|---|
| 2024 EEI report rows | 93 (agencies plus size-group subtotals), 2020–2024 columns |
| Governmentwide EEI 2024 / 2023 / 2022 | 73.0 / 71.7 / 70.5 |
| Governmentwide Global Satisfaction 2024 / 2020 | 65.4 / 68.7 |
| 2024 Report by Agency | 98 sheets (one per item), 50 agency rows, 670,623 item responses total |
| 2024 PRDF as published | 87,320 valid rows (AG 40,305; AF 28,490; AR 18,489; XX 36), then null bytes; 20 `level1` codes |
| 2024 PRDF intent to leave (3 agencies) | no 52,170; yes-other 10,378; yes-within-government 15,673; yes-outside 3,713 |
| 2023 PRDF | 625,568 rows, 31 agencies, weighted total 1.69M, no `level1` |

## Appendix C — Re-identification test (why Non-Goal 2 exists)

Uniqueness of FWD SES rows (pay plan ES, n = 6,647) given keys PLUM also carries:

| Keys | Unique rows | Rows in cells ≤ 5 |
|---|---|---|
| sub-element + duty station + pay plan | 12% | 24% |
| + occupational series | 23% | 46% |
| sub-element + state + pay plan | 8% | 21% |
| agency + state + pay plan | 3% | 11% |

GS-15 at sub-element + duty station + series: 18% unique. Salary, which PLUM often carries exactly, would push the SES figures toward near-total uniqueness.
