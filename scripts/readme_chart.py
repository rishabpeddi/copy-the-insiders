"""Draw docs/dev_growth.png: growth of $1, each strategy's dev-period primary run vs SPY total return."""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SURFACE, INK, MUTED, GRID, SPY = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df", "#8a8984"
PANELS = [("insider", "Insider purchases (Form 4)", "#2a78d6"),
          ("congress", "Congress purchases (House + Senate)", "#eb6834")]

fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True, facecolor=SURFACE)
for ax, (group, title, color) in zip(axes, PANELS, strict=True):
    d = pd.read_parquet(ROOT / f"reports/dev_results/{group}_primary/daily.parquet")
    d["date"] = pd.to_datetime(d["date"])
    ax.set_facecolor(SURFACE)
    ax.plot(d["date"], d["spy_nav"], color=SPY, lw=1.4, ls=(0, (4, 2)), label="SPY total return")
    ax.plot(d["date"], d["nav"], color=color, lw=1.4, label="Strategy, after costs")
    for y, lab, c in [(d["nav"].iloc[-1], f"Strategy ${d['nav'].iloc[-1]:.2f}", INK),
                      (d["spy_nav"].iloc[-1], f"SPY ${d['spy_nav'].iloc[-1]:.2f}", MUTED)]:
        ax.annotate(lab, (d["date"].iloc[-1], y), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=9, color=c)
    ax.set_title(title, loc="left", fontsize=11, color=INK, pad=8)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.legend(frameon=False, fontsize=9, labelcolor=MUTED, loc="upper left")
axes[0].set_ylabel("Growth of $1", color=MUTED, fontsize=9)
fig.suptitle("Dev period 2014–2021 (not the pre-registered test). Free price data, survivors only.",
             x=0.01, ha="left", fontsize=9, color=MUTED, y=0.035)
fig.tight_layout(rect=(0, 0.08, 0.95, 1))
out = ROOT / "docs" / "dev_growth.png"
fig.savefig(out, dpi=160, facecolor=SURFACE)
print(out)
