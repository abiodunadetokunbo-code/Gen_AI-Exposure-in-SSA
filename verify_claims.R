# =============================================================================
# verify_claims.R  -- Test the paper's claims against the REAL panel.
# Outcome tested: self-employment share (WDI SL.EMP.SELF.ZS, % of employment).
# NOTE ON SCALE: WDI series is in PERCENT (0-100), so a DiD coefficient is read
#   directly in percentage points (pp). The paper reports 0.036 on a 0-1
#   PROPORTION scale = 3.6 pp. So compare our pp coefficient to 3.6.
# =============================================================================
suppressMessages({library(fixest); library(dplyr)})

df <- read.csv("africa_genai_real_panel.csv", comment.char = "#",
               stringsAsFactors = FALSE)

df <- df |>
  group_by(country) |>
  mutate(baseline_se = mean(selfemployment_share[year == 2019], na.rm = TRUE),
         internet_dm = internet_pct - mean(df$internet_pct, na.rm = TRUE)) |>
  ungroup()

df_main  <- df |> filter(!is.na(selfemployment_share), covid_window == 0)

cat("== REAL-DATA TEST: self-employment share ~ substitution exposure x post ==\n")
cat("Sample:", nrow(df_main), "country-years,",
    length(unique(df_main$country)), "countries.\n\n")

# (1) FE only
m1 <- feols(selfemployment_share ~ I(post*subst_exp_std) | country + year,
            data = df_main, cluster = ~country)
# (2) + macro controls
m2 <- feols(selfemployment_share ~ I(post*subst_exp_std) +
              log_gdp_ppc + urbanization_pct + female_lfp | country + year,
            data = df_main, cluster = ~country)
# (3) preferred: + baseline self-emp x post
m3 <- feols(selfemployment_share ~ I(post*subst_exp_std) +
              log_gdp_ppc + urbanization_pct + female_lfp + I(baseline_se*post) |
              country + year, data = df_main, cluster = ~country)
# (4) triple-diff: internet moderation (real internet)
m4 <- feols(selfemployment_share ~ I(post*subst_exp_std) +
              I(post*subst_exp_std*internet_dm) + I(post*internet_dm) +
              log_gdp_ppc + urbanization_pct + female_lfp | country + year,
            data = df_main, cluster = ~country)
# (5) placebo: fake shock in 2019 (pre-period only, drop true post)
df_plac <- df |> filter(!is.na(selfemployment_share), year <= 2021) |>
  mutate(post_plac = as.integer(year >= 2019))
m5 <- feols(selfemployment_share ~ I(post_plac*subst_exp_std) +
              log_gdp_ppc + urbanization_pct + female_lfp | country + year,
            data = df_plac, cluster = ~country)

etable(m1, m2, m3, m4,
       headers = c("FE only","+controls","preferred","triple-diff"),
       dict = c("I(post * subst_exp_std)"="SubstExp x Post",
                "I(post * subst_exp_std * internet_dm)"="SubstExp x Post x Internet",
                "I(post * internet_dm)"="Internet x Post"),
       digits = 3, fitstat = ~ n + r2)

grab <- function(m, term="I(post * subst_exp_std)") {
  s <- summary(m)$coeftable
  if (!term %in% rownames(s)) return(c(NA,NA,NA))
  c(coef = s[term,1], se = s[term,2], p = s[term,4])
}
cat("\n================  HEADLINE COMPARISON  ================\n")
cat(sprintf("Paper claim (self-employment): +3.6 pp per SD of substitution exposure (p=0.019)\n\n"))
for (nm in c("m1","m2","m3")) {
  g <- grab(get(nm))
  cat(sprintf("%-10s real-data coef = %+6.3f pp   SE = %5.3f   p = %5.3f\n",
              nm, g[1], g[2], g[3]))
}
gp <- grab(m5, "I(post_plac * subst_exp_std)")
cat(sprintf("%-10s placebo(2019) = %+6.3f pp   SE = %5.3f   p = %5.3f  (should be ~0)\n",
            "m5", gp[1], gp[2], gp[3]))
gt <- grab(m4, "I(post * subst_exp_std * internet_dm)")
cat(sprintf("triple-diff Internet interaction = %+6.4f  SE = %6.4f  p = %5.3f\n",
            gt[1], gt[2], gt[3]))
cat("Paper claims this interaction is negative (connectivity attenuates).\n")

# ===========================================================================
# OUTCOME #1: informal employment rate (real ILOSTAT EMP_NIFL_SEX_RT_A)
# Paper claim: +4.2 pp per SD of substitution exposure (p=0.021).
# Series is survey-based and SPARSE (152 obs, 33 countries).
# ===========================================================================
df_inf <- df |> filter(!is.na(informal_emp_rate), covid_window == 0)
cat(sprintf("\n== REAL-DATA TEST: informal employment rate (n=%d, %d countries) ==\n",
            nrow(df_inf), length(unique(df_inf$country))))
mi1 <- feols(informal_emp_rate ~ I(post*subst_exp_std) | country + year,
             data = df_inf, cluster = ~country)
mi2 <- feols(informal_emp_rate ~ I(post*subst_exp_std) +
               log_gdp_ppc + urbanization_pct + female_lfp | country + year,
             data = df_inf, cluster = ~country)
cat(sprintf("Paper claim (informal emp): +4.2 pp per SD (p=0.021)\n"))
for (nm in c("mi1","mi2")) {
  g <- grab(get(nm))
  cat(sprintf("%-10s real-data coef = %+6.3f pp   SE = %5.3f   p = %5.3f\n",
              nm, g[1], g[2], g[3]))
}
cat("\nNOTE: real ILOSTAT informal series has 152 obs (33 countries), not the\n",
    "paper's claimed ~470; within-FE post variation is very thin.\n")
