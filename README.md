# Generative-AI Exposure in Sub-Saharan African Labour Markets

Replication materials for *Generative-AI Exposure in Sub-Saharan African Labour
Markets: Who Is Exposed, and Why So Few* (Abiodun Adetokunbo, Augustine University).

The paper measures occupational exposure to generative AI across the workforce of
four Sub-Saharan African economies using nationally representative LSMS-ISA
microdata for 23,444 workers (Nigeria 2023, Tanzania 2020, Uganda 2019, Ethiopia
2021), and places the four countries on a 32-country continental gradient.

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

1. `crosswalks/build_isco88_exposure.py`, `build_isco08_exposure.py` build the
   occupation crosswalks (ISCO to O*NET-SOC) and attach the task-level AI exposure
   measure (Althoff and Reichardt 2026, NBER WP 35353) and an independent Atlas
   automation index.
2. `countries/build_harmonized.py` assembles the pooled worker file from the four
   surveys (occupation, exposure, sex, age, urban/rural, employment status,
   informality).
3. `countries/analysis_descriptive.{py,R}` produce the micro results
   (`results/desc_*.json`); `analysis_macro.{py,R}` produce the cross-country
   results and figure (`results/macro_*.json`,
   `results/fig_macro_exposure_informality.pdf`).
4. `paper/paper.tex` compiles the manuscript.

Each analysis step is implemented independently in R and Python and the two are
reconciled value by value before any number enters the paper.

## Contents

- `paper/` manuscript (`paper.tex`, `refs.bib`, `paper.pdf`) and figure.
- `countries/` build and analysis scripts, aggregated results, country-level
  cross-section.
- `crosswalks/` crosswalk build scripts, public ISCO/SOC correspondence inputs,
  and the derived occupation-level exposure lookups.
- `atlas_data/althoff_occ_exposure_onetsoc.csv` occupation-level exposure scores.
- `africa_genai_real_panel.csv` country-level macro panel; `build_real_panel.R`.
- `wb_microdata.py`, `lsms_isa_manifest.csv` data-discovery tool and catalogue.
- `RESULTS_SUMMARY.md` all headline numbers.

## Data sources

- LSMS-ISA surveys, World Bank Microdata Library (licensed; not redistributed).
- AI task-capability ratings: Althoff and Reichardt (2026), NBER WP 35353.
- ISCO/SOC/O*NET crosswalks: ILO and the IBS/eworx `iscoCrosswalks` project.
- Macro indicators: World Bank WDI and ILOSTAT.
