# =============================================================================
# build_real_panel.R
# Sources REAL data from the World Bank WDI API and assembles the 37-country
# Africa panel (2010-2025) used to TEST the paper's claims against real data.
#
# WHAT IS REAL (sourced live at run time from api.worldbank.org):
#   selfemployment_share  SL.EMP.SELF.ZS      (main outcome #2; modeled ILO est.)
#   gdp_ppc_ppp           NY.GDP.PCAP.PP.KD
#   trade_openness        NE.TRD.GNFS.ZS
#   urbanization_pct      SP.URB.TOTL.IN.ZS
#   female_lfp            SL.TLF.ACTI.FE.ZS
#   internet_pct          IT.NET.USER.ZS
#   gdp_growth            NY.GDP.MKTP.KD.ZG
#   hci                   HD.HCI.OVRL         (sparse: only some years)
#
# WHAT IS FROM THE PAPER (atlas_exposure_lookup.csv, documented provenance):
#   subst_exp_c           Global Automation Atlas substitution index (Table A)
#   income_group, internet_2021, informal_2021 baselines
#
# NOT SOURCED HERE: ILOSTAT informal-employment rate time series
#   (bulk path returned 404 at build time; needs ILOSTAT portal/SDMX access).
#   The paper's main outcome #1 therefore cannot be tested with real data here;
#   we test main outcome #2 (self-employment), which IS fully real.
# =============================================================================

suppressMessages({library(jsonlite); library(dplyr); library(tidyr)})
have_ilo <- requireNamespace("Rilostat", quietly = TRUE)

lookup <- read.csv("atlas_exposure_real.csv", comment.char = "#",
                   stringsAsFactors = FALSE)
# REAL Atlas treatment: substitution_share (genuine Atlas substitution exposure).
# NB: paper's S_c ranks like this (cor 0.96) but is ~2x in level; 5 countries
# (BWA,GAB,LBR,MUS,NAM) are absent from the Atlas entirely (NA here).
lookup$subst_exp_c <- lookup$substitution_share
iso <- paste(lookup$iso3, collapse = ";")

# ---- World Bank API pull -----------------------------------------------------
wb_get <- function(indicator, iso_list, d1 = 2010, d2 = 2025) {
  url <- sprintf(
    "https://api.worldbank.org/v2/country/%s/indicator/%s?format=json&date=%d:%d&per_page=20000",
    iso_list, indicator, d1, d2)
  message("  pulling ", indicator, " ...")
  x <- tryCatch(jsonlite::fromJSON(url), error = function(e) NULL)
  if (is.null(x) || length(x) < 2 || is.null(x[[2]])) {
    warning("no data for ", indicator); return(NULL)
  }
  d <- x[[2]]
  data.frame(iso3 = d$countryiso3code,
             year = as.integer(d$date),
             value = as.numeric(d$value),
             stringsAsFactors = FALSE) |>
    setNames(c("iso3", "year", indicator))
}

indicators <- c(
  selfemployment_share = "SL.EMP.SELF.ZS",
  gdp_ppc_ppp          = "NY.GDP.PCAP.PP.KD",
  trade_openness       = "NE.TRD.GNFS.ZS",
  urbanization_pct     = "SP.URB.TOTL.IN.ZS",
  female_lfp           = "SL.TLF.ACTI.FE.ZS",
  internet_pct         = "IT.NET.USER.ZS",
  gdp_growth           = "NY.GDP.MKTP.KD.ZG",
  hci                  = "HD.HCI.OVRL",
  # ---- four secondary controls (WDI / WGI) ----
  gov_effectiveness    = "GE.EST",            # WGI Government Effectiveness
  exch_rate_lcu_usd    = "PA.NUS.FCRF",       # official exch rate (LCU/USD, avg)
  debt_pct_gdp         = "GC.DOD.TOTL.GD.ZS", # central govt debt %GDP (distress proxy)
  exp_yrs_schooling    = "SE.SCH.LIFE"        # expected yrs schooling (schooling proxy)
)

message("Sourcing World Bank WDI (", length(indicators), " indicators, 37 countries, 2010-2025):")
panel <- expand.grid(iso3 = lookup$iso3, year = 2010:2025, stringsAsFactors = FALSE)
for (nm in names(indicators)) {
  d <- wb_get(indicators[[nm]], iso)
  if (!is.null(d)) {
    names(d)[3] <- nm
    panel <- left_join(panel, d, by = c("iso3", "year"))
  } else {
    panel[[nm]] <- NA_real_
  }
}

# ---- ILOSTAT informal employment rate (correct code: EMP_NIFL_SEX_RT_A) -----
# NB: the paper cites EMP_2IFL_SEX_RT_A (Appendix B.2), which does NOT exist in
# ILOSTAT; the real series is EMP_NIFL_SEX_RT_A ("Informal employment rate (%)").
if (have_ilo) {
  message("Sourcing ILOSTAT informal employment (EMP_NIFL_SEX_RT_A) ...")
  ilo <- tryCatch({
    d <- Rilostat::get_ilostat(id = "EMP_NIFL_SEX_RT_A", segment = "indicator",
                               filters = list(ref_area = lookup$iso3, sex = "SEX_T"))
    data.frame(iso3 = d$ref_area, year = as.integer(d$time),
               informal_emp_rate = as.numeric(d$obs_value))
  }, error = function(e) { warning("ILOSTAT pull failed: ", conditionMessage(e)); NULL })
  if (!is.null(ilo)) panel <- left_join(panel, ilo, by = c("iso3", "year"))
}
if (!"informal_emp_rate" %in% names(panel)) panel$informal_emp_rate <- NA_real_

# ---- ILOSTAT sectoral pieces: self-emp split, services shares, wages --------
ilo_series <- function(id, filt) tryCatch({
  d <- Rilostat::get_ilostat(id = id, segment = "indicator", filters = filt)
  d$year <- as.integer(d$time); d
}, error = function(e) { warning(id, ": ", conditionMessage(e)); NULL })

if (have_ilo) {
  flt <- list(ref_area = lookup$iso3, sex = "SEX_T")

  # (a) self-employment by agriculture / non-agriculture (% of total employment)
  message("Sourcing ILOSTAT employment by status x sector ...")
  ste <- ilo_series("EMP_TEMP_SEX_STE_ECO_NB_A", flt)
  if (!is.null(ste)) {
    pick <- function(st, ec) ste |>
      filter(classif1 == st, classif2 == ec) |>
      group_by(iso3 = ref_area, year) |>
      summarise(v = sum(as.numeric(obs_value), na.rm = TRUE), .groups = "drop")
    se_split <- pick("STE_AGGREGATE_TOTAL", "ECO_SECTOR_TOTAL") |> rename(tot = v) |>
      left_join(rename(pick("STE_AGGREGATE_SLF", "ECO_SECTOR_AGR"), sagr = v),
                by = c("iso3", "year")) |>
      left_join(rename(pick("STE_AGGREGATE_SLF", "ECO_SECTOR_NAG"), snag = v),
                by = c("iso3", "year")) |>
      transmute(iso3, year,
                selfemployment_agri    = 100 * sagr / tot,
                selfemployment_nonagri = 100 * snag / tot)
    panel <- left_join(panel, se_split, by = c("iso3", "year"))
  }

  # (b) formal services (ISIC K-Q) vs informal services (G-I,R-T) emp shares
  message("Sourcing ILOSTAT employment by economic activity (ISIC) ...")
  eco <- ilo_series("EMP_TEMP_SEX_ECO_NB_A", flt)
  if (!is.null(eco)) {
    aggc <- function(codes) eco |> filter(classif1 %in% codes) |>
      group_by(iso3 = ref_area, year) |>
      summarise(v = sum(as.numeric(obs_value), na.rm = TRUE), .groups = "drop")
    shr <- aggc("ECO_ISIC4_TOTAL") |> rename(tot = v) |>
      left_join(rename(aggc(paste0("ECO_ISIC4_", c("K","L","M","N","O","P","Q"))), fs = v),
                by = c("iso3", "year")) |>
      left_join(rename(aggc(paste0("ECO_ISIC4_", c("G","H","I","R","S","T"))), isv = v),
                by = c("iso3", "year")) |>
      transmute(iso3, year,
                formal_services_share   = 100 * fs / tot,
                informal_services_share = 100 * isv / tot)
    panel <- left_join(panel, shr, by = c("iso3", "year"))
  }

  # (c) services hourly earnings (nominal LCU, log) -- wage mechanism proxy
  message("Sourcing ILOSTAT earnings by economic activity ...")
  ear <- ilo_series("EAR_EHRA_SEX_ECO_NB_A", flt)
  if (!is.null(ear)) {
    wfs <- ear |> filter(classif1 == "ECO_SECTOR_SER") |>
      group_by(iso3 = ref_area, year) |>
      summarise(log_wage_services = log(mean(as.numeric(obs_value), na.rm = TRUE)),
                .groups = "drop")
    panel <- left_join(panel, wfs, by = c("iso3", "year"))
  }
}
for (v in c("selfemployment_agri","selfemployment_nonagri","formal_services_share",
            "informal_services_share","log_wage_services"))
  if (!v %in% names(panel)) panel[[v]] <- NA_real_

# ---- Merge treatment + derived vars -----------------------------------------
panel <- panel |>
  left_join(lookup[, c("iso3","country","income_group","subst_exp_c",
                       "augmentation_share","share_exposed")], by = "iso3") |>
  mutate(
    post          = as.integer(year >= 2023),
    covid_window  = as.integer(year %in% c(2020, 2021)),
    log_gdp_ppc   = log(gdp_ppc_ppp),
    subst_exp_std = (subst_exp_c - mean(lookup$subst_exp_c, na.rm = TRUE)) /
                     sd(lookup$subst_exp_c, na.rm = TRUE),
    aug_exp_std   = (augmentation_share - mean(lookup$augmentation_share, na.rm = TRUE)) /
                     sd(lookup$augmentation_share, na.rm = TRUE)
  ) |>
  arrange(country, year) |>
  group_by(country) |>
  mutate(real_exrate_lnchange = log(exch_rate_lcu_usd) -
           log(dplyr::lag(exch_rate_lcu_usd))) |>
  ungroup()

writeLines(c(
  "# africa_genai_real_panel.csv  -- BUILT BY build_real_panel.R",
  paste0("# Built: ", Sys.Date(),
         " | Outcome+covariates: World Bank WDI (live API). ",
         "Treatment subst_exp_c: Global Automation Atlas via paper Table A."),
  "# selfemployment_share = SL.EMP.SELF.ZS (% employment, modeled ILO estimate)."
), "africa_genai_real_panel.csv")
suppressWarnings(write.table(panel, "africa_genai_real_panel.csv", sep = ",",
            row.names = FALSE, append = TRUE, col.names = TRUE))

cat("\nBuilt africa_genai_real_panel.csv:",
    nrow(panel), "rows,", length(unique(panel$country)), "countries,",
    length(unique(panel$year)), "years.\n")
cat("Self-employment non-NA:", sum(!is.na(panel$selfemployment_share)),
    "| Informal-emp non-NA:", sum(!is.na(panel$informal_emp_rate)),
    "| GDP non-NA:", sum(!is.na(panel$gdp_ppc_ppp)),
    "| internet non-NA:", sum(!is.na(panel$internet_pct)), "\n")
