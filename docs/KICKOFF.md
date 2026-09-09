# Kickoff prompt for the autonomous MVP run

Paste the block below into a fresh Claude Code session opened in this directory. Edit the pre-flight lines first if any default in `RUNBOOK.md` should change.

```
Build the MVP of the Federal Workforce Explorer in this repo, unattended.

Read CLAUDE.md, then PRD.md, then RUNBOOK.md, in that order. RUNBOOK.md is the plan: execute milestones M0 through M7 in sequence, verify each against its acceptance checks, and commit at each boundary with the milestone name. Take every default listed under "Pre-flight decisions" and every default in PRD Section 7.

Pre-flight overrides: none.

Rules that override everything else: the hard rules in CLAUDE.md. Never identify an individual, never link PLUM to FWD at the record level, never add telemetry, never load the 1.7 GB text file into pandas, never commit data/raw or data/work, never create a public repo or touch awrylabs.com.

Use the files already in data/raw/ for July 2026 and for tests. Download the other 2026 months from OPM one file at a time with backoff. If a source header does not match data/reference, stop that dataset, record the diff, and continue with everything else.

When a milestone's acceptance check fails after two honest attempts, leave it failing, write down why, and move on. Do not weaken a check to pass it.

Finish by writing docs/BUILD-REPORT.md in the format RUNBOOK.md specifies and put its summary in your final message: milestones passed and failed with the failing checks quoted, every deviation and why, months published with counts and sizes, crosswalk/review.json contents needing my eyes, the Pages URL, Release tags, workflow run URL, and anything the PRD got wrong about the sources.
```

## After the run

1. Read `docs/BUILD-REPORT.md`.
2. Resolve `crosswalk/review.json`.
3. Open the Pages URL and walk the three-click acceptance path (landing, Labor, a sub-element, download).
4. Decide the product name and whether the repo goes public.
5. Cutover to an awrylabs.com path is a manual step in the awrylabs.github.io repo.
