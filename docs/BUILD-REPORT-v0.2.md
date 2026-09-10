# Build report — v0.2 enhancement run, 2026-09-09/10

Executed against `docs/ENHANCEMENT-PLAN.md` in the same session that built the MVP, while a subagent explored FEVS history in parallel (`docs/FEVS-EXPLORATION.md`).

## 1. Milestones

| Milestone | Result | Notes |
|---|---|---|
| E0 housekeeping | passed | Labels `pipeline` and `crosswalk` created. PRD 1.3. HTTPS certificate for fedpulse.awrylabs.com still not issued by GitHub at the time of writing (see §4). |
| E1 trend data | passed | 378 nodes (gov, departments, agencies, 245 sub-elements ≥ 500), 4.1 MB total, largest file 21 KB. Sum-to-headcount test passes for every dimension and month. Surfaced and fixed a latent MVP bug: department nodes (`D:DOD`) had no series or mix files. |
| E2 geography data | passed | 130 precomputed geo slices, 0.3 MB. US Atlas counties-10m TopoJSON (842 KB, ISC) committed. Territories (PR, Guam) are disclosed but have no county FIPS; counted separately. Labor: 91% disclosed, 652 counties, DC first. |
| E3 flows chart | passed | Hand-rolled SVG, hover and keyboard, pies per side, DRP hatched. Verified on Labor, September 2025: 1,186 separations, 875 quits, 1,045 DRP. |
| E4 Trend and Composition | passed | Metric × breakdown × compare × range; state in URL (`?code=DLLS&by=grade` verified). Composition replaces eight mix charts with one selector. |
| E5 map | passed | Labor paints from the precomputed slice; BLS paints from a DuckDB-WASM query over the parquet with the duty station lookup; a fully redacted unit shows the notice instead of an empty map. |
| E6 navigator | passed | Spine and shelf, sticky left column on desktop, collapsed `<details>` on mobile, keyboard arrows and Backspace. BLS fits in one viewport at 1280 px with no horizontal scroll. |
| E7 verify and deploy | passed | 32 tests green. Workflow run 34427315929 green (refresh and deploy). Live site serves the navigator, the TopoJSON, and the fact parquet. Screenshots in `docs/screenshots/v0.2/`. |

## 2. Decisions the plan left open, and what was chosen

- **Sub-element trend scope:** breakdowns for units with 500 or more employees; series and step dimensions only for government, departments, and agencies. Budget was 15 MB; actual 4.1 MB.
- **Shelf when a node has no children:** shows the node's siblings under its parent, so a leaf never leaves the reader with an empty shelf.
- **Flows axes:** independent scales above and below zero, ticks thinned when one side is small.
- **Map color:** log scale, Blues, county counts. Per-capita shading deferred (needs population data).
- **Chart widths:** derived from the hosting panel rather than `main`, so the two-column layout and mobile both fit.

## 3. Data and size

- Repo slices: series 3.3 MB, mix 4.5 MB, trend 4.1 MB, geo 0.3 MB, TopoJSON 0.8 MB.
- `_site` assembled: 194 MB, of which 190 MB is the 57 fact parquet files that travel with the site.

## 4. Open items

- **HTTPS on the custom domain.** DNS resolves and HTTP serves. GitHub has not issued the certificate. If it is still missing, remove and re-add the custom domain in Pages settings, then enforce HTTPS.
- **Favicon** added as an inline SVG data URI; the earlier console 404 was the missing favicon.
- **Screenshots** for v0.2 are in `docs/screenshots/v0.2/` (desktop and mobile).

## 5. URLs

- Live: https://fedpulse.awrylabs.com (also https://rhoekstr.github.io/federal-workforce-explorer/)
- Deploy run: https://github.com/rhoekstr/federal-workforce-explorer/actions/runs/34427315929
