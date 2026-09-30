# R twin of althoff_variants_v3.py (see its header). Adds wage_formal,
# wage_informal and formal_minus_informal to the nine task-file variants,
# reusing the worker-vector construction from althoff_variants_v2.R unchanged.
suppressPackageStartupMessages(library(jsonlite))

VARIANTS <- c("canonical_moderate_qwen", "moderate_gptoss", "slow_qwen", "slow_gptoss",
              "rapid_qwen", "rapid_gptoss", "no_explicit_scenario_qwen",
              "no_explicit_scenario_gptoss", "no_explicit_scenario_gpt4o")
X <- read.csv("../crosswalks/isco08_to_exposure.csv", stringsAsFactors = FALSE)
L <- read.csv("../crosswalks/isco08_to_onetsoc10.csv", stringsAsFactors = FALSE)
P <- read.csv("harmonized_workers_v2_R.csv", stringsAsFactors = FALSE)
P$imputed_reason[is.na(P$imputed_reason)] <- ""
A <- "auto_genai"
V2 <- fromJSON("results/althoff_variants_v2_r.json")

isco_vector <- function(tk) {
  num <- tapply(tk$automatable_genai * tk$task_weight, tk$soc_code_onet, sum)
  den <- tapply(tk$task_weight, tk$soc_code_onet, sum)
  occ <- num / den
  lv <- occ[L$onetsoc10]
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

wage <- P$status == "wage_nonag"
formal_mask <- wage & (P$informal_v2 %in% 0)
informal_mask <- wage & (P$informal_v2 %in% 1)
n_wage <- sum(wage); n_formal <- sum(formal_mask); n_informal <- sum(informal_mask)
n_answered <- n_formal + n_informal
stopifnot(n_wage == 4275, n_answered == 4267, n_formal == 1801, n_informal == 2466)

res <- list(); base_vec <- NULL
for (v in VARIANTS) {
  tk <- read.csv(file.path("althoff_variants", paste0(v, ".csv")), stringsAsFactors = FALSE)
  vec <- isco_vector(tk)
  y <- worker_vector(vec)
  if (v == "canonical_moderate_qwen") {
    stopifnot(max(abs(y - P[[A]])) < 1e-9)
    base_vec <- vec
  }
  for (f in c("agriculture", "selfemp_nonag", "wage_nonag")) {
    v3v <- round(mean(y[P$status == f]), 4)
    v2v <- V2[[v]]$status[[f]]
    stopifnot(abs(v3v - v2v) < 5e-4)
  }
  wf <- round(mean(y[formal_mask]), 4)
  wi <- round(mean(y[informal_mask]), 4)
  res[[v]] <- list(wage_formal = wf, wage_informal = wi, formal_minus_informal = round(wf - wi, 4),
                   n_formal = n_formal, n_informal = n_informal)
}

canon <- res[["canonical_moderate_qwen"]]
stopifnot(abs(canon$wage_formal - 0.213) < 5e-4, abs(canon$wage_informal - 0.104) < 5e-4)
cat(sprintf("regression test passed: v3 reproduces v2 status means for all 9 variants; headline wage_formal=%.4f wage_informal=%.4f\n",
            canon$wage_formal, canon$wage_informal))

gaps <- sapply(res, function(r) r$formal_minus_informal)
cat(sprintf("formal_minus_informal across the 9 variants: min=%.4f max=%.4f\n", min(gaps), max(gaps)))
any_flip <- any(gaps <= 0)
cat(sprintf("any variant with formal <= informal: %s\n", any_flip))

out <- list(variants = res, n_wage = n_wage, n_formal = n_formal, n_informal = n_informal,
           formal_minus_informal_min = round(min(gaps), 4), formal_minus_informal_max = round(max(gaps), 4),
           any_sign_flip = any_flip)
write(toJSON(out, auto_unbox = TRUE, digits = 8, pretty = TRUE), "results/althoff_variants_v3_r.json")
cat("wrote results/althoff_variants_v3_r.json\n")
