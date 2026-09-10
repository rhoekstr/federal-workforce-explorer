"""Compute weighted FEVS indices and intent-to-leave per agency per year from the PRDFs."""
import duckdb, csv, sys
OUT = "data/reference/fevs/fevs_agency_year.csv"
FILES = {2019: "data/raw/fevs/2019/2019/2019_OPM_FEVS_PRDF_Redacted.csv",
         2020: "data/raw/fevs/2020/FEVS_2020_PRDF.csv",
         2021: "data/raw/fevs/2021/2021_OPM_FEVS_PRDF.csv",
         2022: "data/raw/fevs/2022/2022_OPM_FEVS_PRDF_revised.csv",
         2023: "data/raw/fevs/2023/2023/2023_OPM_FEVS_PRDF_Redacted.csv"}
# Item numbers per year, matched on exact item wording to the 2023 Indices and Dimensions Guide.
ITEMS = {
 2019: dict(IWE=["Q3","Q4","Q6","Q11","Q12"], LL=["Q53","Q54","Q56","Q60","Q61"], SUP=["Q47","Q48","Q49","Q51","Q52"],
            GS=["Q40","Q69","Q70","Q71"], PC=[], EXI=[],
            recommend="Q40", job_sat="Q69", pay_sat="Q70", org_sat="Q71", encouraged="Q3", workload="Q10",
            skills="Q1", perf_diff="Q24", sat_recog="Q65", recog_quality="Q31"),
 2020: dict(IWE=["Q2","Q3","Q4","Q6","Q7"], LL=["Q26","Q27","Q28","Q30","Q31"], SUP=["Q21","Q22","Q23","Q24","Q25"],
            GS=["Q17","Q36","Q37","Q38"], PC=[], EXI=[],
            recommend="Q17", job_sat="Q36", pay_sat="Q37", org_sat="Q38", encouraged="Q2", workload="Q5",
            skills="Q1", perf_diff="Q12", sat_recog="Q35", recog_quality="Q14"),
 2021: dict(IWE=["Q2","Q3","Q4","Q6","Q7"], LL=["Q32","Q33","Q34","Q36","Q37"], SUP=["Q27","Q28","Q29","Q30","Q31"],
            GS=["Q23","Q42","Q43","Q44"], PC=["Q14","Q15","Q16","Q17"], EXI=[],
            recommend="Q23", job_sat="Q42", pay_sat="Q43", org_sat="Q44", encouraged="Q2", workload="Q5",
            skills="Q1", perf_diff="Q12", sat_recog="Q41", recog_quality="Q20"),
 2022: dict(IWE=["Q2","Q3","Q4","Q6","Q7"], LL=["Q55","Q56","Q57","Q59","Q60"], SUP=["Q46","Q48","Q49","Q50","Q52"],
            GS=["Q43","Q68","Q69","Q70"], PC=["Q19","Q20","Q21","Q22"], EXI=["Q85","Q86","Q87","Q88","Q89"],
            recommend="Q43", job_sat="Q68", pay_sat="Q69", org_sat="Q70", encouraged="Q2", workload="Q5",
            skills="Q1", perf_diff="Q16", sat_recog="Q67", recog_quality="Q35"),
 2023: dict(IWE=["Q2","Q3","Q4","Q6","Q7"], LL=["Q57","Q58","Q59","Q61","Q62"], SUP=["Q48","Q50","Q51","Q52","Q54"],
            GS=["Q46","Q70","Q71","Q72"], PC=["Q20","Q21","Q22","Q23"], EXI=["Q86","Q87","Q88","Q89","Q90"],
            recommend="Q46", job_sat="Q70", pay_sat="Q71", org_sat="Q72", encouraged="Q2", workload="Q5",
            skills="Q1", perf_diff="Q17", sat_recog="Q69", recog_quality="Q35"),
}
# DLEAVING code -> meaning, per year (2019 ordering differs; 2020 has pre-COVID A and "today" B variants).
LEAVE = {2019: dict(no="A", within="B", outside="C", other="D"),
         2020: dict(no="A", other="B", within="C", outside="D"),
         2021: dict(no="A", other="B", within="C", outside="D"),
         2022: dict(no="A", other="B", within="C", outside="D"),
         2023: dict(no="A", other="B", within="C", outside="D")}
LEAVE_VAR = {2019: "DLEAVING", 2020: "DLEAVINGB", 2021: "DLEAVING", 2022: "DLEAVING", 2023: "DLEAVING"}
SINGLE = ["recommend","job_sat","pay_sat","org_sat","encouraged","workload","skills","perf_diff","sat_recog","recog_quality"]

def pp(q):  # weighted percent positive; 'X' (do not know) and blanks excluded from the denominator
    return (f"100.0*sum(case when {q} in ('4','5') then w else 0 end)"
            f"/nullif(sum(case when {q} in ('1','2','3','4','5') then w else 0 end),0)")
def share(var, code):
    return f"100.0*sum(case when {var}='{code}' then w else 0 end)/nullif(sum(case when {var} in ('A','B','C','D') then w else 0 end),0)"

con = duckdb.connect()
rows = []
for year, path in FILES.items():
    it = ITEMS[year]; lv = LEAVE[year]; lvar = LEAVE_VAR[year]
    agency = "AGENCY" if year == 2019 else "agency"
    allq = sorted(set(it["IWE"] + it["LL"] + it["SUP"] + it["GS"] + it["PC"] + it["EXI"] + [it[k] for k in SINGLE]), key=lambda s: int(s[1:]))
    sel = [f"{pp(q)} as pp_{q}" for q in allq]
    sel += [f"{share(lvar, lv[k])} as leave_{k}" for k in ("no","other","within","outside")]
    sel += [f"sum(case when {lvar} in ('A','B','C','D') then 1 else 0 end) as leave_n_valid",
            f"100.0*sum(case when {lvar} is null or {lvar} not in ('A','B','C','D') then 1 else 0 end)/count(*) as leave_missing_pct"]
    if year == 2020:
        sel += [f"{share('DLEAVINGA', lv[k])} as pre_{k}" for k in ("other","within","outside")]
    sql = (f"select coalesce({agency}, 'ALL') as agency, count(*) as n_resp, sum(w) as wt_sum, {', '.join(sel)} "
           f"from (select *, cast(POSTWT as double) as w from read_csv('{path}', all_varchar=true, header=true)) "
           f"group by grouping sets (({agency}), ()) order by 1")
    res = con.execute(sql); cols = [d[0] for d in res.description]
    for r in res.fetchall():
        d = dict(zip(cols, r))
        def mean(qs): 
            vals = [d[f"pp_{q}"] for q in qs]
            return sum(vals)/len(vals) if qs and all(v is not None for v in vals) else None
        iwe, ll, sup = mean(it["IWE"]), mean(it["LL"]), mean(it["SUP"])
        out = dict(year=year, agency=d["agency"], n_resp=d["n_resp"], wt_sum=round(d["wt_sum"], 1),
                   eei=(iwe+ll+sup)/3, eei_leaders=ll, eei_supervisors=sup, eei_intrinsic=iwe,
                   gsi=mean(it["GS"]), pci=mean(it["PC"]), exi=mean(it["EXI"]))
        for k in SINGLE: out[f"pp_{k}"] = d[f"pp_{it[k]}"]
        for k in ("no","other","within","outside"): out[f"leave_{k}"] = d[f"leave_{k}"]
        out["leave_any"] = 100 - d["leave_no"] if d["leave_no"] is not None else None
        out["leave_n_valid"] = d["leave_n_valid"]; out["leave_missing_pct"] = d["leave_missing_pct"]
        for k in ("other","within","outside"): out[f"leave2020pre_{k}"] = d.get(f"pre_{k}")
        rows.append(out)
    print(f"{year}: {len([r for r in rows if r['year']==year])} rows", file=sys.stderr)
fields = list(rows[0].keys())
with open(OUT, "w", newline="") as f:
    wr = csv.DictWriter(f, fieldnames=fields); wr.writeheader()
    for r in rows:
        wr.writerow({k: (round(v, 2) if isinstance(v, float) else ("" if v is None else v)) for k, v in r.items()})
print("wrote", OUT, len(rows), "rows", file=sys.stderr)
