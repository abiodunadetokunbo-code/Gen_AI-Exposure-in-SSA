# R twin of macro_ilostat_v2.py (see its header for the rules). Reads the same
# ILOSTAT files and the R build's worker file, and writes
# results/macro_ilostat_v2_r.json. HC1 standard errors from sandwich::vcovHC.
suppressPackageStartupMessages({ library(jsonlite); library(sandwich) })

X <- read.csv("../crosswalks/isco08_to_exposure.csv")
P <- read.csv("harmonized_workers_v2_R.csv", stringsAsFactors = FALSE)
P$imputed_reason[is.na(P$imputed_reason)] <- ""
cs <- read.csv("macro_country_cross_section.csv", stringsAsFactors = FALSE)
X_SHARE_CUT <- 20

files <- sort(Sys.glob("../ilostat/raw/*.csv"))
D <- do.call(rbind, lapply(files, function(f) {
  if (!startsWith(readLines(f, n = 1, warn = FALSE), "DATAFLOW")) return(NULL)  # "No data is found"
  read.csv(f, stringsAsFactors = FALSE)[, c("REF_AREA", "OCU", "TIME_PERIOD", "OBS_VALUE")]
}))
D <- D[startsWith(D$OCU, "OCU_ISCO08") & D$TIME_PERIOD >= 2015, ]
D <- D[D$TIME_PERIOD == ave(D$TIME_PERIOD, D$REF_AREA, FUN = max), ]
iso <- sort(unique(D$REF_AREA))
val <- function(code) sapply(iso, function(a) {
  v <- D$OBS_VALUE[D$REF_AREA == a & D$OCU == code]; if (length(v)) v[1] else NA })
S <- sapply(1:9, function(i) val(paste0("OCU_ISCO08_", i)))
stopifnot(!anyNA(S))
S <- S / rowSums(S)
xv <- val("OCU_ISCO08_X"); xv[is.na(xv)] <- 0
x_pct <- 100 * xv / val("OCU_ISCO08_TOTAL")
year <- sapply(iso, function(a) D$TIME_PERIOD[D$REF_AREA == a][1])

wm <- function(x, w) sum(x * w) / sum(w)
by_major <- function(d) sapply(1:9, function(m) { k <- d$major == m; wm(d$auto_genai[k], d$weight[k]) })
VECS <- list(exp_unit = sapply(1:9, function(m) mean(X$auto_genai[X$isco08 %/% 1000 == m])),
             exp_lsms = by_major(P),
             exp_lsms_ex = by_major(P[P$imputed_reason != "own_use_farmer_family_use", ]))
YS <- names(VECS)

C <- data.frame(iso3 = iso, year = unname(year), x_pct = round(unname(x_pct), 2),
                agri_share = S[, 6], stringsAsFactors = FALSE)
for (y in YS) C[[y]] <- as.numeric(S %*% VECS[[y]])
C <- merge(C, cs, by = "iso3", all.x = TRUE)
write.csv(C, "macro_ilostat_v2_countries_R.csv", row.names = FALSE)

out <- list(n_countries = nrow(C))
out$vectors <- lapply(VECS, function(v) setNames(as.list(round(v, 4)), as.character(1:9)))
out$countries <- list()
for (i in seq_len(nrow(C))) {
  r <- list(year = C$year[i], x_pct = C$x_pct[i], agri_share = round(C$agri_share[i], 4))
  for (y in YS) r[[y]] <- round(C[[y]][i], 4)
  out$countries[[C$iso3[i]]] <- r
}
for (y in YS) out[[paste0(y, "_summary")]] <- list(
  mean = round(mean(C[[y]]), 4), median = round(median(C[[y]]), 4),
  min = round(min(C[[y]]), 4), max = round(max(C[[y]]), 4))

A <- C[!is.na(C$share_exposed), ]
out$vs_atlas <- lapply(setNames(YS, YS), function(y) list(
  n = nrow(A), pearson = round(cor(A[[y]], A$share_exposed), 4),
  spearman = round(cor(A[[y]], A$share_exposed, method = "spearman"), 4)))

isomap <- c("Nigeria 2023" = "NGA", "Tanzania 2020" = "TZA", "Uganda 2019" = "UGA")
ex <- P[P$imputed_reason != "own_use_farmer_family_use", ]
out$vs_lsms <- list()
for (cn in names(isomap)) {
  g <- P[P$country == cn, ]; e <- ex[ex$country == cn, ]; k <- C$iso3 == isomap[[cn]]
  r <- list(lsms_wtd = round(wm(g$auto_genai, g$weight), 4),
            lsms_wtd_own_use_excluded = round(wm(e$auto_genai, e$weight), 4),
            lsms_agri_share_wtd = round(wm(as.numeric(g$major == 6), g$weight), 4),
            ilostat_agri_share = round(C$agri_share[k], 4))
  for (y in YS) r[[paste0("ilostat_", y)]] <- round(C[[y]][k], 4)
  out$vs_lsms[[isomap[[cn]]]] <- r
}

R <- C[!is.na(C$informal) & !is.na(C$selfemp_agri) & !is.na(C$gdppc), ]
R$lgdp <- log(R$gdppc); R$informal_s <- R$informal / 100; R$agri_s <- R$selfemp_agri / 100
specs <- list("(1) informality" = "informal_s", "(2) agri self-emp" = "agri_s", "(3) log GDPpc" = "lgdp",
              "(4) informality + log GDPpc" = "informal_s + lgdp", "(5) agri + log GDPpc" = "agri_s + lgdp",
              "(6) all three" = "informal_s + agri_s + lgdp")
samples <- list(all = R, x_le_20 = R[R$x_pct <= X_SHARE_CUT, ])
for (lab in names(samples)) for (y in YS) {
  res <- list()
  for (k in names(specs)) {
    m <- lm(as.formula(paste(y, "~", specs[[k]])), data = samples[[lab]])
    se <- sqrt(diag(vcovHC(m, type = "HC1"))); co <- coef(m)
    r <- list()
    for (t in names(co)) r[[if (t == "(Intercept)") "Intercept" else t]] <- list(b = round(unname(co[t]), 4), se = round(unname(se[t]), 4))
    r[["_n"]] <- nrow(samples[[lab]]); r[["_r2"]] <- round(summary(m)$r.squared, 3)
    res[[k]] <- r
  }
  out[[paste0("reg_", y, "_", lab)]] <- res
}
out$x_gt_20 <- sort(C$iso3[C$x_pct > X_SHARE_CUT])

write(toJSON(out, auto_unbox = TRUE, digits = 8, pretty = TRUE), "results/macro_ilostat_v2_r.json")
cat("wrote results/macro_ilostat_v2_r.json\n")
