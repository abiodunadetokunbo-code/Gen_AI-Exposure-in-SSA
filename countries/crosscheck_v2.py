"""Cross-check every revision-2 result pair (Python against R).

Pairs: the worker-level analysis (analysis_v2.py / .R), the Althoff variant
table (althoff_variants_v2.py / .R), the ILOSTAT cross-country rebuild
(macro_ilostat_v2.py / .R), the Atlas AI-route shares (atlas_ai_route_v2.py / .R),
the crosswalk sensitivity (crosswalk_sensitivity_v2.py / .R, which now also
reads the BLS OEWS May 2018 national file for the employment-weighted variant) and the
survey-design standard errors (survey_design_v2.py / .R, whose design-id files
must also match row for row) and the country cross-section (analysis_macro.py / .R). Compares every number each pair shares, at
tolerance 5e-4 (both sides round to four decimals). Fails if a key is present
in one file and missing in the other, or if a result file is older than the
data or task files it was built from.
"""
import glob
import json
import os
import sys

TOL = 5e-4
VARIANT_FILES = sorted(glob.glob("althoff_variants/*.csv"))
ILOSTAT_FILES = sorted(glob.glob("../ilostat/raw/*.csv"))
ATLAS_FILES = sorted(glob.glob("../atlas_data/task_country_core/*.parquet"))
OEWS_FILE = "../oews/oesm18nat/national_M2018_dl.xlsx"
DESIGN_FILES = ["../lsms_probe/w5/Post Harvest Wave 5/Household/secta_harvestw5.csv",
                "TZA_2020_NPS-R5/hh_sec_a.csv", "UGA_2019_UNPS/UGA_2019_UNPS_v03_M_CSV/HH/gsec1.csv",
                "ETH_2021_ESPS-W5/sect1_hh_w5.csv"]
PAIRS = [
    ("revision_v2",
     "results/revision_v2_py.json", ["harmonized_workers_v2.csv", "harmonized_workers_v2_eth_resident.csv"],
     "results/revision_v2_r.json", ["harmonized_workers_v2_R.csv", "harmonized_workers_v2_eth_resident_R.csv"]),
    ("althoff_variants_v2",
     "results/althoff_variants_v2_py.json", ["harmonized_workers_v2.csv"] + VARIANT_FILES,
     "results/althoff_variants_v2_r.json", ["harmonized_workers_v2_R.csv"] + VARIANT_FILES),
    ("macro_ilostat_v2",
     "results/macro_ilostat_v2_py.json", ["harmonized_workers_v2.csv", "macro_country_cross_section.csv"] + ILOSTAT_FILES,
     "results/macro_ilostat_v2_r.json", ["harmonized_workers_v2_R.csv", "macro_country_cross_section.csv"] + ILOSTAT_FILES),
    ("atlas_ai_route_v2",
     "results/atlas_ai_route_v2_py.json", ["macro_ilostat_v2_countries.csv", "macro_country_cross_section.csv"] + ATLAS_FILES,
     "results/atlas_ai_route_v2_r.json", ["macro_ilostat_v2_countries_R.csv", "macro_country_cross_section.csv"] + ATLAS_FILES),
    ("crosswalk_sensitivity_v2",
     "results/crosswalk_sensitivity_v2_py.json", ["harmonized_workers_v2.csv", OEWS_FILE],
     "results/crosswalk_sensitivity_v2_r.json", ["harmonized_workers_v2_R.csv", OEWS_FILE]),
    ("survey_design_v2",
     "results/survey_design_v2_py.json", ["harmonized_workers_v2.csv", "harmonized_workers_v2_eth_resident.csv"] + DESIGN_FILES,
     "results/survey_design_v2_r.json", ["harmonized_workers_v2_R.csv", "harmonized_workers_v2_eth_resident_R.csv"] + DESIGN_FILES),
    # analysis_macro builds macro_country_cross_section.csv, which the ILOSTAT
    # and Atlas pairs above both read, so its own pair is checked here too.
    ("macro",
     "results/macro_py.json", ["../africa_genai_real_panel.csv"],
     "results/macro_r.json", ["../africa_genai_real_panel.csv"]),
]
# Random draws use each language's own generator, so their summaries are compared
# at |py - r| <= 0.003 + 0.05 * |py| (paths starting with these prefixes).
LOOSE = {"crosswalk_sensitivity_v2": ("/draws",)}


def is_missing(v):
    """None, a float NaN (Python) or the string "NaN" (R's jsonlite) all mean an empty cell."""
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

ids_py = open("survey_design_ids_v2.csv").read().replace('"', "").splitlines()
ids_r = open("survey_design_ids_v2_R.csv").read().replace('"', "").splitlines()
print(f"[survey_design_ids_v2] {len(ids_py) - 1} households, identical: {ids_py == ids_r}")
failed = failed or ids_py != ids_r

if failed:
    sys.exit(1)
print("CROSSCHECK PASSED: R and Python agree on every number in every pair.")
