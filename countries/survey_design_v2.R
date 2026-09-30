# R twin of survey_design_v2.py (see its header for the design rules). Builds
# the design ids from the raw files on its own, reads the R build's worker
# files, estimates with the survey package (svymean, svyglm) and writes
# survey_design_ids_v2_R.csv and results/survey_design_v2_r.json.
suppressPackageStartupMessages({library(survey); library(jsonlite)})
options(survey.lonely.psu = "fail")

A <- "auto_genai"
P <- read.csv("harmonized_workers_v2_R.csv", stringsAsFactors = FALSE)
E <- read.csv("harmonized_workers_v2_eth_resident_R.csv", stringsAsFactors = FALSE)

# ---------------- design ids ----------------
ng <- read.csv("../lsms_probe/w5/Post Harvest Wave 5/Household/secta_harvestw5.csv", stringsAsFactors = FALSE)
ng <- data.frame(hhid_c = paste0("NGA", ng$hhid), stratum = paste0("NGA-", ng$strata),
                 psu = paste0("NGA-", ng$cluster))

tz <- read.csv("TZA_2020_NPS-R5/hh_sec_a.csv", stringsAsFactors = FALSE)
boost <- tz$tracking_class == 6  # booster sample: no clusterid or strataid
stopifnot(identical(boost, is.na(tz$clusterid)), identical(boost, is.na(tz$strataid)))
tz <- data.frame(hhid_c = paste0("TZA", tz$y5_hhid),
                 stratum = paste0("TZA-", ifelse(boost, paste0("booster-", substr(tz$y5_cluster, 1, 2)),
                                                 sprintf("%.0f", tz$strataid))),
                 psu = paste0("TZA-", ifelse(boost, tz$y5_cluster, sprintf("%.0f", tz$clusterid))))

ug <- read.csv("UGA_2019_UNPS/UGA_2019_UNPS_v03_M_CSV/HH/gsec1.csv", stringsAsFactors = FALSE)
parts <- c("dc_2018", "cc_2018", "sc_2018", "pc_2018")
has_par <- complete.cases(ug[, parts])
rural <- c("central_rural", "eastern_rural", "northern_rural", "western_rural")
ug_str <- ifelse(toupper(ug$district) %in% "KAMPALA", "kampala",
                 ifelse(ug$urban %in% 1, "other_urban", rural[ug$region]))
ug_str[!has_par] <- "no_location"
ug_psu <- ifelse(has_par, do.call(paste, c(lapply(ug[, parts], function(x) sprintf("%.0f", x)), sep = "-")),
                 paste0("hh-", ug$hhid))
no_urban <- paste0("UGA", ug$hhid[has_par & is.na(ug$urban)])
ug <- data.frame(hhid_c = paste0("UGA", ug$hhid), stratum = paste0("UGA-", ug_str), psu = paste0("UGA-", ug_psu))

# ids run to 18 digits, past double precision: read as text, drop the leading
# zero as the build does (Python's int64 read loses it)
et <- read.csv("ETH_2021_ESPS-W5/sect1_hh_w5.csv", stringsAsFactors = FALSE,
               colClasses = c(household_id = "character", ea_id = "character"))[, c("household_id", "ea_id", "saq01", "saq14")]
et <- et[!is.na(et$household_id) & et$household_id != "", ]
et <- et[!duplicated(et$household_id), ]
et <- data.frame(hhid_c = paste0("ETH", sub("^0+", "", et$household_id)), stratum = paste0("ETH-", et$saq01, "-", et$saq14),
                 psu = paste0("ETH-", sub("^0+", "", et$ea_id)))

IDS <- rbind(ng, tz, ug, et)
stopifnot(!anyDuplicated(IDS$hhid_c))
IDS$psu <- paste0(IDS$stratum, "|", IDS$psu)  # nest PSUs in strata
IDS$stratum[IDS$stratum == "TZA-7"] <- "TZA-8"  # Tanga urban has one PSU with workers
P <- merge(P, IDS, by = "hhid_c", all.x = TRUE, sort = FALSE)
E <- merge(E, IDS, by = "hhid_c", all.x = TRUE, sort = FALSE)
stopifnot(!anyNA(P$psu), !anyNA(E$psu), !any(P$hhid_c %in% no_urban),
          !any(grepl("NA$", P$stratum)), !any(grepl("NA$", E$stratum)))
ids_out <- rbind(P[, c("hhid_c", "country", "stratum", "psu")], E[, c("hhid_c", "country", "stratum", "psu")])
ids_out <- ids_out[!duplicated(ids_out$hhid_c), ]
write.csv(ids_out[order(ids_out$hhid_c), ], "survey_design_ids_v2_R.csv", row.names = FALSE)

describe <- function(d) {
  k <- tapply(d$psu, d$stratum, function(x) length(unique(x)))
  if (any(k == 1)) stop("single-PSU strata: ", paste(names(k)[k == 1], collapse = ", "))
  list(n_workers = nrow(d), n_households = length(unique(d$hhid_c)), n_strata = length(k),
       n_psu = length(unique(paste(d$stratum, d$psu))), min_psu_per_stratum = min(k),
       median_workers_per_psu = median(as.numeric(table(paste(d$stratum, d$psu)))))
}
cn <- sort(unique(P$country))
out <- list(design = c(setNames(lapply(cn, function(c) describe(P[P$country == c, ])), cn),
                       list(pooled = describe(P), ethiopia_resident = describe(E))))

# ---------------- estimators ----------------
P$self_d <- as.integer(P$status == "selfemp_nonag")
P$wage_d <- as.integer(P$status == "wage_nonag")
P$fem <- ifelse(is.na(P$sex), NA, as.numeric(P$sex == "female"))
P$infd <- as.numeric(P$informal_v2)
P$one <- 1; E$one <- 1
des <- function(d, w) svydesign(ids = ~psu, strata = ~stratum, weights = as.formula(paste0("~", w)),
                                data = d, nest = TRUE)
D <- des(P, "one"); DW <- des(P, "weight")

r4 <- function(x) round(unname(x), 4)
m <- function(dsn, cond) {
  cond <- cond & !is.na(dsn$variables[[A]])
  est <- svymean(as.formula(paste0("~", A)), subset(dsn, cond))
  b <- coef(est); se <- as.numeric(SE(est))
  list(mean = r4(b), se = r4(se), lo = r4(b - 1.96 * se), hi = r4(b + 1.96 * se), n = sum(cond))
}
reg <- function(dsn, cond, f) {
  g <- svyglm(as.formula(f), design = subset(dsn, cond))
  s <- summary(g)$coefficients
  keep <- !grepl("^factor\\(country\\)", rownames(s))
  r <- lapply(which(keep), function(i) list(b = r4(s[i, 1]), se = r4(s[i, 2]), p = r4(s[i, 4])))
  names(r) <- sub("^\\(Intercept\\)$", "Intercept", rownames(s)[keep])
  r$`_n` <- length(g$residuals); r$`_df` <- g$df.residual
  r
}
v <- D$variables
st <- v$status; ctry <- v$country; yes <- rep(TRUE, nrow(v))
wage <- st == "wage_nonag"

ci <- list(pooled = m(D, yes), pooled_weighted = m(DW, yes))
for (c in cn) {
  ci[[paste0("country|", c)]] <- m(D, ctry == c)
  ci[[paste0("country_wtd|", c)]] <- m(DW, ctry == c)
}
for (s in sort(unique(st))) {
  ci[[paste0("status_", s)]] <- m(D, st == s)
  ci[[paste0("status_", s, "_wtd")]] <- m(DW, st == s)
  for (c in cn) if (any(st == s & ctry == c)) ci[[paste0("status_", s, "|", c)]] <- m(D, st == s & ctry == c)
}
ci$wage_formal <- m(D, wage & v$informal_v2 %in% 0)
ci$wage_informal <- m(D, wage & v$informal_v2 %in% 1)
ci$urban <- m(D, v$urban %in% 1); ci$rural <- m(D, v$urban %in% 0)
ci$male <- m(D, v$fem %in% 0); ci$female <- m(D, v$fem %in% 1)
for (mj in sort(unique(v$major))) ci[[paste0("major_", mj)]] <- m(D, v$major == mj)
out$group_means_ci <- ci

nonag <- st %in% c("wage_nonag", "selfemp_nonag")
wv <- wage & !is.na(v$informal_v2)
fe <- " + factor(country)"
tests <- list()
for (x in list(list(D, ""), list(DW, "_wtd"))) {
  dsn <- x[[1]]; sfx <- x[[2]]
  tests[[paste0("wage_vs_self_nonag", sfx)]] <- reg(dsn, nonag, "auto_genai ~ wage_d")
  tests[[paste0("wage_vs_self_nonag_cfe", sfx)]] <- reg(dsn, nonag, paste0("auto_genai ~ wage_d", fe))
  tests[[paste0("informal_vs_formal", sfx)]] <- reg(dsn, wv, "auto_genai ~ infd")
  tests[[paste0("informal_vs_formal_cfe", sfx)]] <- reg(dsn, wv, paste0("auto_genai ~ infd", fe))
}
for (k in c("female", "urban")) {
  vv <- if (k == "female") "fem" else "urban"
  ok <- !is.na(v[[vv]])
  tests[[k]] <- reg(D, ok, paste("auto_genai ~", vv))
  tests[[paste0(k, "_cfe")]] <- reg(D, ok, paste0("auto_genai ~ ", vv, fe))
}
out$tests <- tests
ok3 <- complete.cases(v[, c("urban", "fem", "age")])
out$status_reg <- list(
  m1 = reg(D, yes, "auto_genai ~ self_d + wage_d"),
  m2 = reg(D, yes, paste0("auto_genai ~ self_d + wage_d", fe)),
  m3 = reg(D, ok3, paste0("auto_genai ~ self_d + wage_d + urban + fem + age", fe)),
  m2_wtd = reg(DW, yes, paste0("auto_genai ~ self_d + wage_d", fe)))

DE <- des(E, "one"); DEW <- des(E, "weight")
ev <- DE$variables; ey <- rep(TRUE, nrow(ev))
out$ethiopia_resident <- list(ci = m(DE, ey), ci_wtd = m(DEW, ey),
                              ci_formal = m(DE, ev$informal_v2 %in% 0),
                              ci_informal = m(DE, ev$informal_v2 %in% 1))

write(toJSON(out, auto_unbox = TRUE, digits = 8, pretty = TRUE), "results/survey_design_v2_r.json")
cat("wrote survey_design_ids_v2_R.csv and results/survey_design_v2_r.json\n")
