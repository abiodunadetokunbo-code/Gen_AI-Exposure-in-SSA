# R twin of crosswalk_sensitivity_v3.py (see its header). Adds wage_formal,
# wage_informal, formal_minus_informal and draws_share_formal_above_informal,
# reusing the aggregation/worker functions from crosswalk_sensitivity_v2.R.
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
agg_emp <- function() {
  d <- LE[!is.na(LE$emp) & LE$emp > 0, ]
  r <- tapply(seq_len(nrow(d)), d$isco08, function(i) sum(d[[A]][i] * d$emp[i]) / sum(d$emp[i]))
  v <- rep(NA_real_, length(codes)); v[match(as.numeric(names(r)), codes)] <- r
  back <- codes %in% LE$isco08 & is.na(v)
  v[back] <- agg(mean)[back]
  fill(v)
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

wage <- P$status == "wage_nonag"
formal_mask <- wage & (P$informal_v2 %in% 0)
informal_mask <- wage & (P$informal_v2 %in% 1)
n_formal <- sum(formal_mask); n_informal <- sum(informal_mask)
stopifnot(n_formal == 1801, n_informal == 2466)

stats <- function(y) {
  wf <- mean(y[formal_mask]); wi <- mean(y[informal_mask])
  c(wage_formal = wf, wage_informal = wi, formal_minus_informal = wf - wi)
}

base <- agg(mean)
stopifnot(max(abs(base - X[[A]])) < 1e-9, max(abs(workers(base) - P[[A]])) < 1e-9)

V2 <- fromJSON("results/crosswalk_sensitivity_v2_r.json")
out <- list()
for (nm in c("mean", "median", "min", "max")) {
  y <- workers(agg(get(nm)))
  v3p <- round(mean(y), 4); v2p <- V2[[nm]]$pooled
  stopifnot(abs(v3p - v2p) < 5e-4)
  out[[nm]] <- as.list(round(stats(y), 4))
}
y_emp <- workers(agg_emp())
stopifnot(abs(round(mean(y_emp), 4) - V2$emp_weighted$pooled) < 5e-4)
out$emp_weighted <- as.list(round(stats(y_emp), 4))
cat("regression test passed: v3 reproduces v2 pooled means for mean/median/min/max/emp_weighted\n")

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
out$draws_share_formal_above_informal <- round(mean(D[, "formal_minus_informal"] > 0), 3)
out$n_formal <- n_formal
out$n_informal <- n_informal
cat(sprintf("draws_share_formal_above_informal = %.3f (cf. draws_share_wage_above_self = %.3f)\n",
            out$draws_share_formal_above_informal, V2$draws_share_wage_above_self))

write(toJSON(out, auto_unbox = TRUE, digits = 8, pretty = TRUE), "results/crosswalk_sensitivity_v3_r.json")
cat("wrote results/crosswalk_sensitivity_v3_r.json\n")
