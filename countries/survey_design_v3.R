# R twin of survey_design_v3.py (see its header for what this adds: the
# weighted formal/informal, urban/rural, male/female and major-group means,
# plus weight totals by country). Reads the same v2 worker file and the v2
# design-id file that survey_design_v2.R already built; does not touch either.
suppressPackageStartupMessages({library(survey); library(jsonlite)})
options(survey.lonely.psu = "fail")

A <- "auto_genai"
P <- read.csv("harmonized_workers_v2_R.csv", stringsAsFactors = FALSE)
IDS <- read.csv("survey_design_ids_v2_R.csv", stringsAsFactors = FALSE)[, c("hhid_c", "stratum", "psu")]
P <- merge(P, IDS, by = "hhid_c", all.x = TRUE, sort = FALSE)
stopifnot(!anyNA(P$psu))

V2 <- fromJSON("results/survey_design_v2_r.json")

P$fem <- ifelse(is.na(P$sex), NA, as.numeric(P$sex == "female"))
P$one <- 1
des <- function(d, w) svydesign(ids = ~psu, strata = ~stratum, weights = as.formula(paste0("~", w)),
                                data = d, nest = TRUE)
D <- des(P, "one"); DW <- des(P, "weight")

r4 <- function(x) round(unname(x), 4)
m <- function(dsn, cond) {
  cond <- cond & !is.na(dsn$variables[[A]])
  est <- svymean(as.formula(paste0("~", A)), subset(dsn, cond))
  b <- coef(est); se <- as.numeric(SE(est))
  list(mean = r4(b), se = r4(se), lo = r4(b - 1.96 * se), hi = r4(b + 1.96 * se), n = sum(cond))
}

v <- D$variables
st <- v$status; ctry <- v$country; yes <- rep(TRUE, nrow(v))
wage <- st == "wage_nonag"
cn <- sort(unique(ctry))

# ---------------- regression test: reproduce every v2 group_means_ci key ----------------
regress <- list(pooled = m(D, yes), pooled_weighted = m(DW, yes))
for (c in cn) {
  regress[[paste0("country|", c)]] <- m(D, ctry == c)
  regress[[paste0("country_wtd|", c)]] <- m(DW, ctry == c)
}
for (s in sort(unique(st))) {
  regress[[paste0("status_", s)]] <- m(D, st == s)
  regress[[paste0("status_", s, "_wtd")]] <- m(DW, st == s)
  for (c in cn) if (any(st == s & ctry == c)) regress[[paste0("status_", s, "|", c)]] <- m(D, st == s & ctry == c)
}
regress$wage_formal <- m(D, wage & v$informal_v2 %in% 0)
regress$wage_informal <- m(D, wage & v$informal_v2 %in% 1)
regress$urban <- m(D, v$urban %in% 1); regress$rural <- m(D, v$urban %in% 0)
regress$male <- m(D, v$fem %in% 0); regress$female <- m(D, v$fem %in% 1)
for (mj in sort(unique(v$major))) regress[[paste0("major_", mj)]] <- m(D, v$major == mj)

mismatches <- c()
for (k in names(regress)) {
  v2k <- V2$group_means_ci[[k]]
  if (is.null(v2k)) { mismatches <- c(mismatches, paste0(k, ": not in v2 at all")); next }
  for (f in c("mean", "se", "lo", "hi", "n")) {
    if (abs(regress[[k]][[f]] - v2k[[f]]) > 5e-4) {
      mismatches <- c(mismatches, sprintf("%s.%s: v3=%s v2=%s", k, f, regress[[k]][[f]], v2k[[f]]))
    }
  }
}
if (length(mismatches) > 0) stop("v3 does not reproduce v2 group_means_ci:\n", paste(mismatches, collapse = "\n"))
cat(sprintf("regression test passed: %d v2 group_means_ci keys reproduced to the last decimal\n", length(regress)))

# ---------------- step 2: the new weighted groups ----------------
new_ci <- list()
new_ci$wage_formal_wtd <- m(DW, wage & v$informal_v2 %in% 0)
new_ci$wage_informal_wtd <- m(DW, wage & v$informal_v2 %in% 1)
new_ci$urban_wtd <- m(DW, v$urban %in% 1)
new_ci$rural_wtd <- m(DW, v$urban %in% 0)
new_ci$male_wtd <- m(DW, v$fem %in% 0)
new_ci$female_wtd <- m(DW, v$fem %in% 1)
for (mj in sort(unique(v$major))) new_ci[[paste0("major_", mj, "_wtd")]] <- m(DW, v$major == mj)

gap <- new_ci$wage_formal_wtd$mean - new_ci$wage_informal_wtd$mean
cat(sprintf("wage_formal_wtd - wage_informal_wtd = %.4f (cf. weighted regression informal_vs_formal_cfe_wtd = -0.1080)\n", gap))

# ---------------- step 3: weight totals by country ----------------
wsum <- tapply(v$weight, ctry, sum)
pooled_w <- sum(v$weight)
wt_out <- list()
for (c in cn) {
  n_c <- sum(ctry == c)
  wt_out[[c]] <- list(sum_weight = round(unname(wsum[c]), 0),
                       share_of_pooled = round(100 * unname(wsum[c]) / pooled_w, 1),
                       mean_weight = round(unname(wsum[c]) / n_c, 0), n = n_c)
}
wt_out$pooled <- list(sum_weight = round(pooled_w, 0), share_of_pooled = 100.0, n = nrow(v))

implied <- sum(sapply(cn, function(c) wsum[c] / pooled_w * V2$group_means_ci[[paste0("country_wtd|", c)]]$mean))
cat(sprintf("weight-share-weighted average of country means = %.4f (cf. pooled_weighted mean = %.4f)\n",
            implied, V2$group_means_ci$pooled_weighted$mean))
stopifnot(abs(implied - V2$group_means_ci$pooled_weighted$mean) < 5e-4)

out <- list(group_means_ci_v3_additions = new_ci, weight_totals = wt_out,
            wage_formal_minus_informal_wtd = round(gap, 4),
            weight_share_weighted_avg_check = round(implied, 4))
write(toJSON(out, auto_unbox = TRUE, digits = 8, pretty = TRUE), "results/survey_design_v3_r.json")
cat("wrote results/survey_design_v3_r.json\n")
