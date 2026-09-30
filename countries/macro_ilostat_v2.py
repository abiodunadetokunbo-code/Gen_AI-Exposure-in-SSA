"""Cross-country section rebuilt on ILOSTAT (plan item 6, route b; step 10).
Python side; the R twin is macro_ilostat_v2.R.

Country exposure = sum over ISCO-08 major groups 1-9 of the group's share of
employment (ILOSTAT EMP_TEMP_SEX_OCU_NB_A, both sexes, latest year from 2015)
times the group's Althoff-Reichardt score. Armed forces (0) and "not
classified" (X) are left out and the shares rescaled over groups 1-9.
Countries reporting only ISCO-88 are left out (author decision, 2026-09-19).

Three score vectors for the major groups:
  unit : mean over the ISCO-08 unit codes in crosswalks/isco08_to_exposure.csv
  lsms : weighted mean over workers in harmonized_workers.csv (Nigeria,
         Tanzania, Uganda), so each group's mix of unit codes is African
  lsms_ex : the same without family-use farmers, matching the ILO 2013
         employment boundary most ILOSTAT series follow

Outputs: the country table, its correlation with the Atlas share_exposed, a
check against the LSMS worker means for Nigeria, Tanzania and Uganda, and the
six cross-country regressions of the old Table 7 with the new measure as the
outcome (HC1 standard errors). Writes results/macro_ilostat_v2_py.json and
macro_ilostat_v2_countries.csv.
"""
import glob
import json

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

X = pd.read_csv("../crosswalks/isco08_to_exposure.csv")
P = pd.read_csv("harmonized_workers_v2.csv", low_memory=False)
cs = pd.read_csv("macro_country_cross_section.csv")
MAJ = [f"OCU_ISCO08_{i}" for i in range(1, 10)]
X_SHARE_CUT = 20.0  # robustness: drop countries with more than this % "not classified"

frames = []
for f in sorted(glob.glob("../ilostat/raw/*.csv")):
    with open(f, encoding="utf-8", errors="replace") as fh:
        if not fh.read(200).startswith("DATAFLOW"):
            continue  # "No data is found"
    frames.append(pd.read_csv(f, low_memory=False))
D = pd.concat(frames)
D = D[D.OCU.str.startswith("OCU_ISCO08") & (D.TIME_PERIOD >= 2015)]
D = D[D.TIME_PERIOD == D.groupby("REF_AREA").TIME_PERIOD.transform("max")]
W = D.pivot_table(index="REF_AREA", columns="OCU", values="OBS_VALUE", aggfunc="first")
assert W[MAJ].notna().all().all()
emp = W[MAJ].sum(axis=1)
share = W[MAJ].div(emp, axis=0)
share.columns = range(1, 10)
year = D.groupby("REF_AREA").TIME_PERIOD.first()
x_pct = 100 * W.get("OCU_ISCO08_X", pd.Series(0.0, index=W.index)).fillna(0) / W["OCU_ISCO08_TOTAL"]

vec_unit = X.groupby(X.isco08 // 1000).auto_genai.mean()
vec_lsms = P.groupby("major").apply(lambda g: np.average(g.auto_genai, weights=g.weight))
vec_lsms.index = vec_lsms.index.astype(int)
PX = P[P.imputed_reason != "own_use_farmer_family_use"]
vec_lsms_ex = PX.groupby("major").apply(lambda g: np.average(g.auto_genai, weights=g.weight))
vec_lsms_ex.index = vec_lsms_ex.index.astype(int)
VECS = {"exp_unit": vec_unit, "exp_lsms": vec_lsms, "exp_lsms_ex": vec_lsms_ex}
YS = list(VECS)

C = pd.DataFrame({"year": year, "x_pct": x_pct.round(2),
                  **{y: share.mul(v.loc[range(1, 10)].to_numpy(), axis=1).sum(axis=1)
                     for y, v in VECS.items()},
                  "agri_share": share[6], "clerical_share": share[4]})
C.index.name = "iso3"
C = C.reset_index().merge(cs, on="iso3", how="left")
C.to_csv("macro_ilostat_v2_countries.csv", index=False)

out = {"n_countries": int(len(C)),
       "vectors": {y: {str(k): round(float(x), 4) for k, x in v.loc[range(1, 10)].items()}
                   for y, v in VECS.items()},
       "countries": {r["iso3"]: dict(year=int(r["year"]), x_pct=round(float(r["x_pct"]), 2),
                                     agri_share=round(float(r["agri_share"]), 4),
                                     **{y: round(float(r[y]), 4) for y in YS})
                     for _, r in C.iterrows()}}

for y in YS:
    out[f"{y}_summary"] = dict(mean=round(float(C[y].mean()), 4), median=round(float(C[y].median()), 4),
                               min=round(float(C[y].min()), 4), max=round(float(C[y].max()), 4))

# agreement with the Atlas measure on the countries both cover
A = C.dropna(subset=["share_exposed"])
out["vs_atlas"] = {y: dict(n=int(len(A)),
                           pearson=round(float(A[[y, "share_exposed"]].corr().iloc[0, 1]), 4),
                           spearman=round(float(A[[y, "share_exposed"]].corr(method="spearman").iloc[0, 1]), 4))
                   for y in YS}

# check against the worker-level means (the LSMS years differ from ILOSTAT's)
iso = {"Nigeria 2023": "NGA", "Tanzania 2020": "TZA", "Uganda 2019": "UGA"}
ex = P[P.imputed_reason != "own_use_farmer_family_use"]
out["vs_lsms"] = {
    iso[c]: dict(lsms_wtd=round(float(np.average(g.auto_genai, weights=g.weight)), 4),
                 lsms_wtd_own_use_excluded=round(float(np.average(
                     ex[ex.country == c].auto_genai, weights=ex[ex.country == c].weight)), 4),
                 lsms_agri_share_wtd=round(float(np.average(g.major == 6, weights=g.weight)), 4),
                 ilostat_agri_share=round(float(C.loc[C.iso3 == iso[c], "agri_share"].iloc[0]), 4),
                 **{f"ilostat_{y}": round(float(C.loc[C.iso3 == iso[c], y].iloc[0]), 4) for y in YS})
    for c, g in P.groupby("country")}

# the old Table 7 specifications, new outcome
R = C.dropna(subset=["informal", "selfemp_agri", "gdppc"]).copy()
R["lgdp"] = np.log(R.gdppc); R["informal_s"] = R.informal / 100; R["agri_s"] = R.selfemp_agri / 100
specs = {"(1) informality": "informal_s", "(2) agri self-emp": "agri_s", "(3) log GDPpc": "lgdp",
         "(4) informality + log GDPpc": "informal_s + lgdp", "(5) agri + log GDPpc": "agri_s + lgdp",
         "(6) all three": "informal_s + agri_s + lgdp"}
for label, sample in [("all", R), ("x_le_20", R[R.x_pct <= X_SHARE_CUT])]:
    for y in YS:
        res = {}
        for k, rhs in specs.items():
            m = smf.ols(f"{y} ~ {rhs}", data=sample).fit(cov_type="HC1")
            res[k] = {t: dict(b=round(float(m.params[t]), 4), se=round(float(m.bse[t]), 4))
                      for t in m.params.index}
            res[k]["_n"] = int(m.nobs); res[k]["_r2"] = round(float(m.rsquared), 3)
        out[f"reg_{y}_{label}"] = res
out["x_gt_20"] = sorted(C.loc[C.x_pct > X_SHARE_CUT, "iso3"])

json.dump(out, open("results/macro_ilostat_v2_py.json", "w"), indent=2)
print(C[["iso3", "year", "x_pct"] + YS + ["agri_share", "share_exposed"]]
      .sort_values("exp_unit").round(3).to_string(index=False))
print(json.dumps({k: out[k] for k in ["vs_atlas", "vs_lsms", "x_gt_20"]}, indent=1))
print("wrote results/macro_ilostat_v2_py.json, macro_ilostat_v2_countries.csv")
