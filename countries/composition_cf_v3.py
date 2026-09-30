"""The composition counterfactual (plan review3, step 6 / decision D3). The
paper claims the low average is "mostly a composition result" and supplies no
counterfactual anywhere in the build. This gives it one: hold the occupation
exposure vector fixed (the same three score vectors macro_ilostat_v2.py
already builds) and swap in a high-income benchmark's ISCO major-group
employment shares.

Benchmark: GBR, DEU, FRA, fetched into ilostat/raw_benchmark/ by the same
SDMX route as the African files in ilostat/raw/ (which this script does not
touch, so macro_ilostat_v2.py's glob and results stay byte-identical). All
three pass the ISCO-08 coverage check (all nine major groups reported) and
carry a low not-classified share (GBR 0.10%, DEU 0.51%, FRA 1.02%, all under
the 20% cut macro_ilostat_v2.py uses). Headline: GBR. DEU and FRA give the
range.

Construction:
  actual_i   = sum over groups 1-9 of African country i's own employment
               share times the group's exposure score
  cf         = sum over groups 1-9 of the benchmark's employment share times
               the SAME group score (one number per score vector per
               benchmark; it does not vary by African country, since neither
               the benchmark's shares nor the score vector are country-
               specific)
  gap_i      = cf - actual_i, decomposed group by group as
               sum_j (benchmark_share_j - country_i_share_j) * score_j

Two readings:
  1. "These economies": Nigeria, Tanzania, Uganda specifically, actual and cf
     pooled with the same population weight shares as the headline pooled
     mean (67.8 / 16.9 / 15.4, from survey_design_v3's weight_totals).
  2. "The average African country": the simple (unweighted) across-country
     mean of the actual share vector, against the benchmark, decomposed by
     major group, on all African countries the ILOSTAT rebuild covers.

Regression test: reproduces macro_ilostat_v2's per-country actual exposure
(all three score vectors, every African country) before computing anything
new, proving the vector and the African shares are the same ones.

Writes results/composition_cf_v3_py.json.
"""
import glob
import json

import numpy as np
import pandas as pd

MAJ = [f"OCU_ISCO08_{i}" for i in range(1, 10)]
X = pd.read_csv("../crosswalks/isco08_to_exposure.csv")
P = pd.read_csv("harmonized_workers_v2.csv", low_memory=False)


def build_shares(files):
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
    x_pct = 100 * W.get("OCU_ISCO08_X", pd.Series(0.0, index=W.index)).fillna(0) / W["OCU_ISCO08_TOTAL"]
    year = D.groupby("REF_AREA").TIME_PERIOD.first()
    return share, x_pct, year


share_afr, x_pct_afr, year_afr = build_shares(glob.glob("../ilostat/raw/*.csv"))
share_bmk, x_pct_bmk, year_bmk = build_shares(glob.glob("../ilostat/raw_benchmark/*.csv"))

BENCHMARKS = ["GBR", "DEU", "FRA"]
HEADLINE = "GBR"
for c in BENCHMARKS:
    assert c in share_bmk.index, f"{c} missing from the benchmark file"
    s = share_bmk.loc[c, range(1, 10)].sum()
    assert abs(s - 1.0) < 1e-9, f"{c} shares do not sum to 1 over groups 1-9: {s}"
    assert x_pct_bmk[c] < 20, f"{c} not-classified share {x_pct_bmk[c]:.2f}% fails the 20% gate"
print(f"benchmark gate: all of {BENCHMARKS} pass (shares sum to 1, x_pct < 20%)")
print("x_pct:", {c: round(float(x_pct_bmk[c]), 2) for c in BENCHMARKS})

vec_unit = X.groupby(X.isco08 // 1000).auto_genai.mean()
vec_lsms = P.groupby("major").apply(lambda g: np.average(g.auto_genai, weights=g.weight))
vec_lsms.index = vec_lsms.index.astype(int)
PX = P[P.imputed_reason != "own_use_farmer_family_use"]
vec_lsms_ex = PX.groupby("major").apply(lambda g: np.average(g.auto_genai, weights=g.weight))
vec_lsms_ex.index = vec_lsms_ex.index.astype(int)
VECS = {"exp_unit": vec_unit, "exp_lsms": vec_lsms, "exp_lsms_ex": vec_lsms_ex}

# ---------------- regression test against macro_ilostat_v2 ----------------
V2 = json.load(open("results/macro_ilostat_v2_py.json"))
mismatches = []
actual = {}
for y, v in VECS.items():
    a = share_afr.mul(v.loc[range(1, 10)].to_numpy(), axis=1).sum(axis=1)
    actual[y] = a
    for iso3, val in a.items():
        v2v = V2["countries"].get(iso3, {}).get(y)
        if v2v is None:
            continue
        if abs(round(float(val), 4) - v2v) > 5e-4:
            mismatches.append(f"{y}/{iso3}: v3={val:.4f} v2={v2v}")
assert not mismatches, "v3 does not reproduce macro_ilostat_v2's actual exposure:\n" + "\n".join(mismatches)
print(f"regression test passed: reproduced macro_ilostat_v2's actual exposure for "
      f"{len(actual['exp_lsms'])} African countries across all 3 score vectors")

# ---------------- counterfactual: give every country the benchmark's mix ----------------
cf = {(bc, y): float((share_bmk.loc[bc, range(1, 10)].to_numpy() * v.loc[range(1, 10)].to_numpy()).sum())
      for bc in BENCHMARKS for y, v in VECS.items()}

# ---------------- reading 1: "these economies" (NGA, TZA, UGA), pooled with the headline weight shares ----------------
SD3 = json.load(open("results/survey_design_v3_py.json"))
# from the raw weight sums, not survey_design_v3's share_of_pooled: those are
# rounded to one decimal and sum to 100.1, not 100.
_wt = {"NGA": SD3["weight_totals"]["Nigeria 2023"]["sum_weight"],
       "TZA": SD3["weight_totals"]["Tanzania 2020"]["sum_weight"],
       "UGA": SD3["weight_totals"]["Uganda 2019"]["sum_weight"]}
_tot = SD3["weight_totals"]["pooled"]["sum_weight"]
assert abs(sum(_wt.values()) - _tot) < 1e-6, "country weight sums do not add to the pooled total"
wshare = {k: v / _tot for k, v in _wt.items()}
assert abs(sum(wshare.values()) - 1.0) < 1e-9

these = {}
for y in VECS:
    a3 = {iso: round(float(actual[y][iso]), 4) for iso in ["NGA", "TZA", "UGA"]}
    pooled_actual = sum(wshare[iso] * actual[y][iso] for iso in ["NGA", "TZA", "UGA"])
    row = dict(actual_by_country=a3, pooled_actual_ilostat=round(pooled_actual, 4))
    for bc in BENCHMARKS:
        row[f"cf_{bc}"] = round(cf[(bc, y)], 4)
        row[f"gap_{bc}"] = round(cf[(bc, y)] - pooled_actual, 4)
    these[y] = row

# survey-based pooled headline, reported beside the ILOSTAT-based numbers for transparency
V2R = json.load(open("results/survey_design_v2_py.json"))
survey_pooled_weighted = V2R["group_means_ci"]["pooled_weighted"]["mean"]

# ---------------- reading 2: the average African country, group-by-group decomposition ----------------
avg_share = share_afr[range(1, 10)].mean(axis=0)  # simple unweighted mean across African countries
assert abs(avg_share.sum() - 1.0) < 1e-9

decomp = {}
for bc in BENCHMARKS:
    for y, v in VECS.items():
        diff = share_bmk.loc[bc, range(1, 10)] - avg_share
        contrib = (diff * v.loc[range(1, 10)]).to_dict()
        total = sum(contrib.values())
        cf_val = cf[(bc, y)]
        avg_actual = float((avg_share.to_numpy() * v.loc[range(1, 10)].to_numpy()).sum())
        assert abs(total - (cf_val - avg_actual)) < 1e-9, "group decomposition does not sum to the total gap"
        decomp[f"{bc}|{y}"] = dict(
            avg_african_actual=round(avg_actual, 4), cf=round(cf_val, 4), gap=round(total, 4),
            by_group={str(j): round(float(contrib[j]), 4) for j in range(1, 10)},
            top_group=int(max(contrib, key=lambda j: abs(contrib[j]))),
        )

# share of the gap carried by major groups 4 (clerical) and 6 (skilled agriculture), headline benchmark/vector
hd = decomp[f"{HEADLINE}|exp_lsms"]
share_46 = (hd["by_group"]["4"] + hd["by_group"]["6"]) / hd["gap"] if hd["gap"] != 0 else float("nan")
print(f"headline ({HEADLINE}, exp_lsms): average African actual={hd['avg_african_actual']:.4f}, "
      f"cf={hd['cf']:.4f}, gap={hd['gap']:.4f}; groups 4+6 carry {100*share_46:.1f}% of the gap")
print("by_group:", hd["by_group"])

out = {
    "benchmarks": BENCHMARKS, "headline_benchmark": HEADLINE,
    "x_pct": {c: round(float(x_pct_bmk[c]), 2) for c in BENCHMARKS},
    "benchmark_year": {c: int(year_bmk[c]) for c in BENCHMARKS},
    "vectors": {y: {str(k): round(float(x), 4) for k, x in v.loc[range(1, 10)].items()} for y, v in VECS.items()},
    "cf": {f"{bc}|{y}": round(v, 4) for (bc, y), v in cf.items()},
    "these_economies": these,
    "survey_pooled_weighted_headline": survey_pooled_weighted,
    "average_african_country": decomp,
    "group_46_share_of_gap_headline": round(share_46, 4),
    "n_african_countries": int(len(share_afr)),
}
json.dump(out, open("results/composition_cf_v3_py.json", "w"), indent=2)
print("wrote results/composition_cf_v3_py.json")
