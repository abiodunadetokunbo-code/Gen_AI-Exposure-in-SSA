"""Sensitivity of the worker-level results to the ISCO-08 -> O*NET step (plan
item 8, step 11). Python side; the R twin is crosswalk_sensitivity_v2.R.

Each ISCO-08 code links to 1-35 O*NET occupations (crosswalks/isco08_to_onetsoc10.csv).
The headline takes the simple mean of their Althoff scores. Alternatives:
  median, min, max : of the linked scores
  emp_weighted     : mean weighted by US employment, from the BLS OEWS May 2018
                     national file (oews/oesm18nat/national_M2018_dl.xlsx).
                     Each O*NET-SOC 2010 detailed code inherits the employment
                     of its 6-digit SOC base, split evenly among the base's
                     detailed codes in the crosswalk; bases OEWS reports only
                     at the broad level take the broad total the same way.
                     May 2018 is the last OEWS year on the 2010 SOC, which is
                     the vintage of soc10_isco08.dta and of the exposure files.
  draws            : 2,000 draws, each picking one linked occupation per ISCO
                     code at random (seed 20260919)
The 7 codes the exposure file fills from 3- or 2-digit group means, the
own-use farmers, Tanzania's market farmers and the TASCO rows mapped to a
submajor average are rescored from each alternative vector by the same rules
as the headline. The mean must reproduce isco08_to_exposure.csv and the worker
file to 1e-9. Writes results/crosswalk_sensitivity_v2_py.json.
"""
import json

import numpy as np
import pandas as pd

SEED, NDRAW = 20260919, 2000
X = pd.read_csv("../crosswalks/isco08_to_exposure.csv")
L = pd.read_csv("../crosswalks/isco08_to_onetsoc10.csv")
O = pd.read_csv("../atlas_data/althoff_occ_exposure_onetsoc.csv")[["soc_code_onet", "auto_genai"]]
P = pd.read_csv("harmonized_workers_v2.csv", low_memory=False)
A = "auto_genai"

LE = L.merge(O, left_on="onetsoc10", right_on="soc_code_onet", how="inner").sort_values(["isco08", "onetsoc10"])

# US employment per linked O*NET occupation, for the employment-weighted variant.
OEWS = pd.read_excel("../oews/oesm18nat/national_M2018_dl.xlsx",
                     usecols=["OCC_CODE", "OCC_GROUP", "TOT_EMP"])
OEWS["TOT_EMP"] = pd.to_numeric(OEWS.TOT_EMP, errors="coerce")
emp_det = OEWS[OEWS.OCC_GROUP == "detailed"].set_index("OCC_CODE").TOT_EMP
emp_brd = OEWS[OEWS.OCC_GROUP == "broad"].set_index("OCC_CODE").TOT_EMP
soc6 = LE.onetsoc10.str[:7]
unit = soc6.where(soc6.isin(emp_det.index), soc6.str[:6] + "0")
LE["emp"] = ([emp_det.get(u, emp_brd.get(u, np.nan)) for u in unit]
             / unit.map(unit.value_counts()).to_numpy())
codes = X.isco08.to_numpy()
direct = X.match.to_numpy() == "direct"
pos = {c: i for i, c in enumerate(codes)}


def fill(v):
    """Complete a vector over X's codes: fallback codes take 3- then 2-digit means of direct codes."""
    s = pd.Series(v, index=codes)
    d = s[direct]
    g3 = d.groupby(d.index // 10).mean(); g2 = d.groupby(d.index // 100).mean()
    for c, m in zip(codes, X.match):
        if m == "impute_3dig":
            s[c] = g3[c // 10]
        elif m == "impute_2dig":
            s[c] = g2[c // 100]
    return s


def agg(f):
    v = np.full(len(codes), np.nan)
    r = LE.groupby("isco08")[A].agg(f)
    v[[pos[c] for c in r.index]] = r.to_numpy()
    return fill(v)


def agg_emp():
    """Employment-weighted mean; ISCO codes with no OEWS figure keep the simple mean."""
    v = np.full(len(codes), np.nan)
    d = LE[LE.emp.gt(0)]
    r = d.groupby("isco08").apply(lambda g: np.average(g[A], weights=g.emp), include_groups=False)
    v[[pos[c] for c in r.index]] = r.to_numpy()
    linked = np.isin(codes, LE.isco08.unique())
    back = linked & np.isnan(v)
    v[back] = agg("mean").to_numpy()[back]
    return fill(v), int(back.sum()), int(r.size)


# workers: which vector entry each row reads
fam = (P.imputed_reason == "own_use_farmer_family_use").to_numpy()
mkt = (P.imputed_reason == "own_use_farmer_market_oriented").to_numpy()
subr = (P.imputed_reason == "tasco_map_submajor").to_numpy()
coded = P.isco08.notna().to_numpy()
idx = np.full(len(P), -1)
idx[coded] = [pos[int(c)] for c in P.isco08[coded]]
XS0 = X.groupby(X.isco08 // 10)[A].mean()
sub_of = np.array([XS0.index[np.isclose(XS0.values, v, rtol=0, atol=1e-12)][0] if s else -1
                   for v, s in zip(P[A], subr)])
subs_codes = [6310, 6320, 6330, 6340]


def workers(s):
    v = s.to_numpy()
    y = np.empty(len(P))
    y[coded] = v[idx[coded]]
    y[fam] = s.loc[subs_codes].mean()
    y[mkt] = s[s.index // 1000 == 6].mean()
    sm = s.groupby(s.index // 10).mean()
    y[subr] = sm.loc[sub_of[subr]].to_numpy()
    return y


w = P.weight.to_numpy()
masks = {"agriculture": (P.status == "agriculture").to_numpy(),
         "selfemp_nonag": (P.status == "selfemp_nonag").to_numpy(),
         "wage_nonag": (P.status == "wage_nonag").to_numpy()}
cmask = {c: (P.country == c).to_numpy() for c in sorted(P.country.unique())}
m4 = (P.major == 4).to_numpy(); m6 = (P.major == 6).to_numpy()


def stats(y):
    st = {k: float(y[m].mean()) for k, m in masks.items()}
    return {"pooled": float(y.mean()), "pooled_wtd": float(np.average(y, weights=w)),
            **{f"wtd|{c}": float(np.average(y[m], weights=w[m])) for c, m in cmask.items()},
            **st, "wage_minus_self": st["wage_nonag"] - st["selfemp_nonag"],
            "clerical": float(y[m4].mean()), "skilled_agri": float(y[m6].mean()),
            "clerical_over_agri": float(y[m4].mean() / y[m6].mean())}


out = {}
base = agg("mean")
assert np.allclose(base.to_numpy(), X[A].to_numpy(), rtol=0, atol=1e-9), "mean does not reproduce the exposure file"
assert np.allclose(workers(base), P[A].to_numpy(), rtol=0, atol=1e-9), "mean does not reproduce the worker file"
for name, f in [("mean", "mean"), ("median", "median"), ("min", "min"), ("max", "max")]:
    out[name] = {k: round(v, 4) for k, v in stats(workers(agg(f))).items()}
emp_vec, n_back, n_wtd = agg_emp()
out["emp_weighted"] = {k: round(v, 4) for k, v in stats(workers(emp_vec)).items()}

# random draws: one linked occupation per ISCO code
rng = np.random.default_rng(SEED)
groups = [g[A].to_numpy() for _, g in LE.groupby("isco08")]
gpos = np.array([pos[c] for c in LE.isco08.unique()])
draws = []
for _ in range(NDRAW):
    v = np.full(len(codes), np.nan)
    v[gpos] = [g[rng.integers(len(g))] for g in groups]
    draws.append(stats(workers(fill(v))))
D = pd.DataFrame(draws)
out["draws"] = {k: dict(mean=round(float(D[k].mean()), 4), sd=round(float(D[k].std(ddof=1)), 4),
                        p025=round(float(D[k].quantile(0.025)), 4), p975=round(float(D[k].quantile(0.975)), 4))
                for k in D.columns}
out["draws_share_wage_above_self"] = round(float((D.wage_minus_self > 0).mean()), 3)
out["draws_share_clerical_over_agri_gt_10"] = round(float((D.clerical_over_agri > 10).mean()), 3)
out["meta"] = dict(n_draws=NDRAW, seed=SEED, isco_codes_linked=len(groups),
                   isco_single_link=int(sum(len(g) == 1 for g in groups)),
                   oews_release="May 2018 national, 2010 SOC",
                   onetsoc_with_employment=int(LE.emp.gt(0).sum()),
                   onetsoc_linked=int(len(LE)),
                   isco_employment_weighted=n_wtd,
                   isco_fell_back_to_mean=n_back)

json.dump(out, open("results/crosswalk_sensitivity_v2_py.json", "w"), indent=2)
print("mean reproduces the exposure file and the worker file to 1e-9")
print(pd.DataFrame({k: out[k] for k in ["mean", "emp_weighted", "median", "min", "max"]}).round(4).to_string())
print(f"OEWS: {out['meta']['onetsoc_with_employment']}/{len(LE)} linked O*NET codes carry employment; "
      f"{n_wtd} ISCO codes weighted, {n_back} fell back to the simple mean")
print(pd.DataFrame(out["draws"]).T.to_string())
print({k: out[k] for k in ["draws_share_wage_above_self", "draws_share_clerical_over_agri_gt_10"]})
