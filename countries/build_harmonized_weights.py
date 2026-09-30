"""Rebuild the pooled worker file, adding survey weights, the household id
(for clustered standard errors) and a flag for the imputed Tanzanian farmers.

Same variable identities as build_harmonized.py; the only additions are
  weight  - cross-sectional survey weight (NGA wt_cross_wave5 / TZA
            y5_crossweight / UGA wgt / ETH pw_w5)
  hhid_c  - household identifier, used to cluster standard errors
  imputed - 1 for the Tanzanian farmers who receive the ISCO major-6 average
            instead of a coded four-digit occupation
Output: countries/harmonized_workers_wtd.csv  (the original file is untouched)
"""
import pandas as pd, numpy as np, glob

X = pd.read_csv("../crosswalks/isco08_to_exposure.csv")[
    ["isco08", "auto_genai", "augment_genai", "atlas_exposure"]]
XM = X.assign(major=(X.isco08 // 1000).astype(int)).groupby("major")[
    ["auto_genai", "augment_genai", "atlas_exposure"]].mean()
EXP = ["auto_genai", "augment_genai", "atlas_exposure"]
OUT = ["country", "sex", "age", "urban", "isco08", "major", "status", "informal",
       "weight", "hhid_c", "imputed"] + EXP


def sx(s):
    d = pd.to_numeric(s.astype(str).str.extract(r"(\d)")[0], errors="coerce")
    return d.map({1: "male", 2: "female"})


def num(s):
    return pd.to_numeric(s.astype(str).str.extract(r"(\d+\.?\d*)")[0], errors="coerce")


def Y(s):
    return pd.to_numeric(s.astype(str).str.extract(r"(\d)")[0], errors="coerce").eq(1)


def attach(occ, major=None):
    if major is not None:
        df = pd.DataFrame({"major": major.astype("Int64")}).join(XM, on="major")
        df["isco08"] = np.nan
        return df
    iso = num(occ)
    df = pd.DataFrame({"isco08": iso})
    # pd.merge discards the index, so carry the source row position explicitly;
    # without this the demographics join lands on the wrong worker.
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


rows = []

# ---------- NIGERIA ----------
lab = pd.read_csv("../lsms_probe/w5/Post Harvest Wave 5/Household/sect4a_harvestw5.csv", low_memory=False)
r = pd.read_csv("../lsms_probe/w5/Post Harvest Wave 5/Household/sect1_harvestw5.csv", low_memory=False)
wa = pd.read_csv("../lsms_probe/w5/Post Harvest Wave 5/Household/secta_harvestw5.csv", low_memory=False)
wa = wa[["hhid", "wt_wave5", "wt_cross_wave5"]].drop_duplicates("hhid")
d = attach(lab["s4aq40_code"])
ngawage = Y(lab["s4aq51"])
base = pd.DataFrame({"ix": np.arange(len(lab)), "hhid": lab.hhid, "indiv": lab.indiv, "sector": lab["sector"],
                     "wage": ngawage, "self": ~ngawage})
d = d.merge(base, on="ix").merge(
    r[["hhid", "indiv", "s1q2", "s1q6"]], on=["hhid", "indiv"], how="left").merge(wa, on="hhid", how="left")
d["country"] = "Nigeria 2023"
d["sex"] = sx(d.s1q2)
d["age"] = num(d.s1q6)
d["urban"] = num(d.sector).map({1: 1.0, 2: 0.0})
d["status"] = mkstatus(d.isco08, d.wage, d["self"])
d["informal"] = np.nan
d["weight"] = d.wt_cross_wave5.fillna(d.wt_wave5)
d["hhid_c"] = "NGA" + d.hhid.astype(str)
d["imputed"] = 0
rows.append(d.reindex(columns=OUT))

# ---------- TANZANIA ----------
e = pd.read_csv("TZA_2020_NPS-R5/hh_sec_e1.csv", low_memory=False)
b = pd.read_csv("TZA_2020_NPS-R5/hh_sec_b.csv", low_memory=False)
a = pd.read_csv("TZA_2020_NPS-R5/hh_sec_a.csv", low_memory=False)
d = attach(e["hh_e30b_4a"])
tzawage = Y(e["hh_e03"])                   # hh_e203 does not exist in this file
base = pd.DataFrame({"ix": np.arange(len(e)), "indidy5": e["indidy5"], "y5_hhid": e["y5_hhid"],
                     "wage": tzawage, "self": ~tzawage, "tax": Y(e["hh_e44b"])})
# indidy5 is a WITHIN-household person number (41 distinct values), so the
# roster must be keyed on (y5_hhid, indidy5), not on indidy5 alone.
bsel = b[["y5_hhid", "indidy5", "hh_b02", "hh_b04"]].dropna(
    subset=["y5_hhid", "indidy5"]).drop_duplicates(["y5_hhid", "indidy5"])
au = a[["y5_hhid", "y5_rural", "y5_crossweight"]].dropna(subset=["y5_hhid"]).drop_duplicates("y5_hhid")
d = d.merge(base, on="ix").merge(bsel, on=["y5_hhid", "indidy5"], how="left").merge(au, on="y5_hhid", how="left")
d["country"] = "Tanzania 2020"
d["sex"] = sx(d.hh_b02)
d["age"] = num(d.hh_b04)
d["urban"] = num(d.y5_rural).map({2: 1.0, 1: 0.0})
d["status"] = mkstatus(d.isco08, d.wage, d["self"])
d["informal"] = np.where(d.wage, ~d.tax, np.nan)
d["weight"] = d.y5_crossweight
d["hhid_c"] = "TZA" + d.y5_hhid.astype(str)
d["imputed"] = 0
rows.append(d.reindex(columns=OUT))

farm_gate = Y(e["hh_e07"])                 # hh_e205 does not exist in this file
has_occ = num(e["hh_e30b_4a"]).between(1000, 9999)
fe = e.loc[farm_gate & ~has_occ, ["y5_hhid", "indidy5"]].reset_index(drop=True)
fe = fe.merge(bsel, on=["y5_hhid", "indidy5"], how="left").merge(au, on="y5_hhid", how="left")
fe = fe.assign(major=6).join(XM, on="major")
fe["country"] = "Tanzania 2020"
fe["sex"] = sx(fe.hh_b02)
fe["age"] = num(fe.hh_b04)
fe["urban"] = num(fe.y5_rural).map({2: 1.0, 1: 0.0})
fe["isco08"] = np.nan
fe["status"] = "agriculture"
fe["informal"] = np.nan
fe["weight"] = fe.y5_crossweight
fe["hhid_c"] = "TZA" + fe.y5_hhid.astype(str)
fe["imputed"] = 1
rows.append(fe.reindex(columns=OUT))

# ---------- UGANDA ----------
g8 = pd.read_csv(glob.glob("UGA_2019_UNPS/**/gsec8.csv", recursive=True)[0], encoding="latin-1", low_memory=False)
g2 = pd.read_csv("UGA_2019_UNPS/UGA_2019_UNPS_v03_M_CSV/HH/gsec2.csv", encoding="latin-1", low_memory=False)
g1 = pd.read_csv("UGA_2019_UNPS/UGA_2019_UNPS_v03_M_CSV/HH/gsec1.csv", encoding="latin-1", low_memory=False)
d = attach(g8["h8q19b_fourDigit"])
ugawage = Y(g8["s8q04"])
base = pd.DataFrame({"ix": np.arange(len(g8)), "PID": g8["PID"], "hhid": g8.hhid,
                     "wage": ugawage, "self": ~ugawage,
                     "contract": Y(g8["s8q27"]), "pension": Y(g8["s8q23"]), "paye": Y(g8["s8q26"])})
# PID is a within-household person number in this export -> key on (hhid, PID)
g2s = g2[["hhid", "PID", "h2q3", "h2q8"]].dropna(
    subset=["hhid", "PID"]).drop_duplicates(["hhid", "PID"])
g1u = g1[["hhid", "urban", "wgt"]].dropna(subset=["hhid"]).drop_duplicates("hhid")
d = d.merge(base, on="ix").merge(g2s, on=["hhid", "PID"], how="left").merge(g1u, on="hhid", how="left")
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

# ---------- ETHIOPIA ----------
s1 = pd.read_csv("ETH_2021_ESPS-W5/sect1_hh_w5.csv", low_memory=False)
maj = num(s1["s1q32b"])
d = attach(None, major=maj)
d["country"] = "Ethiopia 2021"
d["sex"] = sx(s1["s1q02"])
d["age"] = num(s1["s1q03a"])
d["urban"] = num(s1["saq14"]).map({2: 1.0, 1: 0.0})
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
P.to_csv("harmonized_workers_wtd.csv", index=False)
print(f"pooled workers with exposure: {len(P):,}")
print("\nweight coverage (% non-missing) by country:")
print((100 * P.groupby("country").weight.apply(lambda s: s.notna().mean())).round(1).to_string())
print("\nimputed TZA farmers:", int(P.imputed.sum()))
print("\nunweighted mean exposure by country:")
print(P.groupby("country").auto_genai.mean().round(4).to_string())
print("\nweighted mean exposure by country:")
g = P.dropna(subset=["weight"])
print(g.groupby("country").apply(
    lambda x: np.average(x.auto_genai, weights=x.weight)).round(4).to_string())
