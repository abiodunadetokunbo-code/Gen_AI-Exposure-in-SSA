# R twin of althoff_variants_v2.py (see its header for the rules). Reads the R
# build's worker file and writes results/althoff_variants_v2_r.json. Stops
# unless the canonical task file reproduces isco08_to_exposure.csv and the
# worker file to 1e-9.
suppressPackageStartupMessages(library(jsonlite))

VARIANTS <- c("canonical_moderate_qwen", "moderate_gptoss", "slow_qwen", "slow_gptoss",
              "rapid_qwen", "rapid_gptoss", "no_explicit_scenario_qwen",
              "no_explicit_scenario_gptoss", "no_explicit_scenario_gpt4o")
X <- read.csv("../crosswalks/isco08_to_exposure.csv", stringsAsFactors = FALSE)
L <- read.csv("../crosswalks/isco08_to_onetsoc10.csv", stringsAsFactors = FALSE)
P <- read.csv("harmonized_workers_v2_R.csv", stringsAsFactors = FALSE)
P$imputed_reason[is.na(P$imputed_reason)] <- ""
A <- "auto_genai"

isco_vector <- function(tk) {
  num <- tapply(tk$automatable_genai * tk$task_weight, tk$soc_code_onet, sum)
  den <- tapply(tk$task_weight, tk$soc_code_onet, sum)
  occ <- num / den
  lv <- occ[L$onetsoc10]                      # NA where the O*NET code has no tasks
  out <- tapply(lv, L$isco08, mean, na.rm = TRUE)
  out[is.nan(out)] <- NA
  codes <- as.numeric(names(out))
  g3 <- tapply(out, codes %/% 10, mean, na.rm = TRUE)
  g2 <- tapply(out, codes %/% 100, mean, na.rm = TRUE)
  v <- numeric(nrow(X))
  for (i in seq_len(nrow(X))) {
    cd <- X$isco08[i]
    v[i] <- switch(X$match[i],
                   direct = out[[as.character(cd)]],
                   impute_3dig = g3[[as.character(cd %/% 10)]],
                   impute_2dig = g2[[as.character(cd %/% 100)]])
  }
  setNames(v, X$isco08)
}

# submajor of each TASCO row mapped to a submajor average, read off its canonical value
XS0 <- tapply(X[[A]], X$isco08 %/% 10, mean)
sub_idx <- which(P$imputed_reason == "tasco_map_submajor")
sub_of <- sapply(sub_idx, function(i) {
  hit <- names(XS0)[abs(XS0 - P[[A]][i]) < 1e-12]
  stopifnot(length(hit) == 1)
  as.numeric(hit)
})

worker_vector <- function(vec) {
  codes <- as.numeric(names(vec))
  y <- unname(vec[as.character(P$isco08)])
  y[P$imputed_reason == "own_use_farmer_family_use"] <- mean(vec[as.character(c(6310, 6320, 6330, 6340))])
  y[P$imputed_reason == "own_use_farmer_market_oriented"] <- mean(vec[codes %/% 1000 == 6])
  vs <- tapply(vec, codes %/% 10, mean)
  y[sub_idx] <- vs[as.character(sub_of)]
  stopifnot(!anyNA(y))
  y
}

wm <- function(x, w) sum(x * w) / sum(w)
countries <- sort(unique(P$country))
res <- list(); base_vec <- NULL
for (v in VARIANTS) {
  tk <- read.csv(file.path("althoff_variants", paste0(v, ".csv")), stringsAsFactors = FALSE)
  vec <- isco_vector(tk)
  y <- worker_vector(vec)
  if (v == "canonical_moderate_qwen") {
    stopifnot(max(abs(vec - X[[A]])) < 1e-9, max(abs(y - P[[A]])) < 1e-9)
    base_vec <- vec
  }
  maj <- list(); for (m in 1:9) maj[[as.character(m)]] <- round(mean(y[P$major == m]), 4)
  st <- list(); for (s in c("agriculture", "selfemp_nonag", "wage_nonag")) st[[s]] <- round(mean(y[P$status == s]), 4)
  cu <- list(); cw <- list()
  for (cn in countries) {
    k <- P$country == cn
    cu[[cn]] <- round(mean(y[k]), 4); cw[[cn]] <- round(wm(y[k], P$weight[k]), 4)
  }
  mv <- unlist(maj)
  res[[v]] <- list(
    isco_mean = round(mean(vec), 4),
    corr_pearson = round(cor(vec, base_vec), 4),
    corr_spearman = round(cor(vec, base_vec, method = "spearman"), 4),
    pooled = round(mean(y), 4), pooled_wtd = round(wm(y, P$weight), 4),
    country = cu, country_wtd = cw, status = st,
    wage_minus_self = round(st$wage_nonag - st$selfemp_nonag, 4),
    major = maj, top_major = as.integer(names(mv)[which.max(mv)]),
    clerical_over_agri = round(maj[["4"]] / maj[["6"]], 2),
    near_zero = round(100 * mean(y < 0.05), 1))
}
write(toJSON(res, auto_unbox = TRUE, digits = 8, pretty = TRUE), "results/althoff_variants_v2_r.json")
cat("canonical rebuild matches the exposure file and the worker file to 1e-9\n")
cat("wrote results/althoff_variants_v2_r.json\n")
