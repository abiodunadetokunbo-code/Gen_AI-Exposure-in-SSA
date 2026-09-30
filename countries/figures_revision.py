"""Figures for the revision-2 paper. Writes vector PDFs into paper/figures/.

  fig_occupation_gradient          mean exposure and employment share by ISCO
                                   major group, as paired bars. The mirrored
                                   shape is the point: the groups with long
                                   exposure bars have short employment bars.
  fig_group_means_ci               group means with 95% design-based intervals.
  fig_macro_exposure_informality   country AI-route exposure against the
                                   informal employment rate, African economies.

Numbers come from the cross-checked result files, never recomputed here, apart
from the major-group shares which are counts off the worker file.

fig_tza_robustness is retired: the own-use farmer sensitivity is now
Table~\\ref{tab:imputed}, which covers both countries rather than Tanzania alone.

Colours are the Okabe-Ito scientific pair, which clears the lightness band,
chroma floor, CVD separation and normal-vision checks with margin. Series
identity never rests on colour alone; marker shape carries it too, so the
figures survive greyscale printing.
"""
import json
import os

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

BLUE, VERM, INK, GRID = "#0072B2", "#D55E00", "0.25", "0.85"

plt.rcParams.update({
    "font.family": "serif", "font.size": 10,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": INK, "axes.labelcolor": INK,
    "xtick.color": INK, "ytick.color": INK, "text.color": INK,
    "pdf.fonttype": 42,
})

FIG = "../paper/figures"
os.makedirs(FIG, exist_ok=True)
P = pd.read_csv("harmonized_workers_v2.csv", low_memory=False)
res = json.load(open("results/revision_v2_py.json"))
des = json.load(open("results/survey_design_v2_py.json"))
A = "auto_genai"

LBL = {1: "Managers", 2: "Professionals", 3: "Technicians", 4: "Clerical support",
       5: "Service and sales", 6: "Skilled agriculture", 7: "Craft and trades",
       8: "Plant and machine", 9: "Elementary"}

# ---------- 1. occupational gradient ----------
prof = res["major_profile"]["pooled"]
t = pd.DataFrame([{"major": int(k), "mean": v["mean"], "share": v["share"]}
                  for k, v in prof.items()])
t["label"] = t.major.map(LBL)
t = t.sort_values("mean", ascending=True).reset_index(drop=True)
y = np.arange(len(t))

fig, (axL, axR) = plt.subplots(
    1, 2, sharey=True, figsize=(7.4, 4.5),
    gridspec_kw={"wspace": 0.08, "width_ratios": [1, 1]})

axL.barh(y, t["mean"], height=0.62, color=BLUE, zorder=3)
axL.set_xlim(0, 0.82)
axL.invert_xaxis()
axL.set_xlabel("Mean generative-AI exposure (0 to 1)")
for yi, v in zip(y, t["mean"]):
    axL.text(v + 0.018, yi, f"{v:.3f}", va="center", ha="right", fontsize=8.5)

axR.barh(y, t["share"], height=0.62, color=VERM, zorder=3)
axR.set_xlim(0, 70)
axR.set_xlabel("Share of pooled workers (%)")
for yi, v in zip(y, t["share"]):
    axR.text(v + 1.6, yi, f"{v:.1f}", va="center", ha="left", fontsize=8.5)

for ax in (axL, axR):
    ax.grid(axis="x", ls=":", lw=0.5, color=GRID)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
axL.set_yticks(y)
axL.set_yticklabels(t.label, fontsize=9)
axL.tick_params(axis="y", pad=6)
axR.set_ylim(-0.7, len(t) - 0.3)
# reserve room for the category labels, which sit outside the left axes
fig.subplots_adjust(left=0.205, right=0.975, top=0.97, bottom=0.115)
fig.savefig(f"{FIG}/fig_occupation_gradient.pdf")
plt.close(fig)

# ---------- 2. group means with design-based intervals ----------
ci = des["group_means_ci"]
rows = [("Pooled", ci["pooled"], False),
        ("Agriculture", ci["status_agriculture"], False),
        ("Own-account, non-agriculture", ci["status_selfemp_nonag"], False),
        ("Wage employee, non-agriculture", ci["status_wage_nonag"], False),
        ("Wage, informal", ci["wage_informal"], True),
        ("Wage, formal", ci["wage_formal"], True),
        ("Rural", ci["rural"], False), ("Urban", ci["urban"], False),
        ("Female", ci["female"], False), ("Male", ci["male"], False)]

fig, ax = plt.subplots(figsize=(7.0, 4.3))
y = np.arange(len(rows))[::-1]
for yi, (lab, v, hl) in zip(y, rows):
    # most intervals are narrower than the marker, so cap them to stay readable
    ax.errorbar(v["mean"], yi, xerr=[[v["mean"] - v["lo"]], [v["hi"] - v["mean"]]],
                fmt="none", ecolor=INK, elinewidth=1.2, capsize=3, capthick=1.2, zorder=2)
    ax.plot(v["mean"], yi, "s" if hl else "o", ms=6.5 if hl else 6,
            color=VERM if hl else BLUE, zorder=3,
            markeredgecolor="white", markeredgewidth=0.6)
ax.axvline(ci["pooled"]["mean"], color="0.6", ls="--", lw=0.8, zorder=1)
ax.set_yticks(y)
ax.set_yticklabels([lab for lab, _, _ in rows], fontsize=9)
ax.set_xlabel("Mean generative-AI exposure (0 to 1)")
ax.set_xlim(0, 0.25)
ax.grid(axis="x", ls=":", lw=0.5, color=GRID)
ax.set_axisbelow(True)
h = [plt.Line2D([], [], marker="o", ls="", color=BLUE, ms=6, label="All workers"),
     plt.Line2D([], [], marker="s", ls="", color=VERM, ms=6.5, label="Wage workers by formality")]
ax.legend(handles=h, fontsize=8.5, frameon=False, loc="lower right")
fig.tight_layout()
fig.savefig(f"{FIG}/fig_group_means_ci.pdf")
plt.close(fig)

# ---------- 3. country exposure against informality ----------
C = pd.read_csv("atlas_ai_route_v2_countries.csv")
v = C.dropna(subset=["informal", "ai_route_share"]).copy()
mine = v.iso3.isin(["NGA", "TZA", "UGA"])

fig, ax = plt.subplots(figsize=(7.2, 5.0))
ax.scatter(v.loc[~mine, "informal"], v.loc[~mine, "ai_route_share"], s=34,
           color=BLUE, alpha=0.75, zorder=2, edgecolor="white", linewidth=0.6,
           label="Other African economies")
ax.scatter(v.loc[mine, "informal"], v.loc[mine, "ai_route_share"], s=90, marker="D",
           color=VERM, zorder=4, edgecolor="white", linewidth=0.9,
           label="Countries with worker-level data")
for _, r in v[mine].iterrows():
    ax.annotate(r.iso3, (r.informal, r.ai_route_share), fontsize=9, fontweight="bold",
                xytext=(7, 3), textcoords="offset points", zorder=5)
b, a = np.polyfit(v.informal, v.ai_route_share, 1)
xs = np.linspace(v.informal.min(), v.informal.max(), 50)
ax.plot(xs, a + b * xs, color="0.55", ls="--", lw=1.1, zorder=1)
ax.set_xlabel("Informal employment rate (% of employment)")
ax.set_ylabel("Share of employment in tasks exposed through AI")
ax.grid(ls=":", lw=0.5, color=GRID)
ax.set_axisbelow(True)
ax.legend(fontsize=8.5, frameon=False, loc="upper right")
fig.tight_layout()
fig.savefig(f"{FIG}/fig_macro_exposure_informality.pdf")
plt.close(fig)

print("wrote three vector figures to paper/figures/")
for f in ["fig_occupation_gradient", "fig_group_means_ci", "fig_macro_exposure_informality"]:
    print(f"  {f}.pdf  {os.path.getsize(f'{FIG}/{f}.pdf'):,} bytes")
