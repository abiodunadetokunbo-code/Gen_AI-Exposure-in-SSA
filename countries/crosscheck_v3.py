"""Cross-check every revision-3 result pair (Python against R). Modelled on
crosscheck_v2.py; crosscheck_v2.py itself is untouched and keeps passing on
its own pairs. New pairs, all read the v2 worker files (unchanged) plus new
raw inputs specific to the exercise:

  survey_design_v3          the weighted formal/informal, urban/rural,
                             male/female and major-group means, and weight
                             totals by country (steps 2, 3)
  analysis_v3                the two Nigerian absentees who fail the
                             three-month test (step 4)
  tza_addback_v3              the Tanzanian add-back under five imputation
                             routes and two weight scenarios (step 5)
  althoff_variants_v3         the formal/informal split across the nine
                             task-file variants (step 7)
  crosswalk_sensitivity_v3    the same split across five crosswalk rules and
                             2,000 random draws (step 7)
  composition_cf_v3           the composition counterfactual against three
                             high-income benchmarks (step 6)

Tolerance 5e-4, as in crosscheck_v2.py. Random draws compared at the same
loose tolerance crosscheck_v2.py uses for crosswalk_sensitivity_v2's draws.
"""
import glob
import json
import os
import sys

TOL = 5e-4
VARIANT_FILES = sorted(glob.glob("althoff_variants/*.csv"))
OEWS_FILE = "../oews/oesm18nat/national_M2018_dl.xlsx"
DESIGN_RAW = ["../lsms_probe/w5/Post Harvest Wave 5/Household/secta_harvestw5.csv",
              "TZA_2020_NPS-R5/hh_sec_a.csv", "UGA_2019_UNPS/UGA_2019_UNPS_v03_M_CSV/HH/gsec1.csv"]
NGA_LAB = "../lsms_probe/w5/Post Harvest Wave 5/Household/sect4a_harvestw5.csv"
TZA_RAW = ["TZA_2020_NPS-R5/hh_sec_e1.csv", "TZA_2020_NPS-R5/hh_sec_a.csv", "TZA_2020_NPS-R5/hh_sec_n.csv"]
UGA_RAW = ["UGA_2019_UNPS/UGA_2019_UNPS_v03_M_CSV/HH/gsec1.csv"]
ILO_RAW = sorted(glob.glob("../ilostat/raw/*.csv")) + sorted(glob.glob("../ilostat/raw_benchmark/*.csv"))

PAIRS = [
    ("survey_design_v3",
     "results/survey_design_v3_py.json", ["harmonized_workers_v2.csv", "survey_design_ids_v2.csv",
                                          "results/survey_design_v2_py.json"],
     "results/survey_design_v3_r.json", ["harmonized_workers_v2_R.csv", "survey_design_ids_v2_R.csv",
                                         "results/survey_design_v2_r.json"]),
    ("analysis_v3",
     "results/analysis_v3_py.json", [NGA_LAB, "harmonized_workers_v2.csv"],
     "results/analysis_v3_r.json", [NGA_LAB, "harmonized_workers_v2_R.csv"]),
    ("tza_addback_v3",
     "results/tza_addback_v3_py.json", TZA_RAW + UGA_RAW + ["harmonized_workers_v2.csv",
                                                             "../crosswalks/isco08_to_exposure.csv"],
     "results/tza_addback_v3_r.json", TZA_RAW + UGA_RAW + ["harmonized_workers_v2_R.csv",
                                                            "../crosswalks/isco08_to_exposure.csv"]),
    ("althoff_variants_v3",
     "results/althoff_variants_v3_py.json", ["harmonized_workers_v2.csv", "results/althoff_variants_v2_py.json"] + VARIANT_FILES,
     "results/althoff_variants_v3_r.json", ["harmonized_workers_v2_R.csv", "results/althoff_variants_v2_r.json"] + VARIANT_FILES),
    ("crosswalk_sensitivity_v3",
     "results/crosswalk_sensitivity_v3_py.json", ["harmonized_workers_v2.csv", OEWS_FILE,
                                                   "results/crosswalk_sensitivity_v2_py.json"],
     "results/crosswalk_sensitivity_v3_r.json", ["harmonized_workers_v2_R.csv", OEWS_FILE,
                                                  "results/crosswalk_sensitivity_v2_r.json"]),
    ("composition_cf_v3",
     "results/composition_cf_v3_py.json", ["harmonized_workers_v2.csv", "../crosswalks/isco08_to_exposure.csv",
                                            "results/macro_ilostat_v2_py.json", "results/survey_design_v3_py.json",
                                            "results/survey_design_v2_py.json"] + ILO_RAW,
     "results/composition_cf_v3_r.json", ["harmonized_workers_v2_R.csv", "../crosswalks/isco08_to_exposure.csv",
                                           "results/macro_ilostat_v2_r.json", "results/survey_design_v3_r.json",
                                           "results/survey_design_v2_r.json"] + ILO_RAW),
]
LOOSE = {"crosswalk_sensitivity_v3": ("/draws",)}


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
print("CROSSCHECK V3 PASSED: R and Python agree on every number in every new pair.")
