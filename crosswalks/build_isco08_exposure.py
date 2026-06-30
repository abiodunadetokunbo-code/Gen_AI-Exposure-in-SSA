"""Build ISCO-08 -> AI-exposure lookup for LSMS WAVE 5 (uses ISCO-08, unlike
W4 which uses ISCO-88). Shorter chain:
  ISCO-08 (W5 s4aq40_code)
    -> SOC-2010 base   (IBS soc10_isco08.dta)
    -> O*NET-SOC 2010  (base -> detailed codes present in the exposure files)
    -> exposure        (Althoff auto/augment + Atlas mean_exposure)
Output: isco08_to_exposure.csv  (same schema as isco88_to_exposure.csv).
"""
import pandas as pd

def soc6_to_onetbase(x):
    s = str(int(x)).zfill(6); return f"{s[:2]}-{s[2:6]}"

# ---- 1. ISCO-08 -> SOC-2010 base --------------------------------------------
c = pd.read_stata("soc10_isco08.dta")
c["isco08"] = c["isco08"].astype(int)
c["socbase"] = c["soc10"].map(soc6_to_onetbase)

# ---- 2. SOC-2010 base -> O*NET-SOC 2010 detailed (from exposure universe) ----
alt = pd.read_csv("../atlas_data/althoff_occ_exposure_onetsoc.csv").rename(
    columns={"soc_code_onet": "onetsoc10"})[["onetsoc10", "auto_genai", "augment_genai"]]
atl = pd.read_csv("../atlas_data/country-occupation-panel.csv.gz")
atl = atl.groupby("onet_soc_code")["mean_exposure"].mean().reset_index().rename(
    columns={"onet_soc_code": "onetsoc10", "mean_exposure": "atlas_exposure"})
universe = pd.concat([alt[["onetsoc10"]], atl[["onetsoc10"]]]).drop_duplicates()
universe["base"] = universe["onetsoc10"].str[:7]

link = c.merge(universe, left_on="socbase", right_on="base", how="left")[
    ["isco08", "onetsoc10"]].dropna().drop_duplicates()
link.to_csv("isco08_to_onetsoc10.csv", index=False)

# ---- 3. attach exposure, collapse to ISCO-08 (simple mean) ------------------
le = link.merge(alt, on="onetsoc10", how="left").merge(atl, on="onetsoc10", how="left")
g = le.groupby("isco08")
out = pd.DataFrame({
    "n_onetsoc": g.size(),
    "n_matched_althoff": g["auto_genai"].apply(lambda s: s.notna().sum()),
    "auto_genai": g["auto_genai"].mean(),
    "augment_genai": g["augment_genai"].mean(),
    "atlas_exposure": g["atlas_exposure"].mean(),
}).reset_index()
out["match"] = "direct"

# ---- 4. hierarchical fallback for any W5 code the source misses -------------
EXPCOLS = ["auto_genai", "augment_genai", "atlas_exposure"]
def gmeans(df, n):
    t = df.copy(); t["g"] = t.isco08 // (10**(4-n)); return t.groupby("g")[EXPCOLS].mean()
g3, g2 = gmeans(out, 3), gmeans(out, 2)

w5 = pd.read_csv("../lsms_probe/w5/Post Harvest Wave 5/Household/sect4a_harvestw5.csv",
                 low_memory=False)
w5p = pd.read_csv("../lsms_probe/w5/Post Planting Wave 5/Household/sect4a_plantingw5.csv",
                  low_memory=False)
def codes_of(df):
    s = df["s4aq40_code"].dropna().astype(str).str.extract(r"^(\d+)")[0]
    return pd.to_numeric(s, errors="coerce").dropna().astype(int)
w5_codes = set(codes_of(w5)) | set(codes_of(w5p))
missing = sorted(w5_codes - set(out.isco08))
add = []
for code in missing:
    if (code // 10) in g3.index: row, src = g3.loc[code // 10], "impute_3dig"
    elif (code // 100) in g2.index: row, src = g2.loc[code // 100], "impute_2dig"
    else: continue
    r = {"isco08": code, "n_onetsoc": 0, "n_matched_althoff": 0, "match": src}
    r.update(row.to_dict()); add.append(r)
if add: out = pd.concat([out, pd.DataFrame(add)], ignore_index=True)
out = out.sort_values("isco08").reset_index(drop=True)
out.to_csv("isco08_to_exposure.csv", index=False)

cov_codes = len(w5_codes & set(out.isco08))
ph = codes_of(w5); pp = codes_of(w5p)
print(f"ISCO-08 codes in lookup: {out.isco08.nunique()} (direct {sum(out.match=='direct')}, "
      f"imputed {len(add)})")
print(f"W5 distinct occ codes: {len(w5_codes)} | covered: {cov_codes}")
print(f"worker coverage  post-harvest: {ph.isin(set(out.isco08)).mean()*100:.1f}% "
      f"({ph.isin(set(out.isco08)).sum()}/{len(ph)})")
print(f"worker coverage  post-planting: {pp.isin(set(out.isco08)).mean()*100:.1f}%")
m = pd.DataFrame({"c": ph}).merge(out, left_on="c", right_on="isco08")
print("\nW5 auto_genai across workers:",
      m["auto_genai"].describe()[["mean","50%","max"]].round(3).to_dict())
