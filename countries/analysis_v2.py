"""Worker-level analysis on the revision-2 sample (Python side of the R/Python pair).

Reads harmonized_workers_v2.csv (Nigeria, Tanzania, Uganda) and
harmonized_workers_v2_eth_resident.csv (Ethiopia supplement), both from
build_harmonized_v2.py. The R twin, analysis_v2.R, reads the R build's files.
analysis_revision.py and its results stay as they are for comparison.

  A. country composition, weighted and unweighted
  B. group means with household-clustered 95% CIs; informality by country
  C. clustered difference tests (own-account vs wage is estimated directly)
  D. status regressions with country fixed effects
  E. robustness: own-use farmers, TASCO-mapped rows, imputed exposure values
  F. major-group profile, pooled and by country
  G. Ethiopia resident wage sample (supplementary)

Informality: `informal_v2` is the harmonized rule (Nigeria: no contract and no
pension; Tanzania: no contract and no tax; Uganda: no contract and no PAYE).
`informal` is each country's fuller rule where one exists (Tanzania tax only,
Uganda three questions). Writes results/revision_v2_py.json.
"""
import json
import os

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

os.makedirs("results", exist_ok=True)
P = pd.read_csv("harmonized_workers_v2.csv", low_memory=False)
E = pd.read_csv("harmonized_workers_v2_eth_resident.csv", low_memory=False)
X = pd.read_csv("../crosswalks/isco08_to_exposure.csv")
A = "auto_genai"
out = {}


def wmean(x, w):
    x = np.asarray(x, float); w = np.asarray(w, float)
    k = np.isfinite(x) & np.isfinite(w)
    return float(np.average(x[k], weights=w[k]))


def clustered_ci(df, col=A, cluster="hhid_c", w=None):
    """Mean with a household-clustered 95% CI, from an intercept-only (W)LS."""
    d = df.dropna(subset=[col, cluster]).copy()
    d["_y"] = d[col]
    kw = {}
    if w is not None:
        d = d.dropna(subset=[w])
        kw["weights"] = d[w]
    m = smf.wls("_y ~ 1", data=d, **kw).fit(cov_type="cluster", cov_kwds={"groups": d[cluster]})
    b = float(m.params["Intercept"]); se = float(m.bse["Intercept"])
    return dict(mean=round(b, 4), se=round(se, 4),
                lo=round(b - 1.96 * se, 4), hi=round(b + 1.96 * se, 4), n=int(len(d)))


def fit(df, formula, cluster="hhid_c"):
    """OLS with household-clustered SEs; country dummies left out of the output."""
    d = df.dropna(subset=[cluster]).copy()
    m = smf.ols(formula, data=d).fit(cov_type="cluster", cov_kwds={"groups": d[cluster]})
    r = {k: dict(b=round(float(m.params[k]), 4), se=round(float(m.bse[k]), 4),
                 p=round(float(m.pvalues[k]), 4))
         for k in m.params.index if not k.startswith("C(country)")}
    r["_n"] = int(m.nobs); r["_r2"] = round(float(m.rsquared), 4)
    return r


def stats(g):
    return dict(n=int(len(g)), mean=round(float(g[A].mean()), 4),
                mean_wtd=round(wmean(g[A], g.weight), 4),
                agri_share=round(100 * float((g.status == "agriculture").mean()), 1),
                agri_mean=round(float(g[g.status == "agriculture"][A].mean()), 4),
                self_mean=round(float(g[g.status == "selfemp_nonag"][A].mean()), 4),
                wage_mean=round(float(g[g.status == "wage_nonag"][A].mean()), 4),
                near_zero=round(100 * float((g[A] < 0.05).mean()), 1))


P["self_d"] = (P.status == "selfemp_nonag").astype(int)
P["wage_d"] = (P.status == "wage_nonag").astype(int)
P["fem"] = np.where(P.sex.isna(), np.nan, (P.sex == "female").astype(float))
countries = sorted(P.country.unique())

# ---------------- A. composition ----------------
comp = {}
for c, g in [(c, P[P.country == c]) for c in countries] + [("All (pooled)", P)]:
    comp[c] = dict(
        n=int(len(g)),
        mean_unw=round(float(g[A].mean()), 4),
        mean_wtd=round(wmean(g[A], g.weight), 4),
        agri_unw=round(100 * float((g.status == "agriculture").mean()), 1),
        agri_wtd=round(100 * wmean((g.status == "agriculture").astype(float), g.weight), 1),
        self_unw=round(100 * float((g.status == "selfemp_nonag").mean()), 1),
        wage_unw=round(100 * float((g.status == "wage_nonag").mean()), 1),
        urban_unw=round(100 * float(np.nanmean(g.urban)), 1),
        urban_wtd=round(100 * wmean(g.urban, g.weight), 1),
        female_wtd=round(100 * wmean(g.fem, g.weight), 1),
    )
out["country_composition"] = comp
out["pooled_equal_country_mean"] = round(float(np.mean(
    [wmean(P[P.country == c][A], P[P.country == c].weight) for c in countries])), 4)

# ---------------- B. group means with clustered CIs ----------------
ci = {"pooled": clustered_ci(P), "pooled_weighted": clustered_ci(P, w="weight")}
for s in sorted(P.status.unique()):
    g = P[P.status == s]
    ci[f"status_{s}"] = clustered_ci(g)
    ci[f"status_{s}_wtd"] = clustered_ci(g, w="weight")
    for c in countries:
        if (g.country == c).any():  # Tanzania has no non-farm own-account rows
            ci[f"status_{s}|{c}"] = clustered_ci(g[g.country == c])
W = P[P.status == "wage_nonag"]
Wv = W.dropna(subset=["informal_v2"])
ci["wage_formal"] = clustered_ci(Wv[Wv.informal_v2 == 0])
ci["wage_informal"] = clustered_ci(Wv[Wv.informal_v2 == 1])
pu = P.dropna(subset=["urban"])
ci["urban"] = clustered_ci(pu[pu.urban == 1]); ci["rural"] = clustered_ci(pu[pu.urban == 0])
ps = P.dropna(subset=["fem"])
ci["male"] = clustered_ci(ps[ps.fem == 0]); ci["female"] = clustered_ci(ps[ps.fem == 1])
for mj in sorted(P.major.unique()):
    ci[f"major_{int(mj)}"] = clustered_ci(P[P.major == mj])
out["group_means_ci"] = ci

inf = {}
for c in countries:
    g = W[W.country == c]
    gv = g.dropna(subset=["informal_v2"])
    gf = g.dropna(subset=["informal"])
    inf[c] = dict(n_wage=int(len(g)), n_answered=int(len(gv)),
                  informal_v2=round(float(gv.informal_v2.mean()), 4),
                  informal_v2_wtd=round(wmean(gv.informal_v2, gv.weight), 4),
                  informal_own_rule=round(float(gf.informal.mean()), 4) if len(gf) else None,
                  mean_formal=round(float(gv[gv.informal_v2 == 0][A].mean()), 4),
                  mean_informal=round(float(gv[gv.informal_v2 == 1][A].mean()), 4))
out["informality_by_country"] = inf

# ---------------- C. difference tests ----------------
NA = P[P.status.isin(["wage_nonag", "selfemp_nonag"])]
Wt = Wv.assign(infd=Wv.informal_v2)
out["tests"] = {
    "wage_vs_self_nonag": fit(NA, "auto_genai ~ wage_d"),
    "wage_vs_self_nonag_cfe": fit(NA, "auto_genai ~ wage_d + C(country)"),
    "informal_vs_formal": fit(Wt, "auto_genai ~ infd"),
    "informal_vs_formal_cfe": fit(Wt, "auto_genai ~ infd + C(country)"),
    "female": fit(ps, "auto_genai ~ fem"),
    "female_cfe": fit(ps, "auto_genai ~ fem + C(country)"),
    "urban": fit(pu, "auto_genai ~ urban"),
    "urban_cfe": fit(pu, "auto_genai ~ urban + C(country)"),
}

# ---------------- D. status regressions ----------------
P3 = P.dropna(subset=["urban", "fem", "age"])
out["status_reg"] = {
    "m1": fit(P, "auto_genai ~ self_d + wage_d"),
    "m2": fit(P, "auto_genai ~ self_d + wage_d + C(country)"),
    "m3": fit(P3, "auto_genai ~ self_d + wage_d + urban + fem + age + C(country)"),
}

# ---------------- E. robustness ----------------
tasco = P.imputed_reason.fillna("").str.startswith("tasco_map")
sets = {
    "baseline": P,
    "own_use_excluded": P[P.imputed_reason != "own_use_farmer_family_use"],
    "coded_only": P[P.imputed == 0],
    "drop_tasco_mapped": P[~tasco],
}
rob = {k: stats(g) for k, g in sets.items()}
for c in countries:
    for k in ["baseline", "own_use_excluded", "coded_only"]:
        g = sets[k]
        rob[f"{k}|{c}"] = stats(g[g.country == c])

m6 = X[(X.isco08 >= 6000) & (X.isco08 < 7000)]
alts = {
    "major6_mean": float(m6.auto_genai.mean()),
    "subsistence_mean": float(X[X.isco08.isin([6310, 6320, 6330, 6340])].auto_genai.mean()),
    "min_major6": float(m6.auto_genai.min()),
    "max_major6": float(m6.auto_genai.max()),
    "elementary_agri_9211": float(X[X.isco08 == 9211].auto_genai.mean()),
}
groups = {"family_use": "own_use_farmer_family_use", "tza_market": "own_use_farmer_market_oriented"}
alt_out = {}
for gk, reason in groups.items():
    for ak, v in alts.items():
        g = P.copy()
        g.loc[g.imputed_reason == reason, A] = v
        alt_out[f"{gk}|{ak}"] = dict(
            assigned=round(v, 4), pooled_mean=round(float(g[A].mean()), 4),
            pooled_mean_wtd=round(wmean(g[A], g.weight), 4),
            nga_mean=round(float(g[g.country == "Nigeria 2023"][A].mean()), 4),
            tza_mean=round(float(g[g.country == "Tanzania 2020"][A].mean()), 4),
            agri_mean=round(float(g[g.status == "agriculture"][A].mean()), 4))
rob["imputed_alternatives"] = alt_out
out["robustness"] = rob

# ---------------- F. major-group profile ----------------
mj = {}
for k, g in [("pooled", P)] + [(c, P[P.country == c]) for c in countries]:
    mj[k] = {str(int(m)): dict(n=int((g.major == m).sum()),
                               share=round(100 * float((g.major == m).mean()), 1),
                               mean=round(float(g[g.major == m][A].mean()), 4))
             for m in sorted(g.major.unique())}
out["major_profile"] = mj
out["sample"] = dict(
    n=int(len(P)),
    by_country={c: int((P.country == c).sum()) for c in countries},
    coded_4digit=int(P.isco08.notna().sum()),
    by_reason={k: int(v) for k, v in P.imputed_reason.fillna("coded").value_counts().sort_index().items()},
)

# ---------------- G. Ethiopia resident wage sample ----------------
Ev = E.dropna(subset=["informal_v2"])
out["ethiopia_resident"] = dict(
    n=int(len(E)),
    mean_unw=round(float(E[A].mean()), 4),
    mean_wtd=round(wmean(E[A], E.weight), 4),
    ci=clustered_ci(E),
    ci_wtd=clustered_ci(E, w="weight"),
    informal=round(float(Ev.informal_v2.mean()), 4),
    informal_wtd=round(wmean(Ev.informal_v2, Ev.weight), 4),
    ci_formal=clustered_ci(Ev[Ev.informal_v2 == 0]),
    ci_informal=clustered_ci(Ev[Ev.informal_v2 == 1]),
    by_major88={str(int(m)): dict(n=int((E.major88 == m).sum()),
                                  share=round(100 * float((E.major88 == m).mean()), 1),
                                  mean=round(float(E[E.major88 == m][A].mean()), 4))
                for m in sorted(E.major88.unique())},
)

json.dump(out, open("results/revision_v2_py.json", "w"), indent=2)
print("wrote results/revision_v2_py.json")
