# Independent R implementation of build_harmonized_v2.py. Same raw survey
# files, same author decisions (see build_harmonized_v2.py's header for the
# full explanation of each rule), written independently: no helper functions
# or intermediate files are shared with the Python script. Reconciliation
# against the Python output is done separately (reconcile_v2.py), row by row
# and column by column.
#
# Writes:
#   countries/harmonized_workers_v2_R.csv
#   countries/harmonized_workers_v2_own_use_excluded_R.csv
#   countries/harmonized_workers_v2_eth_outmigrant_R.csv
#   countries/harmonized_workers_v2_eth_resident_R.csv
#   countries/results/sample_flow_v2_R.json
suppressPackageStartupMessages({ library(jsonlite); library(readxl) })

X <- read.csv("../crosswalks/isco08_to_exposure.csv")[, c("isco08","auto_genai","augment_genai","atlas_exposure")]
X$major <- X$isco08 %/% 1000
XM <- aggregate(X[, c("auto_genai","augment_genai","atlas_exposure")], by = list(major = X$major),
                 FUN = function(v) mean(v, na.rm = TRUE))
rownames(XM) <- XM$major

SUBS_CODES <- c(6310, 6320, 6330, 6340)
SUBS <- colMeans(X[X$isco08 %in% SUBS_CODES, c("auto_genai","augment_genai","atlas_exposure")], na.rm = TRUE)
EXP <- c("auto_genai", "augment_genai", "atlas_exposure")
OUTCOLS <- c("country","sex","age","urban","isco08","major","status","informal",
             "informal_v2","weight","hhid_c","imputed","imputed_reason", EXP)

flow <- list()
logstage <- function(country, stage, n, reason = "") {
  key <- country
  entry <- list(stage = stage, n = as.integer(n), reason = reason)
  if (is.null(flow[[key]])) flow[[key]] <<- list()
  flow[[key]][[length(flow[[key]]) + 1]] <<- entry
  cat(sprintf("[%s] %s: %s%s\n", country, stage, format(n, big.mark = ","),
              if (nzchar(reason)) sprintf("  (%s)", reason) else ""))
}

d1 <- function(s) as.numeric(sub("^(\\d+).*$", "\\1", as.character(s)))
sx <- function(s) { v <- d1(s); ifelse(v == 1, "male", ifelse(v == 2, "female", NA)) }
yesq <- function(s) d1(s) == 1
urb <- function(s, urban_code) {
  v <- d1(s); rural_code <- if (urban_code == 1) 2 else 1
  ifelse(v == urban_code, 1, ifelse(v == rural_code, 0, NA))
}
mkstatus <- function(isco, wage, selfe) {
  agri <- (!is.na(isco)) & ((isco %/% 1000 == 6) | (isco %/% 10 == 921))
  ifelse(agri, "agriculture",
         ifelse(!is.na(wage) & wage, "wage_nonag",
                ifelse(!is.na(selfe) & selfe, "selfemp_nonag", "other_nonag")))
}
attach_exposure <- function(occ_codes) {
  iso <- d1(occ_codes)
  ok <- !is.na(iso) & iso >= 1000 & iso <= 9999
  out <- data.frame(row = which(ok), isco08 = iso[ok])
  out$major <- out$isco08 %/% 1000
  m <- merge(out, X[, c("isco08","auto_genai","augment_genai","atlas_exposure")], by = "isco08", all.x = TRUE, sort = FALSE)
  m[order(m$row), ]
}

rows <- list()

# ============================================================ NIGERIA ======
lab <- read.csv("../lsms_probe/w5/Post Harvest Wave 5/Household/sect4a_harvestw5.csv", stringsAsFactors = FALSE)
r1  <- read.csv("../lsms_probe/w5/Post Harvest Wave 5/Household/sect1_harvestw5.csv", stringsAsFactors = FALSE)
wa  <- read.csv("../lsms_probe/w5/Post Harvest Wave 5/Household/secta_harvestw5.csv", stringsAsFactors = FALSE)
wa <- wa[!duplicated(wa$hhid), c("hhid","wt_wave5","wt_cross_wave5")]

logstage("Nigeria 2023", "all roster respondents (sect1)", nrow(r1))
logstage("Nigeria 2023", "labour-module rows (sect4a)", nrow(lab))

at <- attach_exposure(lab$s4aq40_code)
base <- data.frame(row = seq_len(nrow(lab)), hhid = lab$hhid, indiv = lab$indiv,
                    sector = lab$sector, wage = yesq(lab$s4aq51))
base$self <- !base$wage
base$contract <- yesq(lab$s4aq56)
base$pension <- yesq(lab$s4aq57__1)
d <- merge(at, base, by = "row")
d <- merge(d, r1[, c("hhid","indiv","s1q2","s1q6")], by = c("hhid","indiv"), all.x = TRUE, sort = FALSE)
d <- merge(d, wa, by = "hhid", all.x = TRUE, sort = FALSE)
d$country <- "Nigeria 2023"
d$sex <- sx(d$s1q2)
d$age <- d1(d$s1q6)
d$urban <- urb(d$sector, 1)
d$status <- mkstatus(d$isco08, d$wage, d$self)
d$informal <- NA
d$informal_v2 <- ifelse(d$wage, !(d$contract | d$pension), NA)
d$weight <- ifelse(!is.na(d$wt_cross_wave5), d$wt_cross_wave5, d$wt_wave5)
d$hhid_c <- paste0("NGA", d$hhid)
d$imputed <- 0
d$imputed_reason <- ""
logstage("Nigeria 2023", "coded 4-digit occupation, attached exposure", sum(!is.na(d$isco08)))
rows[[length(rows) + 1]] <- d[, OUTCOLS]

famfarm <- d1(lab$s4aq21) == 2
logstage("Nigeria 2023", "family-farm-only (s4aq21=2), no occupation asked", sum(famfarm, na.rm = TRUE),
         "own-use farmers, added under Decision 1")
fb <- lab[which(famfarm), c("hhid","indiv","sector")]
fb <- merge(fb, r1[, c("hhid","indiv","s1q2","s1q6")], by = c("hhid","indiv"), all.x = TRUE, sort = FALSE)
fb <- merge(fb, wa, by = "hhid", all.x = TRUE, sort = FALSE)
fb$country <- "Nigeria 2023"
fb$sex <- sx(fb$s1q2); fb$age <- d1(fb$s1q6); fb$urban <- urb(fb$sector, 1)
fb$isco08 <- NA; fb$major <- 6  # same major group as Tanzania's family-use farmers
fb$auto_genai <- SUBS["auto_genai"]; fb$augment_genai <- SUBS["augment_genai"]; fb$atlas_exposure <- SUBS["atlas_exposure"]
fb$status <- "agriculture"; fb$informal <- NA; fb$informal_v2 <- NA
fb$weight <- ifelse(!is.na(fb$wt_cross_wave5), fb$wt_cross_wave5, fb$wt_wave5)
fb$hhid_c <- paste0("NGA", fb$hhid)
fb$imputed <- 1; fb$imputed_reason <- "own_use_farmer_family_use"
rows[[length(rows) + 1]] <- fb[, OUTCOLS]
logstage("Nigeria 2023", "headline total (coded + own-use farmers)", sum(!is.na(d$isco08)) + nrow(fb))

# ============================================================ TANZANIA =====
e <- read.csv("TZA_2020_NPS-R5/hh_sec_e1.csv", stringsAsFactors = FALSE)
b <- read.csv("TZA_2020_NPS-R5/hh_sec_b.csv", stringsAsFactors = FALSE)
a <- read.csv("TZA_2020_NPS-R5/hh_sec_a.csv", stringsAsFactors = FALSE)
logstage("Tanzania 2020", "all roster respondents (hh_sec_b)", nrow(b))
logstage("Tanzania 2020", "labour-module rows (hh_sec_e1)", nrow(e))

# TASCO codes with no ISCO-08 match take the target in tasco_to_isco08_v2.csv:
# a unit code, or the average of an ISCO-08 submajor group (isco08 left blank)
TM <- read.csv("../crosswalks/tasco_to_isco08_v2.csv", stringsAsFactors = FALSE)
TM$isco08_target <- as.numeric(TM$isco08_target); TM$submajor_target <- as.numeric(TM$submajor_target)
tasco <- d1(e$hh_e30b_4a)
tasco_coded <- !is.na(tasco) & tasco >= 1000 & tasco <= 9999
tasco_unmatched <- tasco_coded & !(tasco %in% X$isco08)
tmd <- TM[!is.na(TM$isco08_target), ]
tms <- TM[!is.na(TM$submajor_target), ]
occ <- tasco
hit <- match(occ, tmd$tasco_code)
occ[!is.na(hit)] <- tmd$isco08_target[hit[!is.na(hit)]]
at <- attach_exposure(occ)
XS <- aggregate(X[, EXP], by = list(sub = X$isco08 %/% 10), FUN = function(v) mean(v, na.rm = TRUE))
hs <- match(at$isco08, tms$tasco_code)
ms <- !is.na(hs)
subv <- tms$submajor_target[hs[ms]]
for (cn in EXP) at[ms, cn] <- XS[match(subv, XS$sub), cn]
at$major[ms] <- subv %/% 100
at$isco08[ms] <- NA
base <- data.frame(row = seq_len(nrow(e)), indidy5 = e$indidy5, y5_hhid = e$y5_hhid,
                    wage = yesq(e$hh_e03))
base$self <- !base$wage
base$contract <- yesq(e$hh_e42)
base$tax <- yesq(e$hh_e44b)
bsel <- b[!duplicated(b[, c("y5_hhid","indidy5")]) & !is.na(b$y5_hhid) & !is.na(b$indidy5),
          c("y5_hhid","indidy5","hh_b02","hh_b04")]
au <- a[!duplicated(a$y5_hhid) & !is.na(a$y5_hhid), c("y5_hhid","y5_rural","y5_crossweight")]
d <- merge(at, base, by = "row")
d <- merge(d, bsel, by = c("y5_hhid","indidy5"), all.x = TRUE, sort = FALSE)
d <- merge(d, au, by = "y5_hhid", all.x = TRUE, sort = FALSE)
d$country <- "Tanzania 2020"
d$sex <- sx(d$hh_b02); d$age <- d1(d$hh_b04); d$urban <- urb(d$y5_rural, 2)
d$status <- mkstatus(d$isco08, d$wage, d$self)
d$informal <- ifelse(d$wage, !d$tax, NA)
d$informal_v2 <- ifelse(d$wage, !(d$contract | d$tax), NA)
d$weight <- d$y5_crossweight
d$hhid_c <- paste0("TZA", d$y5_hhid)
d$imputed <- 0
d$imputed_reason <- ifelse(tasco_unmatched[d$row],
                           ifelse(is.na(d$isco08), "tasco_map_submajor", "tasco_map_direct"), "")
stopifnot(!anyNA(d[, c("auto_genai", "augment_genai")]))
logstage("Tanzania 2020", "TASCO-coded rows (hh_e30b_4a in 1000-9999)", sum(tasco_coded))
logstage("Tanzania 2020", "coded, matched to ISCO-08 exposure", sum(tasco_coded & !tasco_unmatched))
logstage("Tanzania 2020", "coded, TASCO code with no ISCO-08 match, MAPPED", sum(tasco_unmatched))
rows[[length(rows) + 1]] <- d[, OUTCOLS]

nonfarm_biz <- yesq(e$hh_e05) & !yesq(e$hh_e03)
logstage("Tanzania 2020", "non-farm business owner, no wage job, no occupation question, NOT recoverable",
         sum(nonfarm_biz, na.rm = TRUE), "coverage gap, item 4")

farm_gate <- yesq(e$hh_e07)
has_occ <- d1(e$hh_e30b_4a) >= 1000 & d1(e$hh_e30b_4a) <= 9999 & !is.na(d1(e$hh_e30b_4a))
pool <- farm_gate & !has_occ & !is.na(farm_gate)
logstage("Tanzania 2020", "farm gate (hh_e07=yes), no occupation code -- imputed pool", sum(pool, na.rm = TRUE))
c9 <- d1(e$hh_e09)
sale <- pool & c9 %in% c(1, 2) & !is.na(c9)
famuse <- pool & c9 %in% c(3, 4) & !is.na(c9)
logstage("Tanzania 2020", "  of which hh_e09 in {1,2} market-oriented -> major-6 mean", sum(sale, na.rm = TRUE))
logstage("Tanzania 2020", "  of which hh_e09 in {3,4} family use -> subsistence-code mean", sum(famuse, na.rm = TRUE))

build_imputed <- function(mask, expvals, reason) {
  fe <- e[which(mask), c("y5_hhid","indidy5")]
  fe <- merge(fe, bsel, by = c("y5_hhid","indidy5"), all.x = TRUE, sort = FALSE)
  fe <- merge(fe, au, by = "y5_hhid", all.x = TRUE, sort = FALSE)
  fe$country <- "Tanzania 2020"
  fe$sex <- sx(fe$hh_b02); fe$age <- d1(fe$hh_b04); fe$urban <- urb(fe$y5_rural, 2)
  fe$isco08 <- NA; fe$major <- 6
  fe$auto_genai <- expvals[["auto_genai"]]; fe$augment_genai <- expvals[["augment_genai"]]
  fe$atlas_exposure <- expvals[["atlas_exposure"]]
  fe$status <- "agriculture"; fe$informal <- NA; fe$informal_v2 <- NA
  fe$weight <- fe$y5_crossweight
  fe$hhid_c <- paste0("TZA", fe$y5_hhid)
  fe$imputed <- 1; fe$imputed_reason <- reason
  fe[, OUTCOLS]
}
fe_sale <- build_imputed(sale, XM["6", ], "own_use_farmer_market_oriented")
fe_fam <- build_imputed(famuse, SUBS, "own_use_farmer_family_use")
rows[[length(rows) + 1]] <- fe_sale
rows[[length(rows) + 1]] <- fe_fam
logstage("Tanzania 2020", "headline total (coded incl. TASCO-mapped + both imputed groups)",
         nrow(d) + nrow(fe_sale) + nrow(fe_fam))

# ============================================================= UGANDA ======
g8path <- list.files("UGA_2019_UNPS", pattern = "^gsec8\\.csv$", recursive = TRUE, full.names = TRUE)[1]
g8 <- read.csv(g8path, fileEncoding = "latin1", stringsAsFactors = FALSE)
g2 <- read.csv("UGA_2019_UNPS/UGA_2019_UNPS_v03_M_CSV/HH/gsec2.csv", fileEncoding = "latin1", stringsAsFactors = FALSE)
g1 <- read.csv("UGA_2019_UNPS/UGA_2019_UNPS_v03_M_CSV/HH/gsec1.csv", fileEncoding = "latin1", stringsAsFactors = FALSE)
logstage("Uganda 2019", "all roster respondents (gsec2)", nrow(g2))
logstage("Uganda 2019", "labour-module rows (gsec8)", nrow(g8))

at <- attach_exposure(g8$h8q19b_fourDigit)
# wage status from the main job (s8q22 = 1), the job the occupation code and the
# formality questions describe; v1 used s8q04 (any paid work in the last 7 days)
ugamain <- d1(g8$s8q22)
base <- data.frame(row = seq_len(nrow(g8)), PID = g8$PID, hhid = g8$hhid,
                   wage = !is.na(ugamain) & ugamain == 1)
base$self <- !base$wage
base$contract <- yesq(g8$s8q27); base$pension <- yesq(g8$s8q23); base$paye <- yesq(g8$s8q26)
g2s <- g2[!duplicated(g2[, c("hhid","PID")]) & !is.na(g2$hhid) & !is.na(g2$PID), c("hhid","PID","h2q3","h2q8")]
g1u <- g1[!duplicated(g1$hhid) & !is.na(g1$hhid), c("hhid","urban","wgt")]
d <- merge(at, base, by = "row")
d <- merge(d, g2s, by = c("hhid","PID"), all.x = TRUE, sort = FALSE)
d <- merge(d, g1u, by = "hhid", all.x = TRUE, sort = FALSE)
d$country <- "Uganda 2019"
d$sex <- sx(d$h2q3); d$age <- d1(d$h2q8); d$urban <- d1(d$urban)
d$status <- mkstatus(d$isco08, d$wage, d$self)
d$informal <- ifelse(d$wage, !(d$contract | d$pension | d$paye), NA)
d$informal_v2 <- ifelse(d$wage, !(d$contract | d$paye), NA)
d$weight <- d$wgt
d$hhid_c <- paste0("UGA", d$hhid)
d$imputed <- 0; d$imputed_reason <- ""
logstage("Uganda 2019", "coded 4-digit occupation, attached exposure", sum(!is.na(d$isco08)))
rows[[length(rows) + 1]] <- d[, OUTCOLS]

# ============================================================ pool (headline) ==
P <- do.call(rbind, rows)
dropped <- P[is.na(P$auto_genai), ]
for (cn in unique(dropped$country)) {
  logstage(cn, "no exposure value after crosswalk, DROPPED from headline", sum(dropped$country == cn))
}
P <- P[!is.na(P$auto_genai), ]
logstage("ALL", "headline pooled workers (Nigeria+Tanzania+Uganda)", nrow(P))

# ---- guard rails: the counts the author approved on 2026-09-19 -------------
# Same targets as build_harmonized_v2.py; both must move together with any
# approved rebuild. A passing check on a stale number is worse than no check.
APPROVED <- c("Nigeria 2023" = 9547L, "Tanzania 2020" = 7620L, "Uganda 2019" = 7671L)
for (cc in names(APPROVED)) {
  got <- sum(P$country == cc)
  if (got != APPROVED[[cc]]) stop(sprintf("%s: expected %d workers, got %d", cc, APPROVED[[cc]], got))
}
stopifnot(
  nrow(P) == 24838,
  sum(P$imputed) == 7112,
  sum(P$imputed_reason == "own_use_farmer_family_use") == 6372,
  sum(P$imputed_reason == "own_use_farmer_market_oriented") == 740,
  sum(startsWith(P$imputed_reason, "tasco_map")) == 139,
  sum(!is.na(P$isco08)) == 17720,
  !anyNA(P$weight), !anyNA(P$hhid_c), !anyNA(P$auto_genai)
)

dir.create("results", showWarnings = FALSE)
write.csv(P, "harmonized_workers_v2_R.csv", row.names = FALSE)

P_ex <- P[P$imputed_reason != "own_use_farmer_family_use", ]
stopifnot(nrow(P_ex) == 18466)
write.csv(P_ex, "harmonized_workers_v2_own_use_excluded_R.csv", row.names = FALSE)
logstage("ALL", "own-use-excluded robustness sample", nrow(P_ex))

# ============================================================ ETHIOPIA =====
# household_id/individual_id are long integers (up to 17-18 digits) that lose
# precision as R's default numeric double (>~15-16 significant digits); read
# as character to match Python's pandas int64, which is exact at this length.
idcols_eth <- c(household_id = "character", individual_id = "character")
s1e <- read.csv("ETH_2021_ESPS-W5/sect1_hh_w5.csv", stringsAsFactors = FALSE, colClasses = idcols_eth)
logstage("Ethiopia 2021 (out-migrant)", "all roster respondents (sect1)", nrow(s1e))
maj <- d1(s1e$s1q32b)
dE <- data.frame(major = maj)
dE <- merge(dE, data.frame(major = XM$major, XM[, EXP]), by = "major", all.x = TRUE, sort = FALSE)
# merge drops row order / NA rows; rebuild explicitly to keep every roster row
dE <- data.frame(major = maj)
XMkey <- XM; XMkey$major <- as.numeric(rownames(XM))
dE$auto_genai <- XMkey$auto_genai[match(dE$major, XMkey$major)]
dE$augment_genai <- XMkey$augment_genai[match(dE$major, XMkey$major)]
dE$atlas_exposure <- XMkey$atlas_exposure[match(dE$major, XMkey$major)]
dE$isco08 <- NA
dE$country <- "Ethiopia 2021 (out-migrant, not in headline)"
dE$sex <- sx(s1e$s1q02); dE$age <- d1(s1e$s1q03a); dE$urban <- urb(s1e$saq14, 2)
dE$weight <- as.numeric(s1e$pw_w5)
hhcol <- if ("household_id" %in% names(s1e)) "household_id" else names(s1e)[1]
dE$hhid_c <- paste0("ETH", sub("^0+", "", s1e[[hhcol]]))  # strip leading zero: Python's int64 read drops it
dE <- dE[!is.na(dE$major) & dE$major >= 1 & dE$major <= 9, ]
dE$status <- ifelse(dE$major == 6, "agriculture", "other_nonag")
dE$informal <- NA; dE$informal_v2 <- NA; dE$imputed <- 0; dE$imputed_reason <- ""
logstage("Ethiopia 2021 (out-migrant)", "coded (major-group), DEMOTED to supplementary, EXCLUDED from headline",
         nrow(dE))
stopifnot(nrow(dE) == 584)
write.csv(dE[, OUTCOLS], "harmonized_workers_v2_eth_outmigrant_R.csv", row.names = FALSE)

s4e <- read.csv("ETH_2021_ESPS-W5/sect4_hh_w5.csv", stringsAsFactors = FALSE, colClasses = idcols_eth)
maj88 <- d1(s4e$s4q34b)
logstage("Ethiopia 2021 (resident)", "s4q34b non-missing (one-digit ISCO-88 major, incl. armed forces=10)",
         sum(!is.na(maj88)))
armed <- maj88 == 10 & !is.na(maj88)
logstage("Ethiopia 2021 (resident)", "armed forces (code 10), DROPPED", sum(armed))
maj88v <- ifelse(!is.na(maj88) & maj88 >= 1 & maj88 <= 9, maj88, NA)

xw <- as.data.frame(read_excel("../crosswalks/isco88_to_isco08.xlsx", sheet = "ISCO-88 to 08"))
names(xw) <- c("isco88_title","isco88","isco08","partial","isco08_title","comment")
xw$isco88 <- as.numeric(xw$isco88); xw$isco08 <- as.numeric(xw$isco08)
xw <- xw[!is.na(xw$isco88) & !is.na(xw$isco08), ]
xw$isco88_major <- xw$isco88 %/% 1000
xwm <- merge(xw, X[, c("isco08","auto_genai","augment_genai","atlas_exposure")], by = "isco08", all.x = TRUE, sort = FALSE)
M88 <- aggregate(xwm[, EXP], by = list(isco88_major = xwm$isco88_major), FUN = function(v) mean(v, na.rm = TRUE))
logstage("Ethiopia 2021 (resident)", "ISCO-88 major groups with a derived exposure value",
         sum(!is.na(M88$auto_genai)), "via crosswalks/isco88_to_isco08.xlsx unit-group correspondence")

s1dem <- s1e[!duplicated(s1e[, c("household_id","individual_id")]) & !is.na(s1e$household_id),
             c("household_id","individual_id","s1q02","s1q03a")]
dR <- s4e[, c("household_id","individual_id","saq14","pw_w5")]
dR$major88 <- maj88v
dR <- merge(dR, s1dem, by = c("household_id","individual_id"), all.x = TRUE, sort = FALSE)
dR$auto_genai <- M88$auto_genai[match(dR$major88, M88$isco88_major)]
dR$augment_genai <- M88$augment_genai[match(dR$major88, M88$isco88_major)]
dR$atlas_exposure <- M88$atlas_exposure[match(dR$major88, M88$isco88_major)]
dR$isco08 <- NA; dR$major <- NA
dR$country <- "Ethiopia 2021 (resident wage, supplementary)"
dR$sex <- sx(dR$s1q02); dR$age <- d1(dR$s1q03a); dR$urban <- urb(dR$saq14, 2)
dR$status <- "wage_resident_supplementary"
dR$contract <- yesq(s4e$s4q36)
dR$informal <- NA
dR$informal_v2 <- ifelse(!is.na(dR$major88), !dR$contract, NA)
dR$weight <- as.numeric(dR$pw_w5)
dR$hhid_c <- paste0("ETH", sub("^0+", "", dR$household_id))  # strip leading zero: Python's int64 read drops it
dR$imputed <- 0; dR$imputed_reason <- ""
dR <- dR[!is.na(dR$major88), ]
logstage("Ethiopia 2021 (resident)", "final resident wage supplementary sample (major88 1-9, exposure attached)",
         nrow(dR))
stopifnot(nrow(dR) == 1989)
write.csv(dR[, c(OUTCOLS, "major88")], "harmonized_workers_v2_eth_resident_R.csv", row.names = FALSE)

write(toJSON(flow, auto_unbox = TRUE, pretty = TRUE), "results/sample_flow_v2_R.json")

cat("\n=== headline (NGA+TZA+UGA) ===\n")
cat("N =", nrow(P), "\n")
for (cn in sort(unique(P$country))) {
  g <- P[P$country == cn, ]
  cat(sprintf("%-15s n=%-6d mean_auto=%.3f agri_share=%.1f\n", cn, nrow(g), mean(g$auto_genai),
              100 * mean(g$status == "agriculture")))
}
cat("\nwrote harmonized_workers_v2_R.csv and companions\n")
