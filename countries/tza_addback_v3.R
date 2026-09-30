# R twin of tza_addback_v3.py (see its header for the full construction).
# Rebuilds the 1,789 Tanzanian non-farm business owners with no wage job,
# attaches weights under two scenarios (own y5_crossweight and the mean
# Tanzanian worker weight), imputes their exposure score under four flat
# values and an industry-linked route, and reports design-based country and
# pooled weighted means for every scenario.
suppressPackageStartupMessages(library(jsonlite))

num <- function(s) as.numeric(sub(".*?(-?\\d+\\.?\\d*).*", "\\1", as.character(s)))
Y <- function(s) as.numeric(sub(".*?(\\d).*", "\\1", as.character(s))) == 1

A <- "auto_genai"

# ============================================================ 1. rebuild the 1,789
e <- read.csv("TZA_2020_NPS-R5/hh_sec_e1.csv", stringsAsFactors = FALSE)
y5 <- Y(e$hh_e05); w3 <- Y(e$hh_e03)
nonfarm_biz <- y5 & !w3
nonfarm_biz[is.na(nonfarm_biz)] <- FALSE
n1789 <- sum(nonfarm_biz)
stopifnot(n1789 == 1789)
AB <- e[nonfarm_biz, c("y5_hhid", "indidy5")]
AB$indidy5 <- as.numeric(AB$indidy5)

# ============================================================ 2. weights (D1)
a <- read.csv("TZA_2020_NPS-R5/hh_sec_a.csv", stringsAsFactors = FALSE)
au <- a[, c("y5_hhid", "y5_rural", "y5_crossweight", "clusterid", "strataid", "tracking_class", "y5_cluster")]
au <- au[!is.na(au$y5_hhid), ]
au <- au[!duplicated(au$y5_hhid), ]
AB <- merge(AB, au, by = "y5_hhid", all.x = TRUE, sort = FALSE)
stopifnot(!anyNA(AB$y5_crossweight))

P <- read.csv("harmonized_workers_v2_R.csv", stringsAsFactors = FALSE)
TZA_P <- P[P$country == "Tanzania 2020", ]
mean_tza_weight <- sum(TZA_P$weight) / nrow(TZA_P)
cat(sprintf("mean Tanzanian worker weight (placeholder scenario) = %.2f\n", mean_tza_weight))
cat(sprintf("own-weight mean among the 1,789 = %.2f\n", mean(AB$y5_crossweight)))

WEIGHT_SCENARIOS <- list(own = AB$y5_crossweight, mean_placeholder = rep(mean_tza_weight, nrow(AB)))

# ============================================================ 3. flat imputation scores
ag_unw <- mean(P[P$status == "agriculture", A])
selfnonag <- P[P$status == "selfemp_nonag", ]
selfnonag_wtd <- sum(selfnonag[[A]] * selfnonag$weight) / sum(selfnonag$weight)
wagenonag <- P[P$status == "wage_nonag", ]
wagenonag_wtd <- sum(wagenonag[[A]] * wagenonag$weight) / sum(wagenonag$weight)
stopifnot(sum(P$country == "Tanzania 2020" & P$status == "selfemp_nonag") == 0)
cat(sprintf("flat scores: 0.000, agri_unw=%.4f, selfnonag_wtd=%.4f, wagenonag_wtd=%.4f\n",
            ag_unw, selfnonag_wtd, wagenonag_wtd))

FLAT_SCORES <- list(`0.000` = 0.0, `0.029_agri` = round(ag_unw, 4),
                    `0.128_selfnonag` = round(selfnonag_wtd, 4), `0.169_wagenonag` = round(wagenonag_wtd, 4))

# ============================================================ 4. industry imputation (D2)
n_ent <- read.csv("TZA_2020_NPS-R5/hh_sec_n.csv", stringsAsFactors = FALSE)
n_ent <- n_ent[!is.na(n_ent$hh_n02_3a), ]
n_ent$enterprise_id <- as.numeric(n_ent$enterprise_id)
owner_cols <- c("hh_n05_1", "hh_n05_2"); mgr_cols <- c("hh_n04a", "hh_n04b")
eng_cols <- paste0("hh_n03_", 1:6)

link_tier <- character(nrow(AB)); link_section <- rep(NA_real_, nrow(AB))
tier_counts <- c(owner = 0, manager = 0, engaged = 0, none = 0)
for (i in seq_len(nrow(AB))) {
  hh <- AB$y5_hhid[i]; pid <- AB$indidy5[i]
  cand <- n_ent[n_ent$y5_hhid == hh, ]
  tier <- "none"; sec <- NA_real_
  if (nrow(cand) > 0) {
    for (tn in list(list(owner_cols, "owner"), list(mgr_cols, "manager"), list(eng_cols, "engaged"))) {
      cols <- tn[[1]]; name <- tn[[2]]
      hitrows <- apply(cand[, cols, drop = FALSE], 1, function(r) any(r == pid, na.rm = TRUE))
      hit <- cand[hitrows, ]
      if (nrow(hit) > 0) {
        eid <- min(hit$enterprise_id)
        sec <- hit$hh_n02_3a[which(hit$enterprise_id == eid)[1]]
        tier <- name
        break
      }
    }
  }
  link_tier[i] <- tier; link_section[i] <- sec
  tier_counts[tier] <- tier_counts[tier] + 1
}
AB$link_tier <- link_tier; AB$section <- link_section
link_rate <- 100 * (1 - tier_counts["none"] / nrow(AB))
cat(sprintf("industry link: owner=%d manager=%d engaged=%d none=%d, link rate = %.1f%%\n",
            tier_counts["owner"], tier_counts["manager"], tier_counts["engaged"], tier_counts["none"], link_rate))
stopifnot(link_rate >= 60)

X <- read.csv("../crosswalks/isco08_to_exposure.csv")
g8path <- list.files("UGA_2019_UNPS", pattern = "^gsec8\\.csv$", recursive = TRUE, full.names = TRUE)[1]
g8 <- read.csv(g8path, stringsAsFactors = FALSE, encoding = "latin1")
iso <- num(g8$h8q19b_fourDigit)
dU <- data.frame(ix = seq_len(nrow(g8)) - 1, isco08 = iso)
dU <- dU[!is.na(dU$isco08) & dU$isco08 >= 1000 & dU$isco08 <= 9999, ]
dU <- merge(dU, X, by = "isco08", all.x = TRUE, sort = FALSE)
ugawage <- num(g8$s8q22) == 1
baseU <- data.frame(ix = seq_len(nrow(g8)) - 1, wage = ugawage, self = !ugawage,
                    section = floor(num(g8$h8q20b_oneDigit) / 10000), hhid = g8$hhid)
dU <- merge(dU, baseU, by = "ix", sort = FALSE)
g1u <- read.csv("UGA_2019_UNPS/UGA_2019_UNPS_v03_M_CSV/HH/gsec1.csv", stringsAsFactors = FALSE, encoding = "latin1")
g1u <- g1u[!is.na(g1u$hhid), c("hhid", "wgt")]
g1u <- g1u[!duplicated(g1u$hhid), ]
dU <- merge(dU, g1u, by = "hhid", all.x = TRUE, sort = FALSE)

mkstatus <- function(isco, wage, self_) {
  iso <- as.numeric(isco)
  agri <- (iso %/% 1000 == 6) | (iso %/% 10 %in% 921)
  ifelse(agri, "agriculture", ifelse(wage %in% TRUE, "wage_nonag", ifelse(self_ %in% TRUE, "selfemp_nonag", "other_nonag")))
}
dU$status <- mkstatus(dU$isco08, dU$wage, dU$self)
donor <- dU[dU$status == "selfemp_nonag", ]
stopifnot(!anyNA(donor$section))
donor_overall <- sum(donor[[A]] * donor$wgt) / sum(donor$wgt)
sec_levels <- sort(unique(donor$section))
donor_by_section <- data.frame(section = sec_levels,
  n = sapply(sec_levels, function(s) sum(donor$section == s)),
  wmean = sapply(sec_levels, function(s) { g <- donor[donor$section == s, ]; sum(g[[A]] * g$wgt) / sum(g$wgt) }))
cat(sprintf("donor pooled weighted mean (fallback) = %.4f\n", donor_overall))
print(donor_by_section)

sec_map <- setNames(donor_by_section$wmean, donor_by_section$section)
AB$industry_score <- sec_map[as.character(AB$section)]
n_section_matched <- sum(!is.na(AB$industry_score))
AB$industry_score[is.na(AB$industry_score)] <- donor_overall
implied_mean <- mean(AB$industry_score)
flat_lo <- min(unlist(FLAT_SCORES)); flat_hi <- max(unlist(FLAT_SCORES))
stopifnot(implied_mean >= flat_lo, implied_mean <= flat_hi)
cat(sprintf("industry route implied mean = %.4f, inside flat range [%.4f, %.4f]\n", implied_mean, flat_lo, flat_hi))

# ============================================================ 5. design ids
ng <- read.csv("../lsms_probe/w5/Post Harvest Wave 5/Household/secta_harvestw5.csv", stringsAsFactors = FALSE)
ng <- data.frame(hhid_c = paste0("NGA", ng$hhid), stratum = paste0("NGA-", ng$strata), psu = paste0("NGA-", ng$cluster))

boost <- a$tracking_class == 6
stopifnot(identical(boost, is.na(a$clusterid)), identical(boost, is.na(a$strataid)))
tzids <- data.frame(hhid_c = paste0("TZA", a$y5_hhid),
                    stratum = paste0("TZA-", ifelse(boost, paste0("booster-", substr(a$y5_cluster, 1, 2)),
                                                    sprintf("%.0f", a$strataid))),
                    psu = paste0("TZA-", ifelse(boost, a$y5_cluster, sprintf("%.0f", a$clusterid))))

ug <- read.csv("UGA_2019_UNPS/UGA_2019_UNPS_v03_M_CSV/HH/gsec1.csv", stringsAsFactors = FALSE)
parts <- c("dc_2018", "cc_2018", "sc_2018", "pc_2018")
has_par <- complete.cases(ug[, parts])
rural <- c("central_rural", "eastern_rural", "northern_rural", "western_rural")
ug_str <- ifelse(toupper(ug$district) %in% "KAMPALA", "kampala",
                 ifelse(ug$urban %in% 1, "other_urban", rural[ug$region]))
ug_str[!has_par] <- "no_location"
ug_psu <- ifelse(has_par, do.call(paste, c(lapply(ug[, parts], function(x) sprintf("%.0f", x)), sep = "-")),
                 paste0("hh-", ug$hhid))
ug <- data.frame(hhid_c = paste0("UGA", ug$hhid), stratum = paste0("UGA-", ug_str), psu = paste0("UGA-", ug_psu))

IDS <- rbind(ng, tzids, ug)
stopifnot(!anyDuplicated(IDS$hhid_c))
IDS$psu <- paste0(IDS$stratum, "|", IDS$psu)
IDS$stratum[IDS$stratum == "TZA-7"] <- "TZA-8"

AB$hhid_c <- paste0("TZA", AB$y5_hhid)
AB <- merge(AB, IDS[, c("hhid_c", "stratum", "psu")], by = "hhid_c", all.x = TRUE, sort = FALSE)
stopifnot(!anyNA(AB$stratum), !anyNA(AB$psu))

P <- merge(P, IDS[, c("hhid_c", "stratum", "psu")], by = "hhid_c", all.x = TRUE, sort = FALSE)
stopifnot(!anyNA(P$stratum), !anyNA(P$psu))

# ---------------- design machinery (matches survey_design_v3.R's hand-rolled linearization) ----------------
make_design <- function(d) {
  d$psu_f <- factor(d$psu)
  psu_codes <- as.integer(d$psu_f) - 1
  psu_names <- levels(d$psu_f)
  strat_of_psu <- tapply(as.character(d$stratum), d$psu_f, function(x) x[1])[psu_names]
  strat_f <- factor(strat_of_psu)
  psu_stratum <- as.integer(strat_f) - 1
  n_h <- as.integer(table(factor(psu_stratum, levels = 0:(nlevels(strat_f) - 1))))
  list(d = d, psu_codes = psu_codes, psu_stratum = psu_stratum, n_h = n_h, n_psu = length(psu_names))
}
design_var <- function(des, Z) {
  Z <- matrix(Z, nrow = nrow(des$d))
  T <- matrix(0, des$n_psu, ncol(Z))
  for (j in seq_len(ncol(Z))) T[, j] <- tapply(Z[, j], factor(des$psu_codes, levels = 0:(des$n_psu - 1)), sum, na.rm = TRUE)
  V <- matrix(0, ncol(Z), ncol(Z))
  for (h in unique(des$psu_stratum)) {
    idx <- which(des$psu_stratum == h)
    Th <- T[idx, , drop = FALSE]
    n <- length(idx)
    Dh <- sweep(Th, 2, colMeans(Th))
    V <- V + n / (n - 1) * t(Dh) %*% Dh
  }
  V
}
design_mean <- function(des, dom, col = A, w = NULL) {
  y <- des$d[[col]]
  dom <- dom & is.finite(y)
  wt <- if (is.null(w)) rep(1, nrow(des$d)) else des$d[[w]]
  wt <- wt * dom
  s <- sum(wt)
  m <- sum(wt * ifelse(dom, y, 0)) / s
  z <- wt * ifelse(dom, y - m, 0) / s
  se <- sqrt(design_var(des, z)[1, 1])
  list(mean = round(m, 4), se = round(se, 4), lo = round(m - 1.96 * se, 4), hi = round(m + 1.96 * se, 4), n = sum(dom))
}

run_scenario <- function(weight_vals, score_vals, label) {
  ab <- AB
  ab[[A]] <- score_vals
  ab$weight <- weight_vals
  ab$country <- "Tanzania 2020"
  cols <- c("country", "stratum", "psu", "weight", A)
  combined <- rbind(P[, cols], ab[, cols])
  des <- make_design(combined)
  d <- des$d
  countries <- sort(unique(d$country))
  yes <- rep(TRUE, nrow(d))
  pooled_unw <- round(mean(d[[A]]), 4)
  pooled_wtd_point <- round(sum(d[[A]] * d$weight) / sum(d$weight), 4)
  by_country <- setNames(lapply(countries, function(c) design_mean(des, d$country == c, w = "weight")), countries)
  pooled_design <- design_mean(des, yes, w = "weight")
  tza <- by_country[["Tanzania 2020"]]; uga <- by_country[["Uganda 2019"]]
  order_holds <- uga$mean > tza$mean
  overlap <- !(tza$hi < uga$lo || uga$hi < tza$lo)
  list(n_pooled = nrow(d), n_tanzania = sum(d$country == "Tanzania 2020"),
       pooled_mean_unweighted = pooled_unw, pooled_mean_weighted_point = pooled_wtd_point,
       pooled_weighted_design = pooled_design, by_country_weighted_design = by_country,
       order_nga_uga_tza_holds = order_holds, margin_uga_minus_tza = round(uga$mean - tza$mean, 4),
       intervals_overlap = overlap)
}

results <- list()
for (wscn in names(WEIGHT_SCENARIOS)) {
  wvals <- WEIGHT_SCENARIOS[[wscn]]
  for (skey in names(FLAT_SCORES)) {
    sval <- FLAT_SCORES[[skey]]
    results[[paste0(wscn, "|", skey)]] <- run_scenario(wvals, rep(sval, nrow(AB)), paste(wscn, "weight, flat score", sval))
  }
  results[[paste0(wscn, "|industry")]] <- run_scenario(wvals, AB$industry_score, paste(wscn, "weight, industry route"))
}

expected <- list(`0.000` = c(0.087, 0.035), `0.029_agri` = c(0.088, 0.041),
                 `0.128_selfnonag` = c(0.092, 0.060), `0.169_wagenonag` = c(0.093, 0.067))
mismatches <- c()
for (skey in names(expected)) {
  exp <- expected[[skey]]
  r <- results[[paste0("mean_placeholder|", skey)]]
  got_pooled <- r$pooled_weighted_design$mean
  got_tza <- r$by_country_weighted_design[["Tanzania 2020"]]$mean
  if (abs(got_pooled - exp[1]) > 0.001) mismatches <- c(mismatches, sprintf("%s: pooled %.4f vs expected %.3f", skey, got_pooled, exp[1]))
  if (abs(got_tza - exp[2]) > 0.001) mismatches <- c(mismatches, sprintf("%s: tanzania %.4f vs expected %.3f", skey, got_tza, exp[2]))
}
if (length(mismatches) > 0) {
  cat("REGRESSION TEST MISMATCHES:\n"); for (m in mismatches) cat(" ", m, "\n")
} else {
  cat("regression test passed: mean-weight scenario reproduces the verification file's sizing run\n")
  mismatches <- list()  # empty character(0) would serialize as {} rather than []; force a list
}

donor_by_section_out <- setNames(lapply(seq_len(nrow(donor_by_section)), function(i)
  list(n = donor_by_section$n[i], wmean = round(donor_by_section$wmean[i], 4))),
  as.character(as.integer(donor_by_section$section)))

out <- list(
  n_1789 = n1789,
  mean_tza_weight_placeholder = round(mean_tza_weight, 2),
  own_weight_mean_among_1789 = round(mean(AB$y5_crossweight), 2),
  flat_scores = FLAT_SCORES,
  industry_link = list(tier_counts = as.list(tier_counts), link_rate_pct = round(link_rate, 1),
                       n_section_matched = n_section_matched, donor_overall_wtd_mean = round(donor_overall, 4),
                       donor_by_section = donor_by_section_out,
                       implied_mean_unweighted = round(implied_mean, 4)),
  scenarios = results,
  regression_test_mismatches = mismatches
)
write(toJSON(out, auto_unbox = TRUE, digits = 8, pretty = TRUE), "results/tza_addback_v3_r.json")
cat("wrote results/tza_addback_v3_r.json\n")
