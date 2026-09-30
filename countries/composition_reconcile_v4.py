"""Reconcile the two pooled exposure figures the paper reports (plan review4,
step 8 / decision D2). Referee point 3: the composition section opens from
0.080 while the headline pooled weighted mean is 0.090, and the paper never
says why.

The answer is exact and it has one moving part.

  pooled_actual_ilostat = sum_i w_i * sum_j s_ij^ILO * v_j
                        = sum_j v_j * S_j^ILO
  survey pooled mean    = sum_j v_j * S_j^LSMS

with the SAME score vector v (exp_lsms, the survey-derived major-group means)
and the same country weight shares w_i. So the whole difference is the source
of the employment shares S_j, ILOSTAT against LSMS, and it decomposes group by
group as sum_j v_j * (S_j^ILO - S_j^LSMS).

Two things this proves, both asked for in the plan:

  1. Major-group aggregation has NO residual. v_j is itself the weighted mean
     of the worker scores inside group j, so sum_j v_j * S_j^LSMS returns the
     direct survey-weighted pooled mean of the worker scores exactly. Anyone
     suspecting the 0.080/0.090 gap is an aggregation artefact can stop here.
  2. The gap is almost entirely managers. ILOSTAT puts a far smaller share of
     these three countries' employment in ISCO major group 1 than the LSMS
     sample does, which is a fact about how LSMS codes own-account business
     owners.

Regression test: reproduces composition_cf_v3's pooled_actual_ilostat for all
three score vectors before computing anything new, so the ILOSTAT shares, the
score vectors and the country weight shares are provably the same ones.

Also records, for each of the three countries, the ILOSTAT reference year used
beside the survey year, since they are not the same year and the paper should
say so.

Writes results/composition_reconcile_v4_py.json. Touches nothing else.
"""
import glob
import json

import numpy as np
import pandas as pd

MAJ = [f"OCU_ISCO08_{i}" for i in range(1, 10)]
THREE = ["NGA", "TZA", "UGA"]
SURVEY_YEAR = {"NGA": 2023, "TZA": 2020, "UGA": 2019}
GROUP_NAME = {1: "Managers", 2: "Professionals", 3: "Technicians and associates",
              4: "Clerical support", 5: "Service and sales", 6: "Skilled agriculture",
              7: "Craft and trades", 8: "Plant and machine operators",
              9: "Elementary occupations"}

X = pd.read_csv("../crosswalks/isco08_to_exposure.csv")
P = pd.read_csv("harmonized_workers_v2.csv", low_memory=False)


def build_shares(files):
    """Identical to composition_cf_v3.build_shares. Kept local so this script
    reads the same raw ILOSTAT files and cannot drift from them."""
    frames = []
    for f in sorted(files):
        with open(f, encoding="utf-8", errors="replace") as fh:
            if not fh.read(200).startswith("DATAFLOW"):
                continue
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
    return share, year


share_afr, year_afr = build_shares(glob.glob("../ilostat/raw/*.csv"))

vec_unit = X.groupby(X.isco08 // 1000).auto_genai.mean()
vec_lsms = P.groupby("major").apply(lambda g: np.average(g.auto_genai, weights=g.weight))
vec_lsms.index = vec_lsms.index.astype(int)
PX = P[P.imputed_reason != "own_use_farmer_family_use"]
vec_lsms_ex = PX.groupby("major").apply(lambda g: np.average(g.auto_genai, weights=g.weight))
vec_lsms_ex.index = vec_lsms_ex.index.astype(int)
VECS = {"exp_unit": vec_unit, "exp_lsms": vec_lsms, "exp_lsms_ex": vec_lsms_ex}
HEADLINE_VEC = "exp_lsms"

# ---------------- country weight shares, as composition_cf_v3 builds them ----------------
SD3 = json.load(open("results/survey_design_v3_py.json"))
_wt = {"NGA": SD3["weight_totals"]["Nigeria 2023"]["sum_weight"],
       "TZA": SD3["weight_totals"]["Tanzania 2020"]["sum_weight"],
       "UGA": SD3["weight_totals"]["Uganda 2019"]["sum_weight"]}
_tot = SD3["weight_totals"]["pooled"]["sum_weight"]
assert abs(sum(_wt.values()) - _tot) < 1e-6, "country weight sums do not add to the pooled total"
wshare = {k: v / _tot for k, v in _wt.items()}
assert abs(sum(wshare.values()) - 1.0) < 1e-9

# ---------------- regression test against composition_cf_v3 ----------------
CF3 = json.load(open("results/composition_cf_v3_py.json"))
pooled_ilostat = {}
for y, v in VECS.items():
    a = share_afr.mul(v.loc[range(1, 10)].to_numpy(), axis=1).sum(axis=1)
    pooled = sum(wshare[iso] * a[iso] for iso in THREE)
    pooled_ilostat[y] = float(pooled)
    ref = CF3["these_economies"][y]["pooled_actual_ilostat"]
    assert abs(round(pooled, 4) - ref) < 5e-4, \
        f"v4 does not reproduce composition_cf_v3 pooled_actual_ilostat for {y}: {pooled:.4f} vs {ref}"
print("regression test passed: reproduced composition_cf_v3's pooled_actual_ilostat "
      f"for all {len(VECS)} score vectors")

# ---------------- pooled employment shares from each source ----------------
# ILOSTAT: the country shares pooled with the same weight shares as above.
S_ilo = pd.Series({j: sum(wshare[iso] * share_afr.loc[iso, j] for iso in THREE)
                   for j in range(1, 10)})
assert abs(S_ilo.sum() - 1.0) < 1e-9, "pooled ILOSTAT shares do not sum to 1"

# LSMS: survey-weighted major-group shares over the pooled sample.
S_lsms = P.groupby("major").weight.sum() / P.weight.sum()
S_lsms.index = S_lsms.index.astype(int)
S_lsms = S_lsms.reindex(range(1, 10)).fillna(0.0)
assert abs(S_lsms.sum() - 1.0) < 1e-9, "pooled LSMS shares do not sum to 1"

# ---------------- the zero-residual identity ----------------
# Direct survey-weighted pooled mean of the worker scores, computed from the
# worker file with no grouping at all.
direct = float(np.average(P.auto_genai, weights=P.weight))
# The same thing rebuilt from major-group shares times the group score vector.
v_head = VECS[HEADLINE_VEC].loc[range(1, 10)]
via_groups = float((S_lsms.to_numpy() * v_head.to_numpy()).sum())
residual = direct - via_groups
assert abs(residual) < 1e-12, \
    f"major-group aggregation is not residual-free: direct={direct!r} via_groups={via_groups!r}"
print(f"zero-residual identity holds: direct={direct:.6f}, via major groups={via_groups:.6f}, "
      f"residual={residual:.2e}")

# Cross-check the direct mean against the number the paper already reports.
SD2 = json.load(open("results/survey_design_v2_py.json"))
survey_pooled_weighted = SD2["group_means_ci"]["pooled_weighted"]["mean"]
assert abs(round(direct, 4) - survey_pooled_weighted) < 5e-4, \
    f"direct pooled weighted mean {direct:.4f} does not match survey_design_v2 {survey_pooled_weighted}"

# ---------------- decompose the difference by major group ----------------
diff_total = pooled_ilostat[HEADLINE_VEC] - direct
contrib = {j: float((S_ilo[j] - S_lsms[j]) * v_head[j]) for j in range(1, 10)}
assert abs(sum(contrib.values()) - diff_total) < 1e-9, \
    "group decomposition does not sum to the total difference"

# ---------------- what sits in major group 1 in this sample ----------------
# The manager term is the single largest piece of the difference, so record
# what these workers are, rather than leaving the reader to guess.
M1 = P[P.major == 1]
m1_status = (M1.groupby("status").weight.sum() / M1.weight.sum()).to_dict()
m1_isco = (M1.groupby("isco08").weight.sum() / M1.weight.sum()).sort_values(ascending=False)
m1_top_isco = int(m1_isco.index[0])
print(f"major group 1 in the LSMS sample: {len(M1)} workers, "
      f"{100*m1_status.get('selfemp_nonag', 0):.0f}% of the weight own-account non-agricultural, "
      f"top ISCO code {m1_top_isco} at {100*m1_isco.iloc[0]:.0f}%")

ranked = sorted(contrib, key=lambda j: abs(contrib[j]), reverse=True)
print(f"difference {diff_total:+.4f} = ILOSTAT {pooled_ilostat[HEADLINE_VEC]:.4f} "
      f"minus LSMS {direct:.4f}")
for j in ranked[:3]:
    print(f"  group {j} {GROUP_NAME[j]:<28} ILO {100*S_ilo[j]:5.1f}%  LSMS {100*S_lsms[j]:5.1f}%"
          f"  -> {contrib[j]:+.4f}")

# Share of the total difference carried by the single largest group.
top = ranked[0]
top_share = contrib[top] / diff_total

out = {
    "headline_vector": HEADLINE_VEC,
    "survey_year": SURVEY_YEAR,
    "ilostat_year": {iso: int(year_afr[iso]) for iso in THREE},
    "country_weight_share": {k: round(v, 4) for k, v in wshare.items()},
    "score_vector": {str(j): round(float(v_head[j]), 4) for j in range(1, 10)},
    "pooled_share_ilostat": {str(j): round(float(S_ilo[j]), 4) for j in range(1, 10)},
    "pooled_share_lsms": {str(j): round(float(S_lsms[j]), 4) for j in range(1, 10)},
    "pooled_ilostat_by_vector": {y: round(v, 4) for y, v in pooled_ilostat.items()},
    "pooled_ilostat": round(pooled_ilostat[HEADLINE_VEC], 4),
    "pooled_lsms_direct": round(direct, 4),
    "pooled_lsms_via_major_groups": round(via_groups, 4),
    "aggregation_residual": round(residual, 10),
    "difference": round(diff_total, 4),
    "difference_by_group": {str(j): round(contrib[j], 4) for j in range(1, 10)},
    "largest_group": int(top),
    "largest_group_name": GROUP_NAME[top],
    "largest_group_share_of_difference": round(float(top_share), 4),
    "manager_share_ilostat_pct": round(100 * float(S_ilo[1]), 1),
    "manager_share_lsms_pct": round(100 * float(S_lsms[1]), 1),
    "manager_term": round(contrib[1], 4),
    "service_share_ilostat_pct": round(100 * float(S_ilo[5]), 1),
    "service_share_lsms_pct": round(100 * float(S_lsms[5]), 1),
    "service_term": round(contrib[5], 4),
    "major1_n": int(len(M1)),
    "major1_status_share": {k: round(float(v), 4) for k, v in sorted(m1_status.items())},
    "major1_selfemp_nonag_pct": round(100 * float(m1_status.get("selfemp_nonag", 0.0)), 1),
    "major1_top_isco": m1_top_isco,
    "major1_top_isco_pct": round(100 * float(m1_isco.iloc[0]), 1),
    "n_workers": int(len(P)),
}
json.dump(out, open("results/composition_reconcile_v4_py.json", "w"), indent=2)
print("wrote results/composition_reconcile_v4_py.json")
