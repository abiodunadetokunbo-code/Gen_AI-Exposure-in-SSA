"""Robustness of the worker-level results to the Althoff-Reichardt variant used
(plan item 3, step 9). Python side; the R twin is althoff_variants_v2.R.

For each of the nine task files in althoff_variants/ (the canonical v1.3
release, moderate 2030 scenario, Qwen-2.5-72B, plus eight published
alternatives; provenance in althoff_provenance.json):
  1. task -> O*NET occupation: task-weighted mean of automatable_genai
  2. O*NET -> ISCO-08: simple mean over crosswalks/isco08_to_onetsoc10.csv,
     with the 3-digit / 2-digit fallback crosswalks/build_isco08_exposure.py
     uses for the 7 codes it imputes
  3. workers (harmonized_workers_v2.csv): coded rows take their code's value;
     family-use farmers the mean of codes 6310-6340; Tanzania's market farmers
     the major-6 mean; TASCO rows mapped to a submajor the submajor mean.
The canonical file must reproduce isco08_to_exposure.csv and the worker file
to 1e-9, or the script stops. The Ethiopia supplement is not rescored.
Writes results/althoff_variants_v2_py.json.
"""
import json

import numpy as np
import pandas as pd

VARIANTS = ["canonical_moderate_qwen", "moderate_gptoss",
            "slow_qwen", "slow_gptoss", "rapid_qwen", "rapid_gptoss",
            "no_explicit_scenario_qwen", "no_explicit_scenario_gptoss",
            "no_explicit_scenario_gpt4o"]
X = pd.read_csv("../crosswalks/isco08_to_exposure.csv")
L = pd.read_csv("../crosswalks/isco08_to_onetsoc10.csv")
P = pd.read_csv("harmonized_workers_v2.csv", low_memory=False)
A = "auto_genai"


def isco_vector(tasks):
    """ISCO-08 -> exposure under one task file, same rule as build_isco08_exposure.py."""
    tasks = tasks.assign(wa=tasks.automatable_genai * tasks.task_weight)
    g = tasks.groupby("soc_code_onet")
    occ = (g.wa.sum() / g.task_weight.sum()).rename("v")
    le = L.merge(occ, left_on="onetsoc10", right_index=True, how="left")
    out = le.groupby("isco08").v.mean()
    g3 = out.groupby(out.index // 10).mean()
    g2 = out.groupby(out.index // 100).mean()
    vec = {}
    for code, match in zip(X.isco08, X.match):
        if match == "direct":
            vec[code] = out[code]
        elif match == "impute_3dig":
            vec[code] = g3[code // 10]
        else:
            vec[code] = g2[code // 100]
    return pd.Series(vec).sort_index()


# submajor of each TASCO row mapped to a submajor average, read off its canonical value
XS0 = X.groupby(X.isco08 // 10)[A].mean()
sub_rows = P.imputed_reason == "tasco_map_submajor"
sub_of = {}
for i, v in P.loc[sub_rows, A].items():
    hit = XS0.index[np.isclose(XS0.values, v, rtol=0, atol=1e-12)]
    assert len(hit) == 1, f"row {i}: no unique submajor for {v}"
    sub_of[i] = int(hit[0])
sub_of = pd.Series(sub_of, dtype=int)


def worker_vector(vec):
    y = P.isco08.map(vec)
    y[P.imputed_reason == "own_use_farmer_family_use"] = vec.loc[[6310, 6320, 6330, 6340]].mean()
    y[P.imputed_reason == "own_use_farmer_market_oriented"] = vec[vec.index // 1000 == 6].mean()
    vs = vec.groupby(vec.index // 10).mean()
    y[sub_of.index] = sub_of.map(vs).to_numpy()
    assert y.notna().all()
    return y


def wmean(x, w):
    return float(np.average(x, weights=w))


countries = sorted(P.country.unique())
res, base_vec = {}, None
for v in VARIANTS:
    t = pd.read_csv(f"althoff_variants/{v}.csv")
    vec = isco_vector(t)
    y = worker_vector(vec)
    if v == "canonical_moderate_qwen":
        assert np.allclose(vec.to_numpy(), X.set_index("isco08")[A].loc[vec.index].to_numpy(),
                           rtol=0, atol=1e-9), "canonical rebuild differs from isco08_to_exposure.csv"
        assert np.allclose(y.to_numpy(), P[A].to_numpy(), rtol=0, atol=1e-9), \
            "canonical rebuild differs from the worker file"
        base_vec = vec
    maj = {str(m): round(float(y[P.major == m].mean()), 4) for m in range(1, 10)}
    st = {s: round(float(y[P.status == s].mean()), 4)
          for s in ["agriculture", "selfemp_nonag", "wage_nonag"]}
    res[v] = dict(
        isco_mean=round(float(vec.mean()), 4),
        corr_pearson=round(float(np.corrcoef(vec, base_vec.loc[vec.index])[0, 1]), 4),
        corr_spearman=round(float(vec.corr(base_vec.loc[vec.index], method="spearman")), 4),
        pooled=round(float(y.mean()), 4),
        pooled_wtd=round(wmean(y, P.weight), 4),
        country={c: round(float(y[P.country == c].mean()), 4) for c in countries},
        country_wtd={c: round(wmean(y[P.country == c], P.weight[P.country == c]), 4)
                     for c in countries},
        status=st,
        wage_minus_self=round(st["wage_nonag"] - st["selfemp_nonag"], 4),
        major=maj,
        top_major=int(max(maj, key=maj.get)),
        clerical_over_agri=round(maj["4"] / maj["6"], 2),
        near_zero=round(100 * float((y < 0.05).mean()), 1),
    )

json.dump(res, open("results/althoff_variants_v2_py.json", "w"), indent=2)
print("canonical rebuild matches the exposure file and the worker file to 1e-9")
print(pd.DataFrame({v: {k: r[k] for k in ["pooled", "pooled_wtd", "corr_spearman", "top_major",
                                           "clerical_over_agri", "wage_minus_self"]}
                    for v, r in res.items()}).T.to_string())
print("wrote results/althoff_variants_v2_py.json")
