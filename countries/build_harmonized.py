"""Harmonize a pooled worker-level dataset across 4 SSA LSMS surveys with AI
exposure + demographics + employment status + a formality flag.
All variable identities verified against the official DDI codebooks this session.

  NGA 2023 (W5): roster sect1 (s1q2 sex"1.MALE"/age s1q6) + sector(1=urban);
    labour sect4a (occ s4aq40_code ISCO-08; wage s4aq4 / self s4aq6 /
    farm s4aq10|s4aq20). key hhid+indiv.
  TZA 2020 (NPS-R5): roster hh_sec_b (hh_b02 sex 1/2, hh_b04 age) +
    hh_sec_a (y5_rural 2=urban); labour hh_sec_e1 (occ hh_e30b_4a ISCO-08;
    wage hh_e03 / self hh_e05; tax hh_e44b). key indidy5.
    NB: TZA codes occupation only for wage/non-farm jobs -> subsistence
    farmers are NOT in the occupation sample (population caveat).
  UGA 2019 (UNPS): roster gsec2 (h2q3 sex, h2q8 age) + gsec1 (urban 1=urban);
    labour gsec8 (occ h8q19b_fourDigit ISCO-08; wage s8q04 / self s8q06 /
    unpaid s8q08; written-contract s8q27 / pension s8q23 / PAYE s8q26). key PID.
  ETH 2021 (ESPS-W5): roster sect1 (s1q02 sex, s1q03a age, occ s1q32b ISCO
    1-digit MAJOR GROUP) + saq14 (2=urban). exposure at major-group mean.
Output: countries/harmonized_workers.csv
"""
import pandas as pd, numpy as np, glob

X = pd.read_csv("../crosswalks/isco08_to_exposure.csv")[
    ["isco08", "auto_genai", "augment_genai", "atlas_exposure"]]
XM = X.assign(major=(X.isco08 // 1000).astype(int)).groupby("major")[
    ["auto_genai", "augment_genai", "atlas_exposure"]].mean()
EXP = ["auto_genai", "augment_genai", "atlas_exposure"]
OUT = ["country", "sex", "age", "urban", "isco08", "major", "status", "informal"] + EXP

def sx(s):  # robust: "1. MALE"/"1"/1 -> male; 2 -> female
    d = pd.to_numeric(s.astype(str).str.extract(r"(\d)")[0], errors="coerce")
    return d.map({1: "male", 2: "female"})
def num(s): return pd.to_numeric(s.astype(str).str.extract(r"(\d+\.?\d*)")[0], errors="coerce")
def Y(s):   # yes-gate: "1. YES"/"1"/1 -> True
    return pd.to_numeric(s.astype(str).str.extract(r"(\d)")[0], errors="coerce").eq(1)
def attach(occ, major=None):
    if major is not None:
        df = pd.DataFrame({"major": major.astype("Int64")}).join(XM, on="major")
        df["isco08"] = np.nan; return df
    iso = num(occ); df = pd.DataFrame({"isco08": iso})
    df = df[(df.isco08 >= 1000) & (df.isco08 <= 9999)]
    df["major"] = (df.isco08 // 1000).astype(int)
    return df.merge(X, on="isco08", how="left")
def mkstatus(isco, wage, self_):
    # occupation-anchored: agriculture is read off ISCO (major 6 OR 921x ag
    # labourers) -> no 7-day/12-month reference-period problem. wage/self split
    # (using the UNION of available gates) applies only to non-agriculture.
    iso = pd.to_numeric(isco, errors="coerce")
    agri = iso.floordiv(1000).eq(6) | iso.floordiv(10).isin([921])
    s = np.where(agri, "agriculture",
        np.where(wage.fillna(False), "wage_nonag",
        np.where(self_.fillna(False), "selfemp_nonag", "other_nonag")))
    return s
rows = []

# ---------- NIGERIA ----------
lab = pd.read_csv("../lsms_probe/w5/Post Harvest Wave 5/Household/sect4a_harvestw5.csv", low_memory=False)
r = pd.read_csv("../lsms_probe/w5/Post Harvest Wave 5/Household/sect1_harvestw5.csv", low_memory=False)
d = attach(lab["s4aq40_code"]).reset_index().rename(columns={"index": "ix"})
# s4aq51 = main-job employee/apprentice (reference-consistent with occupation);
# everyone else with a main job is own-account/self-employed.
ngawage = Y(lab["s4aq51"])
base = pd.DataFrame({"ix": lab.index, "hhid": lab.hhid, "indiv": lab.indiv, "sector": lab["sector"],
                     "wage": ngawage, "self": ~ngawage})
d = d.merge(base, on="ix").merge(
    r[["hhid", "indiv", "s1q2", "s1q6"]], on=["hhid", "indiv"], how="left")
d["country"] = "Nigeria 2023"; d["sex"] = sx(d.s1q2); d["age"] = num(d.s1q6)
d["urban"] = (num(d.sector) == 1).astype(float)
d["status"] = mkstatus(d.isco08, d.wage, d["self"])
d["informal"] = np.nan  # NGA formality vars deferred
rows.append(d.reindex(columns=OUT))

# ---------- TANZANIA ----------
e = pd.read_csv("TZA_2020_NPS-R5/hh_sec_e1.csv", low_memory=False)
b = pd.read_csv("TZA_2020_NPS-R5/hh_sec_b.csv", low_memory=False)
a = pd.read_csv("TZA_2020_NPS-R5/hh_sec_a.csv", low_memory=False)
d = attach(e["hh_e30b_4a"]).reset_index().rename(columns={"index": "ix"})
tzawage = Y(e["hh_e03"]) | Y(e.get("hh_e203", pd.Series("", index=e.index)))
base = pd.DataFrame({"ix": e.index, "indidy5": e.get("indidy5"),
                     "wage": tzawage, "self": ~tzawage, "tax": Y(e["hh_e44b"])})
bsel = b[["indidy5", "hh_b02", "hh_b04", "y5_hhid"]].dropna(subset=["indidy5"]).drop_duplicates("indidy5")
au = a[["y5_hhid", "y5_rural"]].dropna(subset=["y5_hhid"]).drop_duplicates("y5_hhid")
d = d.merge(base, on="ix").merge(bsel, on="indidy5", how="left").merge(au, on="y5_hhid", how="left")
d["country"] = "Tanzania 2020"; d["sex"] = sx(d.hh_b02); d["age"] = num(d.hh_b04)
d["urban"] = (num(d.y5_rural) == 2).astype(float)
d["status"] = mkstatus(d.isco08, d.wage, d["self"])
d["informal"] = np.where(d.wage, ~d.tax, np.nan)  # wage informal = no tax withheld
rows.append(d.reindex(columns=OUT))
# TZA subsistence farmers are NOT in the non-farm occupation sample -> add them
# (hh_e07=worked HH agriculture last 7d / hh_e205=last 12m) at agriculture (ISCO 6) exposure
farm_gate = Y(e["hh_e07"]) | Y(e.get("hh_e205", pd.Series("", index=e.index)))
has_occ = num(e["hh_e30b_4a"]).between(1000, 9999)
fe = pd.DataFrame({"indidy5": e.loc[farm_gate & ~has_occ, "indidy5"].values})
fe = fe.merge(bsel, on="indidy5", how="left").merge(au, on="y5_hhid", how="left")
fe = fe.assign(major=6).join(XM, on="major")
fe["country"] = "Tanzania 2020"; fe["sex"] = sx(fe.hh_b02); fe["age"] = num(fe.hh_b04)
fe["urban"] = (num(fe.y5_rural) == 2).astype(float); fe["isco08"] = np.nan
fe["status"] = "agriculture"; fe["informal"] = np.nan
rows.append(fe.reindex(columns=OUT))

# ---------- UGANDA ----------
g8 = pd.read_csv(glob.glob("UGA_2019_UNPS/**/gsec8.csv", recursive=True)[0], encoding="latin-1", low_memory=False)
g2 = pd.read_csv("UGA_2019_UNPS/UGA_2019_UNPS_v03_M_CSV/HH/gsec2.csv", encoding="latin-1", low_memory=False)
g1 = pd.read_csv("UGA_2019_UNPS/UGA_2019_UNPS_v03_M_CSV/HH/gsec1.csv", encoding="latin-1", low_memory=False)
d = attach(g8["h8q19b_fourDigit"]).reset_index().rename(columns={"index": "ix"})
ugawage = Y(g8["s8q04"])
base = pd.DataFrame({"ix": g8.index, "PID": g8.get("PID"), "hhid": g8.hhid,
                     "wage": ugawage, "self": ~ugawage,
                     "contract": Y(g8["s8q27"]), "pension": Y(g8["s8q23"]), "paye": Y(g8["s8q26"])})
g2s = g2[["PID", "h2q3", "h2q8"]].dropna(subset=["PID"]).drop_duplicates("PID")
g1u = g1[["hhid", "urban"]].dropna(subset=["hhid"]).drop_duplicates("hhid")
d = d.merge(base, on="ix").merge(g2s, on="PID", how="left").merge(g1u, on="hhid", how="left")
d["country"] = "Uganda 2019"; d["sex"] = sx(d.h2q3); d["age"] = num(d.h2q8)
d["urban"] = num(d.urban)
d["status"] = mkstatus(d.isco08, d.wage, d["self"])
d["informal"] = np.where(d.wage, ~(d.contract | d.pension | d.paye), np.nan)
rows.append(d.reindex(columns=OUT))

# ---------- ETHIOPIA (major-group occupation) ----------
s1 = pd.read_csv("ETH_2021_ESPS-W5/sect1_hh_w5.csv", low_memory=False)
maj = num(s1["s1q32b"])
d = attach(None, major=maj)
d["country"] = "Ethiopia 2021"; d["sex"] = sx(s1["s1q02"]); d["age"] = num(s1["s1q03a"])
d["urban"] = (num(s1["saq14"]) == 2).astype(float)
d = d[(d.major >= 1) & (d.major <= 9)]
d["status"] = np.where(d.major == 6, "agriculture", "other_nonag")
d["informal"] = np.nan
rows.append(d.reindex(columns=OUT))

# ---------- pool ----------
P = pd.concat(rows, ignore_index=True)
P = P[P.auto_genai.notna()].copy()
P.to_csv("harmonized_workers.csv", index=False)
print(f"pooled workers with exposure: {len(P):,}\n")
print(P.groupby("country").agg(n=("auto_genai", "size"),
      pct_female=("sex", lambda s: round(100*(s == "female").mean(), 1)),
      mean_age=("age", "mean"), pct_urban=("urban", lambda s: round(100*np.nanmean(s), 1)),
      mean_auto=("auto_genai", "mean")).round(2).to_string())
print("\nstatus composition by country (%):")
print(pd.crosstab(P.country, P.status, normalize="index").mul(100).round(1).to_string())
print("\nfield coverage (% non-missing):")
print((100*P[["sex","age","urban","isco08","status","informal"]].notna().mean()).round(1).to_string())
