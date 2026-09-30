"""Comparable predictor metrics for Table 10 (plan review4, step 9 / decision
D3). Referee point 7: the paper says income per head "predicts exposure better"
than informality or the agricultural share, but Table 10 reports the two shares
on a 0-1 scale and income on a log scale, with no standardisation and no fit
statistic. Nothing in that table ranks the three.

This script supplies the two metrics that do rank them, on the same data, the
same specification and the same HC1 errors as Table 10:

  standardised coefficient : b_k * sd(x_k) / sd(y), from the full model
  incremental R-squared    : R2(full) - R2(full without x_k)

Both outcomes are covered: the Atlas AI-route share and the ILOSTAT rebuild on
the exp_lsms score vector.

Samples. Table 10's own columns use per-specification complete cases, which is
28 countries for the Atlas outcome and 27 for the ILOSTAT rebuild. The
regression test below reproduces Table 10 on exactly those samples. The
comparable metrics then run on the COMMON complete-case sample, the countries
where both outcomes and all three right-hand variables are present, so the two
outcomes are ranked on identical data. The script asserts the common sample is
a subset of both.

Writes results/macro_fit_v4_py.json. Touches nothing else.
"""
import json

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

RHS = ["informal_s", "agri_s", "lgdp"]
LABEL = {"informal_s": "Informal employment rate",
         "agri_s": "Agricultural self-employment",
         "lgdp": "Log GDP per head"}
OUTCOMES = {"ai_route_share": "Atlas, exposed through AI",
            "exp_lsms": "ILOSTAT rebuild"}

C = pd.read_csv("atlas_ai_route_v2_countries.csv")
C["lgdp"] = np.log(C.gdppc)
C["informal_s"] = C.informal / 100
C["agri_s"] = C.selfemp_agri / 100

# ---------------- regression test: reproduce Table 10 exactly ----------------
ATL = json.load(open("results/atlas_ai_route_v2_py.json"))["reg_ai_route_share"]
ILO = json.load(open("results/macro_ilostat_v2_py.json"))["reg_exp_lsms_all"]
REF = {"ai_route_share": ATL, "exp_lsms": ILO}

own_sample = {}
mismatches = []
for y in OUTCOMES:
    for key, rhs in [("(1) informality", "informal_s"),
                     ("(6) all three", "informal_s + agri_s + lgdp")]:
        s = C.dropna(subset=[y] + [t for t in RHS if t in rhs.split(" + ")])
        m = smf.ols(f"{y} ~ {rhs}", data=s).fit(cov_type="HC1")
        ref = REF[y][key]
        if int(m.nobs) != ref["_n"]:
            mismatches.append(f"{y}/{key}: n={int(m.nobs)} vs {ref['_n']}")
        for t in m.params.index:
            if abs(round(float(m.params[t]), 4) - ref[t]["b"]) > 5e-4:
                mismatches.append(f"{y}/{key}/{t}: b={float(m.params[t]):.4f} vs {ref[t]['b']}")
            if abs(round(float(m.bse[t]), 4) - ref[t]["se"]) > 5e-4:
                mismatches.append(f"{y}/{key}/{t}: se={float(m.bse[t]):.4f} vs {ref[t]['se']}")
        if key == "(6) all three":
            own_sample[y] = sorted(s.iso3)
assert not mismatches, "macro_fit_v4 does not reproduce Table 10:\n" + "\n".join(mismatches)
print("regression test passed: reproduced Table 10 for both outcomes, "
      f"n={len(own_sample['ai_route_share'])} Atlas and {len(own_sample['exp_lsms'])} ILOSTAT")

# ---------------- the common complete-case sample ----------------
S = C.dropna(subset=list(OUTCOMES) + RHS).copy()
common = sorted(S.iso3)
for y in OUTCOMES:
    assert set(common) <= set(own_sample[y]), f"common sample is not a subset of the {y} sample"
print(f"common complete-case sample: {len(common)} countries")

# ---------------- standardised coefficients and incremental R-squared ----------------
metrics, full_fit = {}, {}
for y, y_label in OUTCOMES.items():
    m = smf.ols(f"{y} ~ " + " + ".join(RHS), data=S).fit(cov_type="HC1")
    sd_y = float(S[y].std(ddof=1))
    row = {}
    for t in RHS:
        drop = [v for v in RHS if v != t]
        m_drop = smf.ols(f"{y} ~ " + " + ".join(drop), data=S).fit(cov_type="HC1")
        row[t] = dict(
            label=LABEL[t],
            b=round(float(m.params[t]), 4),
            se=round(float(m.bse[t]), 4),
            beta_std=round(float(m.params[t]) * float(S[t].std(ddof=1)) / sd_y, 4),
            incremental_r2=round(float(m.rsquared) - float(m_drop.rsquared), 4),
        )
    ranked_beta = sorted(RHS, key=lambda t: abs(row[t]["beta_std"]), reverse=True)
    ranked_r2 = sorted(RHS, key=lambda t: row[t]["incremental_r2"], reverse=True)
    metrics[y] = dict(outcome_label=y_label, n=int(m.nobs), r2_full=round(float(m.rsquared), 4),
                      sd_outcome=round(sd_y, 4), terms=row,
                      rank_by_abs_beta=[LABEL[t] for t in ranked_beta],
                      rank_by_incremental_r2=[LABEL[t] for t in ranked_r2],
                      top_by_abs_beta=LABEL[ranked_beta[0]],
                      top_by_incremental_r2=LABEL[ranked_r2[0]])
    full_fit[y] = float(m.rsquared)

for y, d in metrics.items():
    print(f"\n{d['outcome_label']} (n={d['n']}, R2={d['r2_full']:.3f})")
    print(f"  {'term':<30} {'b':>9} {'std beta':>9} {'incr R2':>9}")
    for t in RHS:
        r = d["terms"][t]
        print(f"  {r['label']:<30} {r['b']:>9.4f} {r['beta_std']:>9.3f} {r['incremental_r2']:>9.4f}")
    print(f"  largest |std beta|: {d['top_by_abs_beta']}")
    print(f"  largest incremental R2: {d['top_by_incremental_r2']}")

# Does income rank first on both metrics and both outcomes? The plan makes the
# main-text sentence conditional on this, so record the answer explicitly.
income_first = all(d["top_by_abs_beta"] == LABEL["lgdp"] and
                   d["top_by_incremental_r2"] == LABEL["lgdp"] for d in metrics.values())
print(f"\nincome per head ranks first on both metrics and both outcomes: {income_first}")

out = {
    "common_sample": common,
    "n_common": len(common),
    "own_sample_n": {y: len(v) for y, v in own_sample.items()},
    "metrics": metrics,
    "income_ranks_first_everywhere": bool(income_first),
}
json.dump(out, open("results/macro_fit_v4_py.json", "w"), indent=2)
print("wrote results/macro_fit_v4_py.json")
