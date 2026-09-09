# RUNBOOK — autonomous build to MVP

This is the execution plan for an unattended Claude Code session to take the repo from its current state (PRD, reference data, raw July 2026 files) to a working MVP as defined in `PRD.md` Section 8. Read `CLAUDE.md` first. Work milestone by milestone, verify each against its acceptance checks, commit at each boundary, and write the closing report described at the end.

## Pre-flight decisions (defaults apply unless the kickoff prompt overrides them)

| Decision | Default |
|---|---|
| GitHub repo | `rhoekstr/federal-workforce-explorer`, **private** until Robert flips it |
| Hosting during build | GitHub Pages on the project repo (`rhoekstr.github.io/federal-workforce-explorer/`). Cutover to an awrylabs.com path is a human step after review. |
| Product name in the UI | "Federal Workforce Explorer" |
| History depth | January 2026 through the latest published month |
| Action attribution | Effective month in charts; file month retained |
| Open questions in PRD Section 7 | Take every listed default |

## What already exists

- `PRD.md` — requirements, data model, measured facts. Authoritative.
- `CLAUDE.md` — hard rules, source endpoints, layout, definitions.
- `data/raw/` (gitignored) — `employment_202607_1.parquet` (raw, 2.02M rows, 64 columns, ZSTD), `separations_202607_1.txt`, `accessions_202607_1.txt`, `plum_2026-06-15.csv`, `usaspending_fileB_FY2026_P01-P09.csv`.
- `data/reference/` — FWD header files for all three datasets, `fwd_agencies_202607.json` (128 FWD agencies with headcount), `usaspending_toptier_agencies.json` (111), `omb_ap_fy2027_tables_5-1_to_5-3.xlsx`, `plum_header.txt`, and `fevs/` (2024 index and agency reports, codebook; FEVS is Phase 2, not MVP, but the agency labels are useful when seeding `agency_groups.json`, so add a `fevs_labels` field while curating).
- `.gitignore`, git initialized, no commits yet.
- `gh` is authenticated as `rhoekstr`.

## Environment

```bash
python3 -m venv .venv && .venv/bin/pip install duckdb pyarrow pandas openpyxl requests pytest
```

Pin whatever versions install into `pipeline/requirements.txt`. Node is not required; the site has no build. Use the in-app browser to verify pages by opening `site/index.html` through a local static server (`python3 -m http.server` from `site/` is fine; do not commit a server).

## Milestones

### M0 — Scaffold and first commit

- Create the layout in `CLAUDE.md`. Empty `__init__.py` files, `pipeline/requirements.txt`, `pytest.ini`, `README.md` (one paragraph, link to PRD).
- Commit: `M0 scaffold`.

**Accept:** `pytest` runs and collects zero tests without error.

### M1 — FWD employment: validate, aggregate, lookups

- `pipeline/fwd/schema.py`: expected headers loaded from `data/reference/*_header.txt`; `validate_header(path, dataset)` raises on mismatch.
- `pipeline/fwd/employment.py`: DuckDB transform from raw (text or the raw parquet in `data/raw/`) to `fact_employment_YYYYMM.parquet` at the PRD 5.2 grain. Pay band and `NDS` sentinel as defined. Measures `n`, `pay_sum`, `pay_n`, `los_sum`.
- `pipeline/fwd/lookups.py`: build `org`, `duty_station`, `series`, `pay_plan`, `step`, `codes` from the raw file; merge with any existing lookup JSON in `data/lookups/` preserving `first_seen`, `last_seen`, and `name_history`.
- Tests against `data/raw/employment_202607_1.parquet`: sum of `n` = 2,020,230; every fact `org_code` in `org`; every `duty_station_code` in `duty_station` or `NDS`; functional dependencies from PRD 5.4 hold; row count is within 5% of 1.6M; parquet under 25 MB.
- Commit: `M1 employment aggregation + lookups`.

**Accept:** tests pass; `data/work/fact_employment_202607.parquet` exists; `data/lookups/*.json` exist and total under 5 MB.

### M2 — FWD actions

- `pipeline/fwd/actions.py`: accessions and separations to fact tables per PRD 5.3, with `file_yyyymm` and `effective_yyyymm`, category codes, `drp_indicator`, `pathways_group`.
- Tests: sum of `n` = 19,024 (accessions) and 16,681 (separations) for July 2026; effective months span more than one value.
- Commit: `M2 actions aggregation`.

### M3 — Discovery, download, manifest, multi-month

- `pipeline/fwd/discover.py`: query the metadata API for each dataset; list `(dataset, year, month, version, filename, publishDate)`; compare with `manifest.json`.
- `pipeline/fwd/download.py`: stream the `.txt` to `data/raw/`, validate header, then convert to raw parquet. Retries with backoff. One file at a time.
- Run discovery for 2026 and download every month not already present (January through the latest). Expect roughly 1.7 GB per employment month; delete each `.txt` after its raw parquet is written to stay within disk.
- Build facts and lookups for every month. Update `manifest.json`.
- Tests: manifest lists every month; lookups carry `first_seen`/`last_seen` spanning the months; a sub-element that appears in one month and not another is handled.
- Commit: `M3 discovery + all 2026 months`.

**Accept:** every 2026 month published by OPM has three fact parquets in `data/work/` and `manifest.json` describes them with row counts and checksums.

### M4 — Money: agency groups, USAspending, OMB

- `crosswalk/agency_groups.json`: seed by matching `data/reference/fwd_agencies_202607.json` to `usaspending_toptier_agencies.json` by normalized name, then to OMB Table 5-1 labels. Hand-resolve the known cases in PRD 5.8 (Defense, Corps of Engineers, "War"). Write unmatched items to `crosswalk/review.json`. Every FWD agency with headcount over 1,000 must be in a group.
- `pipeline/money/usaspending.py`: request File B for the three periods needed for the rolling four quarters (current FY through latest closed quarter; prior FY full; prior FY same quarter), poll, download, load with DuckDB, classify object class codes per PRD 5.8, compute rolling values per group.
- `pipeline/money/omb.py`: parse `Table 5-1` to `(label, fy, fte, actual|estimate)`.
- `pipeline/money/overview.py`: `overview/agency_period.parquet` and `data/slices/overview.json` per PRD 5.8, joining FWD headcount at the quarter's last month and the latest month.
- Tests: Labor rolling personnel is within 20% of $2.4B annualized and the in-sourcing ratio is between 0.5 and 0.7; administered plus operations plus other equals total obligations per group; every group with FTE has a headcount.
- Commit: `M4 money overview`.

**Accept:** `data/slices/overview.json` has one row per group with every column in PRD 5.8 populated or explicitly null with a reason.

### M5 — Slices and org tree

- `pipeline/slices.py`: government-wide and per-node series (headcount, accessions, separations by category, by month); grade, step, age mix per node for the latest month; disclosure share per node. Each file under 50 KB; total under 5 MB.
- `pipeline/orgtree.py`: `data/slices/orgtree.json` from the `org` lookup: nodes with code, name, parent, children, first_seen, last_seen, headcount series, collapsed department/agency per PRD 5.5, "small agencies" group.
- Commit: `M5 slices + org tree`.

### M6 — Site

No build. Pinned CDN scripts for DuckDB-WASM and Observable Plot. Mobile-first. State in URL.

- `site/index.html` — cross-government table from `overview.json`, sortable, with the government-wide series above it.
- `site/agency.html?g=` — overview cards, object class split bar, OMB FTE beside FWD headcount (estimates hollow), collapsed org chart for the agency.
- `site/org.html?code=` — classic collapsed org chart (HTML boxes, CSS connectors, horizontal scroll, indented list on mobile), search, node page below with trend lines, separations by category, grade/step/age mix, disclosure badge, and a download link to the Release parquet plus a DuckDB-WASM filter panel that queries it over range requests.
- `site/data.html` — manifest, schema, data dictionary, methodology, caveats (redaction, DOW gap, attribution, definitions).
- `site/about.html` — what it is, what it is not, privacy statement.
- Accessibility: every chart has a data table alternative; org chart is keyboard navigable; color never the only encoding.
- Commit: `M6 site`.

**Accept (Phase 1 acceptance from PRD 10):** from the landing page, reach a Labor sub-element, see 2026 headcount with separations by category, and download the rows behind it, in three clicks. Verify in the in-app browser and save screenshots to `docs/screenshots/`.

### M7 — Publish and automate

- Create the GitHub repo per pre-flight (private), push.
- Upload fact parquets to a Release tagged `data-YYYYMM` per month; record asset URLs in `manifest.json`; the site reads parquet from those URLs.
- Enable Pages from the `site/` directory (or a `gh-pages` branch built by copying `site/` plus `data/slices`, `data/lookups`, `manifest.json`).
- `.github/workflows/monthly.yml`: cron on the 5th of each month plus `workflow_dispatch`; runs discovery, builds new months, uploads Releases, commits slices and manifest, redeploys Pages; opens an issue on failure or when `crosswalk/review.json` is non-empty. Use the default `GITHUB_TOKEN`.
- Run the workflow once by dispatch and confirm it is green.
- Commit: `M7 publish + cron`.

**Accept:** the Pages URL serves the site; DuckDB-WASM loads a parquet from a Release URL in the browser; the workflow has one green run.

## Guardrails

- If a source header does not match, stop that dataset, record the diff in the closing report, and continue with everything else.
- If OPM returns 429 or 5xx repeatedly, back off to a minute between attempts and stop after five failures for that file.
- Never commit anything in `data/raw/` or `data/work/`. Never commit a file over 50 MB.
- Do not create public repos, custom domains, or anything on awrylabs.com. Do not delete Releases.
- Do not add analytics, fonts from third parties, or any network call the PRD does not list.
- If a milestone's acceptance check fails after two honest attempts, leave it failing, note it, and move on. Do not lower the check.

## Closing report

Write `docs/BUILD-REPORT.md` and put its summary in the final message:

1. Which milestones passed acceptance and which did not, with the failing check quoted.
2. Every deviation from PRD or RUNBOOK and why.
3. Months published, with row counts and parquet sizes per dataset.
4. `crosswalk/review.json` contents that need Robert's eyes.
5. The Pages URL, the Release tags, and the workflow run URL.
6. Anything discovered about the sources that PRD 4.4 or Appendix A through D got wrong.
