"""Revision-3 additions to the design-based estimates (plan review3, steps 2
and 3). Reads the same v2 worker files and design ids as survey_design_v2.py;
does not touch survey_design_v2.py, its outputs, or survey_design_ids_v2.csv.

Step 2: `group_means_ci` in the v2 file has no weighted mean for the formal
and informal wage groups, and no weighted mean for the major groups, urban,
rural, male or female. This file adds them, under the same keys with a
`_wtd` suffix, using the same Taylor-linearized design as v2.

Step 3: sum of expansion weights by country and pooled, and each country's
share of the pooled sum, read off the same worker file.

Every key this file shares with survey_design_v2_py.json is recomputed and
asserted equal to the last decimal, so the design machinery is proven
unchanged before the new groups are trusted.

Writes results/survey_design_v3_py.json.
"""
import json

import numpy as np
import pandas as pd

A = "auto_genai"
P = pd.read_csv("harmonized_workers_v2.csv", low_memory=False)
IDS = pd.read_csv("survey_design_ids_v2.csv", low_memory=False)
P = P.merge(IDS[["hhid_c", "stratum", "psu"]], on="hhid_c", how="left", validate="many_to_one")
assert P.psu.notna().all(), "worker without a design id"

V2 = json.load(open("results/survey_design_v2_py.json"))


class Design:
    def __init__(self, d):
        self.d = d.reset_index(drop=True)
        self.psu_codes, psu_names = pd.factorize(self.d.psu)
        s = self.d.groupby("psu").stratum.first().reindex(psu_names)
        self.psu_stratum = pd.factorize(s)[0]
        self.n_h = np.bincount(self.psu_stratum)

    def var(self, Z):
        Z = np.asarray(Z, float).reshape(len(self.d), -1)
        T = np.zeros((self.psu_codes.max() + 1, Z.shape[1]))
        np.add.at(T, self.psu_codes, Z)
        V = np.zeros((Z.shape[1], Z.shape[1]))
        for h, n in enumerate(self.n_h):
            Th = T[self.psu_stratum == h]
            Dh = Th - Th.mean(axis=0)
            V += n / (n - 1) * Dh.T @ Dh
        return V

    def weights(self, w):
        return np.ones(len(self.d)) if w is None else self.d[w].to_numpy(float)

    def mean(self, dom, col=A, w=None):
        y = self.d[col].to_numpy(float)
        dom = np.asarray(dom, bool) & np.isfinite(y)
        wt = self.weights(w) * dom
        s = wt.sum()
        m = float((wt * np.where(dom, y, 0)).sum() / s)
        z = wt * np.where(dom, y - m, 0) / s
        se = float(np.sqrt(self.var(z)[0, 0]))
        return dict(mean=round(m, 4), se=round(se, 4), lo=round(m - 1.96 * se, 4),
                    hi=round(m + 1.96 * se, 4), n=int(dom.sum()))


P["fem"] = np.where(P.sex.isna(), np.nan, (P.sex == "female").astype(float))
D = Design(P)
d = D.d
countries = sorted(d.country.unique())
st = d.status.to_numpy()
wage = st == "wage_nonag"
yes = np.ones(len(d), bool)

# ---------------- regression test: reproduce every v2 group_means_ci key ----------------
regress = {}
regress["pooled"] = D.mean(yes)
regress["pooled_weighted"] = D.mean(yes, w="weight")
for c in countries:
    regress[f"country|{c}"] = D.mean(d.country == c)
    regress[f"country_wtd|{c}"] = D.mean(d.country == c, w="weight")
for s in sorted(d.status.unique()):
    regress[f"status_{s}"] = D.mean(st == s)
    regress[f"status_{s}_wtd"] = D.mean(st == s, w="weight")
    for c in countries:
        if ((st == s) & (d.country == c)).any():
            regress[f"status_{s}|{c}"] = D.mean((st == s) & (d.country == c))
regress["wage_formal"] = D.mean(wage & (d.informal_v2 == 0))
regress["wage_informal"] = D.mean(wage & (d.informal_v2 == 1))
regress["urban"] = D.mean(d.urban == 1)
regress["rural"] = D.mean(d.urban == 0)
regress["male"] = D.mean(d.fem == 0)
regress["female"] = D.mean(d.fem == 1)
for mj in sorted(d.major.unique()):
    regress[f"major_{int(mj)}"] = D.mean(d.major == mj)

mismatches = []
for k, v in regress.items():
    v2 = V2["group_means_ci"].get(k)
    if v2 is None:
        mismatches.append(f"{k}: not in v2 at all")
        continue
    for f in ["mean", "se", "lo", "hi", "n"]:
        if abs(v[f] - v2[f]) > 5e-4:
            mismatches.append(f"{k}.{f}: v3={v[f]} v2={v2[f]}")
assert not mismatches, "v3 does not reproduce v2 group_means_ci:\n" + "\n".join(mismatches)
print(f"regression test passed: {len(regress)} v2 group_means_ci keys reproduced to the last decimal")

# ---------------- step 2: the new weighted groups ----------------
new_ci = {}
new_ci["wage_formal_wtd"] = D.mean(wage & (d.informal_v2 == 0), w="weight")
new_ci["wage_informal_wtd"] = D.mean(wage & (d.informal_v2 == 1), w="weight")
new_ci["urban_wtd"] = D.mean(d.urban == 1, w="weight")
new_ci["rural_wtd"] = D.mean(d.urban == 0, w="weight")
new_ci["male_wtd"] = D.mean(d.fem == 0, w="weight")
new_ci["female_wtd"] = D.mean(d.fem == 1, w="weight")
for mj in sorted(d.major.unique()):
    new_ci[f"major_{int(mj)}_wtd"] = D.mean(d.major == mj, w="weight")

gap = new_ci["wage_formal_wtd"]["mean"] - new_ci["wage_informal_wtd"]["mean"]
print(f"wage_formal_wtd - wage_informal_wtd = {gap:.4f} "
      f"(cf. weighted regression informal_vs_formal_cfe_wtd = -0.1080)")

# ---------------- step 3: weight totals by country ----------------
wsum = d.groupby("country").weight.sum()
pooled_w = float(d.weight.sum())
wt_out = {c: dict(sum_weight=round(float(wsum[c]), 0),
                   share_of_pooled=round(100 * float(wsum[c]) / pooled_w, 1),
                   mean_weight=round(float(wsum[c]) / int((d.country == c).sum()), 0),
                   n=int((d.country == c).sum()))
          for c in countries}
wt_out["pooled"] = dict(sum_weight=round(pooled_w, 0), share_of_pooled=100.0, n=int(len(d)))

# sanity: weight-share-weighted average of the three country weighted means
# should reproduce the pooled weighted mean
implied = sum(wsum[c] / pooled_w * V2["group_means_ci"][f"country_wtd|{c}"]["mean"] for c in countries)
print(f"weight-share-weighted average of country means = {implied:.4f} "
      f"(cf. pooled_weighted mean = {V2['group_means_ci']['pooled_weighted']['mean']:.4f})")
assert abs(implied - V2["group_means_ci"]["pooled_weighted"]["mean"]) < 5e-4

out = {"group_means_ci_v3_additions": new_ci, "weight_totals": wt_out,
       "wage_formal_minus_informal_wtd": round(gap, 4),
       "weight_share_weighted_avg_check": round(implied, 4)}
json.dump(out, open("results/survey_design_v3_py.json", "w"), indent=2)
print("wrote results/survey_design_v3_py.json")
print(pd.DataFrame(wt_out).T.to_string())
