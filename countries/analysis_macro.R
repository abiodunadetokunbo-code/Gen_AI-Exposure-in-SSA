# Country-level augmentation (R) - independent recompute of macro correlations.
suppressMessages(library(jsonlite))
d <- read.csv("../africa_genai_real_panel.csv", comment.char = "#")
agg <- function(x, f) tapply(x, d$iso3, f)
cs <- data.frame(
  iso3 = names(agg(d$share_exposed, function(z) z[1])),
  share_exposed = as.numeric(agg(d$share_exposed, function(z) z[order(d$year)][1])),
  informal = as.numeric(agg(d$informal_emp_rate, function(z) median(z, na.rm = TRUE))),
  selfemp_agri = as.numeric(agg(d$selfemployment_agri, function(z) median(z, na.rm = TRUE))),
  selfemp = as.numeric(agg(d$selfemployment_share, function(z) median(z, na.rm = TRUE))),
  gdppc = as.numeric(agg(d$gdp_ppc_ppp, function(z) median(z, na.rm = TRUE)))
)
cs <- cs[!is.na(cs$share_exposed), ]
out <- list(n_countries = nrow(cs))
for (xv in c("informal", "selfemp_agri", "selfemp", "gdppc")) {
  ok <- !is.na(cs[[xv]]) & !is.na(cs$share_exposed)
  out[[paste0("spearman_exposed_vs_", xv)]] <- round(as.numeric(
    cor(cs[[xv]][ok], cs$share_exposed[ok], method = "spearman")), 6)
  out[[paste0("pearson_exposed_vs_", xv)]] <- round(as.numeric(
    cor(cs[[xv]][ok], cs$share_exposed[ok], method = "pearson")), 6)
  out[[paste0("n_", xv)]] <- sum(ok)
}
out$exposed_median <- round(median(cs$share_exposed), 6)
write_json(out, "results/macro_r.json", auto_unbox = TRUE, pretty = TRUE, digits = 6)
cat("R macro done. exposed~informal spearman=", out$spearman_exposed_vs_informal, "\n")
