# R twin of analysis_v3.py (see its header). Identifies the 2 of 117
# Nigerian coded absentees who do not answer s4aq24 "YES", matches them in
# the R build's worker file by household id and ISCO-08 code, and reports
# the pooled and Nigeria mean exposure with and without them.
suppressPackageStartupMessages(library(jsonlite))

num <- function(s) as.numeric(sub(".*?(\\d+\\.?\\d*).*", "\\1", as.character(s)))

lab <- read.csv("../lsms_probe/w5/Post Harvest Wave 5/Household/sect4a_harvestw5.csv", stringsAsFactors = FALSE)
iso <- num(lab$s4aq40_code)
coded <- !is.na(iso) & iso >= 1000 & iso <= 9999
gate1 <- num(lab$s4aq21) == 3
absent_coded <- coded & !gate1
absent_coded[is.na(absent_coded)] <- FALSE
stopifnot(sum(absent_coded) == 117)
returns_3mo <- num(lab$s4aq24) == 1
returns_3mo[is.na(returns_3mo)] <- FALSE
stopifnot(sum(absent_coded & returns_3mo) == 115)
fail <- absent_coded & !returns_3mo
stopifnot(sum(fail) == 2)

targets <- lab[fail, c("hhid", "s4aq40_code")]
targets$hhid_c <- paste0("NGA", targets$hhid)
targets$isco08 <- num(targets$s4aq40_code)
cat("Target rows (raw Nigeria labour module):\n"); print(targets)

P <- read.csv("harmonized_workers_v2_R.csv", stringsAsFactors = FALSE)
A <- "auto_genai"
wmean <- function(x, w) { k <- is.finite(x) & is.finite(w); sum(x[k] * w[k]) / sum(w[k]) }

drop_idx <- c()
for (i in seq_len(nrow(targets))) {
  t <- targets[i, ]
  m <- which(P$hhid_c == t$hhid_c & P$isco08 == t$isco08)
  stopifnot(length(m) == 1)
  drop_idx <- c(drop_idx, m)
}
stopifnot(length(unique(drop_idx)) == 2)

dropped <- P[drop_idx, ]
cat("Matched rows in harmonized_workers_v2_R.csv:\n")
print(dropped[, c("hhid_c", "country", "status", "isco08", "auto_genai", "weight")])

P_drop <- P[-drop_idx, ]
NGA <- P[P$country == "Nigeria 2023", ]
NGA_drop <- P_drop[P_drop$country == "Nigeria 2023", ]

r4 <- function(x) round(unname(x), 4)
out <- list(
  dropped_rows = lapply(seq_len(nrow(dropped)), function(i) list(
    hhid_c = dropped$hhid_c[i], isco08 = dropped$isco08[i],
    auto_genai = round(dropped$auto_genai[i], 6), weight = round(dropped$weight[i], 4))),
  pooled_mean_baseline = r4(mean(P[[A]])),
  pooled_mean_drop2 = r4(mean(P_drop[[A]])),
  pooled_mean_wtd_baseline = r4(wmean(P[[A]], P$weight)),
  pooled_mean_wtd_drop2 = r4(wmean(P_drop[[A]], P_drop$weight)),
  nga_mean_baseline = r4(mean(NGA[[A]])),
  nga_mean_drop2 = r4(mean(NGA_drop[[A]])),
  nga_mean_wtd_baseline = r4(wmean(NGA[[A]], NGA$weight)),
  nga_mean_wtd_drop2 = r4(wmean(NGA_drop[[A]], NGA_drop$weight)),
  n_baseline = nrow(P), n_drop2 = nrow(P_drop)
)
moves <- any(sapply(c("pooled_mean", "pooled_mean_wtd", "nga_mean", "nga_mean_wtd"),
                    function(k) abs(out[[paste0(k, "_baseline")]] - out[[paste0(k, "_drop2")]]) >= 5e-4))
out$moves_at_3dp <- moves
cat(sprintf("moves at 3 decimals: %s\n", moves))

write(toJSON(out, auto_unbox = TRUE, digits = 8, pretty = TRUE), "results/analysis_v3_r.json")
cat("wrote results/analysis_v3_r.json\n")
