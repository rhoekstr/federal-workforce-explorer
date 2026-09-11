# Fed Pulse measures model

**Status:** design, 2026-09-11 (revised: no append-only ledger; values are recomputed and replaced each run). Supersedes the fact-table-first architecture in PRD 5.2 through 5.8 as the primary product; the fact tables remain a secondary product for 2025 onward.
**Lineage:** a simplification of the Evince manifest and measurement model (`~/Desktop/Code/Evince/evince-prd.md` §1.7–1.8, `docs/architecture.md` A3, A4, A9, A16, A17, A19; `src/Evince.Domain/Measurement/*`). What was kept, what was dropped, and why, is in §7.

## 1. The idea in one paragraph

Fed Pulse stops being a warehouse of row-level cuts and becomes a **registry of measures with value series at every organizational level the source supports, over the longest history the source offers**. Raw files are read once and discarded. Each measure is described once in a catalog (its operational definition, unit, cadence, category, lag, since-date, and, for derived measures, its calculation). Values are facts: measure, node, period, value, count, notation, and which source file produced them. The site is an explorer over that registry: any measure, any node, any span, trended against any other. Twenty-one years of workforce data, fifteen of money, and every survey we can join, on one time axis.

## 2. Objects

Five, down from Evince's dozen.

### 2.1 Measure (the catalog entry)

`catalog/measures.json`, one entry per measure code. Every value in the system must resolve to an entry; an undescribed measure is a pipeline error (Evince A19).

| Field | Type | Meaning |
|---|---|---|
| code | string | Stable identifier, e.g. `quit_rate`. Never reused. |
| title, description | string | Display. |
| definition | string | Operational definition: precise enough that two people produce the same number (Evince 1.7). For derived measures, generated from the calculation and editable (Evince 67). |
| kind | base \| derived | ISO 15939 tiers (Evince 1.7). |
| unit | count \| people \| percentage \| ratio \| currency \| years \| dollars_per_person \| index | Evince `UnitCategory`, trimmed. |
| format, digits | number \| percentage \| currency; int | Display. |
| aggregation | sum \| latest \| average \| manual | Evince `TemporalAggregation`, trimmed. How sub-periods roll up to a coarser period. |
| extensiveness | extensive \| intensive | Evince A16. Authored on base measures; derived on derived measures from the pattern. Governs cadence reconciliation and disaggregation. |
| category | demand \| input \| process \| output \| outcome \| contextual | Evince's modified SIPOC (1.8). Recorded and shown, not a blocking gate. Contextual measures are overlays and never get a rating. |
| cadence | month \| quarter \| fiscal_year \| survey_year | Native period type. |
| year_type | calendar \| federal_fiscal | Evince A9. Federal fiscal year starts in October; survey years are labeled by the year the survey fielded. |
| lag_days | int | Typical delay between period end and value availability. Informational. |
| since, until | period | First and last period the measure can be computed, from the source's era. Employment detail before 2010 lacks step, tenure, veteran, STEM, bargaining unit, and duty station codes. |
| levels | [gov, department, agency, subelement, group] | Which node kinds carry values. |
| dimensions | [dim codes] | Optional. A dimensioned measure also carries values split by these dimensions (Evince 11: composition and dimensionality are orthogonal). |
| sources | [{name, url}] | Evince 59, simplified: name and URL. |
| calculation | see 2.4 | Derived only. |
| lifecycle | active \| retired | Retired measures keep their history. |
| supersedes | code | When a definition changes meaning, a new code supersedes the old (Evince 48, 57). Clarifications are edits. |

### 2.2 Node

`catalog/nodes.json`, from the existing org tree plus the overview groups.

| Field | Meaning |
|---|---|
| code | `gov`, `D:DOD`, `DL`, `DLLS`, or a group id such as `dol` |
| kind | gov \| department \| agency \| subelement \| group |
| name, name_history | display; codes are keys (unchanged rule) |
| parent | tree parent; groups point at their agency nodes through `members` |
| first_seen, last_seen | from the workforce files |

Lineage across reorganizations is not stitched. A code that disappears ends its series; a new code starts one. The tree makes that visible; the values do not pretend otherwise.

### 2.3 Value (the fact)

`measures.parquet`, rebuilt every run. One row per measure, node, period, and dimension value.

| Column | Meaning |
|---|---|
| measure | catalog code |
| node | node code |
| period_type, period_start | e.g. `month`, `2025-09-01`; `fiscal_year`, `2024-10-01`; `survey_year`, `2023-01-01` |
| dim, dim_value | null for flat values; e.g. `grade`, `13` |
| value | decimal, null when notated |
| n | the count behind the value (respondents, employees, records); the denominator for shares |
| notation | null \| estimate \| incomplete \| suppressed \| not_available (Evince `ValueNotation` plus 143) |
| source_ref | e.g. `fwd:separations_202507_4`, `fileb:FY2026Q3`, `omb:AP-FY2027-T5-1`, `fevs:2023-prdf`; carries the OPM version suffix so a restated month is visible in the record |

Rules, from Evince decisions 64 and 143 (the append-only ledger of A3 is deliberately not adopted; this is a dashboard, not a system of record):

- **Every run recomputes everything and replaces the table.** A re-published OPM month, a later File B, or a late-arriving personnel action simply produces new numbers. `source_ref` records which version produced the current value; no history of prior values is kept.
- **A lagged result is dated to the period it describes.** Separations by effective month, FEVS by field year, File B by fiscal quarter. Charts show the period; the catalog states the typical lag.
- **Incomplete periods are flagged, not silently summed.** A fiscal year with ten of twelve months carries `notation = incomplete`. Months OPM marks as missing Department of War submissions carry it too.
- **Sorted by node, then measure, then period**, so a browser can range-request one node's block.

### 2.4 Calculation (derived measures)

Exactly one of three patterns, composed by layering, never nested (Evince A17):

| Pattern | Shape | Example |
|---|---|---|
| additive | signed sum of components | `net_change = accessions − separations` |
| ratio | one numerator over one denominator | `quit_rate = quits / headcount@−1` |
| time_offset | a measure at a shifted period | `headcount@−12` for year-over-year |

Each component is aggregated to the derived measure's cadence by its own aggregation rule before the pattern applies. A ratio is always intensive. An additive's components must share extensiveness. Missing components yield `notation = not_available`, never zero. Recomputation is total, not incremental: the evaluator is cheap enough to rerun every derived measure each run, which removes the staleness ledger Evince needs.

Complex measures layer: `first_year_attrition_rate` is a ratio of `first_year_separations` (base, sum, extensive) over `accessions@−12..−1` (an additive over twelve time offsets, materialized as `accessions_trailing_12`).

### 2.5 Link

Only two link types survive from Evince's typed graph, and both live inside the catalog rather than in a table: `component_of` (implicit in each calculation, with a `lagging` flag on time offsets) and `supersedes`. Cycle detection runs on the catalog at load time. Time offsets are lagging edges and excluded, as in Evince 140.

## 3. The catalog, first release

Category is the modified SIPOC. Since-dates reflect the source era. Levels: G government, D department, A agency, S sub-element, P overview group.

### 3.1 Workforce stock (month, aggregation latest, intensive, from the employment snapshot)

| code | title | unit | category | since | levels | note |
|---|---|---|---|---|---|---|
| headcount | Employees on the rolls | people | input | 2005-03 | G D A S | |
| supervisor_share | Supervisors and managers as a share of employees | percentage | process | 2005-03 | G D A S | |
| span_of_control | Non-supervisors per supervisor | ratio | process | 2005-03 | G D A S | derived: ratio |
| permanent_share | Career and career-conditional appointments | percentage | input | 2005-03 | G D A S | |
| temp_share | Temporary and term appointments | percentage | input | 2005-03 | G D A S | |
| fulltime_share | Full-time work schedule | percentage | input | 2005-03 | G D A S | |
| gs13_plus_share | GS-13 and above, of GS employees | percentage | input | 2005-03 | G D A S | |
| under_30_share | Age under 30 | percentage | contextual | 2005-03 | G D A S | |
| age_55_plus_share | Age 55 and over | percentage | contextual | 2005-03 | G D A S | |
| retirement_eligible_share | Estimated retirement-eligible | percentage | outcome | 2005-03 | G D A S | definition below |
| bachelors_plus_share | Bachelor's degree or higher | percentage | input | 2005-03 | G D A S | |
| avg_service_years | Mean length of federal service | years | contextual | 2005-03 | G D A S | |
| avg_pay | Mean annualized basic pay, disclosed employees | currency | input | 2005-03 | G D A S | n = disclosed count |
| pay_disclosed_share | Share with pay disclosed by OPM | percentage | contextual | 2005-03 | G D A S | honesty measure |
| location_disclosed_share | Share with duty station disclosed | percentage | contextual | 2010-03 | G D A S | |
| veteran_share | Veterans | percentage | input | 2010-03 | G D A S | |
| stem_share | STEM occupations | percentage | input | 2010-03 | G D A S | |
| bargaining_unit_share | In a bargaining unit | percentage | process | 2010-03 | G D A S | field restored at aggregate level |

Retirement-eligible, operational definition: age bracket 62 and over with 5 or more years of service, or 60 and over with 20 or more, or 55 and over with 30 or more, using bracket lower bounds and length of service. It overstates slightly for the 55-to-59 bracket under FERS minimum retirement age rules and is labeled "estimated".

### 3.2 Workforce flows (month by effective month, aggregation sum, extensive, from the action files)

| code | title | category | since | levels |
|---|---|---|---|---|
| accessions | All accessions | output | 2005-01 | G D A S |
| new_hires | Accessions that are new hires, not transfers | output | 2005-01 | G D A S |
| transfers_in | Transfers from another agency | output | 2005-01 | G D A S |
| separations | All separations | outcome | 2005-01 | G D A S |
| quits | Voluntary separations other than retirement | outcome | 2005-01 | G D A S |
| retirements | Retirements, all types | outcome | 2005-01 | G D A S |
| rifs | Reductions in force | outcome | 2005-01 | G D A S |
| transfers_out | Transfers to another agency | outcome | 2005-01 | G D A S |
| deferred_resignations | Separations under the deferred resignation program | outcome | 2025-01 | G D A S |
| first_year_separations | Separations with under one year of service | outcome | 2005-01 | G D A S |

Derived (ratio, intensive, month): `quit_rate`, `retirement_rate`, `separation_rate`, `rif_rate`, `accession_rate`, each over `headcount@−1`; `net_change` (additive); `first_year_attrition_rate` over `accessions_trailing_12`; `churn` = (accessions + separations) / headcount@−1.

### 3.3 Money (fiscal quarter, rolling four quarters, groups only)

`personnel_obligations`, `contracted_services_obligations`, `federal_services_obligations`, `administered_obligations`, `operations_obligations` (currency, input, sum over the trailing four quarters, extensive, since FY2017Q4 when File B begins); `insourcing_ratio` (ratio, intensive); `personnel_per_head` (ratio to headcount at quarter end).

### 3.4 Annual and survey (fiscal year or survey year)

| code | title | unit | category | since | levels | source |
|---|---|---|---|---|---|---|
| omb_fte | Full-time equivalents, OMB | people | input | FY2024 | P | Analytical Perspectives; estimates notated |
| fevs_engagement | Employee Engagement Index | index | outcome | 2019 | A (S for 2019 and 2024 via crosswalk) | PRDF, validated |
| fevs_global_satisfaction | Global Satisfaction Index | index | outcome | 2019 | A | |
| fevs_performance_confidence | Performance Confidence Index | index | outcome | 2021 | A | |
| fevs_leave_any / _outside / _within / _other | Considering leaving, by reason | percentage | outcome | 2019 | A | 2019 codes remapped |
| fevs_pay_satisfaction, fevs_recommend, fevs_workload_reasonable | leading-indicator items | percentage | outcome | 2019 | A | |
| va_aes_* | VA All Employee Survey items and burnout | index / percentage | outcome | 2018 | VA nodes | data.va.gov, station level |
| osha_total_case_rate, osha_lost_time_case_rate | Injury and illness rates per 100 employees | rate | outcome | FY2011 | A | annual President's report; manual load |
| eeoc_complaints_per_1000, eeoc_findings | EEO complaint rate and findings | rate, count | process | FY2012 | A (Defense components) | Form 462 profiles; manual load |
| fitara_score | IT management scorecard, mapped to 0–4 | index | process | FY2015 | P | House Oversight; manual load |

Categorical sources (audit opinions) wait for a categorical value type; they are not forced into numbers.

### 3.5 Dimensioned measures

`headcount` carries dimensions grade, age_bracket, supervisory, appointment_type, pay_band, work_schedule, series, step (top eight values plus other, per node, as today). `separations` and `accessions` carry `category`. Everything else is flat.

## 4. Storage and delivery

- **Catalog:** `catalog/measures.json`, `catalog/nodes.json`, `catalog/dimensions.json` in the repo. Small, human-readable, reviewed like code.
- **Facts:** `measures.parquet` on a rolling `measures` Release, replaced each run. Estimated size: 60 measures × 700 nodes × 260 periods ≈ 11M flat rows plus dimensioned rows, well under 200 MB, sorted by node.
- **Slices for first paint:** government-wide series for every measure, and per-node current snapshots for government, departments, agencies. Everything below that is a browser range-request into `measures.parquet` by node.
- **Fact tables:** the 18-dimension monthly parquet continues for 2025 onward as the researcher download and the engine for the map and query panel. Not built for history.
- **Raw:** read once, deleted. The backfill runs locally in year chunks with a resumable manifest.

## 5. The site

The node page becomes a **measures explorer**: pick any measures, any nodes, any span; overlay on one time axis; native cadence respected (monthly lines, quarterly steps, annual points); every point's tooltip shows value, n, period, and the source file behind it. The four v0.2 panels survive as saved views of the explorer: Trend is the explorer with one node; Composition is a dimensioned measure at the latest period; Flows is two flow measures; Map stays on the fact tables. The vitals strip is the explorer's default selection per node kind, with agency-level values inheriting downward and labeled as such.

## 6. Pipeline shape

```
sources → extractors (one per source, emit base facts with as_of and source_ref)
        → catalog validation (every fact resolves; every period is a valid period for its cadence)
        → derived evaluator (three patterns, cadence reconciliation, notation propagation)
        → write measures.parquet → slices → publish
```

Extractors: `fwd_employment` (stock and dimensioned), `fwd_actions` (flows), `usaspending` (money), `omb`, `fevs`, `va_aes`, `osha` (manual table), `eeoc` (manual table), `fitara` (manual table). Each is a pure function from a source artifact to facts, testable against a golden file, and each declares the eras it supports so `since` is enforced rather than assumed.

## 7. What was kept from Evince, what was dropped

| Evince | Fed Pulse | Why |
|---|---|---|
| Manifest supertype with four subtypes | Measure only | No milestones, risks, or learning questions here. |
| Base and derived tiers; dimensionality orthogonal | Kept | The core discipline. |
| Append-only values, as-of, current projection (A3) | Dropped | Provenance-grade history is for a system of record. Here every run recomputes and replaces; `source_ref` names the version behind each value. |
| Lag dated to the period described (64) | Kept | Already our attribution rule. |
| Incomplete-period notation (143) | Kept | DOW gap, partial fiscal years. |
| Three derived patterns, layered (A17) | Kept | Makes rates decidable and definitions generatable. |
| Cadence reconciliation and disaggregation | Reconciliation kept; disaggregation dropped | We never spread an annual figure across months; annual points are drawn as points. |
| Recompute ledger and lazy evaluation (A5) | Dropped | Total recompute per run is seconds. |
| Targets, status, certification, drafts, tenants, RLS | Dropped | Nothing is authored; nothing is rated; one tenant; no users. |
| Modified SIPOC classification | Kept as a label, not a gate | Useful for the reader; no report gate exists to enforce. |
| Data dictionary drives validation (A19) | Kept | The catalog is the dictionary; undescribed measure is an error. |
| Typed link graph | Reduced to component and supersedes, inside the catalog | Two edge types do not need a table. |
| Fiscal year primitive (A9) | Kept as period types | Money and OMB are fiscal; workforce is calendar; surveys are labeled years. |
| Data source as text plus inventory URI (59) | Name plus URL | No inventory to point at. |
| Strongly-typed IDs, EF, Postgres | Strings, DuckDB, parquet | Static site. |

## 8. Open decisions taken as defaults

1. Fact tables continue for 2025 onward; measures only before. 
2. Backfill to 2005 with era-aware since-dates.
3. The explorer replaces the org-page panels, which become saved views.
4. Manual-load sources (OSHA, EEOC, FITARA) enter as committed CSVs with a documented transcription date, refreshed by hand annually.

## 9. Build plan (v0.3)

- **V1 catalog and evaluator.** `catalog/*.json`, the fact schema, the derived evaluator with tests on synthetic series (each pattern, missing components, incomplete periods, cadence reconciliation).
- **V2 extractors.** FWD stock and flows era-aware; money, OMB, FEVS, VA AES from what exists; OSHA, EEOC, FITARA as committed tables with loaders.
- **V3 backfill.** 2005 to 2024 workforce files, local, year chunks, resumable; publish `values.parquet` and `current.parquet`.
- **V4 site.** Measures explorer, saved views, vitals strip with inheritance, catalog page rendered from the dictionary.
- **V5 cron.** Monthly run recomputes, republishes, and reports which source versions changed.

Each milestone carries acceptance checks in the RUNBOOK style. V3 is the long pole: about 350 GB of downloads and ten hours of processing, run locally, and it needs an explicit go.
