"""Country-level augmentation (Python): aggregate AI exposure vs informality/
agriculture/GDP across African countries. Mirrors the micro insulation finding.
Writes results/macro_py.json and results/fig_macro_exposure_informality.png.
"""
import json, os, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from scipy.stats import spearmanr, pearsonr
os.makedirs("results", exist_ok=True)

d = pd.read_csv("../africa_genai_real_panel.csv", comment="#")
cs = d.sort_values("year").groupby("iso3").agg(
    country=("country", "first"), share_exposed=("share_exposed", "first"),
    subst_exp=("subst_exp_c", "first"), informal=("informal_emp_rate", "median"),
    selfemp_agri=("selfemployment_agri", "median"), selfemp=("selfemployment_share", "median"),
    gdppc=("gdp_ppc_ppp", "median")).reset_index().dropna(subset=["share_exposed"])
cs.to_csv("macro_country_cross_section.csv", index=False)

out = {"n_countries": int(len(cs))}
for xv in ["informal", "selfemp_agri", "selfemp", "gdppc"]:
    v = cs.dropna(subset=[xv, "share_exposed"])
    rho, p = spearmanr(v[xv], v.share_exposed); r, pp = pearsonr(v[xv], v.share_exposed)
    out[f"spearman_exposed_vs_{xv}"] = round(float(rho), 6)
    out[f"pearson_exposed_vs_{xv}"] = round(float(r), 6)
    out[f"n_{xv}"] = int(len(v))
out["exposed_median"] = round(float(cs.share_exposed.median()), 6)
out["micro4_share_exposed"] = {r.iso3: round(float(r.share_exposed), 4)
    for _, r in cs[cs.iso3.isin(["NGA", "ETH", "TZA", "UGA"])].iterrows()}
json.dump(out, open("results/macro_py.json", "w"), indent=2)

# figure: exposure vs informality, micro-4 highlighted
v = cs.dropna(subset=["informal", "share_exposed"])
plt.figure(figsize=(7.5, 5.5))
plt.scatter(v.informal, v.share_exposed, s=28, color="steelblue", alpha=.7)
m4 = v[v.iso3.isin(["NGA", "ETH", "TZA", "UGA"])]
plt.scatter(m4.informal, m4.share_exposed, s=90, color="crimson", zorder=3, label="micro-data countries")
for _, r in m4.iterrows(): plt.annotate(r.iso3, (r.informal, r.share_exposed), fontsize=9, xytext=(4, 4), textcoords="offset points")
b, a = np.polyfit(v.informal, v.share_exposed, 1)
xs = np.linspace(v.informal.min(), v.informal.max(), 50); plt.plot(xs, a + b*xs, color="gray", ls="--", lw=1)
rho = spearmanr(v.informal, v.share_exposed)[0]
plt.xlabel("Informal employment rate (% of employment)"); plt.ylabel("Country AI substitution exposure (Atlas share exposed)")
plt.title(f"More informal African economies are less AI-exposed (Spearman rho={rho:.2f}, n={len(v)})")
plt.legend(fontsize=8); plt.tight_layout(); plt.savefig("results/fig_macro_exposure_informality.png", dpi=120); plt.close()
for k, val in out.items(): print(f"{k}: {val}")
