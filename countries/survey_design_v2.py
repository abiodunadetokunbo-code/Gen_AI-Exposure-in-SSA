"""Survey-design standard errors for the revision-2 worker results (plan item 8,
step 11b). Python side; the R twin is survey_design_v2.R, which uses the
`survey` package. This file codes the same Taylor-linearization variance by hand.

Design, per survey (strata carry a country prefix, PSUs are nested in strata):
  Nigeria   secta_harvestw5: PSU `cluster`, stratum `strata`
  Tanzania  hh_sec_a: PSU `clusterid`, stratum `strataid`. The 545 booster
            households (`tracking_class` 6: new urban households in five
            cities, outside the 2014/15 frame) have neither; each city's
            booster forms a stratum and its EA (`y5_cluster`) is the PSU.
  Uganda    gsec1: PSU = parish (dc_2018, cc_2018, sc_2018, pc_2018); the UNPS
            has defined clusters "up to parish level" since 2010/11 (codebook).
            Strata are the six the codebook names: Kampala, other urban, and
            rural Central, Eastern, Northern, Western. Households with no
            parish codes form one stratum, each household its own PSU; a
            household with no urban flag counts as rural (none holds a worker).
  Ethiopia  sect1_hh_w5: PSU `ea_id`, stratum region (`saq01`) x `saq14`
The frame is the worker file: a stratum's PSU count is the number of its PSUs
with at least one worker. Subgroup estimates keep the full design (domain
estimation), as survey::subset does. No stratum may have a single PSU:
Tanga urban (TZA-7) has one PSU with workers, so it joins Tanga rural (TZA-8).

Estimates: every interval in analysis_v2 sections B, C, D and G, plus
country means and weighted versions of the main contrasts. Means use normal
95% intervals, as in analysis_v2; regression p-values use a t with the
design's degrees of freedom, as svyglm does.
Writes survey_design_ids_v2.csv and results/survey_design_v2_py.json.
"""
import json

import numpy as np
import pandas as pd
import patsy
from scipy import stats as sps

A = "auto_genai"
P = pd.read_csv("harmonized_workers_v2.csv", low_memory=False)
E = pd.read_csv("harmonized_workers_v2_eth_resident.csv", low_memory=False)

# ---------------- design ids ----------------
ng = pd.read_csv("../lsms_probe/w5/Post Harvest Wave 5/Household/secta_harvestw5.csv", low_memory=False)
ng = pd.DataFrame({"hhid_c": "NGA" + ng.hhid.astype(str), "stratum": "NGA-" + ng.strata.astype(int).astype(str),
                   "psu": "NGA-" + ng.cluster.astype(str)})

tz = pd.read_csv("TZA_2020_NPS-R5/hh_sec_a.csv", low_memory=False)
boost = (tz.tracking_class == 6).to_numpy()
assert (boost == tz.clusterid.isna().to_numpy()).all() and (boost == tz.strataid.isna().to_numpy()).all()
tz = pd.DataFrame({"hhid_c": "TZA" + tz.y5_hhid.astype(str),
                   "stratum": "TZA-" + np.where(boost, "booster-" + tz.y5_cluster.str[:2],
                                                tz.strataid.astype("Int64").astype(str)),
                   "psu": "TZA-" + np.where(boost, tz.y5_cluster, tz.clusterid.astype("Int64").astype(str))})

ug = pd.read_csv("UGA_2019_UNPS/UGA_2019_UNPS_v03_M_CSV/HH/gsec1.csv", low_memory=False)
parts = ["dc_2018", "cc_2018", "sc_2018", "pc_2018"]
has_par = ug[parts].notna().all(axis=1)
rural = {1: "central_rural", 2: "eastern_rural", 3: "northern_rural", 4: "western_rural"}
ug_str = np.where(ug.district.astype(str).str.upper() == "KAMPALA", "kampala",
                  np.where(ug.urban == 1, "other_urban", ug.region.map(rural).astype(object)))
ug_str = np.where(has_par, ug_str, "no_location")
ug_psu = np.where(has_par, ug[parts].fillna(0).astype(int).astype(str).agg("-".join, axis=1),
                  "hh-" + ug.hhid.astype(str))
no_urban = set("UGA" + ug.hhid[has_par & ug.urban.isna()].astype(str))
ug = pd.DataFrame({"hhid_c": "UGA" + ug.hhid.astype(str), "stratum": "UGA-" + pd.Series(ug_str).astype(str),
                   "psu": "UGA-" + pd.Series(ug_psu)})

et = pd.read_csv("ETH_2021_ESPS-W5/sect1_hh_w5.csv", low_memory=False,
                 usecols=["household_id", "ea_id", "saq01", "saq14"]).dropna(subset=["household_id"])
et = et.drop_duplicates("household_id")
et = pd.DataFrame({"hhid_c": "ETH" + et.household_id.astype(str),
                   "stratum": "ETH-" + et.saq01.astype(str) + "-" + et.saq14.astype(str),
                   "psu": "ETH-" + et.ea_id.astype(str)})

IDS = pd.concat([ng, tz, ug, et], ignore_index=True)
assert IDS.hhid_c.is_unique
IDS["psu"] = IDS.stratum + "|" + IDS.psu  # nest PSUs in strata
IDS["stratum"] = IDS.stratum.replace({"TZA-7": "TZA-8"})  # collapse the single-PSU stratum
P = P.merge(IDS, on="hhid_c", how="left", validate="many_to_one")
E = E.merge(IDS, on="hhid_c", how="left", validate="many_to_one")
assert P.psu.notna().all() and E.psu.notna().all(), "worker without a design id"
assert not P.hhid_c.isin(no_urban).any(), "a Uganda worker's household has no urban flag"
assert (P.stratum.str.endswith("nan") | P.stratum.str.contains("None")).sum() == 0, "stratum left empty"
pd.concat([P, E])[["hhid_c", "country", "stratum", "psu"]].drop_duplicates("hhid_c").sort_values(
    "hhid_c").to_csv("survey_design_ids_v2.csv", index=False)


def describe(d):
    k = d.groupby("stratum").psu.nunique()
    assert (k > 1).all(), f"single-PSU strata: {list(k[k == 1].index)}"
    return dict(n_workers=int(len(d)), n_households=int(d.hhid_c.nunique()), n_strata=int(len(k)),
                n_psu=int(d.psu.nunique()), min_psu_per_stratum=int(k.min()),
                median_workers_per_psu=float(d.groupby("psu").size().median()))


out = {"design": {c: describe(P[P.country == c]) for c in sorted(P.country.unique())}}
out["design"]["pooled"] = describe(P)
out["design"]["ethiopia_resident"] = describe(E)


# ---------------- estimators ----------------
class Design:
    def __init__(self, d):
        self.d = d.reset_index(drop=True)
        self.psu_codes, psu_names = pd.factorize(self.d.psu)
        s = self.d.groupby("psu").stratum.first().reindex(psu_names)
        self.psu_stratum = pd.factorize(s)[0]
        self.n_h = np.bincount(self.psu_stratum)

    def var(self, Z):
        """Linearized variance of the totals in Z (rows = workers, zero outside the domain)."""
        Z = np.asarray(Z, float).reshape(len(self.d), -1)
        T = np.zeros((self.psu_codes.max() + 1, Z.shape[1]))
        np.add.at(T, self.psu_codes, Z)
        V = np.zeros((Z.shape[1], Z.shape[1]))
        for h, n in enumerate(self.n_h):
            Th = T[self.psu_stratum == h]
            Dh = Th - Th.mean(axis=0)
            V += n / (n - 1) * Dh.T @ Dh
        return V

    def df(self, dom):
        """Design degrees of freedom: PSUs minus strata, counting only those the domain reaches."""
        return int(self.d.psu[dom].nunique() - self.d.stratum[dom].nunique())

    def weights(self, w):
        return np.ones(len(self.d)) if w is None else self.d[w].to_numpy(float)

    def mean(self, dom, col=A, w=None):
        y = self.d[col].to_numpy(float)
        dom = np.asarray(dom, bool) & np.isfinite(y)
        wt = self.weights(w) * dom
        s = wt.sum()
        m = float((wt * np.where(dom, y, 0)).sum() / s)
        z = wt * np.where(dom, y - m, 0) / s
        se = float(np.sqrt(self.var(z)[0, 0]))
        return dict(mean=round(m, 4), se=round(se, 4), lo=round(m - 1.96 * se, 4),
                    hi=round(m + 1.96 * se, 4), n=int(dom.sum()))

    def reg(self, dom, formula, w=None):
        dom = np.asarray(dom, bool)
        sub = self.d[dom]
        y, X = patsy.dmatrices(formula, sub, return_type="dataframe", NA_action="drop")
        keep = np.zeros(len(self.d), bool)
        keep[X.index.to_numpy()] = True
        wt = self.weights(w)[keep]
        Xm, ym = X.to_numpy(), y.to_numpy().ravel()
        Ainv = np.linalg.inv(Xm.T @ (Xm * wt[:, None]))
        b = Ainv @ (Xm.T @ (wt * ym))
        e = ym - Xm @ b
        U = np.zeros((len(self.d), Xm.shape[1]))
        U[keep] = (Xm * (wt * e)[:, None]) @ Ainv
        se = np.sqrt(np.diag(self.var(U)))
        dfr = self.df(keep) + 1 - Xm.shape[1]
        p = 2 * sps.t.sf(np.abs(b / se), dfr)
        r = {k: dict(b=round(float(b[i]), 4), se=round(float(se[i]), 4), p=round(float(p[i]), 4))
             for i, k in enumerate(X.columns) if not k.startswith("C(country)")}
        r["_n"] = int(keep.sum()); r["_df"] = int(dfr)
        return r


P["self_d"] = (P.status == "selfemp_nonag").astype(int)
P["wage_d"] = (P.status == "wage_nonag").astype(int)
P["fem"] = np.where(P.sex.isna(), np.nan, (P.sex == "female").astype(float))
P["infd"] = P.informal_v2
D = Design(P)
d = D.d
countries = sorted(d.country.unique())
st = d.status.to_numpy()
wage = st == "wage_nonag"
yes = np.ones(len(d), bool)

# B. group means
ci = {"pooled": D.mean(yes), "pooled_weighted": D.mean(yes, w="weight")}
for c in countries:
    ci[f"country|{c}"] = D.mean(d.country == c)
    ci[f"country_wtd|{c}"] = D.mean(d.country == c, w="weight")
for s in sorted(d.status.unique()):
    ci[f"status_{s}"] = D.mean(st == s)
    ci[f"status_{s}_wtd"] = D.mean(st == s, w="weight")
    for c in countries:
        if ((st == s) & (d.country == c)).any():
            ci[f"status_{s}|{c}"] = D.mean((st == s) & (d.country == c))
ci["wage_formal"] = D.mean(wage & (d.informal_v2 == 0))
ci["wage_informal"] = D.mean(wage & (d.informal_v2 == 1))
ci["urban"] = D.mean(d.urban == 1); ci["rural"] = D.mean(d.urban == 0)
ci["male"] = D.mean(d.fem == 0); ci["female"] = D.mean(d.fem == 1)
for mj in sorted(d.major.unique()):
    ci[f"major_{int(mj)}"] = D.mean(d.major == mj)
out["group_means_ci"] = ci

# C. difference tests; D. status regressions
nonag = np.isin(st, ["wage_nonag", "selfemp_nonag"])
wv = wage & d.informal_v2.notna().to_numpy()
tests = {}
for w, sfx in [(None, ""), ("weight", "_wtd")]:
    tests["wage_vs_self_nonag" + sfx] = D.reg(nonag, "auto_genai ~ wage_d", w)
    tests["wage_vs_self_nonag_cfe" + sfx] = D.reg(nonag, "auto_genai ~ wage_d + C(country)", w)
    tests["informal_vs_formal" + sfx] = D.reg(wv, "auto_genai ~ infd", w)
    tests["informal_vs_formal_cfe" + sfx] = D.reg(wv, "auto_genai ~ infd + C(country)", w)
for k, v in [("female", "fem"), ("urban", "urban")]:
    tests[k] = D.reg(yes, f"auto_genai ~ {v}")
    tests[k + "_cfe"] = D.reg(yes, f"auto_genai ~ {v} + C(country)")
out["tests"] = tests
out["status_reg"] = {
    "m1": D.reg(yes, "auto_genai ~ self_d + wage_d"),
    "m2": D.reg(yes, "auto_genai ~ self_d + wage_d + C(country)"),
    "m3": D.reg(yes, "auto_genai ~ self_d + wage_d + urban + fem + age + C(country)"),
    "m2_wtd": D.reg(yes, "auto_genai ~ self_d + wage_d + C(country)", "weight"),
}

# G. Ethiopia resident wage sample
DE = Design(E)
ey = np.ones(len(DE.d), bool)
out["ethiopia_resident"] = dict(ci=DE.mean(ey), ci_wtd=DE.mean(ey, w="weight"),
                                ci_formal=DE.mean(DE.d.informal_v2 == 0),
                                ci_informal=DE.mean(DE.d.informal_v2 == 1))

json.dump(out, open("results/survey_design_v2_py.json", "w"), indent=2)
print(pd.DataFrame(out["design"]).T.to_string())
print("wrote survey_design_ids_v2.csv and results/survey_design_v2_py.json")
