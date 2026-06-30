# RESULTS SUMMARY: SSA AI-exposure descriptive paper
*All numbers dual-implemented in R + Python (max abs diff = 0.0). Source: countries/results/desc_*.json, macro_*.json.*

## Sample
- 23,444 workers, 4 LSMS-ISA surveys: Nigeria 2023, Tanzania 2020, Uganda 2019, Ethiopia 2021.
- Per-country n: Ethiopia 2021 584, Nigeria 2023 7,708, Tanzania 2020 7,481, Uganda 2019 7,671

## Headline (the thesis in numbers)
- Mean AI (automation) exposure = 0.088 (median 0.076).
- 33.7% of workers have near-zero exposure (below 0.05).
- 66.1% are in agriculture + elementary occupations.
- Top 10% of workers hold 36% of all exposure mass.

## Table 1: exposure by ISCO major group (pooled)
| Major group | share | mean exposure |
|---|---|---|
| Clerical | 0.7% | 0.605 |
| Technicians | 1.8% | 0.361 |
| Managers | 5.1% | 0.210 |
| Professionals | 4.6% | 0.172 |
| Service/Sales | 12.6% | 0.143 |
| Plant/machine op | 3.6% | 0.143 |
| Skilled agriculture | 54.0% | 0.054 |
| Craft/trades | 5.4% | 0.051 |
| Elementary | 12.1% | 0.030 |

## Table 2: exposure by employment status (pooled)
| Status | share | mean exposure |
|---|---|---|
| other_nonag | 1.9% | 0.163 |
| wage_nonag | 3.5% | 0.142 |
| selfemp_nonag | 36.0% | 0.142 |
| agriculture | 58.6% | 0.050 |

## Table 3: mean exposure by country (micro) vs Atlas macro exposure
| Country | micro mean (Althoff auto) | macro Atlas share-exposed |
|---|---|---|
| Ethiopia 2021 | 0.144 | 0.221 |
| Nigeria 2023 | 0.122 | 0.333 |
| Tanzania 2020 | 0.083 | 0.238 |
| Uganda 2019 | 0.055 | 0.214 |

## Macro augmentation (32 African countries, country-level)
- AI exposure vs informal-employment rate: Spearman -0.74 (n=28).
- vs agricultural self-employment: Spearman -0.75 (n=30).
- vs GDP per capita: Spearman +0.83 (n=31).
- Figure: countries/results/fig_macro_exposure_informality.png

## Secondary / robustness
- Exposure urban 0.095 vs rural 0.087 (gap +0.008); small, so concentration is occupational not geographic.
- Exposure male 0.092 vs female 0.085.
- Informality (wage workers): informal 0.112 vs formal 0.100; formality does NOT add insulation.
