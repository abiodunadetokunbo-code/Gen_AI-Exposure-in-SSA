# R twin of analysis_revision.py. Same inputs, same estimands.
# Writes results/revision_r.json for the R <-> Python cross-check.
suppressPackageStartupMessages({library(jsonlite)})

# NOTE (2026-09-20, plan step 12): reproduces the PRE-REVISION (v1) numbers and
# is kept as the record of the first submission. Reads and writes archive_v1/,
# so it cannot touch the live revision-2 files. Replaced by analysis_v2.R.
P <- read.csv("archive_v1/harmonized_workers.csv", stringsAsFactors = FALSE)
A <- "auto_genai"
out <- list()

wmean <- function(x, w) {
  k <- is.finite(x) & is.finite(w)
  sum(x[k] * w[k]) / sum(w[k])
}

# household-clustered SE of a mean (CR0, matching statsmodels cluster default)
clustered_ci <- function(d, col = A, cl = "hhid_c", w = NULL) {
  y <- d[[col]]; g <- d[[cl]]
  k <- !is.na(y) & !is.na(g)
  y <- y[k]; g <- g[k]
  if (is.null(w)) { ww <- rep(1, length(y)) } else { ww <- d[[w]][k]; k2 <- !is.na(ww)
    y <- y[k2]; g <- g[k2]; ww <- ww[k2] }
  n <- length(y)
  b <- sum(ww * y) / sum(ww)
  u <- ww * (y - b)                     # score for an intercept-only WLS
  sg <- tapply(u, g, sum)
  bread <- 1 / sum(ww)
  ncl <- length(sg)
  meat <- sum(sg^2)
  v <- bread^2 * meat * (ncl / (ncl - 1)) * ((n - 1) / (n - 1))
  se <- sqrt(v)
  list(mean = round(b, 4), se = round(se, 4),
       lo = round(b - 1.96 * se, 4), hi = round(b + 1.96 * se, 4), n = n)
}

# ---------------- A. weights ----------------
comp <- list()
for (cn in c(sort(unique(P$country)), "All (pooled)")) {
  g <- if (cn == "All (pooled)") P else P[P$country == cn, ]
  comp[[cn]] <- list(
    n = nrow(g),
    mean_unw = round(mean(g[[A]]), 4),
    mean_wtd = round(wmean(g[[A]], g$weight), 4),
    agri_unw = round(100 * mean(g$status == "agriculture"), 1),
    agri_wtd = round(100 * wmean(as.numeric(g$status == "agriculture"), g$weight), 1),
    urban_unw = round(100 * mean(g$urban, na.rm = TRUE), 1),
    urban_wtd = round(100 * wmean(g$urban, g$weight), 1),
    female_wtd = round(100 * wmean(as.numeric(g$sex == "female"), g$weight), 1))
}
out$country_composition_weighted <- comp
cw <- sapply(split(P, P$country), function(g) wmean(g[[A]], g$weight))
out$pooled_equal_country_mean <- round(mean(cw), 4)

# ---------------- B. group means with clustered CIs ----------------
ci <- list()
ci[["pooled"]] <- clustered_ci(P)
ci[["pooled_weighted"]] <- clustered_ci(P, w = "weight")
for (s in sort(unique(P$status))) {
  ci[[paste0("status_", s)]] <- clustered_ci(P[P$status == s, ])
  ci[[paste0("status_", s, "_wtd")]] <- clustered_ci(P[P$status == s, ], w = "weight")
}
W <- P[P$status == "wage_nonag" & !is.na(P$informal), ]
ci[["wage_formal"]] <- clustered_ci(W[W$informal == 0, ])
ci[["wage_informal"]] <- clustered_ci(W[W$informal == 1, ])
pu <- P[!is.na(P$urban), ]
ci[["urban"]] <- clustered_ci(pu[pu$urban == 1, ]); ci[["rural"]] <- clustered_ci(pu[pu$urban == 0, ])
ps <- P[!is.na(P$sex), ]
ci[["male"]] <- clustered_ci(ps[ps$sex == "male", ]); ci[["female"]] <- clustered_ci(ps[ps$sex == "female", ])
for (m in sort(unique(P$major[!is.na(P$major)]))) {
  ci[[paste0("major_", m)]] <- clustered_ci(P[!is.na(P$major) & P$major == m, ])
}
out$group_means_ci <- ci

# ---------------- C. status regression ----------------
R <- P
R$st <- factor(R$status, levels = c("agriculture", "selfemp_nonag", "wage_nonag", "other_nonag"))
m1 <- lm(auto_genai ~ st, data = R)
m2 <- lm(auto_genai ~ st + factor(country), data = R)
m3 <- lm(auto_genai ~ st + urban + factor(sex) + age + factor(country), data = R)
tidy <- function(m, pat) {
  co <- coef(m); keep <- grep(pat, names(co))
  r <- list()
  for (k in names(co)[keep]) r[[k]] <- round(unname(co[k]), 4)
  r[["_n"]] <- length(residuals(m)); r[["_r2"]] <- round(summary(m)$r.squared, 4)
  r
}
pat <- "^st|urban|sex|age|Intercept"
out$status_reg <- list(m1 = tidy(m1, pat), m2 = tidy(m2, pat), m3 = tidy(m3, pat))

# ---------------- D. robustness ----------------
sets <- list(
  baseline = P,
  drop_ethiopia = P[P$country != "Ethiopia 2021", ],
  drop_tza_imputed = P[P$imputed == 0, ],
  drop_both = P[P$country != "Ethiopia 2021" & P$imputed == 0, ])
rob <- list()
for (k in names(sets)) {
  g <- sets[[k]]
  rob[[k]] <- list(n = nrow(g), mean = round(mean(g[[A]]), 4),
                   mean_wtd = round(wmean(g[[A]], g$weight), 4),
                   agri_share = round(100 * mean(g$status == "agriculture"), 1),
                   agri_mean = round(mean(g[[A]][g$status == "agriculture"]), 4),
                   self_mean = round(mean(g[[A]][g$status == "selfemp_nonag"]), 4),
                   wage_mean = round(mean(g[[A]][g$status == "wage_nonag"]), 4),
                   near_zero = round(100 * mean(g[[A]] < 0.05), 1))
}
X <- read.csv("../crosswalks/isco08_to_exposure.csv")
m6 <- X[X$isco08 >= 6000 & X$isco08 < 7000, ]
alts <- list(
  flat_major6_baseline = mean(m6$auto_genai),
  subsistence_6xxx_only = mean(X$auto_genai[X$isco08 %in% c(6310, 6320, 6330, 6340)]),
  min_major6 = min(m6$auto_genai),
  max_major6 = max(m6$auto_genai),
  elementary_agri_9211 = mean(X$auto_genai[X$isco08 == 9211]))
alt_out <- list()
for (k in names(alts)) {
  v <- alts[[k]]; g <- P; g[[A]][g$imputed == 1] <- v
  alt_out[[k]] <- list(assigned = round(v, 4), pooled_mean = round(mean(g[[A]]), 4),
                       tza_mean = round(mean(g[[A]][g$country == "Tanzania 2020"]), 4),
                       agri_mean = round(mean(g[[A]][g$status == "agriculture"]), 4))
}
rob$tza_alternatives <- alt_out
out$robustness <- rob

# ---------------- E. cross-country regressions ----------------
cs <- read.csv("macro_country_cross_section.csv")
cs$lgdp <- log(cs$gdppc); cs$informal_s <- cs$informal / 100; cs$agri_s <- cs$selfemp_agri / 100
specs <- list("(1) informality" = share_exposed ~ informal_s,
              "(2) agri self-emp" = share_exposed ~ agri_s,
              "(3) log GDPpc" = share_exposed ~ lgdp,
              "(4) informality + log GDPpc" = share_exposed ~ informal_s + lgdp,
              "(5) agri + log GDPpc" = share_exposed ~ agri_s + lgdp,
              "(6) all three" = share_exposed ~ informal_s + agri_s + lgdp)
macro <- list()
for (k in names(specs)) {
  m <- lm(specs[[k]], data = cs)
  co <- coef(m); r <- list()
  for (p in names(co)) r[[p]] <- round(unname(co[p]), 4)
  r[["_n"]] <- length(residuals(m)); r[["_r2"]] <- round(summary(m)$r.squared, 3)
  macro[[k]] <- r
}
out$macro_reg <- macro
out$macro_corr <- list()
for (v in c("informal", "selfemp_agri", "gdppc", "lgdp")) {
  k <- !is.na(cs[[v]]) & !is.na(cs$share_exposed)
  out$macro_corr[[v]] <- list(pearson = round(cor(cs[[v]][k], cs$share_exposed[k]), 3),
                              spearman = round(cor(cs[[v]][k], cs$share_exposed[k], method = "spearman"), 3),
                              n = sum(k))
}

write(toJSON(out, auto_unbox = TRUE, digits = 8, pretty = TRUE), "archive_v1/results/revision_r.json")
cat("wrote archive_v1/results/revision_r.json\n")
