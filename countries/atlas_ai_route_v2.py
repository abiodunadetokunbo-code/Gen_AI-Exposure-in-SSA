"""AI-route exposure shares from the Atlas task-country file (plan item 6, route a;
step 10). Python side; the R twin is atlas_ai_route_v2.R.

The released countries.csv carries llm_dominant_share = 0 for every country, so
the shares are built here from atlas_data/task_country_core/ (release 20260406,
provenance in that folder). One row per task and country: the file repeats a
task when it sits under several O*NET paths, with identical labels, and
dropping the repeats reproduces countries.csv (share_exposed, task_count) to
1e-12, which the script checks.

  share_exposed      : exposure level 2 or 3 (as published)
  ai_route_share     : exposed, and AI materially involved
  genai_route_share  : exposed, and the AI function is learned content
                       transformation (closest to generative models)
  non_ai_exposed     : share_exposed - ai_route_share

Outputs: the three shares for the African cross-section, their correlation
with the ILOSTAT rebuild, and the old Table 7 specifications with each share
as the outcome (per-specification complete cases and HC1 errors, as the old
table used). The share_exposed run must reproduce the old coefficients.
Writes results/atlas_ai_route_v2_py.json and atlas_ai_route_v2_countries.csv.
"""
import glob
import json

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

COLS = ["iso3", "task_id", "exposure_level_mode", "has_material_ai_integration_mode",
        "dominant_ai_function_mode"]
T = pd.concat([pd.read_parquet(f, columns=COLS)
               for f in sorted(glob.glob("../atlas_data/task_country_core/*.parquet"))],
              ignore_index=True).drop_duplicates(["iso3", "task_id"])
exposed = T.exposure_level_mode.isin([2, 3])
T["exp"] = exposed.astype(float)
T["ai"] = (exposed & T.has_material_ai_integration_mode.astype(bool)).astype(float)
T["genai"] = (exposed & (T.dominant_ai_function_mode == "learned_content_transformation")).astype(float)
g = T.groupby("iso3")
S = pd.DataFrame({"task_count": g.size(), "share_exposed": g.exp.mean(),
                  "ai_route_share": g.ai.mean(), "genai_route_share": g.genai.mean()})
S["non_ai_exposed"] = S.share_exposed - S.ai_route_share

pub = pd.read_csv("../atlas_data/countries.csv").set_index("iso3")
assert (S.task_count == pub.loc[S.index, "task_count"]).all()
assert np.allclose(S.share_exposed, pub.loc[S.index, "share_exposed"], rtol=0, atol=1e-12)

cs = pd.read_csv("macro_country_cross_section.csv")
IL = pd.read_csv("macro_ilostat_v2_countries.csv")[["iso3", "exp_unit", "exp_lsms", "exp_lsms_ex"]]
C = cs.drop(columns="share_exposed").merge(S.reset_index(), on="iso3", how="left").merge(IL, on="iso3", how="left")
assert np.allclose(C.share_exposed, cs.share_exposed, rtol=0, atol=1e-9)
C.to_csv("atlas_ai_route_v2_countries.csv", index=False)

YS = ["share_exposed", "ai_route_share", "genai_route_share", "non_ai_exposed"]
out = {"n_countries": int(len(C)),
       "world": {y: round(float(S[y].median()), 4) for y in YS},
       "africa": {y: dict(mean=round(float(C[y].mean()), 4), median=round(float(C[y].median()), 4),
                          min=round(float(C[y].min()), 4), max=round(float(C[y].max()), 4)) for y in YS},
       "ai_part_of_exposed_africa": round(float((C.ai_route_share / C.share_exposed).mean()), 4),
       "countries": {r["iso3"]: {y: round(float(r[y]), 4) for y in YS} for _, r in C.iterrows()}}

corr = {}
for y in YS:
    for z in ["share_exposed", "exp_unit", "exp_lsms", "exp_lsms_ex"]:
        if y == z:
            continue
        d = C[[y, z]].dropna()
        corr[f"{y}|{z}"] = dict(n=int(len(d)), pearson=round(float(d.corr().iloc[0, 1]), 4),
                                spearman=round(float(d.corr(method="spearman").iloc[0, 1]), 4))
out["corr"] = corr

C["lgdp"] = np.log(C.gdppc); C["informal_s"] = C.informal / 100; C["agri_s"] = C.selfemp_agri / 100
specs = {"(1) informality": "informal_s", "(2) agri self-emp": "agri_s", "(3) log GDPpc": "lgdp",
         "(4) informality + log GDPpc": "informal_s + lgdp", "(5) agri + log GDPpc": "agri_s + lgdp",
         "(6) all three": "informal_s + agri_s + lgdp"}
for y in YS:
    res = {}
    for k, rhs in specs.items():
        m = smf.ols(f"{y} ~ {rhs}", data=C).fit(cov_type="HC1")
        res[k] = {t: dict(b=round(float(m.params[t]), 4), se=round(float(m.bse[t]), 4)) for t in m.params.index}
        res[k]["_n"] = int(m.nobs); res[k]["_r2"] = round(float(m.rsquared), 3)
    out[f"reg_{y}"] = res

old = json.load(open("archive_v1/results/revision_py.json"))["macro_reg"]
for k in specs:
    for t, v in old[k].items():
        if isinstance(v, dict):
            assert abs(v["b"] - out["reg_share_exposed"][k][t]["b"]) < 1e-4, (k, t)
            assert abs(v["se"] - out["reg_share_exposed"][k][t]["se"]) < 1e-4, (k, t)

json.dump(out, open("results/atlas_ai_route_v2_py.json", "w"), indent=2)
print("task file reproduces countries.csv; share_exposed run reproduces the old Table 7")
print(C[["iso3"] + YS + ["exp_lsms"]].sort_values("ai_route_share").round(3).to_string(index=False))
print(json.dumps({k: out[k] for k in ["world", "africa", "ai_part_of_exposed_africa"]}, indent=1))
print("wrote results/atlas_ai_route_v2_py.json, atlas_ai_route_v2_countries.csv")
