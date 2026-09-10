# FEVS as a data source beside staffing

Exploration of the OPM Federal Employee Viewpoint Survey (FEVS) public release data files (PRDF) for 2019 through 2023, plus the published 2024 index spreadsheets, as inputs to Fed Pulse Phase 2 (PRD 5.9). Everything below was measured on 2026-09-09 from the files listed. Computed table: `data/reference/fevs/fevs_agency_year.csv` (175 rows); the script that produces it: `data/reference/fevs/fevs_agency_year_compute.py`.

## 1. Summary

- Five intact respondent files exist (2019–2023, 292k to 625k rows each). The 2024 file is still corrupt as published. There is no 2025 survey; OPM's site carries a notice that materials are being rescinded or revised under EO 14151 and EO 14168.
- Our computed Employee Engagement Index and Global Satisfaction Index match OPM's published unrounded agency values to two decimals for every agency and year 2020–2023 (max difference 0.00 pp). The index method is therefore settled: weighted percent positive per item with "Do Not Know" excluded from the denominator, unrounded item averages, EEI = mean of three subindex means.
- The intent-to-leave item (`DLEAVING`) is in every PRDF, but with a code-order change in 2019 and a two-variant form in 2020. "Yes, to retire" is merged into "Yes, other" in all years, so retirement intent is not separable from the PRDF.
- The 2024 Report by Agency does not contain `DLEAVING` (its 98 sheets are items Q1–Q91A only). PRD 5.9's plan to take "considering leaving by reason" from that report will not work; for 2024 the only source is the corrupt PRDF, or OPM's per-agency PDF reports.
- The DEIA index and its items were redacted from every re-issued file (2019 Q34; 2022 Q71–Q84; 2023 Q73–Q85), and the 2022 readme's "what's new" paragraph is itself redacted.
- FEVS agency codes are the FWD two-letter codes. Of 45 codes that ever appear, only `DR` (FERC), `SN` (National Gallery) and `XX` (pooled "all other") have no FWD row. VA, FDIC, Smithsonian, GPO and the Federal Reserve never appear in a PRDF; VA (446k FWD headcount) is the largest gap by far.
- Sub-agency: 2019 and 2024 carry a `LEVEL1` field. Its codes are agency-prefixed four-character codes, but they are the FWD sub-element codes only for DoD, Treasury, Transportation and a few others. For most civilian departments (Labor, HHS, DHS, Justice, Commerce, Agriculture, SSA, State) FEVS uses its own numbering, and where a code happens to exist in the org tree it can name a different unit (FEVS `IN01` is BLM; FWD `IN01` is the Office of the Secretary). A curated name crosswalk is required; a code join would be silently wrong.
- 2023 intent to leave is negatively correlated with 2025 separation rates across 29 agencies (r ≈ −0.4). The sign is the DRP/RIF confound, not a verdict on the indicator: 2025 exits were concentrated by policy in small, high-engagement domestic agencies (GSA −23%, HUD −28%, SBA −33%, ED −40%, USAID −93%). A fair test needs a normal year's separations, which this repo does not yet hold.

## 2. What exists by year

| Year | URL (`https://www.opm.gov` + path) | Zip | CSV inside | Rows | Cols | Agency codes | Sub-agency field | Weight | Threshold | Field period | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2019 | `/media/rzmnrl5r/2019_opm_fevs_prdf_revised.zip` | 23.9 MB | `2019/2019_OPM_FEVS_PRDF_Redacted.csv` (126 MB) | 615,395 | 94 | 45 (incl. XX) | `LEVEL1`, 238 codes | `POSTWT`, sum 1,394,912 | 300 respondents per LEVEL1 | May–June 2019 | Re-issued 2026-06-16 with Q34 (diversity) redacted; 6 demographics only; shutdown items Q73–Q77 |
| 2020 | `/media/pttd23k5/2020_opm_fevs_prdf_revised.zip` | 28.9 MB | `FEVS_2020_PRDF.csv` (179 MB) | 624,800 | 134 | 32 | none | `POSTWT`, sum 1,452,901 | 750 respondents per agency | Sep–Oct 2020 | 38 core items + COVID `V` items; `DLEAVINGA/B/C` variants; no Performance Confidence items |
| 2021 | `/media/os4dqz0g/2021_opm_fevs_prdf_revised.zip` | 12.1 MB | `2021_OPM_FEVS_PRDF.csv` (52 MB) | 292,520 | 79 | 31 | none | `POSTWT`, sum 1,698,732, max 789 | 750 | Nov–Dec 2021 | Sample, not census; heavy weights |
| 2022 | `/media/wiohpimz/2022_opm_fevs_prdf_revised.zip` | 24.2 MB | `2022_OPM_FEVS_PRDF_revised.csv` (125 MB) | 557,778 | 102 | 31 | none | `POSTWT`, sum 1,669,683 | 750 (implied) | May 30–Jul 22 2022 | Back to census; Q71–Q84 (DEIA) redacted; first negatively worded items (Q12, Q34) |
| 2023 | `/media/knpbcml4/2023_opm_fevs_prdf_revised.zip` | 24.4 MB | `2023/2023_OPM_FEVS_PRDF_Redacted.csv` (134 MB) | 625,568 | 96 | 31 | none | `POSTWT`, sum 1,691,257 | 750 (implied) | May–Jul 2023 | Q73–Q85 (DEIA) redacted; has `Year` column; ships the Indices and Dimensions Guide |
| 2024 | `/media/xywc4uyy/2024_opm_fevs_prdf_revised.zip` | — | corrupt (87,320 rows then null bytes) | — | — | 36 in codebook | `LEVEL1`, 164 codes in codebook | `POSTWT` | 500 | 2024 | Only AG, AF, AR rows survive |

Governmentwide response rates from the 2024 Governmentwide Management Report (revised April 2025): 2020 44%, 2021 34%, 2022 35%, 2023 39%, 2024 41% (over 1.6M invited, over 674,000 responded). Very Large agencies (≥75k) run 29–41%; Small agencies 65–72%. The 2019 rate is not in that report and was not re-verified here. Response rates are not in the PRDF; the per-agency rates are in `.../2024-governmentwide-management-report` Excel appendices.

Raw files are extracted under `data/raw/fevs/{year}/` (gitignored). Every CSV shows signs of a pass through Excel (`RandomID` as `1.12971E+11` in 2019 and 2023, rounded to six significant digits in 2022), but `POSTWT` retains nine or ten significant digits and the validation in section 5 shows no damage to the weights.

## 3. Fields

### 3.1 Index items by year

Item numbers move every year. Matching was done on exact item wording against the 2023 Indices and Dimensions Guide; every item was found by text except where the survey did not carry it.

| Index / subindex | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---|---|---|---|---|---|
| EEI: Intrinsic Work Experience (5) | Q3 Q4 Q6 Q11 Q12 | Q2 Q3 Q4 Q6 Q7 | Q2 Q3 Q4 Q6 Q7 | Q2 Q3 Q4 Q6 Q7 | Q2 Q3 Q4 Q6 Q7 | Q2 Q3 Q4 Q6 Q7 |
| EEI: Leaders Lead (5) | Q53 Q54 Q56 Q60 Q61 | Q26 Q27 Q28 Q30 Q31 | Q32 Q33 Q34 Q36 Q37 | Q55 Q56 Q57 Q59 Q60 | Q57 Q58 Q59 Q61 Q62 | Q57 Q58 Q59 Q61 Q62 |
| EEI: Supervisors (5) | Q47 Q48 Q49 Q51 Q52 | Q21 Q22 Q23 Q24 Q25 | Q27 Q28 Q29 Q30 Q31 | Q46 Q48 Q49 Q50 Q52 | Q48 Q50 Q51 Q52 Q54 | Q48 Q50 Q51 Q52 Q54 |
| Global Satisfaction (4: recommend, job, pay, org) | Q40 Q69 Q70 Q71 | Q17 Q36 Q37 Q38 | Q23 Q42 Q43 Q44 | Q43 Q68 Q69 Q70 | Q46 Q70 Q71 Q72 | Q46 Q70 Q71 Q72 |
| Performance Confidence (4) | absent | absent | Q14 Q15 Q16 Q17 | Q19 Q20 Q21 Q22 | Q20 Q21 Q22 Q23 | Q20 Q21 Q22 Q23 |
| Employee Experience (5) | absent | absent | absent | Q85–Q89 | Q86–Q90 | Q86–Q90 |
| DEIA (4 subindices, 13 items) | Q34 redacted | n/a | n/a | Q71–Q84 redacted | Q73–Q85 redacted | absent from codebook |
| "Encouraged to come up with new and better ways" | Q3 | Q2 | Q2 | Q2 | Q2 | Q2 |
| "My workload is reasonable" | Q10 | Q5 | Q5 | Q5 | Q5 | Q5 |
| "Real opportunity to improve my skills" | Q1 | Q1 | Q1 | Q1 | Q1 | Q1 |
| "Differences in performance are recognized" | Q24 | Q12 | Q12 | Q16 | Q17 | Q17 |
| "Satisfied with the recognition you receive" | Q65 | Q35 | Q41 | Q67 | Q69 | Q69 |

Response codes for all index items: 5 = Strongly Agree / Very Satisfied / Very Good / Always, down to 1; `X` = Do Not Know / No Basis to Judge (present on the Leaders Lead items, PC items and Q48); blank = not answered. The 2020 codebook has a typo in the supervisor item ("by you immediate supervisor"); it is the same item.

### 3.2 Demographics

| Variable | Wording | Codes | Years |
|---|---|---|---|
| `DLEAVING` | Are you considering leaving your organization within the next year, and if so, why? | see 3.3 | 2019, 2021–2024 |
| `DLEAVINGA` / `DLEAVINGB` / `DLEAVINGC` | Same stem, "Before the Covid-19 Pandemic" / "Today (September–October 2020)" / "Has your intention ... changed because of the COVID-19 pandemic?" (A = Yes, B = No) | as `DLEAVING` | 2020 only |
| `DSUPER` | What is your supervisory status? | A = Non-Supervisor/Team Leader, B = Supervisor/Manager/Executive ("Senior Leader" in 2019) | all |
| `DFEDTEN` | How long have you been with the Federal Government (excluding military service)? | A = Ten years or fewer, B = Eleven to 20, C = More than 20 | all |
| `DAGEGRP` | What is your age group? | A = Under 40, B = 40 or Older | 2020–2024 |
| `DSEX` | Are you: | A = Male, B = Female | all |
| `DRNO`, `DHISP`, `DDIS`, `DMIL` | race (A Black, B White, C Asian, D other collapsed), Hispanic, disability, military service | A/B(/C/D) | 2020–2024 |
| `DEDUC`, `DMINORITY` | education (3 groups), minority status derived from race and ethnicity | A/B/C, A/B | 2019 only |

Blank demographics are the product of OPM's masking (section 12). `DLEAVING` is blank for 6.5–9.2% of rows depending on year.

### 3.3 The intent-to-leave codes change order in 2019

| Code | 2019 | 2020 (A and B variants), 2021, 2022, 2023, 2024 |
|---|---|---|
| A | No | No |
| B | Yes, to take another Federal job | Yes, other |
| C | Yes, to take a job outside Federal Gov | Yes, to take another job within the Federal Government |
| D | Other | Yes, to take another job outside the Federal Government |

The 2019 readme states that "Yes, to retire" was recoded into "Yes, other"; later codebooks list only A–D, so the same merge applies. The survey instrument has five options; the PRDF has four.

## 4. Formulas used

- Percent positive for an item = 100 × Σ w·[response ∈ {4, 5}] ÷ Σ w·[response ∈ {1..5}], w = `POSTWT`. `X` and blank drop out of both sums.
- Subindex = unrounded mean of its items' percent positive. EEI = mean of the three subindex means. GSI, PCI, EXI = mean of their items.
- Intent-to-leave shares = 100 × Σ w·[code = k] ÷ Σ w·[code ∈ {A, B, C, D}], k ∈ {no, other, within, outside}; `leave_any` = 100 − no. 2020 uses `DLEAVINGB` ("Today"); `DLEAVINGA` is kept in separate columns.
- One row per agency code per year, plus an `ALL` row over every respondent in the file (including `XX`). The `XX` row is a pool of small agencies and should not be shown as an agency.

## 5. Validation against OPM's published index spreadsheets

Source: `data/reference/fevs/2024-ee-report-excel.xlsx` and `2024-gs-report-excel.xlsx` (one row per agency, unrounded `percentage_2020` … `percentage_2024`).

| Check | Result |
|---|---|
| EEI, 29 agencies + governmentwide, 2020–2023 (110 cells) | max \|computed − published\| = 0.00 pp |
| GSI, same cells | max \|computed − published\| = 0.00 pp |
| Codes with no published row | `NN` (NASA) and `SE` (SEC) have PRDF rows in 2019/2020 but no row in the 2024 index reports (they no longer participate); 2019-only small agencies are absent from a report whose columns start at 2020 |

Sample: Labor EEI 2023 computed 76.40 vs published 76.40; DHS GSI 2022 54.1 vs 54.1; governmentwide EEI 2020 72.45 vs 72.45. The 2019 governmentwide EEI (68.5) matches OPM's 2019 headline of 68 but there is no unrounded 2019 column to check against.

## 6. Agency crosswalk (FEVS `agency` ↔ FWD `agency_code`)

Same two-letter scheme. Checked against `data/reference/fwd_agencies_202607.json` (128 FWD codes).

| Direction | Codes |
|---|---|
| FEVS codes with no FWD row | `DR` Federal Energy Regulatory Commission (in FWD it is inside Energy), `SN` National Gallery of Art (not in FWD), `XX` pooled "All Other Agencies" |
| FWD agencies ≥1,000 headcount that never appear in a PRDF | `VA` Veterans Affairs (446,459), `FD` FDIC (4,989), `SM` Smithsonian (4,096), `LP` GPO (1,625), `FR` Federal Reserve (1,069) |
| Defense | FEVS `AF`, `AR`, `NV`, `DD` map one-to-one to FWD `AF`, `AR`, `NV`, `DD` (FWD labels `DD` "Department of Defense", 137,592 heads; the org tree groups the four under `D:DOD`) |
| Present every year 2019–2023 (30) | AF AG AM AR CM CU DD DJ DL DN DR ED EE EP GS HE HS HU IN NF NQ NU NV OM SB ST SZ TD TR + XX |
| 2019 only (13) | BG BO CT FC FQ HF RR SE SK SN TC NL(also 2020) NN(also 2020) |
| Intermittent | FT (2019, 2022, 2023), IB (2019, 2021), NL (2019, 2020), NN (2019, 2020) |

VA is the elephant: the largest civilian employer is absent from every respondent file because VA runs its own all-employee survey and does not participate in FEVS. Any landing-table column will be blank for VA.

## 7. Governmentwide series (all PRDF respondents, weighted)

| Year | n | Weighted N | EEI | Leaders | Supervisors | Intrinsic | GSI | PCI | EXI | Leave any | Outside gov | Within gov | Other (incl. retire) | DLEAVING blank % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2019 | 615,395 | 1,394,912 | 68.5 | 57.1 | 76.2 | 72.1 | 64.9 | — | — | 35.1 | 4.3 | 20.3 | 10.5 | 6.5 |
| 2020 | 624,800 | 1,452,901 | 72.5 | 61.6 | 80.2 | 75.5 | 68.7 | — | — | 33.1 | 3.8 | 18.0 | 11.3 | 9.2 |
| 2021 | 292,520 | 1,698,732 | 71.0 | 60.0 | 79.8 | 73.1 | 63.9 | 84.5 | — | 38.3 | 5.7 | 17.8 | 14.8 | 6.6 |
| 2022 | 557,778 | 1,669,683 | 70.5 | 59.2 | 79.7 | 72.7 | 61.7 | 83.5 | 71.8 | 38.2 | 5.1 | 19.5 | 13.5 | 7.1 |
| 2023 | 625,568 | 1,691,257 | 71.7 | 61.2 | 80.2 | 73.8 | 63.8 | 83.8 | 73.4 | 37.5 | 4.5 | 20.5 | 12.5 | 6.5 |
| 2024 (published) | ~674,000 | — | 73.0 | 63 | 81 | 75 | 65.4 | — | — | not published | | | | |

2020's "before the pandemic" recall variant (`DLEAVINGA`) gives other 8.9, within 16.3, outside 2.6, so the 2020 "today" figures are the comparable ones. The 2020 jump in every index coincides with the pandemic-era administration and the shortened instrument; treat 2019→2020 with care.

## 8. Intent to leave, top 15 agencies by 2023 respondents

Weighted percent, 2019 → 2020 → 2021 → 2022 → 2023.

| Code | Agency | 2023 n | Leave, any | Outside gov | Within gov | Other (incl. retire) | EEI | GSI |
|---|---|---|---|---|---|---|---|---|
| HS | Homeland Security | 91,700 | 39.0 → 34.3 → 36.9 → 37.5 → 33.1 | 4.8 → 3.8 → 5.2 → 4.7 → 3.6 | 23.8 → 19.9 → 17.8 → 19.9 → 19.2 | 10.3 → 10.6 → 14.0 → 12.9 → 10.2 | 61.7 → 66.5 → 65.2 → 64.3 → 66.9 | 55.9 → 61.1 → 56.8 → 54.1 → 60.2 |
| HE | Health and Human Services | 59,020 | 28.3 → 24.4 → 28.0 → 25.8 → 26.3 | 4.1 → 3.4 → 4.6 → 3.7 → 3.6 | 15.4 → 12.1 → 13.0 → 12.8 → 13.7 | 8.9 → 8.8 → 10.4 → 9.3 → 9.0 | 73.5 → 76.5 → 77.4 → 77.9 → 78.1 | 71.7 → 74.1 → 72.5 → 71.5 → 72.3 |
| AR | Army | 52,833 | 39.7 → 39.3 → 45.6 → 43.8 → 43.0 | 3.2 → 3.3 → 5.1 → 4.4 → 3.6 | 25.7 → 23.7 → 23.7 → 24.8 → 25.8 | 10.9 → 12.3 → 16.8 → 14.7 → 13.6 | 69.8 → 72.7 → 70.2 → 70.6 → 73.3 | 66.4 → 69.0 → 63.3 → 62.5 → 66.3 |
| AG | Agriculture | 48,358 | 34.4 → 30.6 → 34.2 → 33.0 → 34.9 | 6.0 → 4.3 → 8.0 → 6.7 → 6.4 | 15.5 → 13.1 → 11.0 → 13.9 → 16.0 | 12.8 → 13.1 → 15.2 → 12.4 → 12.5 | 64.7 → 69.2 → 70.1 → 70.3 → 71.6 | 59.7 → 64.2 → 59.3 → 58.9 → 60.7 |
| TR | Treasury | 42,362 | 29.7 → 23.7 → 28.3 → 31.5 → 32.4 | 3.2 → 2.0 → 3.5 → 3.6 → 3.1 | 14.4 → 10.3 → 11.1 → 13.8 → 16.7 | 12.1 → 11.4 → 13.8 → 14.0 → 12.5 | 69.5 → 75.0 → 74.3 → 73.7 → 73.7 | 64.4 → 71.2 → 67.5 → 64.5 → 65.1 |
| DD | OSD, Joint Staff, Defense Agencies | 40,324 | 39.4 → 36.5 → 39.6 → 39.6 → 43.6 | 2.9 → 2.7 → 3.6 → 3.2 → 3.7 | 26.3 → 23.0 → 21.7 → 22.9 → 25.2 | 10.2 → 10.9 → 14.3 → 13.6 → 14.7 | 69.6 → 73.9 → 72.7 → 73.1 → 70.1 | 67.2 → 71.5 → 68.3 → 66.3 → 62.7 |
| NV | Navy | 39,201 | 37.2 → 38.2 → 45.1 → 44.9 → 44.4 | 4.0 → 4.4 → 7.0 → 6.5 → 5.6 | 23.3 → 22.1 → 21.9 → 23.6 → 24.5 | 10.0 → 11.7 → 16.1 → 14.8 → 14.3 | 70.0 → 74.1 → 71.5 → 70.4 → 72.1 | 65.6 → 69.6 → 63.1 → 60.4 → 62.8 |
| IN | Interior | 35,949 | 34.2 → 30.4 → 34.5 → 33.9 → 32.3 | 4.5 → 3.2 → 5.6 → 4.4 → 4.0 | 18.8 → 15.3 → 14.9 → 17.0 → 16.7 | 10.9 → 11.8 → 14.0 → 12.5 → 11.6 | 65.7 → 69.4 → 70.2 → 70.4 → 72.3 | 64.5 → 67.3 → 64.9 → 62.6 → 65.0 |
| DJ | Justice | 34,081 | 30.1 → 35.9 → 40.0 → 42.1 → 40.2 | 5.8 → 6.4 → 8.7 → 7.9 → 7.2 | 14.1 → 17.4 → 15.9 → 19.5 → 19.7 | 10.2 → 12.1 → 15.3 → 14.7 → 13.3 | 67.3 → 68.8 → 65.0 → 63.1 → 65.0 | 66.5 → 67.2 → 59.5 → 54.4 → 56.1 |
| AF | Air Force | 29,434 | 42.8 → 41.8 → 48.0 → 44.7 → 46.3 | 4.2 → 4.4 → 6.5 → 5.8 → 5.5 | 27.8 → 25.0 → 23.8 → 23.8 → 26.6 | 10.8 → 12.4 → 17.8 → 15.1 → 14.2 | 69.5 → 74.5 → 72.1 → 72.6 → 73.7 | 63.8 → 68.9 → 63.1 → 63.0 → 65.0 |
| CM | Commerce | 25,906 | 24.1 → 19.7 → 24.5 → 27.9 → 24.4 | 4.3 → 2.8 → 4.5 → 4.6 → 4.3 | 11.3 → 8.0 → 8.6 → 11.1 → 9.9 | 8.5 → 8.9 → 11.5 → 12.2 → 10.3 | 72.6 → 76.0 → 76.5 → 75.1 → 76.0 | 71.1 → 73.7 → 71.1 → 67.1 → 68.2 |
| SZ | Social Security | 25,757 | 29.5 → 25.4 → 31.4 → 36.4 → 36.8 | 3.9 → 2.8 → 4.6 → 5.2 → 4.3 | 15.8 → 12.8 → 14.2 → 17.6 → 21.1 | 9.9 → 9.8 → 12.6 → 13.5 → 11.3 | 66.7 → 68.4 → 68.7 → 65.7 → 65.0 | 64.5 → 65.2 → 60.3 → 53.3 → 51.6 |
| TD | Transportation | 20,624 | 29.6 → 22.1 → 30.9 → 31.1 → 30.0 | 4.7 → 2.3 → 5.6 → 4.8 → 4.7 | 14.5 → 9.7 → 10.5 → 13.6 → 13.3 | 10.4 → 10.1 → 14.8 → 12.6 → 12.1 | 68.6 → 75.8 → 71.7 → 71.9 → 73.4 | 67.4 → 74.4 → 67.7 → 66.5 → 68.7 |
| DN | Energy | 9,481 | 31.7 → 25.7 → 31.7 → 31.0 → 28.6 | 5.2 → 3.5 → 5.3 → 4.8 → 4.3 | 15.6 → 11.0 → 12.7 → 14.4 → 14.7 | 10.8 → 11.2 → 13.6 → 11.9 → 9.6 | 72.0 → 77.1 → 77.3 → 77.6 → 79.2 | 70.0 → 75.1 → 72.0 → 71.6 → 74.6 |
| ST | State | 9,360 | 30.3 → 27.4 → 29.4 → 31.8 → 30.1 | 8.1 → 6.6 → 6.8 → 7.0 → 6.3 | 12.7 → 8.9 → 10.3 → 11.8 → 12.1 | 9.4 → 11.9 → 12.3 → 13.0 → 11.7 | 68.1 → 71.9 → 71.2 → 70.4 → 69.0 | 66.5 → 67.1 → 63.1 → 61.2 → 60.2 |
| ALL | All respondents | 625,568 | 35.1 → 33.1 → 38.3 → 38.2 → 37.5 | 4.3 → 3.8 → 5.7 → 5.1 → 4.5 | 20.3 → 18.0 → 17.8 → 19.5 → 20.5 | 10.5 → 11.3 → 14.8 → 13.5 → 12.5 | 68.5 → 72.5 → 71.0 → 70.5 → 71.7 | 64.9 → 68.7 → 63.9 → 61.7 → 63.8 |

What the split says. "Within government" is the bulk of stated intent (20 of 37 points governmentwide) and is a transfer, not an exit; its FWD analogue is `SA`/`SB` transfer-out, not quits. "Outside government" is small (3–8%) and stable within agency; State and Justice are consistently highest. "Other" carries retirement and moves with the age mix. SSA is the clearest deterioration in the window: leave-any 29.5 → 36.8, GSI 64.5 → 51.6, workload-reasonable 44.2% in 2023 (lowest of the fifteen). Justice's GSI fell ten points 2019→2023 while its outside-government intent is the second highest.

Candidate leading indicators, 2023, same fifteen (percent positive):

| Code | Job sat | Pay sat | Org sat | Recommend | Encouraged new ways | Workload reasonable | Skills opportunity | Perf. differences recognized | Sat. w/ recognition | PCI | EXI | DLEAVING blank % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| HS | 64.0 | 57.5 | 57.1 | 62.2 | 55.3 | 64.0 | 63.8 | 39.4 | 49.6 | 78.3 | 69.7 | 5.7 |
| HE | 76.0 | 63.0 | 72.7 | 77.4 | 74.0 | 64.7 | 77.8 | 54.4 | 65.0 | 89.4 | 81.2 | 4.5 |
| AR | 70.0 | 61.6 | 64.6 | 68.8 | 70.1 | 65.5 | 72.9 | 47.0 | 57.4 | 84.9 | 74.8 | 7.0 |
| AG | 67.5 | 47.9 | 59.6 | 67.9 | 64.9 | 55.7 | 71.9 | 41.1 | 53.5 | 84.7 | 73.9 | 6.2 |
| TR | 69.7 | 54.8 | 65.0 | 71.0 | 64.1 | 64.5 | 71.1 | 49.0 | 59.7 | 86.7 | 71.2 | 6.7 |
| DD | 66.6 | 58.7 | 60.6 | 64.8 | 64.4 | 63.6 | 66.5 | 44.3 | 53.8 | 82.8 | 73.5 | 8.4 |
| NV | 67.6 | 56.2 | 60.5 | 67.0 | 68.8 | 65.3 | 72.2 | 45.2 | 55.0 | 84.8 | 72.3 | 8.1 |
| IN | 71.2 | 54.0 | 64.1 | 70.6 | 71.5 | 54.8 | 75.4 | 45.0 | 58.8 | 84.9 | 77.2 | 4.3 |
| DJ | 61.2 | 50.9 | 53.6 | 58.8 | 55.9 | 58.6 | 63.7 | 37.8 | 49.6 | 77.1 | 69.4 | 8.5 |
| AF | 69.0 | 57.7 | 64.7 | 68.4 | 71.6 | 66.6 | 73.8 | 48.2 | 58.8 | 84.2 | 73.3 | 8.5 |
| CM | 72.8 | 56.1 | 69.2 | 74.8 | 64.8 | 59.4 | 74.3 | 49.5 | 60.1 | 89.1 | 75.6 | 5.0 |
| SZ | 55.7 | 49.3 | 49.2 | 52.2 | 49.3 | 44.2 | 54.7 | 33.7 | 46.9 | 75.8 | 66.9 | 6.9 |
| TD | 72.6 | 61.1 | 66.2 | 74.6 | 67.3 | 63.0 | 73.1 | 45.9 | 59.6 | 87.0 | 75.5 | 5.5 |
| DN | 77.9 | 67.0 | 74.9 | 78.6 | 77.7 | 63.3 | 80.6 | 56.1 | 68.8 | 91.6 | 78.7 | 3.8 |
| ST | 62.5 | 57.6 | 56.5 | 64.2 | 62.5 | 48.1 | 66.6 | 39.0 | 50.2 | 84.6 | 73.2 | 8.2 |
| ALL | 68.1 | 57.4 | 62.3 | 67.5 | 65.5 | 62.3 | 70.3 | 45.0 | 56.0 | 83.8 | 73.4 | 6.5 |

## 9. 2023 intent to leave against 2025 separations

Separations from `data/slices/series/{code}.json`, effective month in 2025, as a share of January 2025 headcount. Retire = `SD`+`SE`+`SG`; transfer out = `SA`+`SB`; DRP is the pipeline's deferred-resignation category. `DR` has no series file (FERC is inside Energy in FWD).

| Code | Agency | Headcount Jan 2025 | Headcount change 2025 % | Quit % | Retire % | DRP % | Transfer out % | Total sep % | 2023 leave any | Outside gov | Within gov | Other | EEI 2023 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| HS | Homeland Security | 231,795 | −1.8 | 5.1 | 4.5 | 2.2 | 0.4 | 14.1 | 33.1 | 3.6 | 19.2 | 10.2 | 66.9 |
| HE | Health and Human Services | 93,397 | −19.6 | 5.4 | 7.7 | 1.6 | 0.4 | 23.8 | 26.3 | 3.6 | 13.7 | 9.0 | 78.1 |
| AR | Army | 221,195 | −10.3 | 6.4 | 6.5 | 7.0 | 0.7 | 23.0 | 43.0 | 3.6 | 25.8 | 13.6 | 73.3 |
| AG | Agriculture | 90,314 | −20.2 | 13.3 | 9.7 | 16.2 | 0.5 | 44.9 | 34.9 | 6.4 | 16.0 | 12.5 | 71.6 |
| TR | Treasury | 116,709 | −23.0 | 16.8 | 12.0 | 19.9 | 0.3 | 50.3 | 32.4 | 3.1 | 16.7 | 12.5 | 73.7 |
| DD | OSD and Defense Agencies | 158,892 | −7.7 | 7.1 | 6.0 | 4.2 | 0.9 | 20.0 | 43.6 | 3.7 | 25.2 | 14.7 | 70.1 |
| NV | Navy | 221,292 | −7.1 | 5.4 | 5.9 | 7.0 | 0.5 | 19.8 | 44.4 | 5.6 | 24.5 | 14.3 | 72.1 |
| IN | Interior | 63,774 | −10.8 | 10.5 | 9.8 | 10.0 | 0.6 | 41.4 | 32.3 | 4.0 | 16.7 | 11.6 | 72.3 |
| DJ | Justice | 116,718 | −8.0 | 5.0 | 6.3 | 2.6 | 0.8 | 15.7 | 40.2 | 7.2 | 19.7 | 13.3 | 65.0 |
| AF | Air Force | 173,193 | −9.5 | 7.2 | 5.8 | 6.2 | 0.7 | 22.2 | 46.3 | 5.5 | 26.6 | 14.2 | 73.7 |
| CM | Commerce | 48,803 | −13.8 | 7.3 | 8.8 | 3.2 | 0.4 | 24.8 | 24.4 | 4.3 | 9.9 | 10.3 | 76.0 |
| SZ | Social Security | 57,384 | −11.6 | 3.6 | 8.3 | 1.4 | 0.2 | 15.0 | 36.8 | 4.3 | 21.1 | 11.3 | 65.0 |
| TD | Transportation | 57,423 | −6.8 | 5.1 | 7.9 | 7.0 | 0.2 | 22.1 | 30.0 | 4.7 | 13.3 | 12.1 | 73.4 |
| DN | Energy | 17,592 | −15.0 | 12.8 | 3.7 | 10.0 | 0.6 | 28.9 | 28.6 | 4.3 | 14.7 | 9.6 | 79.2 |
| ST | State | 14,478 | −19.1 | 7.5 | 7.9 | 3.6 | 0.8 | 32.0 | 30.1 | 6.3 | 12.1 | 11.7 | 69.0 |
| EP | Environmental Protection | 16,931 | −13.4 | 8.6 | 13.6 | 15.5 | 0.4 | 41.8 | 26.0 | 2.6 | 12.0 | 11.4 | 79.2 |
| DL | Labor | 14,237 | −12.8 | 9.3 | 13.7 | 13.7 | 0.8 | 38.3 | 30.4 | 3.0 | 17.7 | 9.7 | 76.4 |
| GS | General Services | 13,367 | −22.6 | 16.3 | 20.7 | 31.7 | 1.2 | 74.5 | 25.9 | 2.2 | 15.2 | 8.5 | 84.7 |
| HU | Housing and Urban Development | 8,791 | −28.3 | 15.3 | 17.2 | 26.2 | 0.8 | 61.2 | 33.2 | 2.7 | 20.8 | 9.7 | 77.5 |
| SB | Small Business | 8,562 | −32.5 | 16.2 | 6.5 | 18.8 | 0.9 | 58.4 | 26.4 | 2.5 | 15.5 | 8.4 | 78.6 |
| ED | Education | 4,111 | −40.3 | 12.1 | 19.3 | 5.4 | 2.0 | 58.3 | 28.2 | 2.7 | 15.5 | 10.0 | 76.4 |
| AM | USAID | 4,969 | −92.6 | 6.1 | 6.8 | 4.7 | 1.9 | 104.3 | 29.9 | 6.4 | 12.2 | 11.3 | 69.9 |
| NU | Nuclear Regulatory | 2,926 | −9.6 | 5.6 | 9.7 | 4.0 | 0.3 | 20.5 | 34.1 | 5.7 | 15.7 | 12.7 | 74.4 |
| OM | OPM | 3,055 | −25.2 | 16.5 | 14.6 | 23.9 | 1.8 | 63.4 | 28.7 | 1.6 | 18.3 | 8.8 | 79.7 |
| NQ | National Archives | 2,888 | −15.7 | 5.8 | 8.1 | 5.2 | 0.7 | 22.9 | 28.5 | 1.8 | 16.3 | 10.4 | 73.3 |
| EE | EEOC | 2,075 | −14.7 | 7.4 | 7.6 | 5.3 | 1.2 | 22.8 | 36.7 | 2.5 | 22.6 | 11.6 | 78.6 |
| NF | National Science Foundation | 1,699 | −29.5 | 10.5 | 13.6 | 19.5 | 1.1 | 54.9 | 28.0 | 4.0 | 13.2 | 10.8 | 78.7 |
| CU | National Credit Union | 1,226 | −3.3 | 6.4 | 17.2 | 21.4 | 0.2 | 46.7 | 21.7 | 3.7 | 10.3 | 7.8 | 77.1 |
| FT | Federal Trade | 1,278 | −20.8 | 14.6 | 8.2 | 7.9 | 0.5 | 33.0 | 23.4 | 7.7 | 8.1 | 7.6 | 78.7 |

Total separation share exceeds headcount change because 2025 accessions partly offset exits; USAID's 104% reflects mass transfers of the residual staff to State after the January base.

Correlations across the 29 agencies (Pearson r / Spearman ρ):

| FEVS 2023 measure | vs quit | vs retire | vs DRP | vs transfer out | vs total separations | vs headcount change |
|---|---|---|---|---|---|---|
| Leave, any | −0.35 / −0.33 | −0.45 / −0.46 | −0.35 / −0.30 | −0.04 / +0.01 | −0.43 / −0.56 | +0.26 / +0.42 |
| Leave, outside government | −0.30 / −0.37 | −0.46 / −0.40 | −0.45 / −0.39 | −0.22 / −0.29 | −0.20 / −0.36 | −0.06 / +0.27 |
| Leave, within government | −0.19 / −0.17 | −0.27 / −0.33 | −0.15 / −0.12 | +0.07 / +0.15 | −0.35 / −0.43 | +0.29 / +0.32 |
| Leave, other (incl. retire) | −0.45 / −0.39 | −0.45 / −0.40 | −0.42 / −0.34 | −0.12 / −0.09 | −0.40 / −0.54 | +0.20 / +0.45 |
| EEI | +0.60 / +0.62 | +0.54 / +0.44 | +0.63 / +0.62 | +0.20 / +0.18 | +0.39 / +0.55 | −0.10 / −0.43 |
| Global Satisfaction | +0.54 / +0.52 | +0.52 / +0.43 | +0.66 / +0.63 | +0.21 / +0.17 | +0.43 / +0.55 | −0.10 / −0.36 |
| Pay satisfaction | +0.29 / +0.32 | +0.51 / +0.35 | +0.51 / +0.44 | +0.40 / +0.38 | +0.45 / +0.50 | −0.24 / −0.34 |
| Recommend organization | +0.53 / +0.54 | +0.45 / +0.38 | +0.65 / +0.67 | +0.08 / +0.01 | +0.40 / +0.55 | −0.06 / −0.30 |

Restricted to the 20 agencies with ≥5,000 headcount: leave-outside vs quit r = −0.46; leave-other vs retire r = −0.40; leave-any vs total r = −0.48; EEI vs total r = +0.69.

Reading this honestly. Every sign is backwards from what a leading indicator should give: the agencies whose staff said in 2023 they were least likely to leave, and were most engaged, lost the most people in 2025. That is what an exogenous shock looks like. The 2025 exits were allocated by executive decision (DRP offers, RIFs, the USAID shutdown, the Education wind-down), and they landed on small domestic agencies that happen to sit at the top of the engagement table, while DHS and DoD, where stated intent is highest, were protected or grew. Three implications: (1) do not publish a 2025 correlation as evidence for or against FEVS; (2) the within-government share, which is the largest component of stated intent, tracks transfers, and transfer-out in 2025 is the one outcome with roughly zero correlation to anything, which is at least consistent; (3) the proper test is 2023 intent against FY2024 separations, before the shock. OPM's FWD separations files for 2024 exist on data.opm.gov but are not in `data/raw/`; pulling twelve 2024 separations months (about 1 MB each as parquet) is the cheapest way to get a real baseline, and the pipeline's `discover` step already knows the URL pattern.

## 10. Sub-agency feasibility

| Year | Sub-agency field | Codes | Threshold | Join to org tree on code |
|---|---|---|---|---|
| 2019 | `LEVEL1` | 238 (194 non-`ZZ` + 44 `ZZ` residuals), min n = 300 for non-`ZZ` | 300 respondents | 86 of 194 codes exist as org-tree nodes (44%) |
| 2020–2023 | none | — | 750 per agency | — |
| 2024 | `LEVEL1` | 164 in codebook (128 non-`ZZ`) | 500 | 57 of 128 codes exist as org-tree nodes (45%) |

The code overlap is real for DoD and a few departments and false for the rest:

- Matches by code and name: all Air Force MAJCOMs (`AF0J` AETC 12,924 heads, `AF1M` AFMC 64,405), Army commands (`ARAF`, `ARTC`, `ARHR`, `ARCE` USACE 34,150), every `DD` defense agency (`DD07` DLA 22,929, `DD35` DFAS, `DD60` DHA), Navy SYSCOMs and fleets, Treasury (`TR93` IRS 71,841, `TRAJ` OCC, `TRFD` Fiscal Service), Transportation (`TD03` FAA 44,651, `TD04`, `TD05`, `TD09`), `HE10` HHS Office of the Secretary.
- Matches by code with the wrong unit: FEVS `IN01` BLM / FWD `IN01` Office of the Secretary; FEVS `IN05` USGS / FWD `IN05` BLM; FEVS `IN06` NPS / FWD `IN06` Indian Affairs; FEVS `IN07` FWS / FWD `IN07` Reclamation; FEVS `HE12` OIG / FWD `HE12` Administration for Community Living; FEVS `AG10` Research, Education and Economics / FWD `AG10` Foreign Agricultural Service; `GS01`/`GS02` map to 38- and 65-person offices; `ARX2` "Army Materiel Command" maps to a 650-person HQ node.
- No code match at all: Labor (`DL03` BLS vs FWD `DLLS`; `DL04` MSHA vs `DLMS`; `DL06` OSHA vs `DLSH`), DHS (`HS02` CBP vs `HSBD`; `HS04` FEMA vs `HSCB`), Justice (`DJFB` FBI vs `DJ02`; `DJBP` BOP vs `DJ03`), HHS operating divisions (`HE09` NIH vs `HE38`), Commerce (`CM03` Census vs `CM63`), Agriculture (`AG05` Forest Service vs `AG11`), SSA (FEVS has seven deputy-commissioner units; FWD has one node `SZ00`), State, Energy.

So the PRD's assumption that `level1` carries "the same keys as our org tree" holds for roughly the DoD half of the government and fails elsewhere. What is needed is a curated `crosswalk/fevs_level1.json` of about 130 rows (2024 list) mapping each FEVS `LEVEL1` to one org-tree node or to a list of nodes (SSA, State bureaus, EPA regions will be one-to-many or many-to-one), built by name, reviewed by hand, the same way `plum_org.json` was. The 2019 file can serve as a rehearsal: it has 194 named units with n ≥ 300 and covers 13 agencies that later dropped out. As a taste of what the node page would carry, Labor's 2019 units:

| LEVEL1 | Unit | n | EEI | Leave, any | Outside gov | Org-tree node |
|---|---|---|---|---|---|---|
| DL03 | Bureau of Labor Statistics | 1,328 | 76.4 | 35.8 | 5.2 | `DLLS` (by name) |
| DL04 | Mine Safety and Health Administration | 877 | 61.5 | 33.5 | 3.5 | `DLMS` |
| DL05 | Employee Benefits Security Administration | 488 | 70.1 | 32.7 | 5.5 | `DLPW` |
| DL06 | Occupational Safety and Health Administration | 1,084 | 70.7 | 30.9 | 3.5 | `DLSH` |
| DL09 | Office of Workers' Compensation Programs | 653 | 59.2 | 44.0 | 4.6 | `DLOW` |
| DL10 | Wage and Hour Division | 961 | 70.0 | 30.4 | 3.4 | `DLWH` |
| DL11 | Office of the Solicitor | 405 | 71.2 | 31.7 | 7.9 | `DLSL` |
| DLZZ | All other Labor | 2,153 | 65.9 | 39.8 | 4.0 | residual, not a node |

If OPM republishes an intact 2024 file, the same script with `LEVEL1` added to the grouping produces this for 128 units at the 500 threshold. Note the residual `ZZ` rows (22% of 2019 respondents) are unattributable below agency.

## 11. Recommended data model

One fact table, `overview/fevs_agency_year.parquet` (and JSON), grain = FEVS agency code × survey year, codes only, labels from the existing agency lookup. Columns as in the CSV shipped with this document:

| Column | Type | Meaning |
|---|---|---|
| `year` | int | survey year, 2019–2024 |
| `agency` | text | FEVS/FWD two-letter code; `ALL` = governmentwide; `XX` = pooled small agencies (do not display as an agency) |
| `n_resp`, `wt_sum` | int, double | unweighted respondents, sum of `POSTWT` |
| `eei`, `eei_leaders`, `eei_supervisors`, `eei_intrinsic` | double | Employee Engagement Index and subindices |
| `gsi`, `pci`, `exi` | double | Global Satisfaction, Performance Confidence (2021+), Employee Experience (2022+); null where the survey lacked the items |
| `pp_recommend`, `pp_job_sat`, `pp_pay_sat`, `pp_org_sat` | double | the four GSI items separately |
| `pp_encouraged`, `pp_workload`, `pp_skills`, `pp_perf_diff`, `pp_sat_recog`, `pp_recog_quality` | double | candidate leading-indicator items |
| `leave_no`, `leave_other`, `leave_within`, `leave_outside`, `leave_any` | double | weighted intent-to-leave shares among valid `DLEAVING` responses |
| `leave_n_valid`, `leave_missing_pct` | int, double | unweighted valid count; share of rows with `DLEAVING` masked |
| `leave2020pre_*` | double | 2020 only, the "before the pandemic" recall variant |
| `source` (to add) | text | `prdf` or `published` so the 2024 row, which can only come from the index spreadsheets, is labelled |

Recommendations that differ from PRD 5.9 as written:

1. Keep the grain at FEVS agency code rather than "overview group"; the codes are FWD codes, so the join to groups is the existing one and no `fevs_labels` name matching is needed. The only label-based join left is the 2024 published spreadsheet (agency names, no codes); that is about 35 names and can be a seed file.
2. For 2024, populate the index columns from the published spreadsheets and leave the intent-to-leave columns null unless OPM fixes the PRDF; the Report by Agency cannot supply them.
3. Add a `response_rate` column from the Governmentwide Management Report's agency-response-rate Excel appendix (one manual annual pull, like OMB FTE); the PRDF has no response rates.
4. Show the intent-to-leave split as three bars (outside, within, other-including-retire) and say in the label that retirement is folded into "other". Put "within government" beside FWD transfers, not beside quits.
5. The landing-table column should be 2023 (last intact respondent file) for intent to leave and 2024 (published) for EEI, each labelled with its year, rather than a single "2024 FEVS" column.

## 12. Caveats the page must carry

- Weighted estimates, not counts. `POSTWT` is OPM's post-stratification weight to the eligible population; 2021 was a sample year with weights up to 789 and 292k respondents, so 2021 agency estimates are noisier.
- Response rates 34–44% governmentwide and 29–41% for very large agencies; non-response bias is unknown and OPM's weights adjust only on known strata.
- No 2025 survey. The 2024 survey fielded before the 2025 reductions, so it is a baseline, not a description of the current workforce, and the 2025 outcome data are shaped by policy, not by the sentiment the survey measured.
- Masking. Demographics, including `DLEAVING`, are blanked for 6–9% of respondents by OPM's rule-of-ten cell suppression; blanks are not random (they concentrate in small demographic cells within work units). Intent-to-leave shares are computed among valid responses.
- Redaction. DEIA items and the DEIA index were removed from the 2019, 2022 and 2023 files in June 2026 and the 2022 readme was partly redacted; files with "revised"/"Redacted" in the name are the only versions now published. Keep the zips in `data/raw/fevs/` so the analysis does not depend on OPM's site.
- Retirement intent is not separable from "other". Pay satisfaction is the one GSI item that is a plausible external-exit driver and it is reported separately for that reason.
- Agency coverage changes by year (45 codes in 2019, 31 in 2021–2023, 36 in 2024) and VA is never present. `XX` is a pool and must not be shown as an agency.
- Sub-agency results, when they exist, need a curated code crosswalk (section 10); a join on code alone mislabels units in Interior, HHS, Agriculture and GSA.
- Item numbers shift every year; any pipeline code must carry the per-year item map in section 3.1 and fail loudly if a mapped column is absent, in line with the schema-drift rule.

## 13. Reproduction

- `data/reference/fevs/fevs_agency_year_compute.py` reads the five CSVs with DuckDB (`read_csv(..., all_varchar=true)`), never pandas, and writes `fevs_agency_year.csv` in about two minutes. Paths inside the script are relative to the repo root.
- Validation and the separations comparison were run from scratchpad scripts; both are straightforward to re-derive from sections 4 and 9 (Pearson and Spearman by hand, no numpy).
- Environment note: files under `.venv/` were iCloud-evicted (`dataless`) on this machine, which is why `import openpyxl` and any pandas import hang; the xlsx files were read with a stdlib zip+XML reader instead. Materializing the venv (`brctl download .venv`) or moving the repo off the synced Desktop would remove that hazard.
