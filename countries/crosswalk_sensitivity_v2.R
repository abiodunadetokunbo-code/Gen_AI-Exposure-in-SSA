# R twin of crosswalk_sensitivity_v2.py (see its header for the rules). Reads the
# R build's worker file and writes results/crosswalk_sensitivity_v2_r.json. The
# random draws use R's own generator (seed 20260919), so crosscheck_v2.py
# compares their summaries at a looser tolerance than the fixed alternatives.
suppressPackageStartupMessages(library(jsonlite))

SEED <- 20260919; NDRAW <- 2000
X <- read.csv("../crosswalks/isco08_to_exposure.csv", stringsAsFactors = FALSE)
L <- read.csv("../crosswalks/isco08_to_onetsoc10.csv", stringsAsFactors = FALSE)
O <- read.csv("../atlas_data/althoff_occ_exposure_onetsoc.csv", stringsAsFactors = FALSE)[, c("soc_code_onet", "auto_genai")]
P <- read.csv("harmonized_workers_v2_R.csv", stringsAsFactors = FALSE)
P$imputed_reason[is.na(P$imputed_reason)] <- ""
A <- "auto_genai"

LE <- merge(L, O, by.x = "onetsoc10", by.y = "soc_code_onet")
LE <- LE[order(LE$isco08, LE$onetsoc10), ]

# US employment per linked O*NET occupation, for the employment-weighted variant.
OEWS <- as.data.frame(readxl::read_excel("../oews/oesm18nat/national_M2018_dl.xlsx"))
OEWS$TOT_EMP <- suppressWarnings(as.numeric(OEWS$TOT_EMP))
emp_det <- setNames(OEWS$TOT_EMP[OEWS$OCC_GROUP == "detailed"], OEWS$OCC_CODE[OEWS$OCC_GROUP == "detailed"])
emp_brd <- setNames(OEWS$TOT_EMP[OEWS$OCC_GROUP == "broad"], OEWS$OCC_CODE[OEWS$OCC_GROUP == "broad"])
soc6 <- substr(LE$onetsoc10, 1, 7)
unit <- ifelse(soc6 %in% names(emp_det), soc6, paste0(substr(soc6, 1, 6), "0"))
emp_unit <- unname(ifelse(unit %in% names(emp_det), emp_det[unit], emp_brd[unit]))
LE$emp <- emp_unit / as.numeric(table(unit)[unit])
codes <- X$isco08
direct <- X$match == "direct"

fill <- function(v) {
  d <- v[direct]; dc <- codes[direct]
  g3 <- tapply(d, dc %/% 10, mean); g2 <- tapply(d, dc %/% 100, mean)
  for (i in which(X$match == "impute_3dig")) v[i] <- g3[[as.character(codes[i] %/% 10)]]
  for (i in which(X$match == "impute_2dig")) v[i] <- g2[[as.character(codes[i] %/% 100)]]
  v
}
agg <- function(f) {
  r <- tapply(LE[[A]], LE$isco08, f)
  v <- rep(NA_real_, length(codes)); v[match(as.numeric(names(r)), codes)] <- r
  fill(v)
}
# Employment-weighted mean; ISCO codes with no OEWS figure keep the simple mean.
agg_emp <- function() {
  d <- LE[!is.na(LE$emp) & LE$emp > 0, ]
  r <- tapply(seq_len(nrow(d)), d$isco08, function(i) sum(d[[A]][i] * d$emp[i]) / sum(d$emp[i]))
  v <- rep(NA_real_, length(codes)); v[match(as.numeric(names(r)), codes)] <- r
  back <- codes %in% LE$isco08 & is.na(v)
  v[back] <- agg(mean)[back]
  list(v = fill(v), n_back = sum(back), n_wtd = length(r))
}

fam <- P$imputed_reason == "own_use_farmer_family_use"
mkt <- P$imputed_reason == "own_use_farmer_market_oriented"
subr <- which(P$imputed_reason == "tasco_map_submajor")
coded <- !is.na(P$isco08)
idx <- match(P$isco08[coded], codes)
XS0 <- tapply(X[[A]], codes %/% 10, mean)
sub_of <- sapply(subr, function(i) as.numeric(names(XS0)[abs(XS0 - P[[A]][i]) < 1e-12]))

workers <- function(v) {
  y <- numeric(nrow(P))
  y[coded] <- v[idx]
  y[fam] <- mean(v[match(c(6310, 6320, 6330, 6340), codes)])
  y[mkt] <- mean(v[codes %/% 1000 == 6])
  sm <- tapply(v, codes %/% 10, mean)
  y[subr] <- sm[as.character(sub_of)]
  y
}

w <- P$weight
cn <- sort(unique(P$country))
m4 <- P$major == 4; m6 <- P$major == 6
wm <- function(x, ww) sum(x * ww) / sum(ww)
stats <- function(y) {
  st <- sapply(c("agriculture", "selfemp_nonag", "wage_nonag"), function(s) mean(y[P$status == s]))
  r <- c(pooled = mean(y), pooled_wtd = wm(y, w))
  for (c in cn) r[paste0("wtd|", c)] <- wm(y[P$country == c], w[P$country == c])
  r <- c(r, st, wage_minus_self = unname(st["wage_nonag"] - st["selfemp_nonag"]),
         clerical = mean(y[m4]), skilled_agri = mean(y[m6]), clerical_over_agri = mean(y[m4]) / mean(y[m6]))
  r
}

base <- agg(mean)
stopifnot(max(abs(base - X[[A]])) < 1e-9, max(abs(workers(base) - P[[A]])) < 1e-9)
out <- list()
for (nm in c("mean", "median", "min", "max")) out[[nm]] <- as.list(round(stats(workers(agg(get(nm)))), 4))
ew <- agg_emp()
out$emp_weighted <- as.list(round(stats(workers(ew$v)), 4))

set.seed(SEED)
grp <- split(LE[[A]], LE$isco08)
gpos <- match(as.numeric(names(grp)), codes)
D <- t(sapply(seq_len(NDRAW), function(i) {
  v <- rep(NA_real_, length(codes))
  v[gpos] <- vapply(grp, function(g) g[sample.int(length(g), 1)], numeric(1))
  stats(workers(fill(v)))
}))
q <- function(x, p) unname(quantile(x, p, type = 7))
out$draws <- lapply(setNames(colnames(D), colnames(D)), function(k) list(
  mean = round(mean(D[, k]), 4), sd = round(sd(D[, k]), 4),
  p025 = round(q(D[, k], 0.025), 4), p975 = round(q(D[, k], 0.975), 4)))
out$draws_share_wage_above_self <- round(mean(D[, "wage_minus_self"] > 0), 3)
out$draws_share_clerical_over_agri_gt_10 <- round(mean(D[, "clerical_over_agri"] > 10), 3)
out$meta <- list(n_draws = NDRAW, seed = SEED, isco_codes_linked = length(grp),
                 isco_single_link = sum(lengths(grp) == 1),
                 oews_release = "May 2018 national, 2010 SOC",
                 onetsoc_with_employment = sum(!is.na(LE$emp) & LE$emp > 0),
                 onetsoc_linked = nrow(LE),
                 isco_employment_weighted = ew$n_wtd,
                 isco_fell_back_to_mean = ew$n_back)

write(toJSON(out, auto_unbox = TRUE, digits = 8, pretty = TRUE), "results/crosswalk_sensitivity_v2_r.json")
cat("mean reproduces the exposure file and the worker file to 1e-9\n")
cat("wrote results/crosswalk_sensitivity_v2_r.json\n")
