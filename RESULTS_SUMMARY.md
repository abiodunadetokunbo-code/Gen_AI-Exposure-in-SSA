# RESULTS SUMMARY: SSA AI-exposure descriptive paper

*Every number below is dual-implemented in R and Python and reconciled before it
enters the paper. Sources: `countries/results/desc_*.json`, `macro_*.json`,
`revision_*.json`. Run `countries/crosscheck_all.py` to reconcile all three
stages (329 numbers, zero disagreement).*

> **Rebuilt 2026-08-26.** Three coding faults in `countries/build_harmonized.py`
> joined each worker's occupation to a different person's sex, age, residence and
> job type. They are fixed at source and documented in the script header and in
> `PAPER_FIGURES_AUDIT.md`. The occupational results were never affected. The
> demographic columns, the wage/own-account split, the formality result and the
> urban/rural gap all changed, and two of them changed direction. Any figure
> quoted from a version of this file dated before 2026-08-26 is stale.

## Sample

- 23,444 workers, 4 LSMS-ISA surveys: Nigeria 2023, Tanzania 2020, Uganda 2019, Ethiopia 2021.
- Per-country n: Nigeria 7,708, Tanzania 7,481, Uganda 7,671, Ethiopia 584.
- 17,587 (75.0%) carry a directly coded four-digit ISCO-08 occupation. The rest
  are 5,273 imputed Tanzanian farmers and 584 Ethiopians on one-digit codes.

## Headline

- Mean generative-AI exposure = **0.088** (median 0.076); survey-weighted **0.107**.
- 33.7% of workers score below 0.05.
- 66.1% are in agriculture or elementary occupations.
- The top 10% of workers hold 36% of all exposure.

## Table 1: sample composition by country

Unweighted shares of survey rows. Weighted counterparts in the next table.

| Country | n | % female | mean age | % urban | % agriculture | mean exposure |
|---|---|---|---|---|---|---|
| Nigeria 2023 | 7,708 | 49.0 | 40.0 | 34.0 | 28.4 | 0.122 |
| Tanzania 2020 | 7,481 | 44.4 | 32.3 | 26.3 | 77.9 | 0.083 |
| Uganda 2019 | 7,671 | 49.7 | 33.4 | 19.3 | 72.8 | 0.055 |
| Ethiopia 2021 | 584 | 38.0 | 26.5 | 44.5 | 22.4 | 0.144 |
| All (pooled) | 23,444 | 47.5 | 35.0 | 27.0 | 58.6 | 0.088 |

## Table 2: sample against survey-weighted

| Country | % agri (sample) | % agri (weighted) | exposure (sample) | exposure (weighted) |
|---|---|---|---|---|
| Nigeria 2023 | 28.4 | 24.1 | 0.122 | 0.125 |
| Tanzania 2020 | 77.9 | 82.1 | 0.083 | 0.078 |
| Uganda 2019 | 72.8 | 64.9 | 0.055 | 0.068 |
| Ethiopia 2021 | 22.4 | 27.7 | 0.144 | 0.123 |
| All (pooled) | 58.6 | 41.7 | 0.088 | 0.107 |

The pooled weighted row is dominated by Nigeria, whose population is far larger
than Tanzania's or Uganda's but whose sample is the same size. Unweighted pooled
figures are **sample shares**, not population estimates.

## Table 3: exposure by ISCO major group (pooled)

| Major group | share | mean exposure | 95% interval |
|---|---|---|---|
| Clerical support | 0.7% | 0.605 | [0.583, 0.626] |
| Technicians | 1.8% | 0.361 | [0.338, 0.384] |
| Managers | 5.1% | 0.210 | [0.205, 0.214] |
| Professionals | 4.6% | 0.172 | [0.162, 0.181] |
| Service and sales | 12.6% | 0.143 | [0.139, 0.147] |
| Plant and machine operators | 3.6% | 0.143 | [0.138, 0.148] |
| Skilled agriculture | 54.0% | 0.054 | [0.052, 0.055] |
| Craft and trades | 5.4% | 0.051 | [0.046, 0.056] |
| Elementary | 12.1% | 0.030 | [0.029, 0.032] |

Intervals clustered by household.

## Table 4: exposure by employment status (pooled)

| Status | share | mean exposure | 95% interval | weighted |
|---|---|---|---|---|
| Agriculture | 58.6% | 0.050 | [0.049, 0.051] | 0.059 |
| Own-account, non-agriculture | 21.8% | 0.133 | [0.130, 0.137] | 0.127 |
| Wage employee, non-agriculture | 17.6% | 0.152 | [0.146, 0.157] | 0.170 |
| Other, non-agriculture | 1.9% | 0.163 | [0.150, 0.177] | 0.140 |

`selfemp_nonag` is a residual and holds unpaid family workers and apprentices as
well as own-account workers. Tanzania contributes none of them: every Tanzanian
worker with a coded occupation answers yes to the wage question.

## Table 5: exposure and employment status, OLS

Agriculture omitted. Standard errors clustered by household.

| | (1) | (2) | (3) |
|---|---|---|---|
| Own-account, non-agriculture | 0.083 (0.002) | 0.076 (0.002) | 0.071 (0.002) |
| Wage employee, non-agriculture | 0.102 (0.003) | 0.097 (0.003) | 0.089 (0.003) |
| Other, non-agriculture | 0.113 (0.007) | 0.087 (0.007) | 0.082 (0.007) |
| Urban | | | 0.015 (0.002) |
| Male | | | 0.004 (0.001) |
| Age | | | 0.0003 (0.00003) |
| Country fixed effects | no | yes | yes |
| R2 | 0.192 | 0.210 | 0.216 |

n = 23,444 throughout. On wage workers alone, informal status carries −0.107
(0.009) with country fixed effects.

## Table 6: micro against Atlas macro exposure

| Country | micro mean (Althoff auto) | macro Atlas share-exposed |
|---|---|---|
| Ethiopia 2021 | 0.144 | 0.221 |
| Nigeria 2023 | 0.122 | 0.333 |
| Tanzania 2020 | 0.083 | 0.238 |
| Uganda 2019 | 0.055 | 0.214 |

Different scales, not comparable in levels. Rank correlation across the four is
0.40: both put Uganda last, they disagree on Ethiopia.

## Macro cross-section (32 African countries)

Rank (Spearman) correlations with the Atlas share exposed:

- informal employment rate: **−0.74** (n = 28)
- agricultural self-employment: **−0.75** (n = 30)
- GDP per capita: **+0.83** (n = 31)

OLS, heteroskedasticity-robust SEs, structural variables on a 0-1 scale:

| | (1) | (2) | (3) | (4) | (5) | (6) |
|---|---|---|---|---|---|---|
| Informal employment | −0.617 (0.077) | | | −0.305 (0.065) | | −0.248 (0.068) |
| Agricultural self-employment | | −0.448 (0.058) | | | −0.201 (0.072) | −0.113 (0.074) |
| Log GDP per head | | | 0.139 (0.013) | 0.092 (0.014) | 0.098 (0.019) | 0.077 (0.015) |
| Countries | 28 | 30 | 31 | 28 | 30 | 28 |
| R2 | 0.656 | 0.630 | 0.760 | 0.837 | 0.801 | 0.855 |

Informality survives conditioning on income. Agricultural self-employment does
not survive in the full specification (p = 0.13).

## Robustness

Sample definition:

| | all four | excl. Ethiopia | excl. imputed TZA | excl. both |
|---|---|---|---|---|
| Workers | 23,444 | 22,860 | 18,171 | 17,587 |
| Mean exposure | 0.088 | 0.087 | 0.092 | 0.090 |
| Mean, weighted | 0.107 | 0.106 | 0.112 | 0.111 |
| % agriculture | 58.6 | 59.5 | 46.6 | 47.4 |
| % below 0.05 | 33.7 | 34.6 | 43.5 | 45.0 |
| Agriculture, mean | 0.050 | 0.050 | 0.034 | 0.033 |
| Own-account, mean | 0.133 | 0.133 | 0.133 | 0.133 |
| Wage, mean | 0.152 | 0.152 | 0.152 | 0.152 |

Exposure value assigned to the 5,273 imputed Tanzanian farmers:

| assignment | value | pooled mean |
|---|---|---|
| Agricultural labourers, ISCO 9211 | 0.000 | 0.071 |
| Subsistence codes 6310-6340 | 0.019 | 0.075 |
| Flat major-6 average (baseline) | 0.076 | 0.088 |
| Highest major-6 occupation | 0.102 | 0.094 |
| Excluded altogether | | 0.092 |

Full range 0.071 to 0.094. Three of the four alternatives sit below baseline, so
if anything the baseline overstates exposure.

Measure agreement across the nine major groups: the Althoff augmentation score
ranks occupations at 0.88 against the automation score; the Atlas index at 0.60
(0.44 across ISCO unit groups). Clerical support leads on all three. Agriculture
sits at the floor only on the automation measure.

## Secondary

- Urban 0.130 against rural 0.073; gap +0.057, and +0.049 with country fixed effects.
- Male 0.093 against female 0.083; gap +0.010.
- Wage workers by formality: **formal 0.213** (n = 618) against **informal 0.108**
  (n = 2,076). Formal wage workers are almost twice as exposed. Same direction in
  both countries carrying the question: Tanzania 0.234 against 0.109, Uganda
  0.197 against 0.106.
- Crosswalk: 423 ISCO-08 unit groups matched directly, 126 one-to-one and 297
  one-to-many (median 2, max 35); 243 O*NET occupations shared by more than one
  ISCO group; 7 codes imputed from a parent group (6 three-digit, 1 two-digit).
