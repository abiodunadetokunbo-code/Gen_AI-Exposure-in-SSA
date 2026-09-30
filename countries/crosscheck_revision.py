"""Cross-check the R and Python PRE-REVISION (v1) results, in archive_v1/results.
Kept as the record of the first submission; crosscheck_v2.py checks the live pairs."""
import json, sys

py = json.load(open("archive_v1/results/revision_py.json"))
r = json.load(open("archive_v1/results/revision_r.json"))
TOL = 5e-4
bad, checked = [], 0


def walk(a, b, path=""):
    global checked
    if isinstance(a, dict) and isinstance(b, dict):
        for k in a:
            if k in b:
                walk(a[k], b[k], f"{path}/{k}")
        return
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        checked += 1
        if abs(float(a) - float(b)) > TOL:
            bad.append((path, a, b))


# the coefficient blocks are stored differently (py keeps se/p, R keeps b only)
def flatten_reg(d, is_py):
    o = {}
    for spec, terms in d.items():
        for t, v in terms.items():
            o[f"{spec}|{t}"] = v["b"] if (is_py and isinstance(v, dict)) else v
    return o


walk(py["country_composition_weighted"], r["country_composition_weighted"], "comp")
walk(py["group_means_ci"], r["group_means_ci"], "ci")
walk({k: v for k, v in py["robustness"].items() if k != "tza_alternatives"},
     {k: v for k, v in r["robustness"].items() if k != "tza_alternatives"}, "rob")
walk(py["robustness"]["tza_alternatives"], r["robustness"]["tza_alternatives"], "tza_alt")
walk(flatten_reg(py["status_reg"], True), flatten_reg(r["status_reg"], False), "statusreg")
walk(flatten_reg(py["macro_reg"], True), flatten_reg(r["macro_reg"], False), "macroreg")
walk({k: v["pearson"] for k, v in py["macro_corr"].items()},
     {k: v["pearson"] for k, v in r["macro_corr"].items()}, "corr")
walk({"pooled_equal_country_mean": py["pooled_equal_country_mean"]},
     {"pooled_equal_country_mean": r["pooled_equal_country_mean"]}, "misc")

print(f"compared {checked} numbers at tolerance {TOL}")
if bad:
    print(f"MISMATCH in {len(bad)}:")
    for p, a, b in bad[:40]:
        print(f"  {p:55s} py={a} r={b}")
    sys.exit(1)
print("R and Python agree on every compared number.")
