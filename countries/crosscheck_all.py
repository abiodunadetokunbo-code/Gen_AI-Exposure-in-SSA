"""Cross-check the R/Python pairs of the PRE-REVISION (v1) pipeline.

  archive_v1/results/desc_py.json     vs desc_r.json       (analysis_descriptive)
  archive_v1/results/revision_py.json vs revision_r.json   (analysis_revision)

Kept as the record of what the first submission reported. The live revision-2
pairs, including analysis_macro, are checked by crosscheck_v2.py, which
run_all.py calls. Exits non-zero on any disagreement.

Run from countries/, after analysis_descriptive and analysis_revision (both of
which now read and write archive_v1/).
"""
import json, os, sys

TOL = 5e-4
total, bad, absent = 0, [], []


def walk(a, b, path):
    global total
    if isinstance(a, dict) and isinstance(b, dict):
        for k in a:
            if k in b:
                walk(a[k], b[k], f"{path}/{k}")
        return
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            walk(x, y, f"{path}[{i}]")
        return
    # R's toJSON wraps scalars in length-1 lists unless auto_unbox is on
    if isinstance(a, list) and len(a) == 1:
        return walk(a[0], b, path)
    if isinstance(b, list) and len(b) == 1:
        return walk(a, b[0], path)
    if isinstance(a, bool) or isinstance(b, bool):
        return
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        total += 1
        if abs(float(a) - float(b)) > TOL:
            bad.append((path, a, b))


def flatten_reg(d, has_se):
    """py stores {term: {b, se, p}}, R stores {term: b}."""
    o = {}
    for spec, terms in d.items():
        for t, v in terms.items():
            o[f"{spec}|{t}"] = v["b"] if (has_se and isinstance(v, dict)) else v
    return o


def load(name):
    p = f"archive_v1/results/{name}"
    if not os.path.exists(p):
        print(f"  missing {p}")
        absent.append(p)
        return None
    return json.load(open(p))


print(f"cross-checking R against Python at tolerance {TOL}\n")

# ---- stage 1: descriptive ----
py, r = load("desc_py.json"), load("desc_r.json")
if py and r:
    before = total
    for k in py:
        if k in r:
            walk(py[k], r[k], f"desc/{k}")
    print(f"  analysis_descriptive : {total - before} numbers")

# ---- stage 2: revision ----
py, r = load("revision_py.json"), load("revision_r.json")
if py and r:
    before = total
    walk(py["country_composition_weighted"], r["country_composition_weighted"], "rev/comp")
    walk(py["group_means_ci"], r["group_means_ci"], "rev/ci")
    walk({k: v for k, v in py["robustness"].items() if k != "tza_alternatives"},
         {k: v for k, v in r["robustness"].items() if k != "tza_alternatives"}, "rev/rob")
    walk(py["robustness"]["tza_alternatives"], r["robustness"]["tza_alternatives"], "rev/tza")
    walk(flatten_reg(py["status_reg"], True), flatten_reg(r["status_reg"], False), "rev/statusreg")
    walk(flatten_reg(py["macro_reg"], True), flatten_reg(r["macro_reg"], False), "rev/macroreg")
    walk({k: v["pearson"] for k, v in py["macro_corr"].items()},
         {k: v["pearson"] for k, v in r["macro_corr"].items()}, "rev/corr")
    walk({"x": py["pooled_equal_country_mean"]}, {"x": r["pooled_equal_country_mean"]}, "rev/misc")
    print(f"  analysis_revision    : {total - before} numbers")

print(f"\ncompared {total} numbers across both v1 stages")
if absent:
    print(f"CANNOT CHECK: {len(absent)} result file(s) missing. "
          "Run analysis_descriptive and analysis_revision (R and Python) from countries/.")
    sys.exit(1)
if total == 0:
    print("CANNOT CHECK: nothing was compared.")
    sys.exit(1)
if bad:
    print(f"MISMATCH in {len(bad)}:")
    for p, a, b in bad[:40]:
        print(f"  {p:50s} py={a} r={b}")
    sys.exit(1)
print("R and Python agree everywhere.")
