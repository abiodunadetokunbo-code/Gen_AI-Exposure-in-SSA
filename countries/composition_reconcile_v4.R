# R twin of composition_reconcile_v4.py (see its header for the construction
# and for what the two results prove). Reads the same raw ILOSTAT files and the
# R build's worker file, and writes results/composition_reconcile_v4_r.json.
suppressPackageStartupMessages({ library(jsonlite) })

MAJ <- paste0("OCU_ISCO08_", 1:9)
THREE <- c("NGA", "TZA", "UGA")
SURVEY_YEAR <- list(NGA = 2023, TZA = 2020, UGA = 2019)
GROUP_NAME <- c("Managers", "Professionals", "Technicians and associates",
                "Clerical support", "Service and sales", "Skilled agriculture",
                "Craft and trades", "Plant and machine operators",
                "Elementary occupations")

X <- read.csv("../crosswalks/isco08_to_exposure.csv")
P <- read.csv("harmonized_workers_v2_R.csv", stringsAsFactors = FALSE)
P$imputed_reason[is.na(P$imputed_reason)] <- ""

# Identical to composition_cf_v3.R's build_shares, minus the x_pct gate this
# script does not need. Kept local so it reads the same raw files.
build_shares <- function(pattern) {
  files <- sort(Sys.glob(pattern))
  D <- do.call(rbind, lapply(files, function(f) {
    if (!startsWith(readLines(f, n = 1, warn = FALSE), "DATAFLOW")) return(NULL)
    read.csv(f, stringsAsFactors = FALSE)[, c("REF_AREA", "OCU", "TIME_PERIOD", "OBS_VALUE")]
  }))
  D <- D[startsWith(D$OCU, "OCU_ISCO08") & D$TIME_PERIOD >= 2015, ]
  D <- D[D$TIME_PERIOD == ave(D$TIME_PERIOD, D$REF_AREA, FUN = max), ]
  iso <- sort(unique(D$REF_AREA))
  val <- function(code) sapply(iso, function(a) {
    v <- D$OBS_VALUE[D$REF_AREA == a & D$OCU == code]; if (length(v)) v[1] else NA })
  S <- sapply(1:9, function(i) val(MAJ[i]))
  stopifnot(!anyNA(S))
  rownames(S) <- iso
  list(share = S / rowSums(S),
       year = sapply(iso, function(a) D$TIME_PERIOD[D$REF_AREA == a][1]), iso = iso)
}

AFR <- build_shares("../ilostat/raw/*.csv")

wm <- function(x, w) sum(x * w) / sum(w)
by_major <- function(d) sapply(1:9, function(m) { k <- d$major == m; wm(d$auto_genai[k], d$weight[k]) })
VECS <- list(exp_unit = sapply(1:9, function(m) mean(X$auto_genai[X$isco08 %/% 1000 == m])),
             exp_lsms = by_major(P),
             exp_lsms_ex = by_major(P[P$imputed_reason != "own_use_farmer_family_use", ]))
YS <- names(VECS)
HEADLINE_VEC <- "exp_lsms"

# ---------------- country weight shares, as composition_cf_v3.R builds them ----------------
SD3 <- fromJSON("results/survey_design_v3_r.json")
wt <- c(NGA = SD3$weight_totals$`Nigeria 2023`$sum_weight,
        TZA = SD3$weight_totals$`Tanzania 2020`$sum_weight,
        UGA = SD3$weight_totals$`Uganda 2019`$sum_weight)
tot <- SD3$weight_totals$pooled$sum_weight
stopifnot(abs(sum(wt) - tot) < 1e-6)
wshare <- wt / tot
stopifnot(abs(sum(wshare) - 1) < 1e-9)

# ---------------- regression test against composition_cf_v3 ----------------
CF3 <- fromJSON("results/composition_cf_v3_r.json")
pooled_ilostat <- list()
for (y in YS) {
  a <- as.numeric(AFR$share %*% VECS[[y]]); names(a) <- AFR$iso
  pooled <- sum(sapply(THREE, function(i) wshare[[i]] * a[[i]]))
  pooled_ilostat[[y]] <- pooled
  ref <- CF3$these_economies[[y]]$pooled_actual_ilostat
  stopifnot(abs(round(pooled, 4) - ref) < 5e-4)
}
cat(sprintf("regression test passed: reproduced composition_cf_v3's pooled_actual_ilostat for all %d score vectors\n",
            length(YS)))

# ---------------- pooled employment shares from each source ----------------
S_ilo <- sapply(1:9, function(j) sum(sapply(THREE, function(i) wshare[[i]] * AFR$share[i, j])))
stopifnot(abs(sum(S_ilo) - 1) < 1e-9)

S_lsms <- sapply(1:9, function(j) sum(P$weight[P$major == j]) / sum(P$weight))
S_lsms[is.na(S_lsms)] <- 0
stopifnot(abs(sum(S_lsms) - 1) < 1e-9)

# ---------------- the zero-residual identity ----------------
v_head <- VECS[[HEADLINE_VEC]]
direct <- wm(P$auto_genai, P$weight)
via_groups <- sum(S_lsms * v_head)
residual <- direct - via_groups
stopifnot(abs(residual) < 1e-12)
cat(sprintf("zero-residual identity holds: direct=%.6f, via major groups=%.6f, residual=%.2e\n",
            direct, via_groups, residual))

SD2 <- fromJSON("results/survey_design_v2_r.json")
survey_pooled_weighted <- SD2$group_means_ci$pooled_weighted$mean
stopifnot(abs(round(direct, 4) - survey_pooled_weighted) < 5e-4)

# ---------------- decompose the difference by major group ----------------
diff_total <- pooled_ilostat[[HEADLINE_VEC]] - direct
contrib <- (S_ilo - S_lsms) * v_head
stopifnot(abs(sum(contrib) - diff_total) < 1e-9)

# ---------------- what sits in major group 1 in this sample ----------------
# The manager term is the single largest piece of the difference, so record
# what these workers are, rather than leaving the reader to guess.
M1 <- P[P$major == 1, ]
m1_status <- tapply(M1$weight, M1$status, sum) / sum(M1$weight)
m1_isco <- sort(tapply(M1$weight, M1$isco08, sum) / sum(M1$weight), decreasing = TRUE)
m1_top_isco <- as.integer(names(m1_isco)[1])
cat(sprintf("major group 1 in the LSMS sample: %d workers, %.0f%% of the weight own-account non-agricultural, top ISCO code %d at %.0f%%\n",
            nrow(M1), 100 * m1_status[["selfemp_nonag"]], m1_top_isco, 100 * m1_isco[[1]]))

ranked <- order(abs(contrib), decreasing = TRUE)
cat(sprintf("difference %+.4f = ILOSTAT %.4f minus LSMS %.4f\n",
            diff_total, pooled_ilostat[[HEADLINE_VEC]], direct))
for (j in ranked[1:3]) {
  cat(sprintf("  group %d %-28s ILO %5.1f%%  LSMS %5.1f%%  -> %+.4f\n",
              j, GROUP_NAME[j], 100 * S_ilo[j], 100 * S_lsms[j], contrib[j]))
}
top <- ranked[1]
top_share <- contrib[top] / diff_total

nm <- function(v, d) as.list(setNames(round(v, d), as.character(1:9)))
out <- list(
  headline_vector = HEADLINE_VEC,
  survey_year = SURVEY_YEAR,
  ilostat_year = lapply(setNames(THREE, THREE), function(i) as.integer(AFR$year[[i]])),
  country_weight_share = lapply(setNames(THREE, THREE), function(i) round(wshare[[i]], 4)),
  score_vector = nm(v_head, 4),
  pooled_share_ilostat = nm(S_ilo, 4),
  pooled_share_lsms = nm(S_lsms, 4),
  pooled_ilostat_by_vector = lapply(pooled_ilostat, function(v) round(v, 4)),
  pooled_ilostat = round(pooled_ilostat[[HEADLINE_VEC]], 4),
  pooled_lsms_direct = round(direct, 4),
  pooled_lsms_via_major_groups = round(via_groups, 4),
  aggregation_residual = round(residual, 10),
  difference = round(diff_total, 4),
  difference_by_group = nm(contrib, 4),
  largest_group = as.integer(top),
  largest_group_name = GROUP_NAME[top],
  largest_group_share_of_difference = round(top_share, 4),
  manager_share_ilostat_pct = round(100 * S_ilo[1], 1),
  manager_share_lsms_pct = round(100 * S_lsms[1], 1),
  manager_term = round(contrib[1], 4),
  service_share_ilostat_pct = round(100 * S_ilo[5], 1),
  service_share_lsms_pct = round(100 * S_lsms[5], 1),
  service_term = round(contrib[5], 4),
  major1_n = nrow(M1),
  major1_status_share = as.list(round(m1_status[order(names(m1_status))], 4)),
  major1_selfemp_nonag_pct = round(100 * m1_status[["selfemp_nonag"]], 1),
  major1_top_isco = m1_top_isco,
  major1_top_isco_pct = round(100 * m1_isco[[1]], 1),
  n_workers = nrow(P)
)
write(toJSON(out, auto_unbox = TRUE, digits = NA, pretty = TRUE),
      "results/composition_reconcile_v4_r.json")
cat("wrote results/composition_reconcile_v4_r.json\n")
