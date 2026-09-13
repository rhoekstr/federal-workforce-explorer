# Overnight run — Fed Pulse v0.5

Written 2026-09-13. Execution plan for an unattended session. Same contract as `RUNBOOK.md` and `docs/ENHANCEMENT-PLAN.md`: work the milestones in order, verify each against its acceptance checks, commit at each boundary with the milestone name, and finish with a build report.

**Read first:** `CLAUDE.md`, then `PRD.md`. The hard rules in CLAUDE.md override everything here.

**Set `FEDPULSE_DATA=~/.fedpulse` for every pipeline command.** The repo is in iCloud by explicit decision; raw and work files must stay outside it.

---

## N0 — Preflight (10 minutes)

- `pytest` green (44 passing, 2 skipped at time of writing).
- `git status` clean; the working tree must start from a pushed commit.
- Confirm the last CI run is green and that its log shows `restored 725 measure extracts`, `va aes: 128 facts`, and `plum slices`. If any is missing, stop and report — something regressed before this run started.

**Accept:** all three present, tree clean.

## N1 — Name the 165 historical org units

165 sub-element nodes render as their own code (`ARXR`, `DLES`, `AM**`) because the org lookup only learns names from the months the fact pipeline has processed, which is 2025 onward. Their headcount series run from 2005, so they are real units on real charts with no name. The names exist in the employment files themselves, in `agency_subelement`.

- Compute the **minimal covering set of months**: for each nameless node take one month where it has headcount (prefer its last-seen month, since names drift toward the end of a unit's life), then reduce to the smallest set of files that covers all 165. Expect roughly 15 to 25 files.
- For each month in that set, one at a time: download the employment file, read only `agency_subelement_code` and `agency_subelement`, harvest the pairs, **delete the text file before moving to the next**. These are about 1.5 GB each; disk is the constraint, not bandwidth.
- Merge into `data/lookups/org.json` as name history entries dated to the month harvested, so the existing name-history mechanism carries them. Do not overwrite a name the current files already provide.
- Rebuild nodes and slices.

**Guardrails:** one download at a time, backoff on 429, never keep two text files on disk. If the covering set exceeds 30 files, take the 30 that name the most nodes and report the remainder.

**Accept:** fewer than 20 nameless nodes remain; `ARXR`, `NV33`, `ARG6` and `DLES` all have names; no node loses a name it already had; disk never exceeds 20 GB used by the run.

## N2 — FEVS at sub-agency level, 2019

The 2019 respondent file is intact and carries `LEVEL1` with 238 codes at a 300-respondent threshold. It is the only year with usable sub-agency survey data: 2020 through 2023 have no such field and the 2024 file is corrupt as published. `docs/FEVS-EXPLORATION.md` section 10 has the analysis and a worked Labor example.

- Build `crosswalk/fevs_level1.json` mapping each 2019 `LEVEL1` to one org node, seeded by **name** matching within the agency. **Never join on code**: FEVS `LEVEL1` codes are FWD sub-element codes only for Defense, Treasury and Transportation, and elsewhere a colliding code can name a different unit. `IN01` is BLM in FEVS and the Office of the Secretary in FWD.
- Anything unmatched stays unmatched and goes to `crosswalk/fevs_review.json`. Do not roll sub-agency survey results up to the agency: the agency already has its own directly measured value, and adding a partial roll-up would corrupt it.
- Compute the same measures already validated at agency level, for mapped units only, and emit them at `survey_year` 2019 to those nodes.
- The site needs no change: the survey panel already prefers a node's own values.

**Accept:** at least 80 of the 194 non-residual 2019 units map to a node; the Labor units reproduce the table in the exploration document (BLS engagement 76.4, MSHA 61.5); no agency-level 2019 value changes; a test asserts no `LEVEL1` value was mapped by code alone.

## N3 — OSHA and EEOC, with a validation gate

Both publish annual per-agency tables inside reports rather than as data. Attempt them the way the VA survey worked: parse, then **prove the parse** against a value read independently from the source. If it cannot be proven, stop that source, keep nothing, and write down what blocked it.

- **OSHA:** federal agency injury and illness rates, total case rate and lost-time case rate per 100 employees, from the annual Federal Agency Program reports at osha.gov. Roughly 2011 onward.
- **EEOC:** complaints filed per 1,000 employees and findings of discrimination, from the Annual Report on the Federal Work Force Part II agency profiles, for agencies with 500 or more employees.

**The gate:** for each source, pick two agencies and one year, read the published figure by eye from the source document, and assert the parser produces the same number. A parser that cannot clear that gate ships nothing. Record the check and its result in the build report either way.

If a source clears the gate: add the measures to the catalog with operational definitions and a `since` date, commit the parsed values as reference data the way `va_aes.csv` and `fevs_agency_year.csv` are committed, and wire them into the build. **A source file that lives outside the repo will be dropped by CI** — that failure has now happened twice.

**Accept:** each source is either shipped with its validation check recorded, or not shipped with the blocker named. Partial parses are not shipped.

## N4 — Cross-source reconciliation report

There are now six sources and 93 measures, and nothing checks them against each other. Produce `docs/RECONCILIATION.md`, a standing report the pipeline can regenerate:

- OMB FTE against FWD headcount per agency per fiscal year, with the expected gap explained (FTE counts hours, headcount counts people; OMB's coverage differs).
- PLUM SES positions against FWD `ES` pay-plan headcount per agency.
- FEVS respondent counts against agency headcount in the survey year.
- Money: personnel obligations divided by headcount, flagged where it falls outside a plausible band per employee.
- Sum of agency headcount against the government total, every month, which should be exact.

Flag rows that disagree by more than a stated tolerance. **This is a report, not a gate** — these sources measure different things and are expected to differ. The value is that an unexplained divergence becomes visible.

**Accept:** the report exists, the agency-sum check is exact for every month, and every flagged row has either an explanation or an entry in the open-items list.

## N5 — Accessibility and performance pass

The site has grown from three pages to seven without an audit since v0.2.

- Every page: keyboard path through the primary interaction, focus visible, headings in order, every chart's data-table alternative present and correct.
- Colour contrast in both themes against WCAG AA.
- Measure first paint and total transfer for Pulse, a unit page, and Explore. The measures parquet is 33 MB and ships with the site; confirm no page pulls it unless the reader asks for a record-level query.
- Fix what is cheap and correct; list what is not.

**Accept:** no page requires a pointer to reach any control; no contrast failure at AA; no page transfers more than 5 MB before interaction.

## N6 — Deploy, verify, report

- `pytest` green. Assemble, commit, push, dispatch the workflow, wait for green.
- Verify **live**, not locally: a named org unit that N1 named, a sub-agency FEVS value from N2, and anything N3 shipped. A green deploy is not evidence; read the value off the page.
- `docs/BUILD-REPORT-v0.5.md`: milestones passed and failed with the failing check quoted, every deviation and why, what each source contributed, the reconciliation flags, and anything discovered that the PRD gets wrong. Update `PRD.md` section 8 to match reality.

---

## Guardrails

- **Never weaken a check to make it pass.** A failing acceptance check is a result; report it.
- **Never publish a partial history.** The extract guard exists because that happened; do not bypass it.
- **Anything the build reads must be in the repo.** CI cannot see `~/.fedpulse`. This has cost two incidents.
- **One OPM download at a time**, with backoff. Delete large raw files as soon as they are consumed.
- **Do not touch `~/Desktop/Code/Evince`.** It is a separate project and must end the run with a clean tree.
- **Do not move the repo out of iCloud.** Declined. The sweep in `pipeline/hygiene.py` runs first on every command; if conflict copies appear in a commit, the sweep has a gap worth fixing.
- **Do not make the repo public, change the domain, or delete a Release.**
- If a milestone is blocked, finish every other milestone and say plainly what was skipped.

## Kickoff prompt

```
Execute docs/OVERNIGHT-v0.5.md in this repo, unattended. Milestones N0 through N6 in order,
acceptance checks after each, one commit per milestone named for it. Read CLAUDE.md first, then
PRD.md; the hard rules in CLAUDE.md override the plan. Export FEDPULSE_DATA=~/.fedpulse for every
pipeline command.

Where the plan leaves a detail open, choose the simpler option and record it in the build report.
Do not weaken an acceptance check to pass it; a failing check is a result worth reporting.

Finish by deploying through the existing workflow, verifying the new values on the live site rather
than locally, writing docs/BUILD-REPORT-v0.5.md, and updating PRD section 8. Put the report's
summary in your final message.
```
