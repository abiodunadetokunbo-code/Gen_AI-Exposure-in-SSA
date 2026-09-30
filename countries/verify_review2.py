"""Read-only checks behind paper/Review2_verification.md.

Reproduces every number quoted in the verification of the second referee
report. Writes nothing to the repository. Run from countries/.
The Althoff-Reichardt check (section 2) needs internet access to download the
canonical v1.3 task file; it is skipped if the download fails.
"""
import io, urllib.request
import numpy as np, pandas as pd

V1 = "archive_v1/harmonized_workers.csv"  # the sample this verification describes

d1 = lambda s: pd.to_numeric(s.astype(str).str.extract(r"^(\d+)")[0], errors="coerce")
yes = lambda s: d1(s).eq(1)

# ---------- 1. Nigeria: who the 7,708 coded workers are ----------
print("== 1. Nigeria sample flow (sect4a_harvestw5)")
lab = pd.read_csv("../lsms_probe/w5/Post Harvest Wave 5/Household/sect4a_harvestw5.csv",
                  low_memory=False)
coded = d1(lab.s4aq40_code).between(1000, 9999)
gate3 = yes(lab.s4aq4) | yes(lab.s4aq6) | yes(lab.s4aq10)   # the gate the paper used
gate14 = yes(lab.s4aq14)                                   # survey's own: Q4,6,8,10,11
print(f"rows {len(lab):,} | coded {coded.sum():,}")
print(f"paper's gate (Q4|Q6|Q10) {gate3.sum():,}; coded inside {(coded & gate3).sum():,}; "
      f"coded outside {(coded & ~gate3).sum():,}")
print(f"codebook gate s4aq14 {gate14.sum():,}; coded outside it {(coded & ~gate14).sum():,}")
print("derived work status s4aq21 x coded:")
print(pd.crosstab(lab.s4aq21.astype(str), coded))
absent = coded & d1(lab.s4aq21).eq(1)
print(f"coded with no work in 7 days: {absent.sum()}, of whom return <=3 months: "
      f"{yes(lab.loc[absent, 's4aq24']).sum()}")

# ---------- 2. Althoff-Reichardt: which release the local file is ----------
print("\n== 2. Althoff-Reichardt source")
loc = pd.read_csv("../atlas_data/althoff_occ_exposure_onetsoc.csv")
url = ("https://raw.githubusercontent.com/lukasalthoff/ai_labor_markets/main/"
       "ai_capabilities/task_ai_capabilities.csv")
try:
    t = pd.read_csv(io.BytesIO(urllib.request.urlopen(url, timeout=60).read()))
    g = t.groupby("soc_code_onet")
    o = pd.DataFrame({
        "auto": g.apply(lambda x: np.average(x.automatable_genai, weights=x.task_weight)),
        "aug": g.apply(lambda x: np.average(x.augmentation_genai, weights=x.task_weight))})
    m = loc.merge(o, left_on="soc_code_onet", right_index=True)
    print(f"canonical v1.3 (Qwen-2.5-72B, moderate 2030) rebuilds {len(m)} of {len(loc)} "
          f"occupations; max abs diff auto {np.abs(m.auto - m.auto_genai).max():.1e}, "
          f"augment {np.abs(m.aug - m.augment_genai).max():.1e}")
    print("automatable_genai values:", sorted(t.automatable_genai.unique()))
except Exception as ex:
    print("download failed, skipped:", ex)
print(f"local augment_genai range {loc.augment_genai.min():.3f} to {loc.augment_genai.max():.3f}")

# ---------- 3. Tanzania: who is missing ----------
print("\n== 3. Tanzania (hh_sec_e1)")
e = pd.read_csv("TZA_2020_NPS-R5/hh_sec_e1.csv", low_memory=False)
X = pd.read_csv("../crosswalks/isco08_to_exposure.csv")
c = pd.to_numeric(e.hh_e30b_4a.astype(str).str.extract(r"(\d+)")[0], errors="coerce")
tc = c.between(1000, 9999)
w, b, f = yes(e.hh_e03), yes(e.hh_e05), yes(e.hh_e07)
print(f"wage {w.sum():,} | non-farm business {b.sum():,} | farm {f.sum():,}")
print(f"coded {tc.sum():,}; coded & not wage {(tc & ~w).sum()}")
print(f"non-farm business, not wage: {(b & ~w).sum():,}; of whom coded {(b & ~w & tc).sum()}")
miss = c[tc & ~c.isin(X.isco08)]
print(f"coded TASCO codes absent from ISCO-08 lookup: {len(miss)} workers, {miss.nunique()} codes")
print("contract question hh_e42 among coded:", e.loc[tc, "hh_e42"].astype(str).value_counts().to_dict())

# ---------- 4. Ethiopia: who the 584 are ----------
print("\n== 4. Ethiopia (sect1_hh_w5)")
s1 = pd.read_csv("ETH_2021_ESPS-W5/sect1_hh_w5.csv", low_memory=False)
h = s1.s1q32b.notna()
print(f"with s1q32b: {h.sum()}")
print("s1q05 still a member:", s1.loc[h, "s1q05"].astype(str).value_counts().to_dict())
print("s1q23 why left (top):", s1.loc[h, "s1q23"].astype(str).value_counts().head(3).to_dict())
print("s1q25 where now:", s1.loc[h, "s1q25"].astype(str).value_counts().to_dict())
s4 = pd.read_csv("ETH_2021_ESPS-W5/sect4_hh_w5.csv", low_memory=False)
v = s4.s4q34b.dropna().astype(str)
print(f"resident wage-job occupation s4q34b: {len(v):,} coded, digit lengths "
      f"{v.str.extract(r'^(\d+)')[0].str.len().value_counts().to_dict()}")

# ---------- 5. Weights and the ranking sentence ----------
print("\n== 5. Weights")
P = pd.read_csv("harmonized_workers.csv")
r = P.groupby("country").apply(lambda g: pd.Series({
    "n": len(g), "weight_sum": g.weight.sum(),
    "mean": g.auto_genai.mean(), "mean_w": np.average(g.auto_genai, weights=g.weight)}))
print(r.round(3).to_string())
print("unweighted rank:", list(r["mean"].sort_values(ascending=False).index))
print("weighted rank:  ", list(r["mean_w"].sort_values(ascending=False).index))

# ---------- 6. Atlas measure ----------
print("\n== 6. Atlas country file")
a = pd.read_csv("../atlas_data/countries.csv")
print("columns with 'share':", [k for k in a.columns if "share" in k])
