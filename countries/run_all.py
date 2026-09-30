"""Single entry point for the pipeline (revision-2 plan step 12, revision-3 step 16c).

Runs every build, analysis and check in dependency order and stops at the first
failure. This replaces the run-these-in-order-by-hand convention in README.md
and is what makes the pipeline repeatable by someone who is not the author.

  1. build_harmonized_v2.py   ) each asserts the counts the author approved
  2. build_harmonized_v2.R    )  on 2026-09-19 before it writes anything
  3. reconcile_v2.py          -  the two builds, row for row and column for column
  4. analysis_macro.py / .R   -  builds macro_country_cross_section.csv, which 5-9 read
  5. analysis_v2.py / .R      -  worker-level results
  6. althoff_variants_v2.py / .R
  7. macro_ilostat_v2.py / .R
  8. atlas_ai_route_v2.py / .R
  9. crosswalk_sensitivity_v2.py / .R
 10. survey_design_v2.py / .R
 11. figures_revision.py     -  the three vector figures, into paper/figures/
 12. survey_design_v3.py / .R  ) the revision-3 stages. Each regression-tests
 13. analysis_v3.py / .R       )  against its v2 twin before it writes, and
 14. tza_addback_v3.py / .R    )  each reads the v2 worker files unchanged.
 15. althoff_variants_v3.py / .R
 16. crosswalk_sensitivity_v3.py / .R
 17. composition_cf_v3.py / .R
 18. composition_reconcile_v4.py / .R  )  revision-4; both read the v2 worker
 19. macro_fit_v4.py / .R              )  files and the v2/v3 results unchanged.
 20. crosscheck_v2.py         -  all seven revision-2 R/Python pairs
 21. crosscheck_v3.py         -  the six revision-3 pairs
 22. crosscheck_v4.py         -  the two revision-4 pairs
 23. refresh the canonical copies (see below)
 24. check_paper_numbers.py   -  every approved number traces to the output
                                 and appears in body.tex

Because every stage reruns before the cross-checks compare, a stale result file
cannot survive a full run. Both cross-checks also fail outright if any result
file is older than the data it claims to summarize, which catches a partial run.

The canonical names harmonized_workers.csv and results/revision_{py,r}.json
hold the revision-2 content (the author approved the swap on 2026-09-19; the
pre-revision files are in archive_v1/). Step 12 copies them from the _v2
outputs rather than leaving them to be refreshed by hand. Nothing in the
pipeline reads them, so the copy cannot affect what the earlier stages see.

Not run here, on purpose:
  - the v1 record: analysis_descriptive, analysis_revision, crosscheck_all,
    crosscheck_revision, verify_review2. All read and write archive_v1/ and
    reproduce what the first submission reported.
  - the ILOSTAT benchmark fetch for the composition counterfactual. Stage 17
    reads ilostat/raw_benchmark/, three files pulled one country at a time from
    the SDMX template recorded in ilostat/provenance_benchmark.json, which also
    carries each file's SHA-256 and byte count. That file is the
    reproducibility record, the same way atlas_data/task_country_core/ and
    oews/ already work, and the fetch stays out of the pipeline so a routine
    run does not hit the network.

Usage:
  python run_all.py                   full run
  python run_all.py --checks          skip the builds and analyses, run 18-21 only
  python run_all.py --allow-tex-drift downgrade the body.tex check to a warning,
                                      for use while the manuscript is mid-rewrite
"""
import argparse
import shutil
import subprocess
import sys
import time

ap = argparse.ArgumentParser()
ap.add_argument("--checks", action="store_true", help="run only the cross-check and number trace")
ap.add_argument("--allow-tex-drift", action="store_true",
                help="downgrade the body.tex number check to a warning")
args = ap.parse_args()

BUILD = [
    ("build the pooled sample (Python)", ["python", "build_harmonized_v2.py"]),
    ("build the pooled sample (R)", ["Rscript", "build_harmonized_v2.R"]),
    ("reconcile the two builds", ["python", "reconcile_v2.py"]),
]
ANALYSIS = [
    ("country cross-section (Python)", ["python", "analysis_macro.py"]),
    ("country cross-section (R)", ["Rscript", "analysis_macro.R"]),
    ("worker-level results (Python)", ["python", "analysis_v2.py"]),
    ("worker-level results (R)", ["Rscript", "analysis_v2.R"]),
    ("Althoff variants (Python)", ["python", "althoff_variants_v2.py"]),
    ("Althoff variants (R)", ["Rscript", "althoff_variants_v2.R"]),
    ("ILOSTAT rebuild (Python)", ["python", "macro_ilostat_v2.py"]),
    ("ILOSTAT rebuild (R)", ["Rscript", "macro_ilostat_v2.R"]),
    ("Atlas AI-route shares (Python)", ["python", "atlas_ai_route_v2.py"]),
    ("Atlas AI-route shares (R)", ["Rscript", "atlas_ai_route_v2.R"]),
    ("crosswalk sensitivity (Python)", ["python", "crosswalk_sensitivity_v2.py"]),
    ("crosswalk sensitivity (R)", ["Rscript", "crosswalk_sensitivity_v2.R"]),
    ("survey-design standard errors (Python)", ["python", "survey_design_v2.py"]),
    ("survey-design standard errors (R)", ["Rscript", "survey_design_v2.R"]),
    ("paper figures", ["python", "figures_revision.py"]),
]
ANALYSIS_V3 = [
    ("weighted group means and weight totals (Python)", ["python", "survey_design_v3.py"]),
    ("weighted group means and weight totals (R)", ["Rscript", "survey_design_v3.R"]),
    ("the two Nigerian absentees (Python)", ["python", "analysis_v3.py"]),
    ("the two Nigerian absentees (R)", ["Rscript", "analysis_v3.R"]),
    ("Tanzanian add-back (Python)", ["python", "tza_addback_v3.py"]),
    ("Tanzanian add-back (R)", ["Rscript", "tza_addback_v3.R"]),
    ("formality across the nine variants (Python)", ["python", "althoff_variants_v3.py"]),
    ("formality across the nine variants (R)", ["Rscript", "althoff_variants_v3.R"]),
    ("formality across the crosswalk rules (Python)", ["python", "crosswalk_sensitivity_v3.py"]),
    ("formality across the crosswalk rules (R)", ["Rscript", "crosswalk_sensitivity_v3.R"]),
    ("composition counterfactual (Python)", ["python", "composition_cf_v3.py"]),
    ("composition counterfactual (R)", ["Rscript", "composition_cf_v3.R"]),
]
ANALYSIS_V4 = [
    ("0.080/0.090 reconciliation (Python)", ["python", "composition_reconcile_v4.py"]),
    ("0.080/0.090 reconciliation (R)", ["Rscript", "composition_reconcile_v4.R"]),
    ("comparable predictor metrics (Python)", ["python", "macro_fit_v4.py"]),
    ("comparable predictor metrics (R)", ["Rscript", "macro_fit_v4.R"]),
]
CANONICAL = [
    ("harmonized_workers_v2.csv", "harmonized_workers.csv"),
    ("results/revision_v2_py.json", "results/revision_py.json"),
    ("results/revision_v2_r.json", "results/revision_r.json"),
]

step = 0


def run(label, cmd):
    global step
    step += 1
    print(f"\n=== {step:2d}. {label}\n    {' '.join(cmd)}", flush=True)
    t0 = time.time()
    r = subprocess.run(cmd)
    if r.returncode != 0:
        print(f"\nFAILED at step {step}: {label} (exit {r.returncode}). Nothing after it was run.")
        sys.exit(r.returncode)
    print(f"    ok, {time.time() - t0:.1f}s", flush=True)


stages = ([] if args.checks else BUILD + ANALYSIS + ANALYSIS_V3 + ANALYSIS_V4)
for label, cmd in stages:
    run(label, cmd)

run("cross-check every revision-2 R/Python pair", ["python", "crosscheck_v2.py"])
run("cross-check every revision-3 R/Python pair", ["python", "crosscheck_v3.py"])
run("cross-check every revision-4 R/Python pair", ["python", "crosscheck_v4.py"])

step += 1
print(f"\n=== {step:2d}. refresh the canonical copies", flush=True)
for src, dst in CANONICAL:
    shutil.copyfile(src, dst)
    print(f"    {src} -> {dst}")

check = ["python", "check_paper_numbers.py"]
if args.allow_tex_drift:
    check.append("--allow-tex-drift")
run("trace every approved number", check)

print("\nALL STAGES PASSED.")
