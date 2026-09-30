"""Trace every headline number in paper/body.tex back to the analysis output.

Each entry in `claims` pairs an approved number with the expression that
rebuilds it from the analysis results. The approved side comes from
paper/Revision_results_v2.md, which the author signed off on 2026-09-19; it is
the same set of targets the build scripts assert on. Two checks run:

  1. every approved number must match what the data now produce;
  2. every approved number must appear verbatim in body.tex.

Both checks are strict. --allow-tex-drift downgrades check 2 to a warning,
which is useful only while body.tex is mid-rewrite.

The revision-3 block at the end adds the numbers steps 5, 6, 7 and 15 put in
the paper: the Tanzanian add-back, the composition counterfactual, and the
formality gap across the crosswalk rules and the nine rating versions. Those
trace to the _v3 result files.

Run from countries/, after run_all.py or the v2 analysis scripts.
"""
import argparse
from decimal import ROUND_HALF_UP, Decimal
import glob
import json
import sys

import numpy as np
import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("--allow-tex-drift", action="store_true",
                help="report but do not fail on numbers missing from body.tex (pre-step-13)")
args = ap.parse_args()

res = json.load(open("results/revision_v2_py.json"))
cws = json.load(open("results/crosswalk_sensitivity_v2_py.json"))
des = json.load(open("results/survey_design_v2_py.json"))
add = json.load(open("results/tza_addback_v3_py.json"))
cmp3 = json.load(open("results/composition_cf_v3_py.json"))
alt3 = json.load(open("results/althoff_variants_v3_py.json"))
cws3 = json.load(open("results/crosswalk_sensitivity_v3_py.json"))
rec4 = json.load(open("results/composition_reconcile_v4_py.json"))
fit4 = json.load(open("results/macro_fit_v4_py.json"))
ngo6 = json.load(open("results/ngownuse_v6_py.json"))
assert ngo6 == json.load(open("results/ngownuse_v6_r.json")), "R/Python disagree on Nigeria own-use rule"


def FIT(outcome, term):
    """One term's comparable metrics from macro_fit_v4 (plan review4 step 9)."""
    return fit4["metrics"][outcome]["terms"][term]
sd3 = json.load(open("results/survey_design_v3_py.json"))
ana3 = json.load(open("results/analysis_v3_py.json"))
P = pd.read_csv("harmonized_workers_v2.csv", low_memory=False)
X = pd.read_csv("../crosswalks/isco08_to_exposure.csv")
# the paper writes thousands as 9{,}547 so LaTeX sets the comma tightly;
# normalise that away before looking for a number verbatim.
tex = open("../paper/body.tex", encoding="utf-8").read().replace("{,}", ",")

A = "auto_genai"
ci = res["group_means_ci"]
rob = res["robustness"]
comp = res["country_composition"]
smp = res["sample"]
eth = res["ethiopia_resident"]
x = np.sort(P[A].values)

# occupation-coding coverage, recomputed from the raw labour modules
_d1 = lambda c: pd.to_numeric(c.astype(str).str.extract(r"(\d+)")[0], errors="coerce")
_yes = lambda c: pd.to_numeric(c.astype(str).str.extract(r"(\d)")[0], errors="coerce").eq(1)
_nga = pd.read_csv("../lsms_probe/w5/Post Harvest Wave 5/Household/sect4a_harvestw5.csv",
                   low_memory=False)
# The survey's own derived work-status variable, not a gate assembled here.
# s4aq21: 1 = no work in the last 7 days, 2 = family farm only, 3 = worked.
nga_status = _d1(_nga.s4aq21)
nga_worked = nga_status.eq(3)
nga_absent_ret = _yes(_nga.s4aq24)
nga_coded = _d1(_nga.s4aq40_code).between(1000, 9999)
_uga = pd.read_csv(glob.glob("UGA_2019_UNPS/**/gsec8.csv", recursive=True)[0],
                   encoding="latin-1", low_memory=False)
uga_coded = _d1(_uga.h8q19b_fourDigit).between(1000, 9999)

SC = add["scenarios"]
UG = SC["own|0.000"]["by_country_weighted_design"]["Uganda 2019"]
TZ = lambda k: SC[k]["by_country_weighted_design"]["Tanzania 2020"]
AV = lambda k: cmp3["average_african_country"][k]
VR = lambda k: alt3["variants"][k]["formal_minus_informal"]

# Uganda is untouched by the add-back, so its design interval is the same in
# every scenario. Assert that rather than trusting it.
for _k, _v in SC.items():
    assert _v["by_country_weighted_design"]["Uganda 2019"] == UG, _k

claims = {
    # ---- sample (Revision_results_v2.md section 1) ----
    "pooled N": (24838, smp["n"]),
    "nigeria N": (9547, smp["by_country"]["Nigeria 2023"]),
    "tanzania N": (7620, smp["by_country"]["Tanzania 2020"]),
    "uganda N": (7671, smp["by_country"]["Uganda 2019"]),
    "coded 4-digit": (17720, smp["coded_4digit"]),
    "coded 4-digit pct": (71.3, round(100 * P.isco08.notna().mean(), 1)),
    "own-use family-use farmers": (6372, smp["by_reason"]["own_use_farmer_family_use"]),
    "tza market farmers": (740, smp["by_reason"]["own_use_farmer_market_oriented"]),
    "tasco mapped": (139, smp["by_reason"]["tasco_map_direct"] + smp["by_reason"]["tasco_map_submajor"]),
    "own-use excluded N": (18466, rob["own_use_excluded"]["n"]),
    "eth out-migrant N": (584, len(pd.read_csv("harmonized_workers_v2_eth_outmigrant.csv"))),
    "eth resident N": (1989, eth["n"]),

    # ---- headline means (section 2) ----
    "pooled mean": (0.072, round(P[A].mean(), 3)),
    "pooled weighted mean": (0.090, round(ci["pooled_weighted"]["mean"], 3)),
    "pooled mean lo": (0.070, ci["pooled"]["lo"]),
    "pooled mean hi": (0.073, ci["pooled"]["hi"]),
    "equal-country mean": (0.073, round(res["pooled_equal_country_mean"], 3)),
    "nigeria mean": (0.102, round(comp["Nigeria 2023"]["mean_unw"], 3)),
    "tanzania mean": (0.050, round(comp["Tanzania 2020"]["mean_unw"], 3)),
    "uganda mean": (0.055, round(comp["Uganda 2019"]["mean_unw"], 3)),
    "nigeria weighted mean": (0.107, round(comp["Nigeria 2023"]["mean_wtd"], 3)),
    "tanzania weighted mean": (0.044, round(comp["Tanzania 2020"]["mean_wtd"], 3)),
    "uganda weighted mean": (0.068, round(comp["Uganda 2019"]["mean_wtd"], 3)),
    "share below 0.05": (57.5, round(100 * (P[A] < 0.05).mean(), 1)),
    "share major 6 or 9": (68.5, round(100 * P.major.isin([6, 9]).mean(), 1)),
    "top decile share": (43, round(100 * x[int(0.9 * len(x)):].sum() / x.sum())),

    # ---- group means (sections 2 and 3) ----
    "agriculture mean": (0.029, ci["status_agriculture"]["mean"]),
    "own-account mean": (0.134, round(ci["status_selfemp_nonag"]["mean"], 3)),
    "wage mean": (0.150, round(ci["status_wage_nonag"]["mean"], 3)),
    "agriculture n": (15441, ci["status_agriculture"]["n"]),
    "clerical mean": (0.615, round(ci["major_4"]["mean"], 3)),
    "clerical lo": (0.590, des["group_means_ci"]["major_4"]["lo"]),
    "clerical hi": (0.639, des["group_means_ci"]["major_4"]["hi"]),
    "clerical share": (0.6, round(100 * (P.major == 4).mean(), 1)),
    "skilled agri mean": (0.031, ci["major_6"]["mean"]),
    "skilled agri share": (57.8, round(100 * (P.major == 6).mean(), 1)),
    "technicians mean": (0.363, round(ci["major_3"]["mean"], 3)),
    "professionals mean": (0.161, round(ci["major_2"]["mean"], 3)),
    "elementary mean": (0.028, ci["major_9"]["mean"]),
    "urban mean": (0.120, round(ci["urban"]["mean"], 3)),
    "rural mean": (0.055, round(ci["rural"]["mean"], 3)),
    "male mean": (0.077, round(ci["male"]["mean"], 3)),
    "female mean": (0.066, round(ci["female"]["mean"], 3)),
    "wage share": (17.2, comp["All (pooled)"]["wage_unw"]),
    "pooled agri share": (62.2, comp["All (pooled)"]["agri_unw"]),
    "weighted agri share": (48.6, comp["All (pooled)"]["agri_wtd"]),

    # ---- formality (sections 2 and 4) ----
    "formal wage mean": (0.213, round(ci["wage_formal"]["mean"], 3)),
    "informal wage mean": (0.104, round(ci["wage_informal"]["mean"], 3)),
    "formal wage n": (1801, ci["wage_formal"]["n"]),
    "formality sample": (4267, ci["wage_formal"]["n"] + ci["wage_informal"]["n"]),

    # ---- direct tests (section 3) ----
    "wage minus own-account": (0.016, res["tests"]["wage_vs_self_nonag"]["wage_d"]["b"]),
    "wage minus own-account with FE": (0.033, round(res["tests"]["wage_vs_self_nonag_cfe"]["wage_d"]["b"], 3)),
    "informal coef": (-0.110, round(res["tests"]["informal_vs_formal"]["infd"]["b"], 3)),
    "informal coef with FE": (-0.102, round(res["tests"]["informal_vs_formal_cfe"]["infd"]["b"], 3)),
    "female coef": (-0.011, round(res["tests"]["female"]["fem"]["b"], 3)),

    # ---- robustness (section 5) ----
    "own-use excluded mean": (0.090, round(rob["own_use_excluded"]["mean"], 3)),
    "coded-only n": (17726, rob["coded_only"]["n"]),
    "coded-only mean": (0.090, round(rob["coded_only"]["mean"], 3)),
    "drop tasco mean": (0.071, round(rob["drop_tasco_mapped"]["mean"], 3)),

    # ---- Ethiopia supplement (section 6) ----
    "eth resident mean": (0.216, round(eth["mean_unw"], 3)),
    "eth resident formal mean": (0.267, round(eth["ci_formal"]["mean"], 3)),
    "eth resident informal mean": (0.129, round(eth["ci_informal"]["mean"], 3)),

    # ---- crosswalk sensitivity (section 11) ----
    "crosswalk emp-weighted pooled wtd": (0.080, round(cws["emp_weighted"]["pooled_wtd"], 3)),
    "crosswalk median pooled wtd": (0.089, round(cws["median"]["pooled_wtd"], 3)),
    "crosswalk min pooled wtd": (0.058, round(cws["min"]["pooled_wtd"], 3)),
    "crosswalk max pooled wtd": (0.126, round(cws["max"]["pooled_wtd"], 3)),
    "crosswalk draws wage above self, pct": (99.3, round(100 * cws["draws_share_wage_above_self"], 1)),

    # ---- crosswalk coverage quoted in the data section ----
    "clerical min code": (0.149, round(X[(X.isco08 // 1000) == 4].auto_genai.min(), 3)),
    "clerical max code": (0.858, round(X[(X.isco08 // 1000) == 4].auto_genai.max(), 3)),
    "nga worked last 7 days (s4aq21=3)": (7656, int(nga_worked.sum())),
    "nga coded among those who worked": (7591, int((nga_worked & nga_coded).sum())),
    "nga worked but uncoded": (65, int((nga_worked & ~nga_coded).sum())),
    "nga coded but absent (s4aq21=1)": (117, int((nga_status.eq(1) & nga_coded).sum())),
    "nga absent returning within 3 months": (115, int((nga_status.eq(1) & nga_coded & nga_absent_ret).sum())),
    "nga family-farm only (s4aq21=2)": (1839, int(nga_status.eq(2).sum())),
    "uga coded": (7671, int(uga_coded.sum())),

    # ---- Tanzanian add-back, plan step 5 (Section 5) ----
    "addback n": (1789, add["n_1789"]),
    "addback own weight mean": (2628, round(add["own_weight_mean_among_1789"])),
    "addback tza mean weight": (2736, round(add["mean_tza_weight_placeholder"])),
    "addback score agri": (0.029, round(add["flat_scores"]["0.029_agri"], 3)),
    "addback score selfnonag": (0.128, round(add["flat_scores"]["0.128_selfnonag"], 3)),
    "addback score wagenonag": (0.169, round(add["flat_scores"]["0.169_wagenonag"], 3)),
    "addback industry linked n": (1555, add["industry_link"]["n_section_matched"]),
    "addback industry link rate": (87.1, add["industry_link"]["link_rate_pct"]),
    "addback industry implied score": (0.162, round(add["industry_link"]["implied_mean_unweighted"], 3)),
    "addback pooled wtd at zero": (0.087, round(SC["own|0.000"]["pooled_mean_weighted_point"], 3)),
    "addback pooled wtd at agri": (0.088, round(SC["own|0.029_agri"]["pooled_mean_weighted_point"], 3)),
    "addback pooled wtd at selfnonag": (0.092, round(SC["own|0.128_selfnonag"]["pooled_mean_weighted_point"], 3)),
    "addback pooled wtd at wagenonag": (0.093, round(SC["own|0.169_wagenonag"]["pooled_mean_weighted_point"], 3)),
    "addback pooled wtd industry": (0.093, round(SC["own|industry"]["pooled_mean_weighted_point"], 3)),
    "addback tza wtd at zero": (0.036, round(TZ("own|0.000")["mean"], 3)),
    "addback tza wtd at agri": (0.041, round(TZ("own|0.029_agri")["mean"], 3)),
    "addback tza wtd at selfnonag": (0.059, round(TZ("own|0.128_selfnonag")["mean"], 3)),
    "addback tza wtd at wagenonag": (0.067, round(TZ("own|0.169_wagenonag")["mean"], 3)),
    "addback tza wtd industry": (0.065, round(TZ("own|industry")["mean"], 3)),
    "addback tza lo at zero": (0.033, round(TZ("own|0.000")["lo"], 3)),
    "addback tza hi at zero": (0.038, round(TZ("own|0.000")["hi"], 3)),
    "addback tza lo at wagenonag": (0.063, round(TZ("own|0.169_wagenonag")["lo"], 3)),
    "addback tza hi at wagenonag": (0.070, round(TZ("own|0.169_wagenonag")["hi"], 3)),
    "addback margin at zero": (0.033, round(SC["own|0.000"]["margin_uga_minus_tza"], 3)),
    "addback margin at wagenonag": (0.001, round(SC["own|0.169_wagenonag"]["margin_uga_minus_tza"], 3)),
    "addback uga wtd": (0.068, round(UG["mean"], 3)),
    "addback uga lo": (0.063, round(UG["lo"], 3)),
    "addback uga hi": (0.073, round(UG["hi"], 3)),

    # ---- composition counterfactual, plan step 6 (Section 6) ----
    "cf these economies, survey scores": (0.080, round(cmp3["these_economies"]["exp_lsms"]["pooled_actual_ilostat"], 3)),
    "cf these economies, crosswalk scores": (0.113, round(cmp3["these_economies"]["exp_unit"]["pooled_actual_ilostat"], 3)),
    "cf these economies, own-use out": (0.088, round(cmp3["these_economies"]["exp_lsms_ex"]["pooled_actual_ilostat"], 3)),
    "cf average african, survey scores": (0.098, round(AV("GBR|exp_lsms")["avg_african_actual"], 3)),
    "cf average african, crosswalk scores": (0.133, round(AV("GBR|exp_unit")["avg_african_actual"], 3)),
    "cf average african, own-use out": (0.104, round(AV("GBR|exp_lsms_ex")["avg_african_actual"], 3)),
    "cf gbr, survey scores": (0.208, round(cmp3["cf"]["GBR|exp_lsms"], 3)),
    "cf deu, survey scores": (0.227, round(cmp3["cf"]["DEU|exp_lsms"], 3)),
    "cf fra, survey scores": (0.203, round(cmp3["cf"]["FRA|exp_lsms"], 3)),
    "cf gbr, crosswalk scores": (0.261, round(cmp3["cf"]["GBR|exp_unit"], 3)),
    "cf deu, crosswalk scores": (0.256, round(cmp3["cf"]["DEU|exp_unit"], 3)),
    "cf fra, crosswalk scores": (0.242, round(cmp3["cf"]["FRA|exp_unit"], 3)),
    "cf gap, average african": (0.111, round(AV("GBR|exp_lsms")["gap"], 3)),
    "cf groups 1-4 contribution": (0.133, round(sum(AV("GBR|exp_lsms")["by_group"][str(j)] for j in range(1, 5)), 3)),
    "cf group 6 contribution": (0.014, abs(round(AV("GBR|exp_lsms")["by_group"]["6"], 3))),
    "cf n african countries": (45, cmp3["n_african_countries"]),

    # ---- formality gap across the nine versions, plan steps 7 and 15 ----
    "variant formal-informal min": (0.067, round(alt3["formal_minus_informal_min"], 3)),
    "variant formal-informal max": (0.155, round(alt3["formal_minus_informal_max"], 3)),
    "variant gap, headline": (0.109, round(VR("canonical_moderate_qwen"), 3)),
    "variant gap, moderate gpt-oss": (0.074, round(VR("moderate_gptoss"), 3)),
    "variant gap, slow qwen": (0.081, round(VR("slow_qwen"), 3)),
    "variant gap, slow gpt-oss": (0.094, round(VR("slow_gptoss"), 3)),
    "variant gap, rapid gpt-oss": (0.143, round(VR("rapid_gptoss"), 3)),
    "variant gap, gpt-4o": (0.086, round(VR("no_explicit_scenario_gpt4o"), 3)),

    # ---- formality gap across the crosswalk rules, plan steps 7 and 15 ----
    "crosswalk formal, emp weighted": (0.206, round(cws3["emp_weighted"]["wage_formal"], 3)),
    "crosswalk formal, median": (0.211, round(cws3["median"]["wage_formal"], 3)),
    "crosswalk formal, min": (0.160, round(cws3["min"]["wage_formal"], 3)),
    "crosswalk formal, max": (0.275, round(cws3["max"]["wage_formal"], 3)),
    "crosswalk informal, emp weighted": (0.102, round(cws3["emp_weighted"]["wage_informal"], 3)),
    "crosswalk informal, median": (0.098, round(cws3["median"]["wage_informal"], 3)),
    "crosswalk informal, min": (0.066, round(cws3["min"]["wage_informal"], 3)),
    "crosswalk gap, headline": (0.109, round(cws3["mean"]["wage_formal"] - cws3["mean"]["wage_informal"], 3)),
    "crosswalk gap, min": (0.094, round(cws3["min"]["formal_minus_informal"], 3)),
    "crosswalk gap, max": (0.120, round(cws3["max"]["formal_minus_informal"], 3)),
    "crosswalk gap, draws lo": (0.096, round(cws3["draws"]["formal_minus_informal"]["p025"], 3)),
    "crosswalk gap, draws hi": (0.124, round(cws3["draws"]["formal_minus_informal"]["p975"], 3)),

    # ---- the 0.080/0.090 reconciliation, plan review4 step 8 (Section 6) ----
    # NOTE: "crosswalk pooled, emp weighted" above is a DIFFERENT 0.080. Two
    # unrelated quantities in this paper round to 0.080. Do not fuse them.
    "reconcile manager share ilostat": (0.7, rec4["manager_share_ilostat_pct"]),
    "reconcile manager share lsms": (8.2, rec4["manager_share_lsms_pct"]),
    "reconcile service share ilostat": (23.3, rec4["service_share_ilostat_pct"]),
    "reconcile service share lsms": (15.8, rec4["service_share_lsms_pct"]),
    "reconcile manager term": (0.015, abs(round(rec4["manager_term"], 3))),
    "reconcile service term": (0.009, round(rec4["service_term"], 3)),
    "reconcile difference": (0.011, abs(round(rec4["difference"], 3))),
    "reconcile major1 workers": (1202, rec4["major1_n"]),
    "reconcile major1 own-account pct": (89, round(rec4["major1_selfemp_nonag_pct"])),
    "reconcile major1 top isco pct": (72, round(rec4["major1_top_isco_pct"])),

    # ---- comparable predictor metrics, plan review4 step 9 (Appendix) ----
    "fit ilostat agri std coef": (0.492, abs(FIT("exp_lsms", "agri_s")["beta_std"])),
    "fit ilostat informal std coef": (0.182, abs(FIT("exp_lsms", "informal_s")["beta_std"])),
    "fit ilostat income std coef": (0.301, FIT("exp_lsms", "lgdp")["beta_std"]),
    "fit atlas informal std coef": (0.401, abs(FIT("ai_route_share", "informal_s")["beta_std"])),
    "fit atlas agri std coef": (0.240, abs(FIT("ai_route_share", "agri_s")["beta_std"])),
    "fit atlas income std coef": (0.406, FIT("ai_route_share", "lgdp")["beta_std"]),
    "fit ilostat agri incr r2": (0.124, FIT("exp_lsms", "agri_s")["incremental_r2"]),
    "fit ilostat informal incr r2": (0.018, FIT("exp_lsms", "informal_s")["incremental_r2"]),
    "fit ilostat income incr r2": (0.043, FIT("exp_lsms", "lgdp")["incremental_r2"]),
    "fit atlas informal incr r2": (0.085, FIT("ai_route_share", "informal_s")["incremental_r2"]),
    "fit atlas agri incr r2": (0.030, FIT("ai_route_share", "agri_s")["incremental_r2"]),
    "fit atlas income incr r2": (0.077, FIT("ai_route_share", "lgdp")["incremental_r2"]),
    "fit ilostat full r2": (0.740, fit4["metrics"]["exp_lsms"]["r2_full"]),
    "fit atlas full r2": (0.837, fit4["metrics"]["ai_route_share"]["r2_full"]),
    "fit common sample": (27, fit4["n_common"]),

    # ---- review 5: own-use-out column becomes the composition headline ----
    # the JSON stores 0.2085 (four decimals), and round() takes that to 0.208.
    # The unrounded value is 0.208528 (composition_cf_v3.py re-run from the
    # scratchpad, 2026-09-23), so the paper's 0.209 is right. Round half up.
    "r5 cf gbr, own-use out": (0.209, float(Decimal(str(cmp3["cf"]["GBR|exp_lsms_ex"])).quantize(Decimal("0.001"), ROUND_HALF_UP))),
    "r5 cf groups 1-4, own-use out": (0.133, round(sum(AV("GBR|exp_lsms_ex")["by_group"][str(j)] for j in range(1, 5)), 3)),
    "r5 cf group 6, own-use out": (0.021, abs(round(AV("GBR|exp_lsms_ex")["by_group"]["6"], 3))),
    # ---- review 5: weighted column (2) of tab:reg, quoted in its note ----
    # NOTE: a THIRD unrelated 0.080. This one is a regression coefficient, not
    # the composition baseline or the crosswalk pooled mean. Do not fuse them.
    "r5 reg m2 weighted, own-account": (0.080, round(des["status_reg"]["m2_wtd"]["self_d"]["b"], 3)),
    "r5 reg m2 weighted, own-account se": (0.003, round(des["status_reg"]["m2_wtd"]["self_d"]["se"], 3)),
    "r5 reg m2 weighted, wage": (0.129, round(des["status_reg"]["m2_wtd"]["wage_d"]["b"], 3)),
    "r5 reg m2 weighted, wage se": (0.006, round(des["status_reg"]["m2_wtd"]["wage_d"]["se"], 3)),
    # ---- review 5: tab:country figures now quoted in the Tanzania paragraph ----
    "r5 uga survey wtd": (0.068, round(UG["mean"], 3)),
    # ---- review 5, point 1: hh_e09 codes 1-2 (only/mainly for sale) ----
    "r5 tza market-oriented farmers": (740, smp["by_reason"]["own_use_farmer_market_oriented"]),
    # ---- review 6, point 1: the residual below the four-digit code ----
    "r6 not four-digit coded": (7118, smp["n"] - smp["coded_4digit"]),
    "r6 not four-digit, submajor TASCO": (6, smp["by_reason"]["tasco_map_submajor"]),
    "r6 farmers without a coded occupation": (7112, smp["by_reason"]["own_use_farmer_family_use"]
                                              + smp["by_reason"]["own_use_farmer_market_oriented"]),
    # ---- review 6, point 2: Nigeria's own-use rule (nigeria_ownuse_rule_v6) ----
    "r6 nga sells nothing": (985, ngo6["only_household_total"]),
    "r6 nga keeps most": (854, ngo6["mainly_household_total"]),
    "r6 nga usual-work route": (24, ngo6["usual_only_household"] + ngo6["usual_mainly_household"]),
}

# the revision-3 claims above read these through short helpers, so the table
# stays one line per number.
bad = []
for k, (paper, data) in claims.items():
    if abs(float(paper) - float(data)) > 1e-6 + 0.0005 * max(1, abs(float(paper))):
        bad.append((k, paper, data))

print(f"checked {len(claims)} approved numbers against the analysis output")
for k, p, d in bad:
    print(f"  MISMATCH {k:36s} approved={p} data={d}")


def forms(v):
    """The paper writes counts with thousands separators (24,838), so try that too."""
    out = {str(v).lstrip("-"), f"{v:g}".lstrip("-")}
    if float(v) == int(float(v)):
        out.add(f"{abs(int(float(v))):,}")
    return out


# review 5 moved the group decomposition in Section 6 to the own-use-out
# column, so these full-sample figures left the text. They are still checked
# against the data above.
RETIRED_FROM_TEX = {"cf group 6 contribution"}
missing_in_tex = [k for k, (p, _) in claims.items()
                  if k not in RETIRED_FROM_TEX and not any(f in tex for f in forms(p))]
if missing_in_tex:
    print(f"\n{len(missing_in_tex)} approved number(s) not found verbatim in body.tex:")
    print("  " + ", ".join(missing_in_tex))

if bad:
    sys.exit(1)
if missing_in_tex and not args.allow_tex_drift:
    sys.exit(1)
if missing_in_tex:
    print("\n--allow-tex-drift: body.tex still holds the pre-revision text (plan step 13).")
print("every approved number traces to the analysis output.")
