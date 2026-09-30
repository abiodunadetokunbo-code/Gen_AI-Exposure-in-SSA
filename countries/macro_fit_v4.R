# R twin of macro_fit_v4.py (see its header for the two metrics, the samples
# and the regression test). HC1 standard errors from sandwich::vcovHC, as in
# macro_ilostat_v2.R and atlas_ai_route_v2.R. Writes
# results/macro_fit_v4_r.json.
suppressPackageStartupMessages({ library(jsonlite); library(sandwich) })

RHS <- c("informal_s", "agri_s", "lgdp")
LABEL <- c(informal_s = "Informal employment rate",
           agri_s = "Agricultural self-employment",
           lgdp = "Log GDP per head")
OUTCOMES <- c(ai_route_share = "Atlas, exposed through AI",
              exp_lsms = "ILOSTAT rebuild")

C <- read.csv("atlas_ai_route_v2_countries_R.csv", stringsAsFactors = FALSE)
C$lgdp <- log(C$gdppc)
C$informal_s <- C$informal / 100
C$agri_s <- C$selfemp_agri / 100

fit <- function(y, terms, d) {
  d <- d[stats::complete.cases(d[, c(y, terms)]), ]
  m <- lm(stats::as.formula(paste(y, "~", paste(terms, collapse = " + "))), data = d)
  list(m = m, d = d, se = sqrt(diag(vcovHC(m, type = "HC1"))), co = coef(m))
}

# ---------------- regression test: reproduce Table 10 exactly ----------------
ATL <- fromJSON("results/atlas_ai_route_v2_r.json")$reg_ai_route_share
ILO <- fromJSON("results/macro_ilostat_v2_r.json")$reg_exp_lsms_all
REF <- list(ai_route_share = ATL, exp_lsms = ILO)

own_sample <- list(); mismatches <- character(0)
for (y in names(OUTCOMES)) {
  for (key in c("(1) informality", "(6) all three")) {
    terms <- if (key == "(1) informality") "informal_s" else RHS
    f <- fit(y, terms, C)
    ref <- REF[[y]][[key]]
    if (nrow(f$d) != ref$`_n`)
      mismatches <- c(mismatches, sprintf("%s/%s: n=%d vs %d", y, key, nrow(f$d), ref$`_n`))
    for (t in names(f$co)) {
      # the JSON twins store the intercept under statsmodels' name
      k <- if (t == "(Intercept)") "Intercept" else t
      if (abs(round(f$co[[t]], 4) - ref[[k]]$b) > 5e-4)
        mismatches <- c(mismatches, sprintf("%s/%s/%s: b=%.4f vs %s", y, key, k, f$co[[t]], ref[[k]]$b))
      if (abs(round(f$se[[t]], 4) - ref[[k]]$se) > 5e-4)
        mismatches <- c(mismatches, sprintf("%s/%s/%s: se=%.4f vs %s", y, key, k, f$se[[t]], ref[[k]]$se))
    }
    if (key == "(6) all three") own_sample[[y]] <- sort(f$d$iso3)
  }
}
stopifnot(length(mismatches) == 0)
cat(sprintf("regression test passed: reproduced Table 10 for both outcomes, n=%d Atlas and %d ILOSTAT\n",
            length(own_sample$ai_route_share), length(own_sample$exp_lsms)))

# ---------------- the common complete-case sample ----------------
S <- C[stats::complete.cases(C[, c(names(OUTCOMES), RHS)]), ]
common <- sort(S$iso3)
for (y in names(OUTCOMES)) stopifnot(all(common %in% own_sample[[y]]))
cat(sprintf("common complete-case sample: %d countries\n", length(common)))

# ---------------- standardised coefficients and incremental R-squared ----------------
metrics <- list()
for (y in names(OUTCOMES)) {
  f <- fit(y, RHS, S)
  r2_full <- summary(f$m)$r.squared
  sd_y <- sd(S[[y]])
  terms <- list()
  for (t in RHS) {
    drop <- setdiff(RHS, t)
    r2_drop <- summary(fit(y, drop, S)$m)$r.squared
    terms[[t]] <- list(label = unname(LABEL[[t]]),
                       b = round(f$co[[t]], 4),
                       se = round(f$se[[t]], 4),
                       beta_std = round(f$co[[t]] * sd(S[[t]]) / sd_y, 4),
                       incremental_r2 = round(r2_full - r2_drop, 4))
  }
  ranked_beta <- RHS[order(sapply(RHS, function(t) abs(terms[[t]]$beta_std)), decreasing = TRUE)]
  ranked_r2 <- RHS[order(sapply(RHS, function(t) terms[[t]]$incremental_r2), decreasing = TRUE)]
  metrics[[y]] <- list(outcome_label = unname(OUTCOMES[[y]]), n = nrow(S),
                       r2_full = round(r2_full, 4), sd_outcome = round(sd_y, 4),
                       terms = terms,
                       rank_by_abs_beta = unname(LABEL[ranked_beta]),
                       rank_by_incremental_r2 = unname(LABEL[ranked_r2]),
                       top_by_abs_beta = unname(LABEL[[ranked_beta[1]]]),
                       top_by_incremental_r2 = unname(LABEL[[ranked_r2[1]]]))
}

for (y in names(metrics)) {
  d <- metrics[[y]]
  cat(sprintf("\n%s (n=%d, R2=%.3f)\n", d$outcome_label, d$n, d$r2_full))
  cat(sprintf("  %-30s %9s %9s %9s\n", "term", "b", "std beta", "incr R2"))
  for (t in RHS) {
    r <- d$terms[[t]]
    cat(sprintf("  %-30s %9.4f %9.3f %9.4f\n", r$label, r$b, r$beta_std, r$incremental_r2))
  }
  cat(sprintf("  largest |std beta|: %s\n", d$top_by_abs_beta))
  cat(sprintf("  largest incremental R2: %s\n", d$top_by_incremental_r2))
}

income_first <- all(sapply(metrics, function(d)
  d$top_by_abs_beta == LABEL[["lgdp"]] && d$top_by_incremental_r2 == LABEL[["lgdp"]]))
cat(sprintf("\nincome per head ranks first on both metrics and both outcomes: %s\n", income_first))

out <- list(common_sample = common, n_common = length(common),
            own_sample_n = lapply(own_sample, length),
            metrics = metrics,
            income_ranks_first_everywhere = income_first)
write(toJSON(out, auto_unbox = TRUE, digits = NA, pretty = TRUE),
      "results/macro_fit_v4_r.json")
cat("wrote results/macro_fit_v4_r.json\n")
