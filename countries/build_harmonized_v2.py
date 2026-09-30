"""Harmonized worker-level build, revision 2 (response to the second referee
report). Reads the same raw survey files as build_harmonized.py and applies
the author's binding decisions from paper/Revision_plan_review2.md
("Decisions taken by the author (2026-09-18)"):

  1. Own-use farmers count as workers in EVERY country.
     - Tanzania's imputed pool (hh_e07 yes, no occupation code, n=5,273)
       splits on hh_e09 ("is production mainly for sale or for household
       use?"): codes 1-2, market-oriented (n=740), keep the ISCO major-6
       mean, as the original build already did for the whole pool. Codes
       3-4, family use (n=4,533), take the mean of the four subsistence
       ISCO-08 codes 6310/6320/6330/6340 (about 0.019) instead.
     - Nigeria's 1,839 s4aq21=2 ("family farm only") workers, who get no
       occupation question and were dropped entirely by the original build,
       are added with status="agriculture", imputed=1, and the SAME
       subsistence-code value as Tanzania's family-use group.
     - This goes beyond the ILO 2013 employment boundary, which puts
       own-use production of goods outside "employment": both countries'
       family-use farmers are counted as workers here because the paper's
       contribution is precisely to describe this population, and Option A
       (excluding them, matching the ILO boundary) is reported alongside as
       a named robustness variant (own-use farmers excluded) rather than
       silently dropped.
  2. Ethiopia: the out-migrant sample (sect1 s1q32b) is DROPPED from the
     headline pooled dataset. It is still built and written to its own file
     (harmonized_workers_v2_eth_outmigrant.csv) for the record, exactly as
     before, but never concatenated into P. A resident wage sample is built
     from sect4_hh_w5 s4q34b (one-digit, ISCO-88 major-group labels,
     n=2,030) and written to a SEPARATE supplementary file
     (harmonized_workers_v2_eth_resident.csv). It maps ISCO-88 major group
     to ISCO-08 exposure via the true unit-group correspondence in
     crosswalks/isco88_to_isco08.xlsx (not by assuming the same-numbered
     major groups match), and carries a contract-based formality flag
     (s4q36), the only formality question found in this wave. The headline
     pooled sample (P below) is Nigeria, Tanzania and Uganda only.

Every filter that removes or adds rows prints a labeled count (country,
stage, reason, n) to stdout AND is collected into `flow`, written to
results/sample_flow_v2.json, which is what the per-country sample-flow
table in paper/Revision_results_v2.md is built from.

139 Tanzanian wage workers (19 TASCO codes) have no match in
crosswalks/isco08_to_exposure.csv (hh_e30b_4a is TASCO, the Tanzanian
national classification -- see paper/Review2_verification.md problem C).
They are mapped with crosswalks/tasco_to_isco08_v2.csv (author-approved
2026-09-18; no published TASCO-to-ISCO-08 table was found, so each code was
checked against the respondents' job descriptions in hh_e30a). Mapped rows
carry imputed_reason "tasco_map_direct" or "tasco_map_submajor"; dropping
them reproduces the earlier sample without the map.

Does not touch harmonized_workers.csv, build_harmonized.py, or any existing
results file. Writes:
  countries/harmonized_workers_v2.csv                  (headline: NGA+TZA+UGA)
  countries/harmonized_workers_v2_own_use_excluded.csv (robustness: Option A)
  countries/harmonized_workers_v2_eth_outmigrant.csv   (old ETH sample, kept for record)
  countries/harmonized_workers_v2_eth_resident.csv     (new ETH supplementary sample)
  countries/results/sample_flow_v2.json
"""
import json
import os

import numpy as np
import pandas as pd

os.makedirs("results", exist_ok=True)

X = pd.read_csv("../crosswalks/isco08_to_exposure.csv")[
    ["isco08", "auto_genai", "augment_genai", "atlas_exposure"]]
XM = X.assign(major=(X.isco08 // 1000).astype(int)).groupby("major")[
    ["auto_genai", "augment_genai", "atlas_exposure"]].mean()
SUBSISTENCE_CODES = [6310, 6320, 6330, 6340]
SUBS = X[X.isco08.isin(SUBSISTENCE_CODES)][["auto_genai", "augment_genai", "atlas_exposure"]].mean()
EXP = ["auto_genai", "augment_genai", "atlas_exposure"]
OUT = ["country", "sex", "age", "urban", "isco08", "major", "status", "informal",
       "informal_v2", "weight", "hhid_c", "imputed", "imputed_reason"] + EXP

flow = {}  # country -> ordered list of {stage, n, reason}


def log(country, stage, n, reason=""):
    flow.setdefault(country, []).append({"stage": stage, "n": int(n), "reason": reason})
    print(f"[{country}] {stage}: {n:,}" + (f"  ({reason})" if reason else ""))


def sx(s):
    d = pd.to_numeric(s.astype(str).str.extract(r"(\d)")[0], errors="coerce")
    return d.map({1: "male", 2: "female"})


def num(s):
    return pd.to_numeric(s.astype(str).str.extract(r"(\d+\.?\d*)")[0], errors="coerce")


def Y(s):
    return pd.to_numeric(s.astype(str).str.extract(r"(\d)")[0], errors="coerce").eq(1)


def Y3(s):
    """Yes/no for formality questions, keeping missing answers missing: code 1 -> True,
    other positive code -> False, blank or negative (-99 DON'T KNOW) -> NA. The nullable
    boolean dtype makes `|` follow R's three-valued logic (NA | TRUE = TRUE)."""
    v = pd.to_numeric(s.astype(str).str.extract(r"^(\d+)")[0], errors="coerce")
    return pd.Series(pd.array(v.eq(1), dtype="boolean"), index=s.index).mask(v.isna())


def flag(cond, gate):
    """Formality flag as float 1/0; NaN outside the gate or where the answer is missing."""
    return np.where(gate, cond.astype("Float64").to_numpy(dtype=float, na_value=np.nan), np.nan)


def urb(s, urban_code):
    d = num(s)
    return d.map({urban_code: 1.0, (2 if urban_code == 1 else 1): 0.0})


def attach(occ, major=None):
    if major is not None:
        df = pd.DataFrame({"major": major.astype("Int64")}).join(XM, on="major")
        df["isco08"] = np.nan
        return df
    iso = num(occ)
    df = pd.DataFrame({"isco08": iso})
    df["ix"] = np.arange(len(df))
    df = df[(df.isco08 >= 1000) & (df.isco08 <= 9999)]
    df["major"] = (df.isco08 // 1000).astype(int)
    return df.merge(X, on="isco08", how="left")


def mkstatus(isco, wage, self_):
    iso = pd.to_numeric(isco, errors="coerce")
    agri = iso.floordiv(1000).eq(6) | iso.floordiv(10).isin([921])
    return np.where(agri, "agriculture",
                    np.where(wage.fillna(False), "wage_nonag",
                             np.where(self_.fillna(False), "selfemp_nonag", "other_nonag")))


rows = []               # headline pooled rows (NGA + TZA + UGA)
own_use_rows_ex = {}    # per-country frame with own-use family farmers EXCLUDED

# ============================================================ NIGERIA ======
lab = pd.read_csv("../lsms_probe/w5/Post Harvest Wave 5/Household/sect4a_harvestw5.csv", low_memory=False)
r = pd.read_csv("../lsms_probe/w5/Post Harvest Wave 5/Household/sect1_harvestw5.csv", low_memory=False)
wa = pd.read_csv("../lsms_probe/w5/Post Harvest Wave 5/Household/secta_harvestw5.csv", low_memory=False)
wa = wa[["hhid", "wt_wave5", "wt_cross_wave5"]].drop_duplicates("hhid")

log("Nigeria 2023", "all roster respondents (sect1)", len(r))
log("Nigeria 2023", "labour-module rows (sect4a)", len(lab))

d = attach(lab["s4aq40_code"])
ngawage = Y(lab["s4aq51"])
base = pd.DataFrame({"ix": np.arange(len(lab)), "hhid": lab.hhid, "indiv": lab.indiv,
                     "sector": lab["sector"], "wage": ngawage, "self": ~ngawage,
                     "contract": Y3(lab["s4aq56"]), "pension": Y3(lab["s4aq57__1"])})
d = d.merge(base, on="ix").merge(
    r[["hhid", "indiv", "s1q2", "s1q6"]], on=["hhid", "indiv"], how="left").merge(
    wa, on="hhid", how="left")
d["country"] = "Nigeria 2023"
d["sex"] = sx(d.s1q2)
d["age"] = num(d.s1q6)
d["urban"] = urb(d.sector, 1)
d["status"] = mkstatus(d.isco08, d.wage, d["self"])
d["informal"] = np.nan  # NGA formality vars were treated as absent in v1; corrected below
# CORRECTION vs. v1 / the plan's stated residual: s4aq56 (written contract) and
# s4aq57__1 (pension-scheme benefit flag) DO exist in the W5 labour module and
# are answered by every coded wage worker (1,441 of 1,448 yes/no + 7 don't-know).
# v1's "Nigeria formality variables are genuinely absent" is wrong; see report.
d["informal_v2"] = flag(~(d.contract | d.pension), d.wage)
d["weight"] = d.wt_cross_wave5.fillna(d.wt_wave5)
d["hhid_c"] = "NGA" + d.hhid.astype(str)
d["imputed"] = 0
d["imputed_reason"] = ""
log("Nigeria 2023", "coded 4-digit occupation, attached exposure", d.isco08.notna().sum())
log("Nigeria 2023", "final coded rows (pre pool)", len(d))
rows.append(d.reindex(columns=OUT))
own_use_rows_ex["Nigeria 2023"] = [d.reindex(columns=OUT)]  # same rows kept in the excluded variant

# ---- Nigeria family-farm-only workers (s4aq21 == 2): Decision 1 ----------
famfarm = num(lab["s4aq21"]).eq(2)
log("Nigeria 2023", "family-farm-only (s4aq21=2), no occupation asked", int(famfarm.sum()),
    "own-use farmers, added under Decision 1")
fb = lab.loc[famfarm, ["hhid", "indiv", "sector"]].reset_index(drop=True)
fb = fb.merge(r[["hhid", "indiv", "s1q2", "s1q6"]], on=["hhid", "indiv"], how="left").merge(
    wa, on="hhid", how="left")
fb["country"] = "Nigeria 2023"
fb["sex"] = sx(fb.s1q2)
fb["age"] = num(fb.s1q6)
fb["urban"] = urb(fb.sector, 1)
fb["isco08"] = np.nan
fb["major"] = 6  # same major group as Tanzania's family-use farmers (Decision 1)
fb[EXP] = [SUBS[c] for c in EXP]
fb["status"] = "agriculture"
fb["informal"] = np.nan
fb["informal_v2"] = np.nan
fb["weight"] = fb.wt_cross_wave5.fillna(fb.wt_wave5)
fb["hhid_c"] = "NGA" + fb.hhid.astype(str)
fb["imputed"] = 1
fb["imputed_reason"] = "own_use_farmer_family_use"
rows.append(fb.reindex(columns=OUT))
log("Nigeria 2023", "headline total (coded + own-use farmers)", d.isco08.notna().sum() + len(fb))

# ============================================================ TANZANIA =====
e = pd.read_csv("TZA_2020_NPS-R5/hh_sec_e1.csv", low_memory=False)
b = pd.read_csv("TZA_2020_NPS-R5/hh_sec_b.csv", low_memory=False)
a = pd.read_csv("TZA_2020_NPS-R5/hh_sec_a.csv", low_memory=False)
log("Tanzania 2020", "all roster respondents (hh_sec_b)", len(b))
log("Tanzania 2020", "labour-module rows (hh_sec_e1)", len(e))

# TASCO codes with no ISCO-08 match take the target in tasco_to_isco08_v2.csv:
# a unit code, or the average of an ISCO-08 submajor group (isco08 left blank).
TM = pd.read_csv("../crosswalks/tasco_to_isco08_v2.csv")
tasco = num(e["hh_e30b_4a"])
tasco_coded = tasco.between(1000, 9999)
tasco_unmatched = tasco_coded & ~tasco.isin(X.isco08)
tm_direct = TM.dropna(subset=["isco08_target"]).set_index("tasco_code").isco08_target
tm_sub = TM.dropna(subset=["submajor_target"]).set_index("tasco_code").submajor_target
XS = X.assign(sub=X.isco08 // 10).groupby("sub")[EXP].mean()
d = attach(tasco.where(~tasco.isin(tm_direct.index), tasco.map(tm_direct)))
m = d.isco08.isin(tm_sub.index)
sub = d.loc[m, "isco08"].map(tm_sub)
for c in EXP:
    d.loc[m, c] = sub.map(XS[c]).to_numpy()
d.loc[m, "major"] = (sub // 100).astype(int).to_numpy()
d.loc[m, "isco08"] = np.nan
tzawage = Y(e["hh_e03"])
base = pd.DataFrame({"ix": np.arange(len(e)), "indidy5": e["indidy5"],
                     "y5_hhid": e["y5_hhid"], "wage": tzawage, "self": ~tzawage,
                     "contract": Y3(e["hh_e42"]), "tax": Y3(e["hh_e44b"])})
bsel = b[["y5_hhid", "indidy5", "hh_b02", "hh_b04"]].dropna(
    subset=["y5_hhid", "indidy5"]).drop_duplicates(["y5_hhid", "indidy5"])
au = a[["y5_hhid", "y5_rural", "y5_crossweight"]].dropna(
    subset=["y5_hhid"]).drop_duplicates("y5_hhid")
d = d.merge(base, on="ix").merge(
    bsel, on=["y5_hhid", "indidy5"], how="left").merge(au, on="y5_hhid", how="left")
d["country"] = "Tanzania 2020"
d["sex"] = sx(d.hh_b02)
d["age"] = num(d.hh_b04)
d["urban"] = urb(d.y5_rural, 2)
d["status"] = mkstatus(d.isco08, d.wage, d["self"])
d["informal"] = flag(~d.tax, d.wage)                      # v1 rule, kept for comparability
d["informal_v2"] = flag(~(d.contract | d.tax), d.wage)     # harmonized: contract + tax
d["weight"] = d.y5_crossweight
d["hhid_c"] = "TZA" + d.y5_hhid.astype(str)
d["imputed"] = 0
mapped = tasco_unmatched.to_numpy()[d.ix]
d["imputed_reason"] = np.where(mapped, np.where(d.isco08.isna(), "tasco_map_submajor",
                                                "tasco_map_direct"), "")
assert d[["auto_genai", "augment_genai"]].notna().all().all(), "Tanzania coded row without exposure after the TASCO map"
log("Tanzania 2020", "TASCO-coded rows (hh_e30b_4a in 1000-9999)", int(tasco_coded.sum()))
log("Tanzania 2020", "coded, matched to ISCO-08 exposure", int((tasco_coded & ~tasco_unmatched).sum()))
log("Tanzania 2020", "coded, TASCO code with no ISCO-08 match, MAPPED", int(tasco_unmatched.sum()),
    f"{num(e.loc[tasco_unmatched, 'hh_e30b_4a']).nunique()} distinct TASCO codes; "
    "see crosswalks/tasco_to_isco08_v2.csv")
rows.append(d.reindex(columns=OUT))

# ---- Tanzania non-farm business owners with no wage job: item 4 ----------
nonfarm_biz = Y(e["hh_e05"]) & ~Y(e["hh_e03"])
log("Tanzania 2020", "non-farm business owner, no wage job, no occupation question, NOT recoverable",
    int(nonfarm_biz.sum()), "coverage gap, item 4; hh_sec_n has industry not occupation")

# ---- Tanzania own-use farmers: Decision 1, split on hh_e09 ---------------
farm_gate = Y(e["hh_e07"])
has_occ = num(e["hh_e30b_4a"]).between(1000, 9999)
pool = farm_gate & ~has_occ
log("Tanzania 2020", "farm gate (hh_e07=yes), no occupation code -- imputed pool", int(pool.sum()))
c9 = num(e["hh_e09"])
sale = pool & c9.isin([1, 2])
famuse = pool & c9.isin([3, 4])
other = pool & ~c9.isin([1, 2, 3, 4])
log("Tanzania 2020", "  of which hh_e09 in {1,2} market-oriented -> major-6 mean", int(sale.sum()))
log("Tanzania 2020", "  of which hh_e09 in {3,4} family use -> subsistence-code mean", int(famuse.sum()))
if other.sum():
    log("Tanzania 2020", "  hh_e09 missing/other -> DROPPED", int(other.sum()))


def build_imputed(mask, exp_vals, reason):
    fe = e.loc[mask, ["y5_hhid", "indidy5"]].reset_index(drop=True)
    fe = fe.merge(bsel, on=["y5_hhid", "indidy5"], how="left").merge(au, on="y5_hhid", how="left")
    fe["country"] = "Tanzania 2020"
    fe["sex"] = sx(fe.hh_b02)
    fe["age"] = num(fe.hh_b04)
    fe["urban"] = urb(fe.y5_rural, 2)
    fe["isco08"] = np.nan
    fe["major"] = 6
    for c in EXP:
        fe[c] = exp_vals[c]
    fe["status"] = "agriculture"
    fe["informal"] = np.nan
    fe["informal_v2"] = np.nan
    fe["weight"] = fe.y5_crossweight
    fe["hhid_c"] = "TZA" + fe.y5_hhid.astype(str)
    fe["imputed"] = 1
    fe["imputed_reason"] = reason
    return fe.reindex(columns=OUT)


fe_sale = build_imputed(sale, XM.loc[6], "own_use_farmer_market_oriented")
fe_fam = build_imputed(famuse, SUBS, "own_use_farmer_family_use")
rows.append(fe_sale)
rows.append(fe_fam)
log("Tanzania 2020", "headline total (coded incl. TASCO-mapped + both imputed groups)",
    len(d) + len(fe_sale) + len(fe_fam))

# ============================================================= UGANDA ======
import glob
g8 = pd.read_csv(glob.glob("UGA_2019_UNPS/**/gsec8.csv", recursive=True)[0],
                 encoding="latin-1", low_memory=False)
g2 = pd.read_csv("UGA_2019_UNPS/UGA_2019_UNPS_v03_M_CSV/HH/gsec2.csv",
                 encoding="latin-1", low_memory=False)
g1 = pd.read_csv("UGA_2019_UNPS/UGA_2019_UNPS_v03_M_CSV/HH/gsec1.csv",
                 encoding="latin-1", low_memory=False)
log("Uganda 2019", "all roster respondents (gsec2)", len(g2))
log("Uganda 2019", "labour-module rows (gsec8)", len(g8))
# Confirmed (this revision): 66.3% of Uganda's coded workers are ISCO major 6
# (agriculture), reached directly through gsec8's own occupation code, not
# through a separate imputation. Only 1,635+1,246=2,881 of the 7,671 coded
# workers answer yes to the wage (s8q04) or business (s8q06) questions, so
# the great majority of Uganda's farm workers, including own-use farmers,
# already carry a genuine ISCO-08 code. No analogous own-use-farmer
# exclusion gate was found in gsec8; Uganda needs no Decision-1 adjustment.
d = attach(g8["h8q19b_fourDigit"])
# Wage status comes from the main job (s8q22 = 1, "working for someone else for
# pay"), the job the occupation code and the formality questions describe.
# v1 used s8q04 (any paid work in the last 7 days), which put 317 workers whose
# main job is farming or own-account work into the wage group, and left out 81
# whose main job is paid employment.
ugawage = num(g8["s8q22"]).eq(1)
base = pd.DataFrame({"ix": np.arange(len(g8)), "PID": g8["PID"], "hhid": g8.hhid,
                     "wage": ugawage, "self": ~ugawage,
                     "contract": Y3(g8["s8q27"]), "pension": Y3(g8["s8q23"]),
                     "paye": Y3(g8["s8q26"])})
g2s = g2[["hhid", "PID", "h2q3", "h2q8"]].dropna(
    subset=["hhid", "PID"]).drop_duplicates(["hhid", "PID"])
g1u = g1[["hhid", "urban", "wgt"]].dropna(subset=["hhid"]).drop_duplicates("hhid")
d = d.merge(base, on="ix").merge(
    g2s, on=["hhid", "PID"], how="left").merge(g1u, on="hhid", how="left")
d["country"] = "Uganda 2019"
d["sex"] = sx(d.h2q3)
d["age"] = num(d.h2q8)
d["urban"] = num(d.urban)
d["status"] = mkstatus(d.isco08, d.wage, d["self"])
d["informal"] = flag(~(d.contract | d.pension | d.paye), d.wage)  # full 3-question rule
d["informal_v2"] = flag(~(d.contract | d.paye), d.wage)           # harmonized: contract + PAYE
d["weight"] = d.wgt
d["hhid_c"] = "UGA" + d.hhid.astype(str)
d["imputed"] = 0
d["imputed_reason"] = ""
log("Uganda 2019", "coded 4-digit occupation, attached exposure", d.isco08.notna().sum())
rows.append(d.reindex(columns=OUT))

# ============================================================ pool (headline) ==
P = pd.concat(rows, ignore_index=True)
n_before_exp_drop = len(P)
P_dropped_no_exposure = P[P.auto_genai.isna()]
P = P[P.auto_genai.notna()].copy()
for c, g in P_dropped_no_exposure.groupby("country"):
    log(c, "no exposure value after crosswalk, DROPPED from headline", len(g))
log("ALL", "headline pooled workers (Nigeria+Tanzania+Uganda)", len(P))

# ---- guard rails: the counts the author approved on 2026-09-19 -------------
# Every number here is quoted in paper/Revision_results_v2.md and pinned again
# in check_paper_numbers.py. Change them only alongside an approved rebuild;
# a passing assert on a stale number is worse than no assert.
APPROVED = {"Nigeria 2023": 9547, "Tanzania 2020": 7620, "Uganda 2019": 7671}
for c, n in APPROVED.items():
    got = int((P.country == c).sum())
    assert got == n, f"{c}: expected {n:,} workers, got {got:,}"
assert len(P) == 24838, f"expected 24,838 pooled workers, got {len(P):,}"
assert int(P.imputed.sum()) == 7112,     f"expected 7,112 own-use farmers at an imputed exposure value, got {int(P.imputed.sum()):,}"
assert int((P.imputed_reason == "own_use_farmer_family_use").sum()) == 6372
assert int((P.imputed_reason == "own_use_farmer_market_oriented").sum()) == 740
assert int(P.imputed_reason.fillna("").str.startswith("tasco_map").sum()) == 139,     "expected 139 Tanzanian rows carried in by the TASCO map"
assert int(P.isco08.notna().sum()) == 17720, "expected 17,720 rows with a 4-digit ISCO-08 code"
assert P.weight.notna().all(), "every worker must carry a survey weight"
assert P.hhid_c.notna().all(), "every worker must carry a household id"
assert P.auto_genai.notna().all(), "every worker must carry an exposure score"

os.makedirs("results", exist_ok=True)
P.to_csv("harmonized_workers_v2.csv", index=False)

# ---- robustness variant: own-use (family-use) farmers excluded everywhere -
excl_mask = ~P.imputed_reason.eq("own_use_farmer_family_use")
P_ex = P[excl_mask].copy()
assert len(P_ex) == 18466, f"expected 18,466 in the own-use-excluded sample, got {len(P_ex):,}"
P_ex.to_csv("harmonized_workers_v2_own_use_excluded.csv", index=False)
log("ALL", "own-use-excluded robustness sample (drops family-use farmers, keeps market-oriented)",
    len(P_ex))

with open("tasco_unmatched_codes.csv", "w") as f:
    f.write("tasco_code,n_workers\n")
    vc = num(e.loc[tasco_unmatched, "hh_e30b_4a"]).value_counts().sort_index()
    for code, n in vc.items():
        f.write(f"{int(code)},{int(n)}\n")

# ============================================================ ETHIOPIA =====
s1 = pd.read_csv("ETH_2021_ESPS-W5/sect1_hh_w5.csv", low_memory=False)
log("Ethiopia 2021 (out-migrant)", "all roster respondents (sect1)", len(s1))
maj = num(s1["s1q32b"])
dE = attach(None, major=maj)
dE["country"] = "Ethiopia 2021 (out-migrant, not in headline)"
dE["sex"] = sx(s1["s1q02"])
dE["age"] = num(s1["s1q03a"])
dE["urban"] = urb(s1["saq14"], 2)
dE["weight"] = pd.to_numeric(s1["pw_w5"], errors="coerce").values
hhcol = "household_id" if "household_id" in s1.columns else s1.columns[0]
dE["hhid_c"] = "ETH" + s1[hhcol].astype(str).values
dE = dE[(dE.major >= 1) & (dE.major <= 9)]
dE["status"] = np.where(dE.major == 6, "agriculture", "other_nonag")
dE["informal"] = np.nan
dE["informal_v2"] = np.nan
dE["imputed"] = 0
dE["imputed_reason"] = ""
log("Ethiopia 2021 (out-migrant)", "coded (major-group), DEMOTED to supplementary, EXCLUDED from headline",
    len(dE), "Decision 2: population is people who left the origin household (see verification file)")
assert len(dE) == 584, f"expected 584 Ethiopian out-migrant workers, got {len(dE):,}"
dE.reindex(columns=OUT).to_csv("harmonized_workers_v2_eth_outmigrant.csv", index=False)

# ---- Ethiopia resident wage sample (Decision 2, adopted supplementary) ----
s4 = pd.read_csv("ETH_2021_ESPS-W5/sect4_hh_w5.csv", low_memory=False)
maj88 = num(s4["s4q34b"])
log("Ethiopia 2021 (resident)", "s4q34b non-missing (one-digit ISCO-88 major, incl. armed forces=10)",
    int(maj88.notna().sum()))
armed = maj88.eq(10)
log("Ethiopia 2021 (resident)", "armed forces (code 10), DROPPED", int(armed.sum()))
maj88v = maj88.where(maj88.between(1, 9))

# ISCO-88 major group -> ISCO-08 exposure, via the true unit-group
# correspondence (crosswalks/isco88_to_isco08.xlsx), NOT same-numbered majors.
xw = pd.read_excel("../crosswalks/isco88_to_isco08.xlsx", sheet_name="ISCO-88 to 08", header=0)
xw.columns = ["isco88_title", "isco88", "isco08", "partial", "isco08_title", "comment"]
xw["isco88"] = pd.to_numeric(xw.isco88, errors="coerce")
xw["isco08"] = pd.to_numeric(xw.isco08, errors="coerce")
xw = xw.dropna(subset=["isco88", "isco08"])
xw["isco88_major"] = (xw.isco88 // 1000).astype(int)
xwm = xw.merge(X[["isco08", "auto_genai", "augment_genai", "atlas_exposure"]], on="isco08", how="left")
M88 = xwm.groupby("isco88_major")[EXP].mean()
log("Ethiopia 2021 (resident)", "ISCO-88 major groups with a derived exposure value",
    int(M88[EXP[0]].notna().sum()), "via crosswalks/isco88_to_isco08.xlsx unit-group correspondence")

# sect4_hh_w5 already carries its own household_id/individual_id, saq14
# (urban) and pw_w5 (weight); only sex/age need a merge to sect1 (roster).
s1dem = s1[["household_id", "individual_id", "s1q02", "s1q03a"]].dropna(
    subset=["household_id", "individual_id"]).drop_duplicates(["household_id", "individual_id"])
dR = s4[["household_id", "individual_id", "saq14", "pw_w5"]].copy()
dR["major88"] = maj88v.values
dR = dR.merge(s1dem, on=["household_id", "individual_id"], how="left")
dR = dR.join(M88, on="major88")
dR["isco08"] = np.nan
dR["major"] = np.nan  # not an ISCO-08 major group; kept separate from the headline major column
dR["country"] = "Ethiopia 2021 (resident wage, supplementary)"
dR["sex"] = sx(dR["s1q02"])
dR["age"] = num(dR["s1q03a"])
dR["urban"] = urb(dR["saq14"], 2)
dR["status"] = "wage_resident_supplementary"
dR["contract"] = Y3(s4["s4q36"]).values
dR["informal"] = np.nan
dR["informal_v2"] = flag(~dR["contract"], dR["major88"].notna())
dR["weight"] = pd.to_numeric(dR["pw_w5"], errors="coerce")
dR["hhid_c"] = "ETH" + dR["household_id"].astype(str)
dR["imputed"] = 0
dR["imputed_reason"] = ""
dR = dR[dR["major88"].notna()]
log("Ethiopia 2021 (resident)", "final resident wage supplementary sample (major88 1-9, exposure attached)",
    len(dR), "wage-job occupation only; cannot support an agriculture/own-account row")
assert len(dR) == 1989, f"expected 1,989 Ethiopian resident wage workers, got {len(dR):,}"
dR.reindex(columns=OUT + ["major88"]).to_csv("harmonized_workers_v2_eth_resident.csv", index=False)

# ============================================================ write flow ===
with open("results/sample_flow_v2.json", "w") as f:
    json.dump(flow, f, indent=2)

print("\n=== headline (NGA+TZA+UGA) ===")
print(f"N = {len(P):,}")
print(P.groupby("country").agg(n=("auto_genai", "size"),
                                mean_auto=("auto_genai", "mean"),
                                agri_share=("status", lambda s: round(100*(s=="agriculture").mean(),1))
                                ).round(3).to_string())
print("\nwrote harmonized_workers_v2.csv, harmonized_workers_v2_own_use_excluded.csv,")
print("      harmonized_workers_v2_eth_outmigrant.csv, harmonized_workers_v2_eth_resident.csv,")
print("      results/sample_flow_v2.json, tasco_unmatched_codes.csv")
