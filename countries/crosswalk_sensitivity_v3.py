"""Revision-3 addition to the crosswalk sensitivity table (plan review3, step
7). Adds wage_formal, wage_informal and formal_minus_informal to each of the
five crosswalk rules (mean, median, min, max, employment-weighted) and to the
2,000 random draws, alongside draws_share_formal_above_informal, the twin of
the existing draws_share_wage_above_self. Reuses the aggregation and
worker-vector functions from crosswalk_sensitivity_v2.py unchanged. Does not
touch crosswalk_sensitivity_v2.py or its output.

Writes results/crosswalk_sensitivity_v3_py.json.
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
    v = np.full(len(codes), np.nan)
    d = LE[LE.emp.gt(0)]
    r = d.groupby("isco08").apply(lambda g: np.average(g[A], weights=g.emp), include_groups=False)
    v[[pos[c] for c in r.index]] = r.to_numpy()
    linked = np.isin(codes, LE.isco08.unique())
    back = linked & np.isnan(v)
    v[back] = agg("mean").to_numpy()[back]
    return fill(v)


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


wage = (P.status == "wage_nonag").to_numpy()
formal_mask = wage & (P.informal_v2 == 0).to_numpy()
informal_mask = wage & (P.informal_v2 == 1).to_numpy()
n_formal = int(formal_mask.sum()); n_informal = int(informal_mask.sum())
assert n_formal == 1801 and n_informal == 2466, f"expected 1,801/2,466, got {n_formal}/{n_informal}"


def stats(y):
    wf = float(y[formal_mask].mean())
    wi = float(y[informal_mask].mean())
    return {"wage_formal": wf, "wage_informal": wi, "formal_minus_informal": wf - wi}


base = agg("mean")
assert np.allclose(base.to_numpy(), X[A].to_numpy(), rtol=0, atol=1e-9), "mean does not reproduce the exposure file"
assert np.allclose(workers(base), P[A].to_numpy(), rtol=0, atol=1e-9), "mean does not reproduce the worker file"

V2 = json.load(open("results/crosswalk_sensitivity_v2_py.json"))
out = {}
for name, f in [("mean", "mean"), ("median", "median"), ("min", "min"), ("max", "max")]:
    y = workers(agg(f))
    # regression check: reproduce v2's pooled figure for this rule
    v2p = V2[name]["pooled"]
    assert abs(round(float(y.mean()), 4) - v2p) < 5e-4, f"{name}: v3 pooled {y.mean():.4f} vs v2 {v2p}"
    out[name] = {k: round(v, 4) for k, v in stats(y).items()}
y_emp = workers(agg_emp())
v2p = V2["emp_weighted"]["pooled"]
assert abs(round(float(y_emp.mean()), 4) - v2p) < 5e-4
out["emp_weighted"] = {k: round(v, 4) for k, v in stats(y_emp).items()}
print("regression test passed: v3 reproduces v2 pooled means for mean/median/min/max/emp_weighted")

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
out["draws_share_formal_above_informal"] = round(float((D.formal_minus_informal > 0).mean()), 3)
out["n_formal"] = n_formal
out["n_informal"] = n_informal
print(f"draws_share_formal_above_informal = {out['draws_share_formal_above_informal']} "
      f"(cf. draws_share_wage_above_self = {V2['draws_share_wage_above_self']})")

json.dump(out, open("results/crosswalk_sensitivity_v3_py.json", "w"), indent=2)
print("wrote results/crosswalk_sensitivity_v3_py.json")
print(pd.DataFrame({k: out[k] for k in ["mean", "emp_weighted", "median", "min", "max"]}).round(4).to_string())
