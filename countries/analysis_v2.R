# R twin of analysis_v2.py. Reads the R build's files (harmonized_workers_v2_R.csv,
# harmonized_workers_v2_eth_resident_R.csv), computes the same estimands, and
# writes results/revision_v2_r.json. Clustered SEs use sandwich::vcovCL (HC1),
# the same small-sample correction statsmodels applies by default.
suppressPackageStartupMessages({ library(jsonlite); library(sandwich) })

P <- read.csv("harmonized_workers_v2_R.csv", stringsAsFactors = FALSE)
E <- read.csv("harmonized_workers_v2_eth_resident_R.csv", stringsAsFactors = FALSE)
X <- read.csv("../crosswalks/isco08_to_exposure.csv")
A <- "auto_genai"
out <- list()

wmean <- function(x, w) { k <- is.finite(x) & is.finite(w); sum(x[k] * w[k]) / sum(w[k]) }

# household-clustered SE of a (weighted) mean, CR1 with K = 1
clustered_ci <- function(d, col = A, cl = "hhid_c", w = NULL) {
  k <- !is.na(d[[col]]) & !is.na(d[[cl]])
  if (!is.null(w)) k <- k & !is.na(d[[w]])
  y <- d[[col]][k]; g <- d[[cl]][k]
  ww <- if (is.null(w)) rep(1, length(y)) else d[[w]][k]
  b <- sum(ww * y) / sum(ww)
  sg <- tapply(ww * (y - b), g, sum)
  G <- length(sg)
  se <- sqrt(sum(sg^2) / sum(ww)^2 * G / (G - 1))
  list(mean = round(b, 4), se = round(se, 4), lo = round(b - 1.96 * se, 4),
       hi = round(b + 1.96 * se, 4), n = length(y))
}

# OLS with household-clustered SEs; country dummies left out of the output
fit <- function(d, f, cl = "hhid_c") {
  d <- d[!is.na(d[[cl]]), ]
  vars <- all.vars(f)
  d <- d[complete.cases(d[, c(vars, cl)]), ]
  m <- lm(f, data = d)
  V <- vcovCL(m, cluster = d[[cl]], type = "HC1")
  co <- coef(m); se <- sqrt(diag(V)); tv <- co / se
  pv <- 2 * pnorm(-abs(tv))
  r <- list()
  for (k in names(co)) {
    if (grepl("^factor\\(country\\)", k)) next
    nm <- if (k == "(Intercept)") "Intercept" else k
    r[[nm]] <- list(b = round(unname(co[k]), 4), se = round(unname(se[k]), 4), p = round(unname(pv[k]), 4))
  }
  r[["_n"]] <- nrow(d); r[["_r2"]] <- round(summary(m)$r.squared, 4)
  r
}

stats <- function(g) {
  list(n = nrow(g), mean = round(mean(g[[A]]), 4), mean_wtd = round(wmean(g[[A]], g$weight), 4),
       agri_share = round(100 * mean(g$status == "agriculture"), 1),
       agri_mean = round(mean(g[[A]][g$status == "agriculture"]), 4),
       self_mean = round(mean(g[[A]][g$status == "selfemp_nonag"]), 4),
       wage_mean = round(mean(g[[A]][g$status == "wage_nonag"]), 4),
       near_zero = round(100 * mean(g[[A]] < 0.05), 1))
}

P$self_d <- as.integer(P$status == "selfemp_nonag")
P$wage_d <- as.integer(P$status == "wage_nonag")
P$fem <- ifelse(is.na(P$sex), NA, as.numeric(P$sex == "female"))
P$imputed_reason[is.na(P$imputed_reason)] <- ""
countries <- sort(unique(P$country))

# ---------------- A. composition ----------------
comp <- list()
for (cn in c(countries, "All (pooled)")) {
  g <- if (cn == "All (pooled)") P else P[P$country == cn, ]
  comp[[cn]] <- list(
    n = nrow(g), mean_unw = round(mean(g[[A]]), 4), mean_wtd = round(wmean(g[[A]], g$weight), 4),
    agri_unw = round(100 * mean(g$status == "agriculture"), 1),
    agri_wtd = round(100 * wmean(as.numeric(g$status == "agriculture"), g$weight), 1),
    self_unw = round(100 * mean(g$status == "selfemp_nonag"), 1),
    wage_unw = round(100 * mean(g$status == "wage_nonag"), 1),
    urban_unw = round(100 * mean(g$urban, na.rm = TRUE), 1),
    urban_wtd = round(100 * wmean(g$urban, g$weight), 1),
    female_wtd = round(100 * wmean(g$fem, g$weight), 1))
}
out$country_composition <- comp
out$pooled_equal_country_mean <- round(mean(sapply(countries, function(cn) {
  g <- P[P$country == cn, ]; wmean(g[[A]], g$weight) })), 4)

# ---------------- B. group means with clustered CIs ----------------
ci <- list(pooled = clustered_ci(P), pooled_weighted = clustered_ci(P, w = "weight"))
for (s in sort(unique(P$status))) {
  g <- P[P$status == s, ]
  ci[[paste0("status_", s)]] <- clustered_ci(g)
  ci[[paste0("status_", s, "_wtd")]] <- clustered_ci(g, w = "weight")
  for (cn in countries) if (any(g$country == cn))  # Tanzania has no non-farm own-account rows
    ci[[paste0("status_", s, "|", cn)]] <- clustered_ci(g[g$country == cn, ])
}
W <- P[P$status == "wage_nonag", ]
Wv <- W[!is.na(W$informal_v2), ]
ci$wage_formal <- clustered_ci(Wv[Wv$informal_v2 == 0, ])
ci$wage_informal <- clustered_ci(Wv[Wv$informal_v2 == 1, ])
pu <- P[!is.na(P$urban), ]
ci$urban <- clustered_ci(pu[pu$urban == 1, ]); ci$rural <- clustered_ci(pu[pu$urban == 0, ])
ps <- P[!is.na(P$fem), ]
ci$male <- clustered_ci(ps[ps$fem == 0, ]); ci$female <- clustered_ci(ps[ps$fem == 1, ])
for (m in sort(unique(P$major))) ci[[paste0("major_", m)]] <- clustered_ci(P[P$major == m, ])
out$group_means_ci <- ci

inf <- list()
for (cn in countries) {
  g <- W[W$country == cn, ]
  gv <- g[!is.na(g$informal_v2), ]
  gf <- g[!is.na(g$informal), ]
  inf[[cn]] <- list(n_wage = nrow(g), n_answered = nrow(gv),
                    informal_v2 = round(mean(gv$informal_v2), 4),
                    informal_v2_wtd = round(wmean(gv$informal_v2, gv$weight), 4),
                    informal_own_rule = if (nrow(gf)) round(mean(gf$informal), 4) else NULL,
                    mean_formal = round(mean(gv[[A]][gv$informal_v2 == 0]), 4),
                    mean_informal = round(mean(gv[[A]][gv$informal_v2 == 1]), 4))
}
out$informality_by_country <- inf

# ---------------- C. difference tests ----------------
NAg <- P[P$status %in% c("wage_nonag", "selfemp_nonag"), ]
Wt <- Wv; Wt$infd <- as.numeric(Wt$informal_v2)  # R build writes the flag as TRUE/FALSE
out$tests <- list(
  wage_vs_self_nonag = fit(NAg, auto_genai ~ wage_d),
  wage_vs_self_nonag_cfe = fit(NAg, auto_genai ~ wage_d + factor(country)),
  informal_vs_formal = fit(Wt, auto_genai ~ infd),
  informal_vs_formal_cfe = fit(Wt, auto_genai ~ infd + factor(country)),
  female = fit(ps, auto_genai ~ fem),
  female_cfe = fit(ps, auto_genai ~ fem + factor(country)),
  urban = fit(pu, auto_genai ~ urban),
  urban_cfe = fit(pu, auto_genai ~ urban + factor(country)))

# ---------------- D. status regressions ----------------
out$status_reg <- list(
  m1 = fit(P, auto_genai ~ self_d + wage_d),
  m2 = fit(P, auto_genai ~ self_d + wage_d + factor(country)),
  m3 = fit(P, auto_genai ~ self_d + wage_d + urban + fem + age + factor(country)))

# ---------------- E. robustness ----------------
tasco <- startsWith(P$imputed_reason, "tasco_map")
sets <- list(baseline = P,
             own_use_excluded = P[P$imputed_reason != "own_use_farmer_family_use", ],
             coded_only = P[P$imputed == 0, ],
             drop_tasco_mapped = P[!tasco, ])
rob <- lapply(sets, stats)
for (cn in countries) for (k in c("baseline", "own_use_excluded", "coded_only")) {
  g <- sets[[k]]; rob[[paste0(k, "|", cn)]] <- stats(g[g$country == cn, ])
}
m6 <- X[X$isco08 >= 6000 & X$isco08 < 7000, ]
alts <- list(major6_mean = mean(m6$auto_genai),
             subsistence_mean = mean(X$auto_genai[X$isco08 %in% c(6310, 6320, 6330, 6340)]),
             min_major6 = min(m6$auto_genai), max_major6 = max(m6$auto_genai),
             elementary_agri_9211 = mean(X$auto_genai[X$isco08 == 9211]))
groups <- c(family_use = "own_use_farmer_family_use", tza_market = "own_use_farmer_market_oriented")
alt_out <- list()
for (gk in names(groups)) for (ak in names(alts)) {
  v <- alts[[ak]]; g <- P; g[[A]][g$imputed_reason == groups[[gk]]] <- v
  alt_out[[paste0(gk, "|", ak)]] <- list(
    assigned = round(v, 4), pooled_mean = round(mean(g[[A]]), 4),
    pooled_mean_wtd = round(wmean(g[[A]], g$weight), 4),
    nga_mean = round(mean(g[[A]][g$country == "Nigeria 2023"]), 4),
    tza_mean = round(mean(g[[A]][g$country == "Tanzania 2020"]), 4),
    agri_mean = round(mean(g[[A]][g$status == "agriculture"]), 4))
}
rob$imputed_alternatives <- alt_out
out$robustness <- rob

# ---------------- F. major-group profile ----------------
mj <- list()
for (k in c("pooled", countries)) {
  g <- if (k == "pooled") P else P[P$country == k, ]
  mj[[k]] <- list()
  for (m in sort(unique(g$major))) mj[[k]][[as.character(m)]] <- list(
    n = sum(g$major == m), share = round(100 * mean(g$major == m), 1),
    mean = round(mean(g[[A]][g$major == m]), 4))
}
out$major_profile <- mj
rs <- ifelse(P$imputed_reason == "", "coded", P$imputed_reason)
out$sample <- list(n = nrow(P), by_country = as.list(table(P$country)),
                   coded_4digit = sum(!is.na(P$isco08)), by_reason = as.list(table(rs)))

# ---------------- G. Ethiopia resident wage sample ----------------
Ev <- E[!is.na(E$informal_v2), ]
bym <- list()
for (m in sort(unique(E$major88))) bym[[as.character(m)]] <- list(
  n = sum(E$major88 == m), share = round(100 * mean(E$major88 == m), 1),
  mean = round(mean(E[[A]][E$major88 == m]), 4))
out$ethiopia_resident <- list(
  n = nrow(E), mean_unw = round(mean(E[[A]]), 4), mean_wtd = round(wmean(E[[A]], E$weight), 4),
  ci = clustered_ci(E), ci_wtd = clustered_ci(E, w = "weight"),
  informal = round(mean(Ev$informal_v2), 4), informal_wtd = round(wmean(Ev$informal_v2, Ev$weight), 4),
  ci_formal = clustered_ci(Ev[Ev$informal_v2 == 0, ]), ci_informal = clustered_ci(Ev[Ev$informal_v2 == 1, ]),
  by_major88 = bym)

write(toJSON(out, auto_unbox = TRUE, digits = 8, pretty = TRUE, null = "null"), "results/revision_v2_r.json")
cat("wrote results/revision_v2_r.json\n")
