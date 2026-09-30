"""Analysis for the revision (Python side of the R/Python cross-check).

Produces everything the referee asked for that needs computation:
  A. weighted vs unweighted country estimates and pooled shares
  B. group means with household-clustered 95 percent confidence intervals
  C. country fixed-effects regressions of exposure on employment status
  D. robustness: drop Ethiopia; drop / re-assign the imputed Tanzanian farmers
  E. cross-country regressions of Atlas exposure on structure
  F. crosswalk mapping counts (one-to-many, many-to-one, unmatched)
Writes archive_v1/results/revision_py.json

NOTE (2026-09-20, plan step 12): this script reproduces the PRE-REVISION (v1)
numbers and is kept as the record of what the first submission reported. It
reads and writes archive_v1/, so it cannot touch the live revision-2 files.
The live replacement is analysis_v2.py / .R, run by run_all.py.

"""
import json, os, numpy as np, pandas as pd
import statsmodels.formula.api as smf

os.makedirs("results", exist_ok=True)
P = pd.read_csv("archive_v1/harmonized_workers.csv", low_memory=False)
A = "auto_genai"
out = {}


def wmean(x, w):
    x = np.asarray(x, float); w = np.asarray(w, float)
    k = np.isfinite(x) & np.isfinite(w)
    return float(np.average(x[k], weights=w[k]))


def clustered_ci(df, col=A, cluster="hhid_c", w=None):
    """Mean with a household-clustered 95% CI, from an intercept-only OLS."""
    d = df.dropna(subset=[col, cluster]).copy()
    d["_y"] = d[col]
    kw = {}
    if w is not None:
        d = d.dropna(subset=[w])
        kw["weights"] = d[w]
    m = smf.wls("_y ~ 1", data=d, **kw).fit(
        cov_type="cluster", cov_kwds={"groups": d[cluster]})
    b = float(m.params["Intercept"]); se = float(m.bse["Intercept"])
    return dict(mean=round(b, 4), se=round(se, 4),
                lo=round(b - 1.96 * se, 4), hi=round(b + 1.96 * se, 4), n=int(len(d)))


# ---------------- A. weights ----------------
comp = {}
for c, g in list(P.groupby("country")) + [("All (pooled)", P)]:
    comp[c] = dict(
        n=int(len(g)),
        mean_unw=round(float(g[A].mean()), 4),
        mean_wtd=round(wmean(g[A], g.weight), 4),
        agri_unw=round(100 * float((g.status == "agriculture").mean()), 1),
        agri_wtd=round(100 * wmean((g.status == "agriculture").astype(float), g.weight), 1),
        urban_unw=round(100 * float(np.nanmean(g.urban)), 1),
        urban_wtd=round(100 * wmean(g.urban, g.weight), 1),
        female_wtd=round(100 * wmean((g.sex == "female").astype(float), g.weight), 1),
    )
out["country_composition_weighted"] = comp

# pooled with each country weighted to its own population, then equal-country pooling
cw = {c: wmean(g[A], g.weight) for c, g in P.groupby("country")}
out["pooled_equal_country_mean"] = round(float(np.mean(list(cw.values()))), 4)

# ---------------- B. group means with clustered CIs ----------------
ci = {}
ci["pooled"] = clustered_ci(P)
ci["pooled_weighted"] = clustered_ci(P, w="weight")
for s, g in P.groupby("status"):
    ci[f"status_{s}"] = clustered_ci(g)
    ci[f"status_{s}_wtd"] = clustered_ci(g, w="weight")
W = P[P.status == "wage_nonag"].dropna(subset=["informal"])
ci["wage_formal"] = clustered_ci(W[W.informal == 0])
ci["wage_informal"] = clustered_ci(W[W.informal == 1])
pu = P.dropna(subset=["urban"])
ci["urban"] = clustered_ci(pu[pu.urban == 1]); ci["rural"] = clustered_ci(pu[pu.urban == 0])
ps = P.dropna(subset=["sex"])
ci["male"] = clustered_ci(ps[ps.sex == "male"]); ci["female"] = clustered_ci(ps[ps.sex == "female"])
for mj, g in P.dropna(subset=["major"]).groupby("major"):
    ci[f"major_{int(mj)}"] = clustered_ci(g)
out["group_means_ci"] = ci

# difference tests (clustered)
def diff_test(df, formula, cluster="hhid_c", w=None):
    d = df.dropna(subset=[cluster]).copy()
    kw = {"weights": d[w]} if w else {}
    m = smf.wls(formula, data=d, **kw).fit(cov_type="cluster", cov_kwds={"groups": d[cluster]})
    return {k: dict(b=round(float(m.params[k]), 4), se=round(float(m.bse[k]), 4),
                    t=round(float(m.tvalues[k]), 2), p=round(float(m.pvalues[k]), 4))
            for k in m.params.index if k != "Intercept"}


NA = P[P.status.isin(["wage_nonag", "selfemp_nonag"])].copy()
NA["wage"] = (NA.status == "wage_nonag").astype(int)
out["test_wage_vs_self_nonag"] = diff_test(NA, "auto_genai ~ wage")
out["test_wage_vs_self_nonag_cfe"] = diff_test(NA, "auto_genai ~ wage + C(country)")
out["test_formal_vs_informal"] = diff_test(W.assign(infd=W.informal.astype(int)), "auto_genai ~ infd")
out["test_formal_vs_informal_cfe"] = diff_test(
    W.assign(infd=W.informal.astype(int)), "auto_genai ~ infd + C(country)")
out["test_sex"] = diff_test(ps.assign(fem=(ps.sex == "female").astype(int)), "auto_genai ~ fem")
out["test_sex_cfe"] = diff_test(ps.assign(fem=(ps.sex == "female").astype(int)),
                                "auto_genai ~ fem + C(country)")
out["test_urban"] = diff_test(pu, "auto_genai ~ urban")
out["test_urban_cfe"] = diff_test(pu, "auto_genai ~ urban + C(country)")

# ---------------- C. status regression with country FE ----------------
R = P.copy()
R["st"] = pd.Categorical(R.status, categories=["agriculture", "selfemp_nonag", "wage_nonag", "other_nonag"])
m1 = smf.ols("auto_genai ~ C(st)", data=R).fit(
    cov_type="cluster", cov_kwds={"groups": R.hhid_c})
m2 = smf.ols("auto_genai ~ C(st) + C(country)", data=R).fit(
    cov_type="cluster", cov_kwds={"groups": R.hhid_c})
m3 = smf.ols("auto_genai ~ C(st) + urban + C(sex) + age + C(country)",
             data=R.dropna(subset=["urban", "sex", "age"])).fit(
    cov_type="cluster", cov_kwds={"groups": R.dropna(subset=["urban", "sex", "age"]).hhid_c})


def tidy(m, keep=None):
    r = {}
    for k in m.params.index:
        if keep and not any(s in k for s in keep):
            continue
        r[k] = dict(b=round(float(m.params[k]), 4), se=round(float(m.bse[k]), 5),
                    p=round(float(m.pvalues[k]), 4))
    r["_n"] = int(m.nobs); r["_r2"] = round(float(m.rsquared), 4)
    return r


K = ["C(st)", "urban", "C(sex)", "age", "Intercept"]
out["status_reg"] = {"m1": tidy(m1, K), "m2": tidy(m2, K), "m3": tidy(m3, K)}

# ---------------- D. robustness ----------------
rob = {}
sets = {
    "baseline": P,
    "drop_ethiopia": P[P.country != "Ethiopia 2021"],
    "drop_tza_imputed": P[P.imputed == 0],
    "drop_both": P[(P.country != "Ethiopia 2021") & (P.imputed == 0)],
    "three_country_4digit": P[(P.country != "Ethiopia 2021") & (P.imputed == 0)],
}
for k, g in sets.items():
    rob[k] = dict(n=int(len(g)), mean=round(float(g[A].mean()), 4),
                  mean_wtd=round(wmean(g[A], g.weight), 4),
                  agri_share=round(100 * float((g.status == "agriculture").mean()), 1),
                  agri_mean=round(float(g[g.status == "agriculture"][A].mean()), 4),
                  self_mean=round(float(g[g.status == "selfemp_nonag"][A].mean()), 4),
                  wage_mean=round(float(g[g.status == "wage_nonag"][A].mean()), 4),
                  near_zero=round(100 * float((g[A] < 0.05).mean()), 1))

# alternative exposure values for the imputed Tanzanian farmers
X = pd.read_csv("../crosswalks/isco08_to_exposure.csv")
m6 = X[(X.isco08 >= 6000) & (X.isco08 < 7000)]
alts = {
    "flat_major6_baseline": float(m6.auto_genai.mean()),
    "subsistence_6xxx_only": float(X[X.isco08.isin([6310, 6320, 6330, 6340])].auto_genai.mean()),
    "min_major6": float(m6.auto_genai.min()),
    "max_major6": float(m6.auto_genai.max()),
    "elementary_agri_9211": float(X[X.isco08 == 9211].auto_genai.mean()),
}
alt_out = {}
for k, v in alts.items():
    g = P.copy()
    g.loc[g.imputed == 1, A] = v
    alt_out[k] = dict(assigned=round(v, 4), pooled_mean=round(float(g[A].mean()), 4),
                      tza_mean=round(float(g[g.country == "Tanzania 2020"][A].mean()), 4),
                      agri_mean=round(float(g[g.status == "agriculture"][A].mean()), 4))
rob["tza_alternatives"] = alt_out
out["robustness"] = rob

# major-group profile with and without Ethiopia (Ethiopia enters only at major level)
mj = {}
for k, g in [("all", P), ("ex_eth", P[P.country != "Ethiopia 2021"])]:
    mj[k] = {int(m): dict(share=round(100 * float((g.major == m).mean()), 1),
                          mean=round(float(g[g.major == m][A].mean()), 4))
             for m in sorted(g.major.dropna().unique())}
out["major_profile"] = mj

# ---------------- E. cross-country regressions ----------------
cs = pd.read_csv("macro_country_cross_section.csv")
cs["lgdp"] = np.log(cs.gdppc)
cs["informal_s"] = cs.informal / 100.0
cs["agri_s"] = cs.selfemp_agri / 100.0
specs = {
    "(1) informality": "share_exposed ~ informal_s",
    "(2) agri self-emp": "share_exposed ~ agri_s",
    "(3) log GDPpc": "share_exposed ~ lgdp",
    "(4) informality + log GDPpc": "share_exposed ~ informal_s + lgdp",
    "(5) agri + log GDPpc": "share_exposed ~ agri_s + lgdp",
    "(6) all three": "share_exposed ~ informal_s + agri_s + lgdp",
}
macro = {}
for k, f in specs.items():
    m = smf.ols(f, data=cs).fit(cov_type="HC1")
    macro[k] = {p: dict(b=round(float(m.params[p]), 4), se=round(float(m.bse[p]), 4),
                        p=round(float(m.pvalues[p]), 4)) for p in m.params.index}
    macro[k]["_n"] = int(m.nobs); macro[k]["_r2"] = round(float(m.rsquared), 3)
out["macro_reg"] = macro
out["macro_corr"] = {v: dict(pearson=round(float(cs[[v, "share_exposed"]].corr().iloc[0, 1]), 3),
                             n=int(cs[[v, "share_exposed"]].dropna().shape[0]))
                     for v in ["informal", "selfemp_agri", "gdppc", "lgdp"]}

# ---------------- F. crosswalk mapping counts ----------------
cw08 = pd.read_csv("../crosswalks/isco08_to_onetsoc10.csv")
xw = pd.read_csv("../crosswalks/isco08_to_exposure.csv")
iso_col = [c for c in cw08.columns if "isco" in c.lower()][0]
soc_col = [c for c in cw08.columns if "onet" in c.lower() or "soc" in c.lower()][0]
per_isco = cw08.groupby(iso_col)[soc_col].nunique()
per_soc = cw08.groupby(soc_col)[iso_col].nunique()
out["crosswalk"] = dict(
    n_isco08=int(per_isco.size),
    n_onetsoc=int(per_soc.size),
    isco_to_one_onet=int((per_isco == 1).sum()),
    isco_to_many_onet=int((per_isco > 1).sum()),
    max_onet_per_isco=int(per_isco.max()),
    median_onet_per_isco=float(per_isco.median()),
    onet_shared_by_many_isco=int((per_soc > 1).sum()),
    isco_with_exposure=int(xw.auto_genai.notna().sum()),
    isco_direct=int((xw.match == "direct").sum()) if "match" in xw else None,
    isco_imputed_match=int((xw.match != "direct").sum()) if "match" in xw else None,
)
out["sample_occ_coverage"] = dict(
    coded_4digit=int(P.isco08.notna().sum()),
    coded_4digit_pct=round(100 * float(P.isco08.notna().mean()), 1),
    tza_imputed=int((P.imputed == 1).sum()),
    eth_1digit=int((P.country == "Ethiopia 2021").sum()),
)

json.dump(out, open("archive_v1/results/revision_py.json", "w"), indent=2)
print(json.dumps(out, indent=2)[:200])
print("\nwrote archive_v1/results/revision_py.json")
