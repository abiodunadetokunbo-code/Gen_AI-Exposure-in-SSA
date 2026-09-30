"""Revision-3 addition to the nine-variant robustness table (plan review3,
step 7). The formal/informal wage split is an abstract-level finding
(-0.102, SE 0.006 under country fixed effects; survey_design_v3 adds the
weighted group means) and it appears in neither robustness table. This adds
two masks, `wage_formal` and `wage_informal`, and one derived quantity,
`formal_minus_informal`, to the same nine task-file variants
althoff_variants_v2.py already scores. Does not touch althoff_variants_v2.py
or its output; the worker-vector construction is copied unchanged so the two
scripts can be compared key for key.

The formality sample is smaller than the status columns: 4,267 of the 4,275
non-agricultural wage workers answer the formality questions (1,801 formal,
2,466 informal); the other 8 are missing under the harmonized rule
(`informal_v2`).

Writes results/althoff_variants_v3_py.json.
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
V2 = json.load(open("results/althoff_variants_v2_py.json"))


def isco_vector(tasks):
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


wage = (P.status == "wage_nonag").to_numpy()
formal_mask = wage & (P.informal_v2 == 0).to_numpy()
informal_mask = wage & (P.informal_v2 == 1).to_numpy()
n_wage = int(wage.sum())
n_formal = int(formal_mask.sum())
n_informal = int(informal_mask.sum())
n_answered = n_formal + n_informal
assert n_wage == 4275, f"expected 4,275 non-agricultural wage workers, got {n_wage}"
assert n_answered == 4267, f"expected 4,267 wage workers with an answered formality question, got {n_answered}"
assert n_formal == 1801 and n_informal == 2466, f"expected 1,801/2,466, got {n_formal}/{n_informal}"

res, base_vec = {}, None
for v in VARIANTS:
    t = pd.read_csv(f"althoff_variants/{v}.csv")
    vec = isco_vector(t)
    y = worker_vector(vec)
    if v == "canonical_moderate_qwen":
        assert np.allclose(y.to_numpy(), P[A].to_numpy(), rtol=0, atol=1e-9), \
            "canonical rebuild differs from the worker file"
        base_vec = vec
    st_check = {s: round(float(y[P.status == s].mean()), 4) for s in ["agriculture", "selfemp_nonag", "wage_nonag"]}
    for f, v2f in [("agriculture", "agriculture"), ("selfemp_nonag", "selfemp_nonag"), ("wage_nonag", "wage_nonag")]:
        v2v = V2[v]["status"][v2f]
        assert abs(st_check[f] - v2v) < 5e-4, f"{v}/{f}: v3={st_check[f]} v2={v2v}"
    wf = round(float(y[formal_mask].mean()), 4)
    wi = round(float(y[informal_mask].mean()), 4)
    res[v] = dict(wage_formal=wf, wage_informal=wi, formal_minus_informal=round(wf - wi, 4),
                 n_formal=n_formal, n_informal=n_informal)

canon = res["canonical_moderate_qwen"]
assert abs(canon["wage_formal"] - 0.213) < 5e-4 and abs(canon["wage_informal"] - 0.104) < 5e-4, \
    f"headline variant should give 0.213/0.104, got {canon['wage_formal']}/{canon['wage_informal']}"
print("regression test passed: v3 reproduces v2 status means for all 9 variants; "
      f"headline wage_formal={canon['wage_formal']} wage_informal={canon['wage_informal']}")

gaps = [r["formal_minus_informal"] for r in res.values()]
print(f"formal_minus_informal across the 9 variants: min={min(gaps):.4f} max={max(gaps):.4f}")
any_flip = any(g <= 0 for g in gaps)
print(f"any variant with formal <= informal: {any_flip}")

out = {"variants": res, "n_wage": n_wage, "n_formal": n_formal, "n_informal": n_informal,
       "formal_minus_informal_min": round(min(gaps), 4), "formal_minus_informal_max": round(max(gaps), 4),
       "any_sign_flip": bool(any_flip)}
json.dump(out, open("results/althoff_variants_v3_py.json", "w"), indent=2)
print("wrote results/althoff_variants_v3_py.json")
