"""Headline descriptive statistics for the SSA AI-exposure paper (Python).
Writes results/desc_py.json for the R<->Python cross-check."""
import json, os, numpy as np, pandas as pd
os.makedirs("results", exist_ok=True)
P = pd.read_csv("harmonized_workers.csv", low_memory=False)
A = "auto_genai"

def m(s): return round(float(np.mean(s)), 6)
out = {}
out["n_total"] = int(len(P))
out["mean_auto"] = m(P[A])
out["median_auto"] = round(float(P[A].median()), 6)
out["share_near_zero_lt0.05"] = m(P[A] < 0.05)
out["share_agri_elem_major69"] = m(P.major.isin([6, 9]))
# by country
out["by_country_mean"] = {k: m(v) for k, v in P.groupby("country")[A]}
out["by_country_n"] = {k: int(v) for k, v in P.groupby("country").size().items()}
# by ISCO major group
out["by_major_mean"] = {int(k): m(v) for k, v in P.dropna(subset=["major"]).groupby("major")[A]}
out["by_major_share"] = {int(k): m(P.major == k) for k in sorted(P.major.dropna().unique())}
# per-country sample composition (for the summary-statistics table)
comp = {}
for c, g in list(P.groupby("country")) + [("All (pooled)", P)]:
    comp[c] = {"n": int(len(g)),
               "pct_female": round(100 * (g.sex == "female").mean(), 1),
               "mean_age": round(float(g.age.mean()), 1),
               "pct_urban": round(100 * float(np.nanmean(g.urban)), 1),
               "pct_agri": round(100 * (g.status == "agriculture").mean(), 1),
               "pct_wage": round(100 * (g.status == "wage_nonag").mean(), 1),
               "mean_auto": m(g.auto_genai)}
out["country_composition"] = comp
# by employment status
out["by_status_mean"] = {k: m(v) for k, v in P.groupby("status")[A]}
out["by_status_share"] = {k: m(P.status == k) for k in sorted(P.status.unique())}
# by urban/rural (exclude missing)
pu = P.dropna(subset=["urban"])
out["mean_urban"] = m(pu[pu.urban == 1][A]); out["mean_rural"] = m(pu[pu.urban == 0][A])
# by sex
ps = P.dropna(subset=["sex"])
out["mean_male"] = m(ps[ps.sex == "male"][A]); out["mean_female"] = m(ps[ps.sex == "female"][A])
# top decile concentration: share of all "exposure mass" held by top 10% of workers
x = np.sort(P[A].values)
top10 = x[int(0.9*len(x)):].sum() / x.sum()
out["top10pct_share_of_exposure"] = round(float(top10), 6)
# urban gap regression-free: mean diff
out["urban_minus_rural"] = round(out["mean_urban"] - out["mean_rural"], 6)

with open("results/desc_py.json", "w") as f: json.dump(out, f, indent=2)
for k, v in out.items():
    print(f"{k}: {v}" if not isinstance(v, dict) else f"{k}: {{...{len(v)}...}}")
