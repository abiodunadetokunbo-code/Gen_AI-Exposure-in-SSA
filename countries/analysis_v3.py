"""Revision-3 addition to the worker-level analysis (plan review3, step 4).

All 117 Nigerian coded workers who report no work in the last seven days
(`s4aq21` == "1. NO TYPE OF WORK" but a coded `s4aq40_code`) enter the sample.
115 of them answer `s4aq24` ("do you expect to return to a job within the
next 3 months?") "YES"; 2 do not answer it at all, so they enter on a test
they fail. This script identifies those 2 rows in the raw Nigeria labour
module, finds their matching rows in harmonized_workers_v2.csv by household
id and ISCO-08 code (each match is unique within its household), and reports
the pooled and Nigeria mean exposure with and without them.

Does not touch harmonized_workers_v2.csv or any v2 output. Writes
results/analysis_v3_py.json.
"""
import json

import numpy as np
import pandas as pd


def num(s):
    return pd.to_numeric(s.astype(str).str.extract(r"(\d+\.?\d*)")[0], errors="coerce")


lab = pd.read_csv("../lsms_probe/w5/Post Harvest Wave 5/Household/sect4a_harvestw5.csv", low_memory=False)
iso = num(lab["s4aq40_code"])
coded = iso.between(1000, 9999)
gate1 = num(lab["s4aq21"]).eq(3)  # "worked farm for market, any wage, or any NFE"
absent_coded = coded & ~gate1
assert int(absent_coded.sum()) == 117, f"expected 117 coded absentees, got {int(absent_coded.sum())}"
returns_3mo = num(lab["s4aq24"]).eq(1)
assert int((absent_coded & returns_3mo).sum()) == 115
fail = absent_coded & ~returns_3mo
assert int(fail.sum()) == 2, f"expected 2 absentees failing the return-within-3-months test, got {int(fail.sum())}"

targets = lab.loc[fail, ["hhid", "s4aq40_code"]].copy()
targets["hhid_c"] = "NGA" + targets.hhid.astype(str)
targets["isco08"] = num(targets["s4aq40_code"])
print("Target rows (raw Nigeria labour module):")
print(targets)

P = pd.read_csv("harmonized_workers_v2.csv", low_memory=False)
A = "auto_genai"


def wmean(x, w):
    x = np.asarray(x, float); w = np.asarray(w, float)
    k = np.isfinite(x) & np.isfinite(w)
    return float(np.average(x[k], weights=w[k]))


drop_idx = []
for _, t in targets.iterrows():
    m = P[(P.hhid_c == t.hhid_c) & (P.isco08 == t.isco08)]
    assert len(m) == 1, f"expected exactly 1 match for {t.hhid_c} isco08={t.isco08}, got {len(m)}"
    drop_idx.append(m.index[0])
assert len(set(drop_idx)) == 2, "the two target rows must be distinct"

dropped = P.loc[drop_idx]
print("Matched rows in harmonized_workers_v2.csv:")
print(dropped[["hhid_c", "country", "status", "isco08", "auto_genai", "weight"]])

P_drop = P.drop(index=drop_idx)
NGA = P[P.country == "Nigeria 2023"]
NGA_drop = P_drop[P_drop.country == "Nigeria 2023"]

out = {
    "dropped_rows": [
        dict(hhid_c=r.hhid_c, isco08=float(r.isco08), auto_genai=round(float(r.auto_genai), 6),
             weight=round(float(r.weight), 4))
        for r in dropped.itertuples()
    ],
    "pooled_mean_baseline": round(float(P[A].mean()), 4),
    "pooled_mean_drop2": round(float(P_drop[A].mean()), 4),
    "pooled_mean_wtd_baseline": round(wmean(P[A], P.weight), 4),
    "pooled_mean_wtd_drop2": round(wmean(P_drop[A], P_drop.weight), 4),
    "nga_mean_baseline": round(float(NGA[A].mean()), 4),
    "nga_mean_drop2": round(float(NGA_drop[A].mean()), 4),
    "nga_mean_wtd_baseline": round(wmean(NGA[A], NGA.weight), 4),
    "nga_mean_wtd_drop2": round(wmean(NGA_drop[A], NGA_drop.weight), 4),
    "n_baseline": int(len(P)),
    "n_drop2": int(len(P_drop)),
}
moves = any(abs(out[f"{k}_baseline"] - out[f"{k}_drop2"]) >= 5e-4
            for k in ["pooled_mean", "pooled_mean_wtd", "nga_mean", "nga_mean_wtd"])
out["moves_at_3dp"] = bool(moves)
print(f"moves at 3 decimals: {moves}")

json.dump(out, open("results/analysis_v3_py.json", "w"), indent=2)
print("wrote results/analysis_v3_py.json")
print(json.dumps(out, indent=2))
