"""Build ISCO-88 -> AI-exposure lookup, mergeable onto LSMS-ISA workers.

Chain (all many-to-many, handled by averaging at the end):
  ISCO-88 (LSMS s3q13b)
    -> SOC-2000            (IBS isco88_soc00.dta)
    -> O*NET-SOC 2000      (SOC base -> detailed O*NET codes)
    -> O*NET-SOC 2006/09/10 (IBS onetsoc update crosswalks)
    -> exposure            (Althoff & Reichardt auto/augment; Atlas mean_exposure)

Output: isco88_to_exposure.csv  (one row per ISCO-88 code, with the count of
O*NET-SOC occupations it maps to and the simple-mean exposure across them).
Simple mean (not employment-weighted) because we have no within-ISCO US
employment weights; documented as a limitation.
"""
import pandas as pd, numpy as np

CW = "."  # run from crosswalks/
def soc6_to_onetbase(x):
    s = str(int(x)).zfill(6)
    return f"{s[:2]}-{s[2:6]}"          # 111011 -> "11-1011"

# ---- 1. ISCO-88 -> SOC-2000 base --------------------------------------------
a = pd.read_stata(f"{CW}/isco88_soc00.dta")
a["socbase"] = a["soc00"].map(soc6_to_onetbase)
a["isco88"] = a["isco88"].astype(int)

# ---- 2. SOC-2000 base -> O*NET-SOC 2000 detailed ----------------------------
c00 = pd.read_stata(f"{CW}/onetsoc00_onetsoc06.dta")
c00["base"] = c00["onetsoc00"].str[:7]
soc2onet = c00[["base", "onetsoc00"]].drop_duplicates()
m = a.merge(soc2onet, left_on="socbase", right_on="base", how="left")

# ---- 3. update O*NET-SOC 2000 -> 2006 -> 2009 -> 2010 -----------------------
def chain(df, left, fpath, fl, fr):
    cw = pd.read_stata(fpath)[[fl, fr]].drop_duplicates()
    return df.merge(cw, left_on=left, right_on=fl, how="left")
m = chain(m, "onetsoc00", f"{CW}/onetsoc00_onetsoc06.dta", "onetsoc00", "onetsoc06")
m = chain(m, "onetsoc06", f"{CW}/onetsoc06_onetsoc09.dta", "onetsoc06", "onetsoc09")
m = chain(m, "onetsoc09", f"{CW}/onetsoc09_onetsoc10.dta", "onetsoc09", "onetsoc10")

link = m[["isco88", "onetsoc10"]].dropna().drop_duplicates()
link.to_csv("isco88_to_onetsoc10.csv", index=False)

# ---- 4. attach exposure (Althoff + Atlas global) ----------------------------
alt = pd.read_csv("../atlas_data/althoff_occ_exposure_onetsoc.csv")  # soc_code_onet key
alt = alt.rename(columns={"soc_code_onet": "onetsoc10"})[
    ["onetsoc10", "auto_genai", "augment_genai"]]

# Atlas: average mean_exposure across countries -> a global occupation exposure
atl = pd.read_csv("../atlas_data/country-occupation-panel.csv.gz")
atl = atl.groupby("onet_soc_code")["mean_exposure"].mean().reset_index()
atl = atl.rename(columns={"onet_soc_code": "onetsoc10", "mean_exposure": "atlas_exposure"})

le = link.merge(alt, on="onetsoc10", how="left").merge(atl, on="onetsoc10", how="left")

# ---- 5. collapse to ISCO-88 (simple mean across mapped O*NET occupations) ----
g = le.groupby("isco88")
out = pd.DataFrame({
    "n_onetsoc": g.size(),
    "n_matched_althoff": g["auto_genai"].apply(lambda s: s.notna().sum()),
    "auto_genai": g["auto_genai"].mean(),
    "augment_genai": g["augment_genai"].mean(),
    "atlas_exposure": g["atlas_exposure"].mean(),
}).reset_index()

out["match"] = "direct"

# ---- 5b. hierarchical fallback for LSMS codes the IBS source misses ----------
# borrow the 3-digit (then 2-digit) minor-group mean of DIRECT matches.
EXPCOLS = ["auto_genai", "augment_genai", "atlas_exposure"]
def group_means(df, ndig):
    t = df.copy(); t["g"] = (t.isco88 // (10**(4-ndig)))
    return t.groupby("g")[EXPCOLS].mean()
g3, g2 = group_means(out, 3), group_means(out, 2)

lsms = pd.read_csv("../lsms_probe/sect3a_harvestw4.csv", low_memory=False)
lsms_codes = set(lsms["s3q13b"].dropna().astype(int).unique())
missing = sorted(lsms_codes - set(out.isco88))
add = []
for code in missing:
    src = None
    if (code // 10) in g3.index: row, src = g3.loc[code // 10], "impute_3dig"
    elif (code // 100) in g2.index: row, src = g2.loc[code // 100], "impute_2dig"
    if src:
        r = {"isco88": code, "n_onetsoc": 0, "n_matched_althoff": 0, "match": src}
        r.update(row.to_dict()); add.append(r)
if add:
    out = pd.concat([out, pd.DataFrame(add)], ignore_index=True)

# labels (NB: ISCOGroups_en.csv is ISCO-08; codes mostly align but treat as approximate)
lab = pd.read_csv("ISCOGroups_en.csv")[["code", "preferredLabel"]]
lab["code"] = pd.to_numeric(lab["code"], errors="coerce")
out = out.merge(lab, left_on="isco88", right_on="code", how="left").drop(columns="code")
out = out.rename(columns={"preferredLabel": "isco08_label_approx"})
out = out.sort_values("isco88").reset_index(drop=True)
out.to_csv("isco88_to_exposure.csv", index=False)
covered = len(lsms_codes & set(out.isco88))
print(f"[fallback] recovered {len(add)} missing LSMS codes; "
      f"LSMS coverage now {covered}/{len(lsms_codes)} codes")

print(f"ISCO-88 codes covered: {out.isco88.nunique()}  (of 1169 in IBS source)")
print(f"with >=1 Althoff match: {(out.n_matched_althoff>0).sum()}")
print("\n=== face-validity spot checks ===")
for code in [2331, 2320, 1120, 4112, 5220, 3471, 2230, 9211, 7124]:
    r = out[out.isco88 == code]
    if len(r):
        r = r.iloc[0]
        print(f"  {code} {str(r.isco08_label_approx)[:42]:42s} n={int(r.n_onetsoc):2d} "
              f"auto={r.auto_genai:.2f} augment={r.augment_genai:.2f} atlas={r.atlas_exposure:.2f}")
