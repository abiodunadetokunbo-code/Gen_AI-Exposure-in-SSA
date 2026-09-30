# Generative-AI Exposure in Sub-Saharan African Labour Markets

Replication materials for *Generative-AI Exposure in Sub-Saharan African Labour
Markets: Who Is Exposed, and Why So Few*.

The paper measures occupational exposure to generative AI across the workforce of
three Sub-Saharan African economies using LSMS-ISA microdata for 24,838 workers
(Nigeria 2023, Tanzania 2020, Uganda 2019), and places them on a 32-country
continental gradient. Ethiopia 2021 carries only one-digit occupation codes, so
it is reported as a supplement (1,989 resident wage workers, 584 out-migrants)
and left out of the headline sample.

## Important: the microdata is not redistributed here

The worker-level LSMS-ISA surveys are licensed by the World Bank and **cannot be
redistributed**. This repository therefore contains the **code, the public
occupation crosswalks, and the aggregated/derived results**, but not the raw or
worker-level survey files. Every number in the paper can be checked against the
aggregated outputs in `countries/results/` and `RESULTS_SUMMARY.md`. To rebuild
from scratch, obtain the surveys yourself (see below) and run the pipeline.

## How to obtain the data

Register (free) at the World Bank Microdata Library
(https://microdata.worldbank.org) and download the four surveys. `wb_microdata.py`
enumerates every LSMS-ISA dataset and its files without a login:

```
python wb_microdata.py discover          # lists all LSMS-ISA datasets -> lsms_isa_manifest.csv
python wb_microdata.py files <idno>       # lists a study's data files
python wb_microdata.py download <id> --cookie "<your session cookie>"
```

The country-level macro panel (`africa_genai_real_panel.csv`) is built from public
World Bank WDI / ILOSTAT indicators by `build_real_panel.R`.

## Pipeline

One command, from `countries/`:

```
python run_all.py
```

It runs every build, analysis and check in dependency order and stops at the
first failure: the two builds, the row-for-row reconcile between them, the
seven R/Python analysis pairs, the cross-check, and the number trace. A full
run takes about four minutes.

1. `crosswalks/build_isco88_exposure.py`, `build_isco08_exposure.py` build the
   occupation crosswalks (ISCO to O*NET-SOC) and attach the task-level AI exposure
   measure (Althoff and Reichardt 2026, NBER WP 35353) and an independent Atlas
   automation index.
2. `build_harmonized_v2.py` and `build_harmonized_v2.R` each assemble the pooled
   worker file from the four surveys: occupation, exposure, sex, age,
   urban/rural, employment status, informality, the survey weight, the household
   id used for clustering, and the reason any exposure value was imputed. The
   two are written independently in the two languages and both assert the counts
   the author approved, so a silent regression fails the build. Every filter
   that drops rows logs a labelled count, which is what `results/sample_flow_v2*.json`
   and the paper's sample-flow table are built from.
3. `reconcile_v2.py` compares the two builds row for row and column for column.
4. The analysis pairs, each implemented independently in R and Python:
   `analysis_macro` (country cross-section), `analysis_v2` (worker-level
   results), `althoff_variants_v2` (the nine Althoff exposure variants),
   `macro_ilostat_v2` (the ILOSTAT rebuild), `atlas_ai_route_v2` (AI-route
   shares), `crosswalk_sensitivity_v2` (the ISCO-to-O*NET step, including an
   employment-weighted version from BLS OEWS) and `survey_design_v2`
   (survey-design standard errors).
5. `crosscheck_v2.py` reconciles R against Python across all seven pairs, about
   2,390 numbers, and exits non-zero on any disagreement. It also fails if a
   result file is older than the data it claims to summarize, so a partial run
   cannot pass unnoticed.
6. `paper/paper_anon.tex` compiles the manuscript. `check_paper_numbers.py` verifies
   that every approved number traces back to the analysis output and appears in
   `paper/body.tex`.

Every analysis step is implemented independently in R and Python, and the two are
reconciled value by value before any number enters the paper. Since the revision
the build step has a second implementation too.

### The pre-revision (v1) record

`archive_v1/` holds the sample and results of the first submission (23,444
workers). `analysis_descriptive.{py,R}`, `analysis_revision.{py,R}`,
`crosscheck_all.py`, `crosscheck_revision.py` and `verify_review2.py` all read
and write that directory and reproduce what the first submission reported.
`run_all.py` does not call them. `build_harmonized.py`, the v1 build, refuses
to write and points at its replacement.

### A note on an earlier defect

Versions of `build_harmonized.py` before 2026-08-26 carried three faults that
joined each worker's occupation to a different person's demographics and job
type. All three are fixed and documented in the script header, with the full
trace in `PAPER_FIGURES_AUDIT.md`. The occupational results were never affected;
the demographic columns, the wage/own-account split, the formality result and the
urban/rural gap were, and are corrected throughout.

### Weights

Each survey supplies a cross-sectional weight, and all four are carried through
the build with complete coverage. The paper reports weighted and unweighted
figures side by side. Unweighted pooled statistics are sample shares, not
population estimates, and are labelled as such.

## Contents

- `paper/` manuscript (`paper_anon.tex`, `refs.bib`, `paper_anon.pdf`) and figure.
- `countries/` build and analysis scripts, aggregated results, country-level
  cross-section.
- `crosswalks/` crosswalk build scripts, public ISCO/SOC correspondence inputs,
  and the derived occupation-level exposure lookups.
- `atlas_data/althoff_occ_exposure_onetsoc.csv` occupation-level exposure scores;
  `countries/althoff_variants/` the nine published variants, with
  `countries/althoff_provenance.json` recording the source and hash of each.
- `oews/` BLS OEWS May 2018 national employment, for the employment-weighted
  crosswalk, with `oews/oews_provenance.json`.
- `ilostat/` employment by occupation, for the cross-country rebuild.
- `africa_genai_real_panel.csv` country-level macro panel; `build_real_panel.R`.
- `wb_microdata.py`, `lsms_isa_manifest.csv` data-discovery tool and catalogue.
- `RESULTS_SUMMARY.md` all headline numbers.
- `PAPER_FIGURES_AUDIT.md` independent audit of every number in the paper.
- `paper/Revision_plan_review2.md`, `Revision_results_v2.md`,
  `Revision_progress_v2.md` the second-round revision: plan, results and log.

## Data sources

- LSMS-ISA surveys, World Bank Microdata Library (licensed; not redistributed).
- AI task-capability ratings: Althoff and Reichardt (2026), NBER WP 35353.
- ISCO/SOC/O*NET crosswalks: ILO and the IBS/eworx `iscoCrosswalks` project.
- US employment by occupation: BLS Occupational Employment and Wage Statistics,
  May 2018 national (https://www.bls.gov/oes/tables.htm). May 2018 is the last
  release coded to the 2010 SOC, which the exposure crosswalk uses.
- Macro indicators: World Bank WDI and ILOSTAT.
