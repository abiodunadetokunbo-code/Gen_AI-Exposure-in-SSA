# Headline descriptive statistics for the SSA AI-exposure paper (R).
# Independent re-implementation; writes results/desc_r.json for cross-check.
suppressMessages({library(jsonlite)})
P <- read.csv("harmonized_workers.csv", stringsAsFactors = FALSE)
A <- P$auto_genai
rnd <- function(x) round(as.numeric(x), 6)
out <- list()
out$n_total <- nrow(P)
out$mean_auto <- rnd(mean(A))
out$median_auto <- rnd(median(A))
out[["share_near_zero_lt0.05"]] <- rnd(mean(A < 0.05))
out$share_agri_elem_major69 <- rnd(mean(P$major %in% c(6, 9)))
out$by_country_mean <- as.list(rnd(tapply(A, P$country, mean)))
out$by_country_n <- as.list(as.integer(table(P$country)))
names(out$by_country_n) <- names(table(P$country))
mj <- !is.na(P$major)
out$by_major_mean <- as.list(rnd(tapply(A[mj], P$major[mj], mean)))
out$by_major_share <- as.list(rnd(sapply(sort(unique(P$major[mj])), function(k) mean(P$major == k, na.rm = TRUE))))
names(out$by_major_share) <- sort(unique(P$major[mj]))
comp <- list()
for (c in c(sort(unique(P$country)), "All (pooled)")) {
  g <- if (c == "All (pooled)") P else P[P$country == c, ]
  comp[[c]] <- list(n = nrow(g),
    pct_female = round(100 * mean(g$sex == "female", na.rm = TRUE), 1),
    mean_age = round(mean(g$age, na.rm = TRUE), 1),
    pct_urban = round(100 * mean(g$urban, na.rm = TRUE), 1),
    pct_agri = round(100 * mean(g$status == "agriculture"), 1),
    pct_wage = round(100 * mean(g$status == "wage_nonag"), 1),
    mean_auto = rnd(mean(g$auto_genai)))
}
out$country_composition <- comp
out$by_status_mean <- as.list(rnd(tapply(A, P$status, mean)))
out$by_status_share <- as.list(rnd(sapply(sort(unique(P$status)), function(k) mean(P$status == k))))
names(out$by_status_share) <- sort(unique(P$status))
pu <- P[!is.na(P$urban), ]
out$mean_urban <- rnd(mean(pu$auto_genai[pu$urban == 1]))
out$mean_rural <- rnd(mean(pu$auto_genai[pu$urban == 0]))
ps <- P[!is.na(P$sex), ]
out$mean_male <- rnd(mean(ps$auto_genai[ps$sex == "male"]))
out$mean_female <- rnd(mean(ps$auto_genai[ps$sex == "female"]))
x <- sort(A)
out$top10pct_share_of_exposure <- rnd(sum(x[(floor(0.9 * length(x)) + 1):length(x)]) / sum(x))
out$urban_minus_rural <- rnd(out$mean_urban - out$mean_rural)
write_json(out, "results/desc_r.json", auto_unbox = TRUE, pretty = TRUE, digits = 6)
cat("R done. mean_auto=", out$mean_auto, " urban-rural=", out$urban_minus_rural, "\n")
