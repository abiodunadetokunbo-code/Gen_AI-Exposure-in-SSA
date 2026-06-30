"""Build the Nigeria W4(2018)->W5(2023) worker panel with AI exposure merged.

Links individuals on (hhid, indiv). Occupation/exposure scales are comparable
across waves (both -> O*NET-SOC Althoff+Atlas), BUT note the population gap:
  W4 occupation (s3q13b, ISCO-88) exists ONLY for the main WAGE/salaried job.
  W5 occupation (s4aq40_code, ISCO-08) exists for the main job of ANY type.
So the clean comparable core is the forward panel of W4 wage workers.
Output: panel_nga_w4w5.csv (one row per linked individual).
"""
import pandas as pd, numpy as np

W4 = "../lsms_probe/sect3a_harvestw4.csv"
W5 = "../lsms_probe/w5/Post Harvest Wave 5/Household/sect4a_harvestw5.csv"
yes = lambda s: s.astype(str).str.startswith("1")

# ---- W4 person record -------------------------------------------------------
w4 = pd.read_csv(W4, low_memory=False)
w4d = pd.DataFrame({
    "hhid": w4.hhid, "indiv": w4.indiv,
    "w4_wage": (w4.get("s3q12b1") == 1),
    "w4_selfemp": (w4.get("s3q6") == 1),
    "w4_isco88": pd.to_numeric(w4.get("s3q13b"), errors="coerce"),
})
x88 = pd.read_csv("isco88_to_exposure.csv")[
    ["isco88", "auto_genai", "augment_genai", "atlas_exposure"]].add_prefix("w4_")
w4d = w4d.merge(x88, left_on="w4_isco88", right_on="w4_isco88", how="left")

# ---- W5 person record -------------------------------------------------------
w5 = pd.read_csv(W5, low_memory=False)
w5_isco08 = pd.to_numeric(
    w5["s4aq40_code"].dropna().astype(str).str.extract(r"^(\d+)")[0], errors="coerce")
w5d = pd.DataFrame({
    "hhid": w5.hhid, "indiv": w5.indiv,
    "w5_wage": yes(w5["s4aq4"]), "w5_selfemp_nf": yes(w5["s4aq6"]),
    "w5_farm": yes(w5["s4aq10"]),
    "w5_worked": w5["s4aq21"].astype(str).ne("1. NO TYPE OF WORK"),
    "w5_isco08": w5_isco08.reindex(w5.index),
})
x08 = pd.read_csv("isco08_to_exposure.csv")[
    ["isco08", "auto_genai", "augment_genai", "atlas_exposure"]].add_prefix("w5_")
w5d = w5d.merge(x08, left_on="w5_isco08", right_on="w5_isco08", how="left")

# ---- link -------------------------------------------------------------------
p = w4d.merge(w5d, on=["hhid", "indiv"], how="inner")
p.to_csv("panel_nga_w4w5.csv", index=False)

# ---- report -----------------------------------------------------------------
print(f"Linked individuals (hhid+indiv): {len(p):,}")
wage4 = p[p.w4_wage].copy()
print(f"\nW4 wage workers (linked): {len(wage4):,} | with ISCO-88 exposure: "
      f"{wage4.w4_auto_genai.notna().sum():,}")

print("\n=== W5 outcome for W4 wage workers ===")
def share(mask): return f"{mask.mean()*100:4.1f}% ({mask.sum()})"
print(f"  still wage-employed:     {share(wage4.w5_wage)}")
print(f"  self-emp non-farm:       {share(wage4.w5_selfemp_nf)}")
print(f"  any farm work:           {share(wage4.w5_farm)}")
print(f"  did any work:            {share(wage4.w5_worked)}")
print(f"  has W5 main-job occ:     {share(wage4.w5_auto_genai.notna())}")

both = wage4.dropna(subset=["w4_auto_genai", "w5_auto_genai"])
print(f"\n=== exposure change, W4 wage workers with occ in BOTH waves (n={len(both)}) ===")
for c in ["auto_genai", "augment_genai", "atlas_exposure"]:
    a, b = both[f"w4_{c}"].mean(), both[f"w5_{c}"].mean()
    print(f"  {c:14s} W4={a:.3f}  W5={b:.3f}  delta={b-a:+.3f}")

# descriptive: did high-W4-exposure wage workers leave wage work more?
print("\n=== W4 wage workers: exit-from-wage by W4 exposure tercile ===")
wage4 = wage4.dropna(subset=["w4_auto_genai"]).copy()
wage4["terc"] = pd.qcut(wage4.w4_auto_genai, 3, labels=["low", "mid", "high"])
tab = wage4.groupby("terc", observed=True).apply(
    lambda g: pd.Series({"n": len(g), "still_wage_%": g.w5_wage.mean()*100,
                         "w4_auto": g.w4_auto_genai.mean()}))
print(tab.round(2).to_string())
