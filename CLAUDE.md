# Fed Pulse — repo instructions

Awry Labs project (product name: Fed Pulse; repo keeps its original name). Static, privacy-first dashboard over OPM Federal Workforce Data (FWD), PLUM, USAspending, and OMB FTE. Read `PRD.md` before changing scope; read `RUNBOOK.md` before building. Every number in those documents was measured on the July 2026 files on 2026-09-09.

## Hard rules

- **No individuals.** FWD has no names and the product never adds them. No lookup, search, or display of any non-executive employee. No record-level linkage between PLUM and FWD under any framing (PRD Non-Goal 2, Appendix C).
- **Strict coarsening.** Everything published is derivable from OPM's public release by dropping or bucketing columns. Never add a field about a person.
- **No telemetry, no backend.** The site makes requests only to its own origin, GitHub Releases, and pinned CDN script URLs. No analytics, no cookies, no third-party fonts.
- **Codes are keys, names are display.** Fact tables carry codes only. Labels live in lookups with name history.
- **Fail loudly on schema drift.** Every downloaded file's header is checked against `data/reference/*_header.txt`. A mismatch stops the run and reports; it never guesses.
- **Never load the FWD employment text file into pandas.** It is 1.7 GB. Use DuckDB `read_csv` with `delim='|'`, `quote=''`, `all_varchar=true`.
- **Do not re-download what is in `data/raw/`.** July 2026 FWD files, the June 2026 PLUM CSV, and a USAspending File B sample are already there (gitignored). Use them for development and tests.

## Sources (verified 2026-09-09; all unauthenticated)

| Source | Discovery | Fetch |
|---|---|---|
| FWD metadata | `GET https://data.opm.gov/api/v1/files/{employment,accessions,separations}?year=&month=` | — |
| FWD files | filename from metadata | `GET https://data.opm.gov/data/blob/download/chunked/{filename}.txt` (pipe-delimited, undocumented path) |
| PLUM | — | `GET https://escs.opm.gov/escs-net/api/pbpub/download-data` with JSON body `{}` → CSV |
| USAspending agencies | `GET https://api.usaspending.gov/api/v2/references/toptier_agencies/` | — |
| USAspending File B | `POST https://api.usaspending.gov/api/v2/download/accounts/` (see PRD 4.4) | poll status URL, fetch zip |
| OMB FTE | manual, annual | `data/reference/omb_ap_fy2027_tables_5-1_to_5-3.xlsx`, sheet `Table 5-1` |

Be polite to OPM: one download per file, exponential backoff on 429, no parallel fetches.

## Layout

```
pipeline/        Python package: discover, download, validate, aggregate, publish
  fwd/           employment, accessions, separations loaders
  plum/          PLUM loader, crosswalk apply, drift report
  money/         USAspending File B, OMB FTE, overview table
  tests/         pytest; golden checks against data/raw
site/            static site, no build: index.html, agency/, org/, data/, js/, css/
data/
  reference/     headers, agency lists, OMB xlsx, crosswalk seeds (committed)
  raw/           downloaded source files (gitignored)
  work/          intermediate parquet (gitignored)
  slices/        pre-computed JSON for the site (committed, small)
  lookups/       org, duty_station, series, pay_plan, step, codes (committed)
crosswalk/       agency_groups.json, plum_org.json, review.json (committed, curated)
manifest.json    what is published, versions, checksums
.github/workflows/  monthly.yml (cron), on-demand rebuild
```

## Conventions

- Python 3.12+, DuckDB for every transform, pyarrow for parquet writing, pytest. A `.venv` in the repo root. Pin versions in `pipeline/requirements.txt`.
- Site: plain HTML and ES modules, pinned CDN URLs for DuckDB-WASM and Observable Plot. Mobile-first. Semantic HTML, keyboard paths, text alternatives for every chart. Selection state lives in the URL.
- Follow `code-base` and `code-web` conventions: small functions, explicit errors, no clever indirection.
- Commit at milestone boundaries listed in `RUNBOOK.md` with messages that name the milestone.
- Parquet goes to GitHub Releases (`data-YYYYMM` tags). Nothing over 50 MB is committed to the repo.

## Definitions that must not drift

- Fact grain: PRD 5.2. Eighteen dimensions, four measures.
- Not-disclosed sentinel: duty_station_code `NDS`.
- Pay band: `floor(pay / 10000) * 10` as a string; `R` if redacted.
- In-sourcing ratio: personnel (11.x, 12.x, 13.0) ÷ (personnel + 25.1 + 25.2). Class 25.3 is shown, never in the ratio.
- Administered vs operations: PRD 5.8.
- Rolling four quarters: `YTD(Y,P) + YTD(Y-1,12) − YTD(Y-1,P)`. Direct obligations only (`direct_or_reimbursable_funding_source = 'D'`); reimbursable double counts across government.
- Action attribution: charts use effective month; file month is kept in the fact table.

## Operational gotchas (learned 2026-09-09)

- **Never run `sync` and `publish` at the same time.** Both load, modify, and save `manifest.json`; the later save wins and drops the other's months. The monthly workflow runs them in sequence.
- **Do not build tables with pyarrow's `from_pylist`.** It imports pandas, which hung indefinitely in this environment. Write parquet through DuckDB.
- **Early 2025 files have blank sub-element codes** on a few hundred rows. They map to `<agency>__` ("Unspecified sub-element") so the prefix rule holds.
- **OPM re-publishes months** with a version suffix (2025 months are at v3 and v4). The manifest keys on version.
