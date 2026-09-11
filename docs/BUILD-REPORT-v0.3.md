# Build report — v0.3, the measures model

**Date:** 2026-09-11
**Plan:** `docs/MEASURES-MODEL.md` §9 (V1 catalog and evaluator, V2 extractors, V3 backfill, V4 site, V5 cron)
**Repo:** https://github.com/rhoekstr/federal-workforce-explorer · **Live:** https://fedpulse.awrylabs.com

## 1. Milestones

| Milestone | Result | Evidence |
|---|---|---|
| V1 catalog and evaluator | passed | 78 measures (46 base, 32 derived; 55 shown, 23 components). Three patterns with cadence reconciliation, carry-forward, notation propagation. 7 evaluator tests on synthetic series. Cycle detection and generated definitions verified. |
| V2 extractors | passed | Era-aware FWD employment and actions (31-, 62-, 64-column eras), USAspending rolling four quarters (36 fiscal quarters, FY2018 Q2 to FY2026 Q3), OMB FTE, FEVS 2019 to 2023 including government-wide. July 2026 reconciles exactly: 2,020,230 employees, 16,681 separations, 19,024 accessions. |
| V3 backfill | passed | 725 OPM files, 2005 to 2026, 722 extracted and 3 already present, 0 era errors, 0 failures, 8 h 49 min wall clock, run locally outside iCloud. Extracts 27 MB. |
| V4 site | passed | Explorer (any measures, any units, any span, native or indexed), catalog page rendered from the dictionary, vitals strip on org and agency pages. Verified locally: 21-year government headcount and quit-rate series draw; September 2025 spike visible. |
| V5 cron | passed with a caveat | Workflow gained extract, build, and publish steps; the extract archive restores from the rolling Release so CI never re-reads history. Deploy run https://github.com/rhoekstr/federal-workforce-explorer/actions/runs/34654373912 green (refresh and deploy). Live slices verified: government headcount series has 207 snapshots, March 2005 to July 2026. |

## 2. The table

| | |
|---|---|
| Rows | 12,141,293 (7.4M flat, 3.7M dimensioned, 0.4M zero-filled flows) |
| Nodes | 978: government, 4 departments, 132 agencies, 731 sub-elements (186 historical, code-named), and 118 overview groups |
| Measures | 78 |
| Months | 259, January 2005 to July 2026 |
| Quarters (money) | 34, FY2018 Q2 to FY2026 Q3 |
| Parquet | 32 MB, rolling `measures` Release |
| Site slices | 26 MB (per-node series for government, departments, agencies, groups; current snapshot for every node; catalog) |

Reconciliation: government headcount equals the sum of every agency code in every one of 259 months. Annual quit rate (sum of monthly rates) runs 3.6 to 4.9% from 2006 through 2024, 7.4% in 2025. Retirement-eligible share is 10.6% government-wide in July 2026. Notations: 126k estimate (OMB FY2026 and FY2027 rows and retirement-eligible shares), 98k not available (mostly early-period ratios before their components exist).

## 3. Decisions made during the build

- **Shares are derived, not extracted.** Every share is a ratio of two extracted counts, so it is correct at every roll-up level for free, and the count behind it is the `n` on the row. This is the Evince composition discipline doing real work.
- **Carry-forward for the prior-month denominator.** OPM published employment quarterly before mid-2011, so monthly rates would have existed four months a year. The time-offset pattern gained an optional carry-forward (up to two periods) used only by `headcount_prior_month`; the definition says so.
- **Zero-fill for flows.** A unit with a headcount but no quits in a month has zero quits, not an unknown number. Without this, trailing sums and first-year attrition went missing for small units. 395k zero rows, tagged `zero-fill` in `source_ref`.
- **Historical nodes are code-named.** 21 agencies and 165 sub-elements appear in the history but not in the current OPM files, so the lookups have no names for them. They exist as nodes with their code and first and last seen. None of the agencies exceeded 233 employees. A names side-file from the next extraction pass will fill them in.
- **Dimensioned values stop at agency level.** Headcount by grade, age, and so on is stored for government, departments, and agencies. Sub-elements keep the v0.2 trend slices for 2025 onward.
- **Money begins FY2018 Q2**, the first quarter with four trailing quarters of File B behind it.

## 4. What the history shows at a glance

| | Mar 2005 | Sep 2015 | Sep 2020 | Jan 2025 | Jul 2026 |
|---|---|---|---|---|---|
| Headcount | 1,844,598 | 2,071,716 | 2,181,106 | 2,304,585 | 2,020,230 |

Government-wide, July 2026: quit rate 0.29% per month, separation rate 0.64%, span of control 5.9, temp and term 5.6%, bargaining unit coverage 45% of disclosed, average disclosed pay $117,422.

## 5. Operational findings

- **iCloud.** The repo sits in the synced Desktop; large files under `data/` were evicted and re-fetched, turning a ten-second extraction into seven minutes. Raw and intermediate data now live under `~/.fedpulse`, selected by `FEDPULSE_DATA`. Recorded in CLAUDE.md.
- **OPM throughput.** One 1.7 GB employment file every 2.7 minutes, sequential, no throttling seen across 725 files.
- **The evaluator is fast.** Total recompute of 32 derived measures over 12 million rows takes about 12 seconds, which is what made dropping the append-only ledger and the staleness machinery safe.

## 6. Open items

- Historical node names (see §3). Cheap to add by emitting a names table in the extractor and re-running the backfill in the background at some point.
- Slice size: 26 MB committed per refresh. Acceptable for now; if repo growth becomes a nuisance, move per-node series to the Release and keep only government and agency slices in the repo.
- The v0.2 panels remain on the org page beside the vitals strip, per Robert's instruction.
- OSHA, EEOC, FITARA, and VA survey measures are in the model design but not yet in the catalog; each is a hand-transcribed table plus a small extractor.
