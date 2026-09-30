"""Cross-check every revision-4 result pair (Python against R). Modelled on
crosscheck_v3.py; crosscheck_v2.py and crosscheck_v3.py are untouched and keep
passing on their own pairs. Two new pairs, both reading the v2 worker files
(unchanged) and the v2/v3 result JSONs they regression-test against:

  composition_reconcile_v4   the 0.080 against 0.090 reconciliation: the
                             zero-residual aggregation identity and the
                             group-by-group decomposition of the employment-
                             share difference (point 3, step 8)
  macro_fit_v4               standardised coefficients and incremental
                             R-squared for the three Table 10 predictors, on
                             the common complete-case sample (point 7, step 9)

Tolerance 5e-4, as in crosscheck_v2.py and crosscheck_v3.py.
"""
import glob
import json
import os
import sys

TOL = 5e-4
ILO_RAW = sorted(glob.glob("../ilostat/raw/*.csv"))

PAIRS = [
    ("composition_reconcile_v4",
     "results/composition_reconcile_v4_py.json",
     ["harmonized_workers_v2.csv", "../crosswalks/isco08_to_exposure.csv",
      "results/composition_cf_v3_py.json", "results/survey_design_v3_py.json",
      "results/survey_design_v2_py.json"] + ILO_RAW,
     "results/composition_reconcile_v4_r.json",
     ["harmonized_workers_v2_R.csv", "../crosswalks/isco08_to_exposure.csv",
      "results/composition_cf_v3_r.json", "results/survey_design_v3_r.json",
      "results/survey_design_v2_r.json"] + ILO_RAW),
    ("macro_fit_v4",
     "results/macro_fit_v4_py.json",
     ["atlas_ai_route_v2_countries.csv", "results/atlas_ai_route_v2_py.json",
      "results/macro_ilostat_v2_py.json"],
     "results/macro_fit_v4_r.json",
     ["atlas_ai_route_v2_countries_R.csv", "results/atlas_ai_route_v2_r.json",
      "results/macro_ilostat_v2_r.json"]),
]
LOOSE = {}


def is_missing(v):
    return v is None or v == "NaN" or (isinstance(v, float) and v != v)


def compare(py, r, loose=()):
    bad, missing, checked = [], [], 0

    def walk(a, b, path):
        nonlocal checked
        if is_missing(a) and is_missing(b):
            return
        if isinstance(a, dict) and isinstance(b, dict):
            for k in sorted(set(a) | set(b)):
                if k not in a or k not in b:
                    if not (a.get(k) is None and b.get(k) is None):
                        missing.append(f"{path}/{k} (only in {'py' if k in a else 'R'})")
                    continue
                walk(a[k], b[k], f"{path}/{k}")
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                bad.append((path, f"len {len(a)}", f"len {len(b)}"))
                return
            for i, (x, y) in enumerate(zip(a, b)):
                walk(x, y, f"{path}[{i}]")
        elif isinstance(a, bool) or isinstance(b, bool):
            if a != b:
                bad.append((path, a, b))
        elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
            checked += 1
            tol = 0.003 + 0.05 * abs(float(a)) if path.startswith(loose) else TOL
            if abs(float(a) - float(b)) > tol:
                bad.append((path, a, b))
        elif a != b:
            bad.append((path, a, b))

    walk(py, r, "")
    return bad, missing, checked


failed = False
for name, py_res, py_deps, r_res, r_deps in PAIRS:
    stale = [(res, dat) for res, deps in [(py_res, py_deps), (r_res, r_deps)] for dat in deps
             if os.path.getmtime(res) < os.path.getmtime(dat)]
    if stale:
        for res, dat in stale:
            print(f"[{name}] STALE: {res} is older than {dat}; rerun it")
        failed = True
        continue
    bad, missing, checked = compare(json.load(open(py_res)), json.load(open(r_res)), LOOSE.get(name, ()))
    print(f"[{name}] compared {checked} numbers at tolerance {TOL}")
    for m in missing[:40]:
        print(f"  key in one file only: {m}")
    for p, a, b in bad[:40]:
        print(f"  MISMATCH {p:60s} py={a} r={b}")
    failed = failed or bool(missing or bad)

if failed:
    sys.exit(1)
print("CROSSCHECK V4 PASSED: R and Python agree on every number in every new pair.")
