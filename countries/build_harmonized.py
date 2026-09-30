"""Harmonize a pooled worker-level dataset across 4 SSA LSMS surveys with AI
exposure + demographics + employment status + a formality flag + survey weights.
All variable identities verified against the official DDI codebooks.

  NGA 2023 (W5): roster sect1 (s1q2 sex"1.MALE"/age s1q6) + sector(1=urban);
    labour sect4a (occ s4aq40_code ISCO-08; employee/apprentice s4aq51).
    key hhid+indiv. weight secta wt_cross_wave5 (falls back to wt_wave5).
  TZA 2020 (NPS-R5): roster hh_sec_b (hh_b02 sex 1/2, hh_b04 age) +
    hh_sec_a (y5_rural 2=urban, y5_crossweight); labour hh_sec_e1
    (occ hh_e30b_4a ISCO-08; wage hh_e03; tax hh_e44b; farm gate hh_e07).
    key (y5_hhid, indidy5).
    NB: TZA codes occupation only for wage/non-farm jobs -> subsistence
    farmers are NOT in the occupation sample and are added separately at the
    ISCO major-6 average (flagged imputed=1).
  UGA 2019 (UNPS): roster gsec2 (h2q3 sex, h2q8 age) + gsec1 (urban 1=urban,
    wgt); labour gsec8 (occ h8q19b_fourDigit ISCO-08; wage s8q04;
    written-contract s8q27 / pension s8q23 / PAYE s8q26). key (hhid, PID).
  ETH 2021 (ESPS-W5): roster sect1 (s1q02 sex, s1q03a age, occ s1q32b ISCO
    1-digit MAJOR GROUP) + saq14 (2=urban) + pw_w5. exposure at major-group mean.

Three faults present in earlier versions of this script are fixed here, and
each is marked FIX in the code below:

  FIX 1  pd.merge discards the index, so the `ix` row-identity column built by
         `.reset_index()` after `attach()` was the rank among surviving rows,
         not the labour-file row number. Every worker's occupation was joined
         to a different person's demographics and job type. `attach()` now
         carries an explicit `ix` column through the merge.
  FIX 2  `indidy5` (TZA) and `PID` (UGA) are WITHIN-household person numbers,
         with 41 and 22 distinct values. Keying the roster on them alone and
         calling drop_duplicates collapsed a 23,592-row roster to 41 rows.
         Both rosters are now keyed on (household, person).
  FIX 3  `e.get("hh_e203")` and `e.get("hh_e205")` name columns that are not in
         the Tanzanian file. The .get default returned empty strings, so the
         12-month arm of the wage gate and the farm gate silently never fired.
         Both arms are removed and the gates now run on the 7-day questions
         only, which is what they always in fact did.

Output: countries/harmonized_workers.csv
"""
import pandas as pd, numpy as np, glob

X = pd.read_csv("../crosswalks/isco08_to_exposure.csv")[
    ["isco08", "auto_genai", "augment_genai", "atlas_exposure"]]
XM = X.assign(major=(X.isco08 // 1000).astype(int)).groupby("major")[
    ["auto_genai", "augment_genai", "atlas_exposure"]].mean()
EXP = ["auto_genai", "augment_genai", "atlas_exposure"]
OUT = ["country", "sex", "age", "urban", "isco08", "major", "status", "informal",
       "weight", "hhid_c", "imputed"] + EXP


def sx(s):  # robust: "1. MALE"/"1"/1 -> male; 2 -> female
    d = pd.to_numeric(s.astype(str).str.extract(r"(\d)")[0], errors="coerce")
    return d.map({1: "male", 2: "female"})


def num(s):
    return pd.to_numeric(s.astype(str).str.extract(r"(\d+\.?\d*)")[0], errors="coerce")


def Y(s):   # yes-gate: "1. YES"/"1"/1 -> True
    return pd.to_numeric(s.astype(str).str.extract(r"(\d)")[0], errors="coerce").eq(1)


def urb(s, urban_code):
    """1/0 for urban/rural, NaN when the source is missing. Never defaults to
    rural, which an .eq().astype(float) comparison would silently do."""
    d = num(s)
    return d.map({urban_code: 1.0, (2 if urban_code == 1 else 1): 0.0})


def attach(occ, major=None):
    if major is not None:
        df = pd.DataFrame({"major": major.astype("Int64")}).join(XM, on="major")
        df["isco08"] = np.nan
        return df
    iso = num(occ)
    df = pd.DataFrame({"isco08": iso})
    df["ix"] = np.arange(len(df))          # FIX 1: keep the source row number
    df = df[(df.isco08 >= 1000) & (df.isco08 <= 9999)]
    df["major"] = (df.isco08 // 1000).astype(int)
    return df.merge(X, on="isco08", how="left")


def mkstatus(isco, wage, self_):
    # occupation-anchored: agriculture is read off ISCO (major 6 OR 921x ag
    # labourers) -> no 7-day/12-month reference-period problem. wage/self split
    # applies only to non-agriculture. `self` is a residual and therefore holds
    # unpaid family workers and apprentices as well as own-account workers.
    iso = pd.to_numeric(isco, errors="coerce")
    agri = iso.floordiv(1000).eq(6) | iso.floordiv(10).isin([921])
    return np.where(agri, "agriculture",
                    np.where(wage.fillna(False), "wage_nonag",
                             np.where(self_.fillna(False), "selfemp_nonag", "other_nonag")))


rows = []

# ---------- NIGERIA ----------
lab = pd.read_csv("../lsms_probe/w5/Post Harvest Wave 5/Household/sect4a_harvestw5.csv", low_memory=False)
r = pd.read_csv("../lsms_probe/w5/Post Harvest Wave 5/Household/sect1_harvestw5.csv", low_memory=False)
wa = pd.read_csv("../lsms_probe/w5/Post Harvest Wave 5/Household/secta_harvestw5.csv", low_memory=False)
wa = wa[["hhid", "wt_wave5", "wt_cross_wave5"]].drop_duplicates("hhid")
d = attach(lab["s4aq40_code"])
# s4aq51 = main-job employee/apprentice (reference-consistent with occupation);
# everyone else with a main job is own-account or other.
ngawage = Y(lab["s4aq51"])
base = pd.DataFrame({"ix": np.arange(len(lab)), "hhid": lab.hhid, "indiv": lab.indiv,
                     "sector": lab["sector"], "wage": ngawage, "self": ~ngawage})
d = d.merge(base, on="ix").merge(
    r[["hhid", "indiv", "s1q2", "s1q6"]], on=["hhid", "indiv"], how="left").merge(
    wa, on="hhid", how="left")
d["country"] = "Nigeria 2023"
d["sex"] = sx(d.s1q2)
d["age"] = num(d.s1q6)
d["urban"] = urb(d.sector, 1)
d["status"] = mkstatus(d.isco08, d.wage, d["self"])
d["informal"] = np.nan  # NGA formality vars deferred
d["weight"] = d.wt_cross_wave5.fillna(d.wt_wave5)
d["hhid_c"] = "NGA" + d.hhid.astype(str)
d["imputed"] = 0
rows.append(d.reindex(columns=OUT))

# ---------- TANZANIA ----------
e = pd.read_csv("TZA_2020_NPS-R5/hh_sec_e1.csv", low_memory=False)
b = pd.read_csv("TZA_2020_NPS-R5/hh_sec_b.csv", low_memory=False)
a = pd.read_csv("TZA_2020_NPS-R5/hh_sec_a.csv", low_memory=False)
d = attach(e["hh_e30b_4a"])
tzawage = Y(e["hh_e03"])                   # FIX 3: hh_e203 does not exist
base = pd.DataFrame({"ix": np.arange(len(e)), "indidy5": e["indidy5"],
                     "y5_hhid": e["y5_hhid"], "wage": tzawage, "self": ~tzawage,
                     "tax": Y(e["hh_e44b"])})
# FIX 2: indidy5 is a within-household person number -> key on the pair.
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
d["informal"] = np.where(d.wage, ~d.tax, np.nan)  # wage informal = no tax withheld
d["weight"] = d.y5_crossweight
d["hhid_c"] = "TZA" + d.y5_hhid.astype(str)
d["imputed"] = 0
rows.append(d.reindex(columns=OUT))

# TZA subsistence farmers are NOT in the non-farm occupation sample -> add them
# (hh_e07 = worked HH agriculture in the last 7 days) at ISCO major-6 exposure.
farm_gate = Y(e["hh_e07"])                 # FIX 3: hh_e205 does not exist
has_occ = num(e["hh_e30b_4a"]).between(1000, 9999)
fe = e.loc[farm_gate & ~has_occ, ["y5_hhid", "indidy5"]].reset_index(drop=True)
fe = fe.merge(bsel, on=["y5_hhid", "indidy5"], how="left").merge(au, on="y5_hhid", how="left")
fe = fe.assign(major=6).join(XM, on="major")
fe["country"] = "Tanzania 2020"
fe["sex"] = sx(fe.hh_b02)
fe["age"] = num(fe.hh_b04)
fe["urban"] = urb(fe.y5_rural, 2)
fe["isco08"] = np.nan
fe["status"] = "agriculture"
fe["informal"] = np.nan
fe["weight"] = fe.y5_crossweight
fe["hhid_c"] = "TZA" + fe.y5_hhid.astype(str)
fe["imputed"] = 1
rows.append(fe.reindex(columns=OUT))

# ---------- UGANDA ----------
g8 = pd.read_csv(glob.glob("UGA_2019_UNPS/**/gsec8.csv", recursive=True)[0],
                 encoding="latin-1", low_memory=False)
g2 = pd.read_csv("UGA_2019_UNPS/UGA_2019_UNPS_v03_M_CSV/HH/gsec2.csv",
                 encoding="latin-1", low_memory=False)
g1 = pd.read_csv("UGA_2019_UNPS/UGA_2019_UNPS_v03_M_CSV/HH/gsec1.csv",
                 encoding="latin-1", low_memory=False)
d = attach(g8["h8q19b_fourDigit"])
ugawage = Y(g8["s8q04"])
base = pd.DataFrame({"ix": np.arange(len(g8)), "PID": g8["PID"], "hhid": g8.hhid,
                     "wage": ugawage, "self": ~ugawage,
                     "contract": Y(g8["s8q27"]), "pension": Y(g8["s8q23"]),
                     "paye": Y(g8["s8q26"])})
# FIX 2: PID is a within-household person number in this export.
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
d["informal"] = np.where(d.wage, ~(d.contract | d.pension | d.paye), np.nan)
d["weight"] = d.wgt
d["hhid_c"] = "UGA" + d.hhid.astype(str)
d["imputed"] = 0
rows.append(d.reindex(columns=OUT))

# ---------- ETHIOPIA (major-group occupation) ----------
s1 = pd.read_csv("ETH_2021_ESPS-W5/sect1_hh_w5.csv", low_memory=False)
maj = num(s1["s1q32b"])
d = attach(None, major=maj)   # the major= branch keeps s1's index, so no FIX 1 needed
d["country"] = "Ethiopia 2021"
d["sex"] = sx(s1["s1q02"])
d["age"] = num(s1["s1q03a"])
d["urban"] = urb(s1["saq14"], 2)
d["weight"] = pd.to_numeric(s1["pw_w5"], errors="coerce").values
hhcol = "household_id" if "household_id" in s1.columns else s1.columns[0]
d["hhid_c"] = "ETH" + s1[hhcol].astype(str).values
d = d[(d.major >= 1) & (d.major <= 9)]
d["status"] = np.where(d.major == 6, "agriculture", "other_nonag")
d["informal"] = np.nan
d["imputed"] = 0
rows.append(d.reindex(columns=OUT))

# ---------- pool ----------
P = pd.concat(rows, ignore_index=True)
P = P[P.auto_genai.notna()].copy()

# guard rails: these must hold for the paper's numbers to be reproducible
assert len(P) == 23444, f"expected 23,444 pooled workers, got {len(P):,}"
assert P.weight.notna().all(), "every worker must carry a survey weight"
assert int(P.imputed.sum()) == 5273, "expected 5,273 imputed Tanzanian farmers"
assert P.hhid_c.notna().all(), "every worker must carry a household id"

# Since 2026-09-19 harmonized_workers.csv holds the revision-2 sample from
# build_harmonized_v2.py (the author approved the swap; this build's last output
# is in archive_v1/). Writing here would put the old sample back.
raise SystemExit("build_harmonized.py is superseded by build_harmonized_v2.py; "
                 "harmonized_workers.csv was not written")
P.to_csv("harmonized_workers.csv", index=False)
print(f"pooled workers with exposure: {len(P):,}\n")
print(P.groupby("country").agg(
    n=("auto_genai", "size"),
    pct_female=("sex", lambda s: round(100 * (s == "female").mean(), 1)),
    mean_age=("age", "mean"),
    pct_urban=("urban", lambda s: round(100 * np.nanmean(s), 1)),
    mean_auto=("auto_genai", "mean")).round(2).to_string())
print("\nstatus composition by country (%):")
print(pd.crosstab(P.country, P.status, normalize="index").mul(100).round(1).to_string())
print("\nfield coverage (% non-missing):")
print((100 * P[["sex", "age", "urban", "isco08", "status", "informal",
                "weight", "hhid_c"]].notna().mean()).round(1).to_string())
print("\nunweighted vs survey-weighted mean exposure:")
for c, g in P.groupby("country"):
    print(f"  {c:15s} {g.auto_genai.mean():.4f}  {np.average(g.auto_genai, weights=g.weight):.4f}")
