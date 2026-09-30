"""The Tanzanian add-back (plan review3, step 5). The referee's central worry
was that the headline pooled mean is fragile to the 1,789 Tanzanian non-farm
business owners the survey asks no occupation question of. The verification
found the real casualty is not the pooled mean but the country ordering:
Uganda's weighted mean (0.068) sits close enough to Tanzania's (0.044) that a
generous imputation for the 1,789 can put Tanzania at or above Uganda. This
script puts the 1,789 back in the denominator under a range of imputed scores
and reports design-based intervals so that comparison is honest.

Does not touch harmonized_workers_v2.csv or any v2 result. All add-back rows
are held in memory / a new v3 CSV; the headline sample (24,838) is untouched
(decision D5).

Construction, in order (see Revision_plan_review3.md step 5 for the numbered
list this follows):
  1. Rebuild the 1,789 from hh_sec_e1.csv: hh_e05 == yes (non-farm business)
     and hh_e03 != yes (no wage job), the same rule as
     build_harmonized_v2.py:256.
  2. Attach weights: own y5_crossweight (decision D1, the recommended route)
     and, as a second scenario, the mean Tanzanian worker weight (the sizing
     run's placeholder).
  3. Flat imputation at four scores, read off the existing v2/v3 results so
     they are not retyped: 0.000, the unweighted agriculture status mean
     (~0.029), the weighted own-account mean, which is exactly the Nigeria +
     Uganda figure because Tanzania has no non-farm own-account workers under
     the existing rule (~0.128), and the weighted non-agricultural wage mean
     (~0.169).
  4. Industry imputation: link each of the 1,789 to an enterprise in the same
     household (hh_sec_n.csv) by owner, then manager, then engaged-member id,
     lowest enterprise_id on a tie; read the ISIC section (hh_n02_3a); donor
     is Uganda's non-agricultural own-account workers (status selfemp_nonag),
     whose industry section comes from gsec8's h8q20b_oneDigit (which turns
     out to carry the same 1-21 ISIC-section numbering as Tanzania's
     hh_n02_3a: dividing by 10,000 recovers the section number exactly).
     Unmatched sections or unlinked people fall back to the donor's own
     overall weighted mean.
  5. Design-based intervals on every scenario's country and pooled means,
     using the same Taylor-linearized design as survey_design_v2/v3. The
     1,789 sit in already-sampled Tanzanian households, so their strata and
     PSUs are rebuilt fresh from hh_sec_a.csv here (the same rule
     survey_design_v2.py uses) rather than assumed from the existing design
     id file, so coverage cannot silently fail for a household with no other
     worker in the file.
  6. Outputs per scenario, keyed `{weight_scenario}|{score_key}`.

Writes results/tza_addback_v3_py.json and
harmonized_workers_v3_tza_addback.csv (the 1,789 rows alone, one column per
scenario score, for inspection; not read by any other script).
"""
import json

import numpy as np
import pandas as pd

A = "auto_genai"


def num(s):
    return pd.to_numeric(s.astype(str).str.extract(r"(\d+\.?\d*)")[0], errors="coerce")


def Y(s):
    return pd.to_numeric(s.astype(str).str.extract(r"(\d)")[0], errors="coerce").eq(1)


# ============================================================ 1. rebuild the 1,789
e = pd.read_csv("TZA_2020_NPS-R5/hh_sec_e1.csv", low_memory=False)
nonfarm_biz = Y(e["hh_e05"]) & ~Y(e["hh_e03"])
n1789 = int(nonfarm_biz.sum())
assert n1789 == 1789, f"expected 1,789 non-farm business owners with no wage job, got {n1789}"
AB = e.loc[nonfarm_biz, ["y5_hhid", "indidy5"]].reset_index(drop=True)
AB["indidy5"] = pd.to_numeric(AB.indidy5, errors="coerce")

# ============================================================ 2. weights (D1)
a = pd.read_csv("TZA_2020_NPS-R5/hh_sec_a.csv", low_memory=False)
au = a[["y5_hhid", "y5_rural", "y5_crossweight", "clusterid", "strataid", "tracking_class", "y5_cluster"]].dropna(
    subset=["y5_hhid"]).drop_duplicates("y5_hhid")
AB = AB.merge(au, on="y5_hhid", how="left")
assert AB.y5_crossweight.notna().all(), "an add-back row has no household weight"

P = pd.read_csv("harmonized_workers_v2.csv", low_memory=False)
TZA_P = P[P.country == "Tanzania 2020"]
mean_tza_weight = float(TZA_P.weight.sum() / len(TZA_P))
print(f"mean Tanzanian worker weight (placeholder scenario) = {mean_tza_weight:.2f}")
print(f"own-weight mean among the 1,789 = {AB.y5_crossweight.mean():.2f}")

WEIGHT_SCENARIOS = {"own": AB.y5_crossweight.to_numpy(float),
                    "mean_placeholder": np.full(len(AB), mean_tza_weight)}

# ============================================================ 3. flat imputation scores
ag_unw = float(P[P.status == "agriculture"][A].mean())
selfnonag = P[P.status == "selfemp_nonag"]
selfnonag_wtd = float(np.average(selfnonag[A], weights=selfnonag.weight))
wagenonag = P[P.status == "wage_nonag"]
wagenonag_wtd = float(np.average(wagenonag[A], weights=wagenonag.weight))
assert (P[P.country == "Tanzania 2020"].status == "selfemp_nonag").sum() == 0, \
    "Tanzania now has non-farm own-account workers; the 0.128 score is no longer NGA+UGA only"
print(f"flat scores: 0.000, agri_unw={ag_unw:.4f}, selfnonag_wtd={selfnonag_wtd:.4f}, wagenonag_wtd={wagenonag_wtd:.4f}")

FLAT_SCORES = {"0.000": 0.0, "0.029_agri": round(ag_unw, 4),
               "0.128_selfnonag": round(selfnonag_wtd, 4), "0.169_wagenonag": round(wagenonag_wtd, 4)}

# ============================================================ 4. industry imputation (D2)
n_ent = pd.read_csv("TZA_2020_NPS-R5/hh_sec_n.csv", low_memory=False)
n_ent = n_ent[n_ent.hh_n02_3a.notna()].copy()
n_ent["enterprise_id"] = pd.to_numeric(n_ent.enterprise_id, errors="coerce")
owner_cols = ["hh_n05_1", "hh_n05_2"]
mgr_cols = ["hh_n04a", "hh_n04b"]
eng_cols = [f"hh_n03_{i}" for i in range(1, 7)]
grp = {k: g for k, g in n_ent.groupby("y5_hhid")}

link_tier = []
link_section = []
tier_counts = {"owner": 0, "manager": 0, "engaged": 0, "none": 0}
for hh, pid in zip(AB.y5_hhid, AB.indidy5):
    cand = grp.get(hh)
    found_tier, found_sec = "none", np.nan
    if cand is not None:
        for cols, name in [(owner_cols, "owner"), (mgr_cols, "manager"), (eng_cols, "engaged")]:
            hit = cand[cand[cols].eq(pid).any(axis=1)]
            if not hit.empty:
                eid = hit.enterprise_id.min()
                found_sec = hit.loc[hit.enterprise_id == eid, "hh_n02_3a"].iloc[0]
                found_tier = name
                break
    link_tier.append(found_tier)
    link_section.append(found_sec)
    tier_counts[found_tier] += 1

AB["link_tier"] = link_tier
AB["section"] = link_section
link_rate = 100 * (1 - tier_counts["none"] / len(AB))
print(f"industry link: {tier_counts}, link rate = {link_rate:.1f}%")
assert link_rate >= 60, f"industry link rate {link_rate:.1f}% is below the 60% gate; route becomes a footnote"

# donor: Ugandan non-agricultural own-account workers, section from gsec8's h8q20b_oneDigit
X = pd.read_csv("../crosswalks/isco08_to_exposure.csv")
import glob
g8 = pd.read_csv(glob.glob("UGA_2019_UNPS/**/gsec8.csv", recursive=True)[0], encoding="latin-1", low_memory=False)
iso = num(g8["h8q19b_fourDigit"])
dU = pd.DataFrame({"ix": np.arange(len(g8)), "isco08": iso})
dU = dU[(dU.isco08 >= 1000) & (dU.isco08 <= 9999)]
dU = dU.merge(X, on="isco08", how="left")
ugawage = num(g8["s8q22"]).eq(1)
baseU = pd.DataFrame({"ix": np.arange(len(g8)), "wage": ugawage, "self": ~ugawage,
                      "section": (num(g8["h8q20b_oneDigit"]) // 10000), "hhid": g8.hhid})
dU = dU.merge(baseU, on="ix")
g1u = pd.read_csv("UGA_2019_UNPS/UGA_2019_UNPS_v03_M_CSV/HH/gsec1.csv", encoding="latin-1", low_memory=False)
g1u = g1u[["hhid", "wgt"]].dropna(subset=["hhid"]).drop_duplicates("hhid")
dU = dU.merge(g1u, on="hhid", how="left")


def mkstatus(isco, wage, self_):
    iso = pd.to_numeric(isco, errors="coerce")
    agri = iso.floordiv(1000).eq(6) | iso.floordiv(10).isin([921])
    return np.where(agri, "agriculture", np.where(wage.fillna(False), "wage_nonag",
                    np.where(self_.fillna(False), "selfemp_nonag", "other_nonag")))


dU["status"] = mkstatus(dU.isco08, dU.wage, dU["self"])
donor = dU[dU.status == "selfemp_nonag"]
assert donor.section.notna().all(), "a Ugandan own-account worker has no industry section"
donor_overall = float(np.average(donor[A], weights=donor.wgt))
donor_by_section = donor.groupby("section").apply(
    lambda g: pd.Series({"n": len(g), "wmean": np.average(g[A], weights=g.wgt)}), include_groups=False)
print(f"donor pooled weighted mean (fallback) = {donor_overall:.4f}")
print(donor_by_section)

sec_map = donor_by_section["wmean"].to_dict()
AB["industry_score"] = AB.section.map(sec_map)
n_section_matched = AB.industry_score.notna().sum()
AB["industry_score"] = AB.industry_score.fillna(donor_overall)
print(f"industry route: {n_section_matched} of {len(AB)} matched to a donor section "
      f"({100 * n_section_matched / len(AB):.1f}%); rest fall back to the donor overall mean")
for lo, hi, label in [(0, min(FLAT_SCORES.values()), "below range")]:
    pass
implied_mean = float(AB.industry_score.mean())
flat_lo, flat_hi = min(FLAT_SCORES.values()), max(FLAT_SCORES.values())
assert flat_lo <= implied_mean <= flat_hi, \
    f"industry route implied mean {implied_mean:.4f} sits outside the flat range [{flat_lo:.4f}, {flat_hi:.4f}]"
print(f"industry route implied mean (unweighted over the 1,789) = {implied_mean:.4f}, "
      f"inside the flat range [{flat_lo:.4f}, {flat_hi:.4f}]")

# ============================================================ 5. design ids
# Rebuilt independently from hh_sec_a for full coverage (see module docstring).
ng = pd.read_csv("../lsms_probe/w5/Post Harvest Wave 5/Household/secta_harvestw5.csv", low_memory=False)
ng = pd.DataFrame({"hhid_c": "NGA" + ng.hhid.astype(str), "stratum": "NGA-" + ng.strata.astype(int).astype(str),
                   "psu": "NGA-" + ng.cluster.astype(str)})

boost = (a.tracking_class == 6).to_numpy()
assert (boost == a.clusterid.isna().to_numpy()).all() and (boost == a.strataid.isna().to_numpy()).all()
tzids = pd.DataFrame({"hhid_c": "TZA" + a.y5_hhid.astype(str),
                      "stratum": "TZA-" + np.where(boost, "booster-" + a.y5_cluster.str[:2],
                                                   a.strataid.astype("Int64").astype(str)),
                      "psu": "TZA-" + np.where(boost, a.y5_cluster, a.clusterid.astype("Int64").astype(str))})

ug = pd.read_csv("UGA_2019_UNPS/UGA_2019_UNPS_v03_M_CSV/HH/gsec1.csv", low_memory=False)
parts = ["dc_2018", "cc_2018", "sc_2018", "pc_2018"]
has_par = ug[parts].notna().all(axis=1)
rural = {1: "central_rural", 2: "eastern_rural", 3: "northern_rural", 4: "western_rural"}
ug_str = np.where(ug.district.astype(str).str.upper() == "KAMPALA", "kampala",
                  np.where(ug.urban == 1, "other_urban", ug.region.map(rural).astype(object)))
ug_str = np.where(has_par, ug_str, "no_location")
ug_psu = np.where(has_par, ug[parts].fillna(0).astype(int).astype(str).agg("-".join, axis=1),
                  "hh-" + ug.hhid.astype(str))
ug = pd.DataFrame({"hhid_c": "UGA" + ug.hhid.astype(str), "stratum": "UGA-" + pd.Series(ug_str).astype(str),
                   "psu": "UGA-" + pd.Series(ug_psu)})

IDS = pd.concat([ng, tzids, ug], ignore_index=True)
assert IDS.hhid_c.is_unique
IDS["psu"] = IDS.stratum + "|" + IDS.psu
IDS["stratum"] = IDS.stratum.replace({"TZA-7": "TZA-8"})

AB["hhid_c"] = "TZA" + AB.y5_hhid.astype(str)
AB = AB.merge(IDS[["hhid_c", "stratum", "psu"]], on="hhid_c", how="left")
assert AB.stratum.notna().all() and AB.psu.notna().all(), "an add-back row has no design id"

P = P.merge(IDS[["hhid_c", "stratum", "psu"]], on="hhid_c", how="left", validate="many_to_one")
assert P.stratum.notna().all() and P.psu.notna().all(), "a headline worker has no design id"


class Design:
    def __init__(self, d):
        self.d = d.reset_index(drop=True)
        self.psu_codes, psu_names = pd.factorize(self.d.psu)
        s = self.d.groupby("psu").stratum.first().reindex(psu_names)
        self.psu_stratum = pd.factorize(s)[0]
        self.n_h = np.bincount(self.psu_stratum)

    def var(self, Z):
        Z = np.asarray(Z, float).reshape(len(self.d), -1)
        T = np.zeros((self.psu_codes.max() + 1, Z.shape[1]))
        np.add.at(T, self.psu_codes, Z)
        V = np.zeros((Z.shape[1], Z.shape[1]))
        for h, n in enumerate(self.n_h):
            Th = T[self.psu_stratum == h]
            Dh = Th - Th.mean(axis=0)
            V += n / (n - 1) * Dh.T @ Dh
        return V

    def weights(self, w):
        return np.ones(len(self.d)) if w is None else self.d[w].to_numpy(float)

    def mean(self, dom, col=A, w=None):
        y = self.d[col].to_numpy(float)
        dom = np.asarray(dom, bool) & np.isfinite(y)
        wt = self.weights(w) * dom
        s = wt.sum()
        m = float((wt * np.where(dom, y, 0)).sum() / s)
        z = wt * np.where(dom, y - m, 0) / s
        se = float(np.sqrt(self.var(z)[0, 0]))
        return dict(mean=round(m, 4), se=round(se, 4), lo=round(m - 1.96 * se, 4),
                    hi=round(m + 1.96 * se, 4), n=int(dom.sum()))


UGANDA_WTD = None  # filled below from scenario "own"/"0.000" design (unaffected by add-back)


def run_scenario(weight_col_values, score_values, label):
    ab = AB.copy()
    ab[A] = score_values
    ab["weight"] = weight_col_values
    ab["country"] = "Tanzania 2020"
    combined = pd.concat([P[["country", "stratum", "psu", "weight", A]],
                          ab[["country", "stratum", "psu", "weight", A]]], ignore_index=True)
    D = Design(combined)
    d = D.d
    countries = sorted(d.country.unique())
    yes = np.ones(len(d), bool)
    pooled_unw = round(float(d[A].mean()), 4)
    pooled_wtd_point = round(float(np.average(d[A], weights=d.weight)), 4)
    by_country = {c: D.mean(d.country == c, w="weight") for c in countries}
    pooled_design = D.mean(yes, w="weight")
    tza = by_country["Tanzania 2020"]
    uga = by_country["Uganda 2019"]
    order_holds = uga["mean"] > tza["mean"]
    overlap = not (tza["hi"] < uga["lo"] or uga["hi"] < tza["lo"])
    return dict(n_pooled=int(len(d)), n_tanzania=int((d.country == "Tanzania 2020").sum()),
                pooled_mean_unweighted=pooled_unw, pooled_mean_weighted_point=pooled_wtd_point,
                pooled_weighted_design=pooled_design, by_country_weighted_design=by_country,
                order_nga_uga_tza_holds=bool(order_holds),
                margin_uga_minus_tza=round(uga["mean"] - tza["mean"], 4),
                intervals_overlap=bool(overlap))


results = {}
for wscn, wvals in WEIGHT_SCENARIOS.items():
    for skey, sval in FLAT_SCORES.items():
        scores = np.full(len(AB), sval)
        results[f"{wscn}|{skey}"] = run_scenario(wvals, scores, f"{wscn} weight, flat score {sval}")
    results[f"{wscn}|industry"] = run_scenario(wvals, AB.industry_score.to_numpy(float), f"{wscn} weight, industry route")

# ---- regression test against the verification file's mean-weight sizing run ----
expected = {"0.000": (0.087, 0.035), "0.029_agri": (0.088, 0.041),
           "0.128_selfnonag": (0.092, 0.060), "0.169_wagenonag": (0.093, 0.067)}
mismatches = []
for skey, (exp_pooled, exp_tza) in expected.items():
    r = results[f"mean_placeholder|{skey}"]
    got_pooled = r["pooled_weighted_design"]["mean"]
    got_tza = r["by_country_weighted_design"]["Tanzania 2020"]["mean"]
    if abs(got_pooled - exp_pooled) > 0.001:
        mismatches.append(f"{skey}: pooled {got_pooled} vs expected {exp_pooled}")
    if abs(got_tza - exp_tza) > 0.001:
        mismatches.append(f"{skey}: tanzania {got_tza} vs expected {exp_tza}")
if mismatches:
    print("REGRESSION TEST MISMATCHES (verification file's sizing run):")
    for m in mismatches:
        print(" ", m)
else:
    print("regression test passed: mean-weight scenario reproduces the verification file's sizing run")

out = {
    "n_1789": n1789,
    "mean_tza_weight_placeholder": round(mean_tza_weight, 2),
    "own_weight_mean_among_1789": round(float(AB.y5_crossweight.mean()), 2),
    "flat_scores": FLAT_SCORES,
    "industry_link": dict(tier_counts=tier_counts, link_rate_pct=round(link_rate, 1),
                          n_section_matched=int(n_section_matched), donor_overall_wtd_mean=round(donor_overall, 4),
                          donor_by_section={str(int(k)): dict(n=int(v["n"]), wmean=round(float(v["wmean"]), 4))
                                            for k, v in donor_by_section.iterrows()},
                          implied_mean_unweighted=round(implied_mean, 4)),
    "scenarios": results,
    "regression_test_mismatches": mismatches,
}
json.dump(out, open("results/tza_addback_v3_py.json", "w"), indent=2)
AB.to_csv("harmonized_workers_v3_tza_addback.csv", index=False)
print("wrote results/tza_addback_v3_py.json and harmonized_workers_v3_tza_addback.csv")

print("\nSummary (own weight scenario):")
for skey in list(FLAT_SCORES) + ["industry"]:
    r = results[f"own|{skey}"]
    tza = r["by_country_weighted_design"]["Tanzania 2020"]
    uga = r["by_country_weighted_design"]["Uganda 2019"]
    print(f"  {skey:20s} pooled_wtd={r['pooled_weighted_design']['mean']:.4f}  "
          f"tza={tza['mean']:.4f} [{tza['lo']:.4f},{tza['hi']:.4f}]  "
          f"uga={uga['mean']:.4f} [{uga['lo']:.4f},{uga['hi']:.4f}]  "
          f"order_holds={r['order_nga_uga_tza_holds']}  overlap={r['intervals_overlap']}")
