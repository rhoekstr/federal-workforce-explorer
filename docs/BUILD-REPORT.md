# Build report — autonomous MVP run, 2026-09-09

Run executed against `RUNBOOK.md` in one Claude Code session on Robert's Mac, starting from PRD v1.1 and the reference data in `data/reference/`.

## 1. Milestones

| Milestone | Result | Notes |
|---|---|---|
| M0 scaffold | passed | |
| M1 employment aggregation + lookups | passed | 13 golden tests. Lookups restructured (codes-only duty station, separate county/CBSA/locality/country tables) to meet the 5 MB budget: 3.1 MB. |
| M2 actions | passed | |
| M3 discovery + all months | passed | Employment, accessions, separations for January 2025 through July 2026 (19 months, 57 files, 0 failures). See §3 for counts. |
| M4 money overview | passed | 118 groups, 95 with money. Labor: personnel $2.1B, contracted $1.7B, ratio 0.56, within the acceptance band. |
| M5 slices + org tree | passed | 674 nodes; slices 5.6 MB total. |
| M6 site | passed | Three-click path verified in the in-app browser: landing → Labor row → BLS box → download link and working DuckDB-WASM query. Screenshots in `docs/screenshots/`. |
| M7 publish + automate | **partial** | Repo created (private), pushed, Releases published. **Pages could not be enabled: the account is on the free plan and Pages requires a public repo.** The deploy job is gated on repository variable `PAGES_ENABLED`; the refresh job runs green. See §5. |

## 2. Deviations from PRD and RUNBOOK, and why

1. **Direct obligations only.** File B includes reimbursable obligations (22% of Defense, 8% of Labor), which double count across agencies. All money figures use `direct_or_reimbursable_funding_source = 'D'`. Recorded in `CLAUDE.md` and on the data page. PRD 5.8 should say so.
2. **Fact parquet ships with the site as well as on Releases.** Release assets on a private repo are not anonymously fetchable, so DuckDB-WASM could not read them. `_site/data/facts/` carries every month's fact parquet (~9 MB each). Releases remain the archival copy with raw parquet.
3. **2025 was built, not just 2026.** The twelve-month change column on the landing page needs the prior year. The runbook default was January 2026 onward; the data is the same schema and the cost was runner time only.
4. **Money "quarter end" headcount** uses the closest available month at or before the quarter end.
5. **Screenshots** were taken with headless Chrome rather than the in-app browser (which cannot save images).
6. **Restore step** downloads published fact parquet only; raw parquet is restored only with `--raw`, since lookups are committed and only new months need raw.

## 3. Months published

Nineteen months per dataset, January 2025 through July 2026. All sums of `n` equal the source row counts.

| Month | Employment rows → fact rows (MB) | Accessions | Separations |
|---|---|---|---|
| 2025-01 | 2,304,585 → 1,676,147 (10.1) | 22,325 → 18,550 | 22,271 → 21,149 |
| 2025-02 | 2,272,018 → 1,653,666 (10.1) | 9,746 → 7,819 | 15,620 → 14,808 |
| 2025-03 | 2,289,192 → 1,660,958 (10.0) | 4,889 → 3,732 | 22,084 → 20,816 |
| 2025-04 | 2,271,969 → 1,646,271 (9.9) | 7,193 → 5,657 | 24,135 → 22,592 |
| 2025-05 | 2,255,056 → 1,631,839 (9.8) | 8,953 → 7,074 | 26,616 → 24,690 |
| 2025-06 | 2,241,780 → 1,615,722 (9.6) | 10,070 → 7,627 | 20,029 → 18,506 |
| 2025-07 | 2,224,444 → 1,600,357 (9.5) | 7,841 → 6,168 | 22,825 → 21,290 |
| 2025-08 | 2,218,561 → 1,593,915 (9.6) | 8,469 → 6,638 | 18,377 → 17,216 |
| 2025-09 | 2,190,219 → 1,572,473 (9.4) | 12,017 → 8,601 | 121,014 → 110,647 |
| 2025-10 | 2,097,534 → 1,501,884 (8.9) | 5,902 → 3,933 | 12,526 → 11,742 |
| 2025-11 | 2,084,618 → 1,488,733 (8.9) | 11,976 → 9,119 | 19,584 → 18,385 |
| 2025-12 | 2,074,649 → 1,479,675 (8.8) | 8,381 → 6,956 | 30,139 → 29,020 |
| 2026-01 | 2,035,344 → 1,447,423 (8.6) | 15,423 → 12,020 | 37,883 → 35,117 |
| 2026-02 | 2,027,301 → 1,440,813 (8.6) | 8,997 → 7,422 | 16,988 → 16,296 |
| 2026-03 | 2,023,318 → 1,438,072 (8.7) | 15,100 → 12,881 | 21,991 → 21,140 |
| 2026-04 | 2,021,167 → 1,436,531 (8.7) | 16,021 → 13,394 | 15,571 → 14,783 |
| 2026-05 | 2,025,993 → 1,439,853 (8.6) | 24,325 → 19,729 | 17,872 → 17,008 |
| 2026-06 | 2,029,748 → 1,436,063 (8.7) | 16,610 → 13,252 | 16,299 → 14,895 |
| 2026-07 | 2,020,230 → 1,438,035 (8.7) | 19,024 → 15,271 | 16,681 → 15,482 |

## 4. Crosswalk review (`crosswalk/review.json`)

- FWD agencies with no USAspending counterpart (headcount > 300): Smithsonian Institution (4,096), Government Publishing Office (1,625), Federal Reserve System (1,069), Federal Housing Finance Agency (599), Farm Credit Administration (317).
- USAspending agencies with no FWD counterpart: 11 (tiny commissions and boards; none over the 1,000-headcount threshold).
- OMB labels without a group: Tennessee Valley Authority.
- FEVS labels without a group: 11 (Phase 2 concern).


## 5. URLs

- Repo: https://github.com/rhoekstr/federal-workforce-explorer (private)
- Releases: `data-YYYYMM` tags, one per month, fact parquet plus raw parquet.
- Pages: not enabled (free plan, private repo). To publish: make the repo public, enable Pages with source "GitHub Actions", set repository variable `PAGES_ENABLED=true`, dispatch the workflow. Expected URL: https://rhoekstr.github.io/federal-workforce-explorer/
- Workflow: green run https://github.com/rhoekstr/federal-workforce-explorer/actions/runs/34420881208 (dispatch with since=202608: restored 57 fact files from Releases, found nothing new at OPM, rebuilt money and slices, assembled the site, committed the refreshed data). Two earlier dispatches failed in the restore step (anonymous 404 on private Release assets, then a transient GitHub 500); both fixed in `pipeline/restore.py`. The failure-issue step could not create issues because the `pipeline` and `crosswalk` labels do not exist yet; create them or drop the `--label` flags.

## 6. What the PRD got wrong or did not know about the sources

- **History is not a Phase 4 problem.** The FWD metadata API lists the same schema back to March 2005: quarterly through 2011, monthly from July 2011, 207 employment files and 259 action files. Legacy FedScope cubes are unnecessary. (PRD Open Question 4 updated.)
- **The `count` column** in FWD files exists and is always 1.
- **File B object class endpoint** on the agency API has no codes; the bulk account download does. PRD 4.4 already says this; confirmed.
- **File B agency identity**: `owning_agency_name` matches the toptier list's `agency_name` exactly, so no CGAC/FREC mapping is needed.
- **CFPB** has no FWD rows at all; it has an OMB FTE line. The group carries FTE without headcount.
- **OMB Table 5-1** also lists Tennessee Valley Authority, which is in neither FWD nor USAspending.
- **Reimbursable obligations** (deviation 1).
- **OPM re-publishes months with version suffixes** (2025 months are at v3 and v4). The manifest keys on version, so a re-publication rebuilds the month.

## 7. Tests

`pytest`: 20 passed (13 golden checks on the July 2026 files, 7 money checks). The final run took 7.5 minutes instead of seconds because Release uploads were saturating the disk at the same time; earlier runs were 2 to 4 seconds.
