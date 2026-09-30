# Round 6, point 2: how Nigeria's 1,839 own-use producers are identified.
# R twin of nigeria_ownuse_rule_v6.py. Writes results/ngownuse_v6_r.json only.
suppressPackageStartupMessages(library(jsonlite))

lab <- read.csv("../lsms_probe/w5/Post Harvest Wave 5/Household/sect4a_harvestw5.csv",
                stringsAsFactors = FALSE, na.strings = c("", "NA"))

code <- function(x) suppressWarnings(as.integer(sub("^\\s*(\\d+).*$", "\\1", x)))
isin <- function(x, v) !is.na(x) & x %in% v

st <- code(lab$s4aq21)
a <- code(lab$s4aq13a); b <- code(lab$s4aq13b); cc <- code(lab$s4aq13c)
ua <- code(lab$s4aq19a); ub <- code(lab$s4aq19b)

week_only    <- isin(a, 3)
week_mainly  <- isin(a, 2) & (isin(b, 1:2) | (isin(b, 3) & isin(cc, 2)))
usual_only   <- is.na(a) & isin(ua, 3)
usual_mainly <- is.na(a) & isin(ua, 2) & isin(ub, 1:2)
rule <- week_only | week_mainly | usual_only | usual_mainly
fam <- isin(st, 2)

out <- list(
  family_farm_only         = sum(fam),
  week_only_household      = sum(fam & week_only),
  week_mainly_household    = sum(fam & week_mainly),
  usual_only_household     = sum(fam & usual_only),
  usual_mainly_household   = sum(fam & usual_mainly),
  only_household_total     = sum(fam & (week_only | usual_only)),
  mainly_household_total   = sum(fam & (week_mainly | usual_mainly)),
  family_farm_failing_rule = sum(fam & !rule),
  rule_met_with_other_work = sum(rule & isin(st, 3))
)
stopifnot(out$family_farm_only == 1839, out$family_farm_failing_rule == 0)
f <- "results/ngownuse_v6_r.json"
stopifnot(!file.exists(f))
write_json(out, f, auto_unbox = TRUE, pretty = TRUE)
print(toJSON(out, auto_unbox = TRUE, pretty = TRUE))
