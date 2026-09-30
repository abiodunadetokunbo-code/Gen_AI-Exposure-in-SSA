"""Row-by-row, column-by-column reconciliation of the Python and R v2 builds.

Unlike a row count match, this sorts both frames onto a stable key
(hhid_c + a within-household running index, since raw files carry no global
person id that both languages would reconstruct identically for the
imputed-farmer blocks) and compares every shared column exactly (strings)
or to a tight numeric tolerance (floats). Exits non-zero on any mismatch.
"""
import sys

import numpy as np
import pandas as pd

FILES = [
    ("harmonized_workers_v2.csv", "harmonized_workers_v2_R.csv", "headline"),
    ("harmonized_workers_v2_own_use_excluded.csv", "harmonized_workers_v2_own_use_excluded_R.csv",
     "own_use_excluded"),
    ("harmonized_workers_v2_eth_outmigrant.csv", "harmonized_workers_v2_eth_outmigrant_R.csv",
     "eth_outmigrant"),
    ("harmonized_workers_v2_eth_resident.csv", "harmonized_workers_v2_eth_resident_R.csv",
     "eth_resident"),
]

NUMCOLS = ["age", "urban", "isco08", "major", "auto_genai", "augment_genai", "atlas_exposure",
           "weight", "imputed", "informal", "informal_v2", "major88"]
# R writes logicals as TRUE/FALSE, Python as 1.0/0.0; map both to 1/0 before comparing
BOOL = {"TRUE": 1, "FALSE": 0, "True": 1, "False": 0}
STRCOLS = ["country", "sex", "status", "hhid_c", "imputed_reason"]

overall_ok = True
for py_path, r_path, label in FILES:
    py = pd.read_csv(py_path, low_memory=False)
    rr = pd.read_csv(r_path, low_memory=False)
    print(f"\n=== {label}: py {py.shape} vs R {rr.shape} ===")
    if len(py) != len(rr):
        print(f"  ROW COUNT MISMATCH: py={len(py)} r={len(rr)}")
        overall_ok = False
        continue
    # stable sort key: hhid_c, then a within-group running index (both
    # builds append rows within each household in the same source-file
    # order, since neither language reorders the raw file before iterating)
    py = py.copy(); rr = rr.copy()
    py["_k"] = py.groupby("hhid_c").cumcount()
    rr["_k"] = rr.groupby("hhid_c").cumcount()
    py = py.sort_values(["hhid_c", "_k"]).reset_index(drop=True)
    rr = rr.sort_values(["hhid_c", "_k"]).reset_index(drop=True)

    mism = {}
    for c in STRCOLS:
        if c not in py.columns or c not in rr.columns:
            continue
        a = py[c].astype(str).where(py[c].notna(), "NA")
        b = rr[c].astype(str).where(rr[c].notna(), "NA")
        bad = (a != b).sum()
        if bad:
            mism[c] = int(bad)
    for c in NUMCOLS:
        if c not in py.columns or c not in rr.columns:
            continue
        a = pd.to_numeric(py[c].replace(BOOL), errors="coerce")
        b = pd.to_numeric(rr[c].replace(BOOL), errors="coerce")
        both_na = a.isna() & b.isna()
        diff = (a - b).abs()
        bad = (~both_na & (diff.isna() | (diff > 1e-6))).sum()
        if bad:
            mism[c] = int(bad)
    if mism:
        print(f"  MISMATCHES: {mism}")
        overall_ok = False
    else:
        ncols = sum(c in py.columns and c in rr.columns for c in STRCOLS + NUMCOLS)
        print(f"  all {ncols} shared columns match row-for-row "
              f"({len(py):,} rows)")

print()
if overall_ok:
    print("RECONCILE PASSED: Python and R v2 builds agree row-for-row on every file.")
    sys.exit(0)
else:
    print("RECONCILE FAILED: see mismatches above.")
    sys.exit(1)
