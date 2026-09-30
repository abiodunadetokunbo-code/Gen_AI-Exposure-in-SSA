# R twin of composition_cf_v3.py (see its header for the construction and the
# reason the benchmark files sit in their own directory). Reads the same
# ILOSTAT files and the R build's worker file, and writes
# results/composition_cf_v3_r.json.
suppressPackageStartupMessages({ library(jsonlite) })

MAJ <- paste0("OCU_ISCO08_", 1:9)
X <- read.csv("../crosswalks/isco08_to_exposure.csv")
P <- read.csv("harmonized_workers_v2_R.csv", stringsAsFactors = FALSE)
P$imputed_reason[is.na(P$imputed_reason)] <- ""

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
  xv <- val("OCU_ISCO08_X"); xv[is.na(xv)] <- 0
  list(share = S / rowSums(S), x_pct = 100 * xv / val("OCU_ISCO08_TOTAL"),
       year = sapply(iso, function(a) D$TIME_PERIOD[D$REF_AREA == a][1]), iso = iso)
}

AFR <- build_shares("../ilostat/raw/*.csv")
BMK <- build_shares("../ilostat/raw_benchmark/*.csv")

BENCHMARKS <- c("GBR", "DEU", "FRA")
HEADLINE <- "GBR"
for (c in BENCHMARKS) {
  stopifnot(c %in% BMK$iso)
  stopifnot(abs(sum(BMK$share[c, ]) - 1) < 1e-9)
  stopifnot(BMK$x_pct[[c]] < 20)
}
cat("benchmark gate: all of", paste(BENCHMARKS, collapse = ", "),
    "pass (shares sum to 1, x_pct < 20%)\n")

wm <- function(x, w) sum(x * w) / sum(w)
by_major <- function(d) sapply(1:9, function(m) { k <- d$major == m; wm(d$auto_genai[k], d$weight[k]) })
VECS <- list(exp_unit = sapply(1:9, function(m) mean(X$auto_genai[X$isco08 %/% 1000 == m])),
             exp_lsms = by_major(P),
             exp_lsms_ex = by_major(P[P$imputed_reason != "own_use_farmer_family_use", ]))
YS <- names(VECS)

# ---------------- regression test against macro_ilostat_v2 ----------------
V2 <- fromJSON("results/macro_ilostat_v2_r.json")
actual <- list(); mismatches <- character(0)
for (y in YS) {
  a <- as.numeric(AFR$share %*% VECS[[y]]); names(a) <- AFR$iso
  actual[[y]] <- a
  for (iso3 in AFR$iso) {
    v2v <- V2$countries[[iso3]][[y]]
    if (is.null(v2v)) next
    if (abs(round(a[[iso3]], 4) - v2v) > 5e-4)
      mismatches <- c(mismatches, sprintf("%s/%s: v3=%.4f v2=%s", y, iso3, a[[iso3]], v2v))
  }
}
stopifnot(length(mismatches) == 0)
cat(sprintf("regression test passed: reproduced macro_ilostat_v2's actual exposure for %d African countries across all 3 score vectors\n",
            length(actual$exp_lsms)))

# ---------------- counterfactual ----------------
cf <- list()
for (bc in BENCHMARKS) for (y in YS) cf[[paste0(bc, "|", y)]] <- sum(BMK$share[bc, ] * VECS[[y]])

# ---------------- reading 1: these economies, pooled on the headline weight shares ----------------
SD3 <- fromJSON("results/survey_design_v3_r.json")
wt <- c(NGA = SD3$weight_totals$`Nigeria 2023`$sum_weight,
        TZA = SD3$weight_totals$`Tanzania 2020`$sum_weight,
        UGA = SD3$weight_totals$`Uganda 2019`$sum_weight)
tot <- SD3$weight_totals$pooled$sum_weight
stopifnot(abs(sum(wt) - tot) < 1e-6)
wshare <- wt / tot
stopifnot(abs(sum(wshare) - 1) < 1e-9)

these <- list()
for (y in YS) {
  a3 <- lapply(setNames(c("NGA", "TZA", "UGA"), c("NGA", "TZA", "UGA")),
               function(i) round(actual[[y]][[i]], 4))
  pooled_actual <- sum(sapply(names(wshare), function(i) wshare[[i]] * actual[[y]][[i]]))
  row <- list(actual_by_country = a3, pooled_actual_ilostat = round(pooled_actual, 4))
  for (bc in BENCHMARKS) {
    row[[paste0("cf_", bc)]] <- round(cf[[paste0(bc, "|", y)]], 4)
    row[[paste0("gap_", bc)]] <- round(cf[[paste0(bc, "|", y)]] - pooled_actual, 4)
  }
  these[[y]] <- row
}
V2R <- fromJSON("results/survey_design_v2_r.json")
survey_pooled_weighted <- V2R$group_means_ci$pooled_weighted$mean

# ---------------- reading 2: the average African country, decomposed by major group ----------------
avg_share <- colMeans(AFR$share)
stopifnot(abs(sum(avg_share) - 1) < 1e-9)

decomp <- list()
for (bc in BENCHMARKS) for (y in YS) {
  contrib <- (BMK$share[bc, ] - avg_share) * VECS[[y]]
  total <- sum(contrib)
  cf_val <- cf[[paste0(bc, "|", y)]]
  avg_actual <- sum(avg_share * VECS[[y]])
  stopifnot(abs(total - (cf_val - avg_actual)) < 1e-9)
  decomp[[paste0(bc, "|", y)]] <- list(
    avg_african_actual = round(avg_actual, 4), cf = round(cf_val, 4), gap = round(total, 4),
    by_group = setNames(as.list(round(contrib, 4)), as.character(1:9)),
    top_group = which.max(abs(contrib)))
}

hd <- decomp[[paste0(HEADLINE, "|exp_lsms")]]
share_46 <- (hd$by_group[["4"]] + hd$by_group[["6"]]) / hd$gap
cat(sprintf("headline (%s, exp_lsms): average African actual=%.4f, cf=%.4f, gap=%.4f; groups 4+6 carry %.1f%% of the gap\n",
            HEADLINE, hd$avg_african_actual, hd$cf, hd$gap, 100 * share_46))

out <- list(
  benchmarks = BENCHMARKS, headline_benchmark = HEADLINE,
  x_pct = lapply(setNames(BENCHMARKS, BENCHMARKS), function(c) round(BMK$x_pct[[c]], 2)),
  benchmark_year = lapply(setNames(BENCHMARKS, BENCHMARKS), function(c) as.integer(BMK$year[[c]])),
  vectors = lapply(VECS, function(v) setNames(as.list(round(v, 4)), as.character(1:9))),
  cf = lapply(cf, function(v) round(v, 4)),
  these_economies = these,
  survey_pooled_weighted_headline = survey_pooled_weighted,
  average_african_country = decomp,
  group_46_share_of_gap_headline = round(share_46, 4),
  n_african_countries = length(AFR$iso))

write(toJSON(out, auto_unbox = TRUE, digits = 8, pretty = TRUE), "results/composition_cf_v3_r.json")
cat("wrote results/composition_cf_v3_r.json\n")
