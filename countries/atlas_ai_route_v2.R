# R twin of atlas_ai_route_v2.py (see its header for the definitions). Reads the
# Parquet shards with nanoparquet, the R-side ILOSTAT table
# (macro_ilostat_v2_countries_R.csv), and writes results/atlas_ai_route_v2_r.json.
# Stops unless the task file reproduces countries.csv and the share_exposed run
# reproduces the archived Table 7 coefficients.
suppressPackageStartupMessages({ library(jsonlite); library(sandwich); library(nanoparquet) })

COLS <- c("iso3", "task_id", "exposure_level_mode", "has_material_ai_integration_mode",
          "dominant_ai_function_mode")
T <- do.call(rbind, lapply(sort(Sys.glob("../atlas_data/task_country_core/*.parquet")),
                           function(f) as.data.frame(read_parquet(f, col_select = COLS))))
T <- T[!duplicated(T[, c("iso3", "task_id")]), ]
exposed <- T$exposure_level_mode %in% c(2, 3)
T$exp <- as.numeric(exposed)
T$ai <- as.numeric(exposed & as.logical(T$has_material_ai_integration_mode))
T$genai <- as.numeric(exposed & T$dominant_ai_function_mode == "learned_content_transformation")
S <- data.frame(iso3 = sort(unique(T$iso3)), stringsAsFactors = FALSE)
S$task_count <- as.numeric(table(T$iso3)[S$iso3])
for (v in c("exp", "ai", "genai")) S[[v]] <- as.numeric(tapply(T[[v]], T$iso3, mean)[S$iso3])
names(S)[names(S) == "exp"] <- "share_exposed"
names(S)[names(S) == "ai"] <- "ai_route_share"
names(S)[names(S) == "genai"] <- "genai_route_share"
S$non_ai_exposed <- S$share_exposed - S$ai_route_share

pub <- read.csv("../atlas_data/countries.csv", stringsAsFactors = FALSE)
k <- match(S$iso3, pub$iso3)
stopifnot(all(S$task_count == pub$task_count[k]), max(abs(S$share_exposed - pub$share_exposed[k])) < 1e-12)

cs <- read.csv("macro_country_cross_section.csv", stringsAsFactors = FALSE)
IL <- read.csv("macro_ilostat_v2_countries_R.csv", stringsAsFactors = FALSE)[, c("iso3", "exp_unit", "exp_lsms", "exp_lsms_ex")]
C <- merge(merge(cs[, names(cs) != "share_exposed"], S, by = "iso3", all.x = TRUE), IL, by = "iso3", all.x = TRUE)
stopifnot(max(abs(C$share_exposed - cs$share_exposed[match(C$iso3, cs$iso3)])) < 1e-9)
write.csv(C, "atlas_ai_route_v2_countries_R.csv", row.names = FALSE)

YS <- c("share_exposed", "ai_route_share", "genai_route_share", "non_ai_exposed")
summ <- function(x) list(mean = round(mean(x), 4), median = round(median(x), 4),
                         min = round(min(x), 4), max = round(max(x), 4))
out <- list(n_countries = nrow(C),
            world = lapply(setNames(YS, YS), function(y) round(median(S[[y]]), 4)),
            africa = lapply(setNames(YS, YS), function(y) summ(C[[y]])),
            ai_part_of_exposed_africa = round(mean(C$ai_route_share / C$share_exposed), 4))
out$countries <- list()
for (i in seq_len(nrow(C))) out$countries[[C$iso3[i]]] <- lapply(setNames(YS, YS), function(y) round(C[[y]][i], 4))

out$corr <- list()
for (y in YS) for (z in c("share_exposed", "exp_unit", "exp_lsms", "exp_lsms_ex")) {
  if (y == z) next
  ok <- !is.na(C[[y]]) & !is.na(C[[z]])
  out$corr[[paste0(y, "|", z)]] <- list(n = sum(ok), pearson = round(cor(C[[y]][ok], C[[z]][ok]), 4),
                                        spearman = round(cor(C[[y]][ok], C[[z]][ok], method = "spearman"), 4))
}

C$lgdp <- log(C$gdppc); C$informal_s <- C$informal / 100; C$agri_s <- C$selfemp_agri / 100
specs <- list("(1) informality" = "informal_s", "(2) agri self-emp" = "agri_s", "(3) log GDPpc" = "lgdp",
              "(4) informality + log GDPpc" = "informal_s + lgdp", "(5) agri + log GDPpc" = "agri_s + lgdp",
              "(6) all three" = "informal_s + agri_s + lgdp")
for (y in YS) {
  res <- list()
  for (sp in names(specs)) {
    m <- lm(as.formula(paste(y, "~", specs[[sp]])), data = C)
    se <- sqrt(diag(vcovHC(m, type = "HC1"))); co <- coef(m)
    r <- list()
    for (t in names(co)) r[[if (t == "(Intercept)") "Intercept" else t]] <- list(b = round(unname(co[t]), 4), se = round(unname(se[t]), 4))
    r[["_n"]] <- length(residuals(m)); r[["_r2"]] <- round(summary(m)$r.squared, 3)
    res[[sp]] <- r
  }
  out[[paste0("reg_", y)]] <- res
}

old <- fromJSON("archive_v1/results/revision_py.json")$macro_reg
for (sp in names(specs)) for (t in names(old[[sp]])) {
  if (!is.list(old[[sp]][[t]])) next
  stopifnot(abs(old[[sp]][[t]]$b - out$reg_share_exposed[[sp]][[t]]$b) < 1e-4,
            abs(old[[sp]][[t]]$se - out$reg_share_exposed[[sp]][[t]]$se) < 1e-4)
}

write(toJSON(out, auto_unbox = TRUE, digits = 8, pretty = TRUE), "results/atlas_ai_route_v2_r.json")
cat("task file reproduces countries.csv; share_exposed run reproduces the old Table 7\n")
cat("wrote results/atlas_ai_route_v2_r.json\n")
