#!/usr/bin/env python3
"""
Overlay your measured results against digitized data from the CellReplay paper.

Paper figures digitized from Figure 10 and Figure 12 (T-Mobile, stationary):
  - Fig 10 top:    RTT CDF  (Live, CellReplay, Mahimahi)
  - Fig 10 bottom: TCT vs train size (Live, CellReplay, Mahimahi)
  - Fig 12:        Download time vs file size (Live, CellReplay, Mahimahi)

Your data: baseline (Ethernet) + netem variants
"""

import json, os, statistics
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

plt.rcParams.update(
    {
        "font.size": 10,
        "axes.labelsize": 11,
        "axes.titlesize": 11,
        "legend.fontsize": 8.5,
        "lines.linewidth": 1.8,
        "figure.dpi": 150,
    }
)

OUT_DIR = "figures_vs_paper"
os.makedirs(OUT_DIR, exist_ok=True)

# ── Paper digitized values (T-Mobile, stationary) ─────────────────────────────
# Fig 10 top: RTT CDF -- read from graph, X=RTT(ms), Y=CDF
PAPER_RTT = {
    "Live": [
        (30, 0),
        (35, 0.02),
        (40, 0.08),
        (45, 0.2),
        (50, 0.36),
        (55, 0.52),
        (60, 0.66),
        (65, 0.77),
        (70, 0.86),
        (75, 0.93),
        (80, 0.97),
        (90, 1.0),
    ],
    "CellReplay": [
        (30, 0),
        (35, 0.03),
        (40, 0.10),
        (45, 0.22),
        (50, 0.38),
        (55, 0.54),
        (60, 0.67),
        (65, 0.78),
        (70, 0.87),
        (75, 0.93),
        (80, 0.97),
        (90, 1.0),
    ],
    "Mahimahi": [
        (28, 0),
        (32, 0.03),
        (36, 0.10),
        (40, 0.25),
        (44, 0.45),
        (48, 0.60),
        (52, 0.73),
        (56, 0.83),
        (60, 0.91),
        (65, 0.96),
        (72, 1.0),
    ],
}

# Fig 10 bottom: TCT vs train size (ms) -- T-Mobile
PAPER_TCT_SIZES = [1, 10, 25, 50, 75, 100, 150, 200]
PAPER_TCT = {
    "Live": [42, 46, 50, 57, 65, 72, 79, 86],
    "CellReplay": [42, 46, 50, 57, 64, 70, 77, 83],
    "Mahimahi": [41, 44, 47, 51, 54, 57, 59, 62],
}

# Fig 12: Download time vs file size (ms) -- T-Mobile
PAPER_DL_SIZES = [1, 10, 50, 100, 150, 200, 250]
PAPER_DL = {
    "Live": [46, 48, 53, 58, 63, 68, 73],
    "CellReplay": [46, 48, 52, 57, 62, 66, 72],
    "Mahimahi": [41, 42, 44, 47, 50, 52, 55],
}


# ── Load your results ─────────────────────────────────────────────────────────
def load(path):
    with open(path) as f:
        d = json.load(f)
    d["_path"] = path
    return d


files = {
    "baseline": "results_baseline.json",
    "netem_50ms": "results_netem_50ms.json",
    "netem_500ms": "results_netem_500ms.json",
    "netem_dist": "results_netem_dist.json",
}
results = {k: load(f"/mnt/project/{v}") for k, v in files.items()}

TRAIN_SIZES = [1, 10, 25, 50, 75, 100, 150, 200]
FILE_SIZES_KB = [1, 10, 50, 100, 250]

# Color scheme: paper=muted, yours=vivid
PAPER_COLORS = {
    "Live": "#2ca02c",  # green
    "CellReplay": "#1f77b4",  # blue
    "Mahimahi": "#9467bd",  # purple
}
YOUR_COLORS = {
    "baseline": "#d62728",  # red
    "netem_50ms": "#ff7f0e",  # orange
    "netem_500ms": "#8c564b",  # brown
    "netem_dist": "#e377c2",  # pink
}
YOUR_LABELS = {
    "baseline": "Yours: Ethernet baseline",
    "netem_50ms": "Yours: netem 50ms",
    "netem_500ms": "Yours: netem 500ms",
    "netem_dist": "Yours: netem+dist",
}


# ─────────────────────────────────────────────────────────────────────────────
# Figure 1: RTT CDF — paper (dashed) + yours (solid)
# ─────────────────────────────────────────────────────────────────────────────
def plot_rtt_comparison():
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))

    # Left panel: raw CDFs (different absolute scales)
    ax = axes[0]
    for name, pts in PAPER_RTT.items():
        xs, ys = zip(*pts)
        ax.plot(xs, ys, color=PAPER_COLORS[name], linestyle="--", linewidth=1.6, label=f"Paper: {name}")
    for key, d in results.items():
        rtts = sorted(d["rtt_ms"])
        cdf = np.arange(1, len(rtts) + 1) / len(rtts)
        ax.plot(rtts, cdf, color=YOUR_COLORS[key], linestyle="-", linewidth=1.6, label=YOUR_LABELS[key])
    ax.set_xlabel("RTT (ms)")
    ax.set_ylabel("CDF")
    ax.set_title("RTT CDF — Absolute scale\n(paper T-Mobile vs your Ethernet+netem)")
    ax.set_ylim(0, 1)
    ax.set_xlim(0, 200)
    ax.legend(fontsize=7.5)
    ax.grid(True, alpha=0.3)

    # Right panel: normalized CDFs (shape comparison)
    # Shift each distribution so median = 0 to compare spread/shape
    ax = axes[1]
    for name, pts in PAPER_RTT.items():
        xs, ys = zip(*pts)
        xs = np.array(xs)
        ys = np.array(ys)
        # find median
        med = float(np.interp(0.5, ys, xs))
        ax.plot(xs - med, ys, color=PAPER_COLORS[name], linestyle="--", linewidth=1.6, label=f"Paper: {name}")
    for key, d in results.items():
        rtts = np.array(sorted(d["rtt_ms"]))
        cdf = np.arange(1, len(rtts) + 1) / len(rtts)
        med = float(np.interp(0.5, cdf, rtts))
        ax.plot(rtts - med, cdf, color=YOUR_COLORS[key], linestyle="-", linewidth=1.6, label=YOUR_LABELS[key])
    ax.set_xlabel("RTT − median (ms)  [median-centered]")
    ax.set_ylabel("CDF")
    ax.set_title("RTT CDF — Median-centered shape\n(compare spread/variability)")
    ax.set_ylim(0, 1)
    ax.set_xlim(-40, 80)
    ax.axvline(0, color="gray", linestyle=":", linewidth=1, alpha=0.5)
    ax.legend(fontsize=7.5)
    ax.grid(True, alpha=0.3)

    plt.suptitle("Figure 10 (top) Comparison — RTT CDF", fontsize=12, y=1.02)
    plt.tight_layout()
    out = f"{OUT_DIR}/compare_rtt_cdf.png"
    plt.savefig(out, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")


# ─────────────────────────────────────────────────────────────────────────────
# Figure 2: TCT vs Train Size
# ─────────────────────────────────────────────────────────────────────────────
def plot_tct_comparison():
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))

    # Left: absolute TCT
    ax = axes[0]
    for name, vals in PAPER_TCT.items():
        ax.plot(
            PAPER_TCT_SIZES,
            vals,
            color=PAPER_COLORS[name],
            linestyle="--",
            marker="^",
            markersize=5,
            label=f"Paper: {name}",
        )
    for key, d in results.items():
        train = d.get("train", {})
        means = []
        for s in TRAIN_SIZES:
            entry = train.get(str(s), {})
            tct_vals = entry.get("tct_ms", []) if isinstance(entry, dict) else []
            means.append(statistics.mean(tct_vals) if tct_vals else float("nan"))
        ax.plot(
            TRAIN_SIZES,
            means,
            color=YOUR_COLORS[key],
            linestyle="-",
            marker="o",
            markersize=5,
            label=YOUR_LABELS[key],
        )
    ax.set_xlabel("Train size (packets)")
    ax.set_ylabel("Mean TCT (ms)")
    ax.set_title("TCT vs Train Size — Absolute")
    ax.legend(fontsize=7.5)
    ax.grid(True, alpha=0.3)

    # Right: normalized (0-1 scale, so shape comparison works across different
    #         absolute bandwidths)
    ax = axes[1]
    for name, vals in PAPER_TCT.items():
        v = np.array(vals, dtype=float)
        ax.plot(
            PAPER_TCT_SIZES,
            (v - v[0]) / (v[-1] - v[0]),
            color=PAPER_COLORS[name],
            linestyle="--",
            marker="^",
            markersize=5,
            label=f"Paper: {name}",
        )
    for key, d in results.items():
        train = d.get("train", {})
        means = []
        for s in TRAIN_SIZES:
            entry = train.get(str(s), {})
            tct_vals = entry.get("tct_ms", []) if isinstance(entry, dict) else []
            means.append(statistics.mean(tct_vals) if tct_vals else float("nan"))
        v = np.array(means, dtype=float)
        span = v[-1] - v[0]
        if span > 0:
            ax.plot(
                TRAIN_SIZES,
                (v - v[0]) / span,
                color=YOUR_COLORS[key],
                linestyle="-",
                marker="o",
                markersize=5,
                label=YOUR_LABELS[key],
            )
    ax.set_xlabel("Train size (packets)")
    ax.set_ylabel("Normalized TCT  (0=min, 1=max)")
    ax.set_title("TCT vs Train Size — Normalized shape\n(key: non-linearity pattern)")
    ax.legend(fontsize=7.5)
    ax.grid(True, alpha=0.3)

    # Annotate what to look for
    ax.annotate(
        "Paper: Live/CellReplay\nshow non-linear\n(light→heavy transition)",
        xy=(75, 0.55),
        fontsize=7.5,
        color=PAPER_COLORS["Live"],
        ha="center",
        bbox=dict(boxstyle="round,pad=0.2", fc="lightyellow", alpha=0.8),
    )
    ax.annotate(
        "Mahimahi: nearly\nlinear (pure BW)",
        xy=(120, 0.28),
        fontsize=7.5,
        color=PAPER_COLORS["Mahimahi"],
        ha="center",
        bbox=dict(boxstyle="round,pad=0.2", fc="lightyellow", alpha=0.8),
    )

    plt.suptitle("Figure 10 (bottom) Comparison — TCT vs Train Size", fontsize=12, y=1.02)
    plt.tight_layout()
    out = f"{OUT_DIR}/compare_tct.png"
    plt.savefig(out, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")


# ─────────────────────────────────────────────────────────────────────────────
# Figure 3: Download Time vs File Size
# ─────────────────────────────────────────────────────────────────────────────
def plot_download_comparison():
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))

    # Left: absolute
    ax = axes[0]
    for name, vals in PAPER_DL.items():
        ax.plot(
            PAPER_DL_SIZES,
            vals,
            color=PAPER_COLORS[name],
            linestyle="--",
            marker="^",
            markersize=5,
            label=f"Paper: {name}",
        )
    for key, d in results.items():
        dl = d.get("download_ms", {})
        means = []
        for kb in FILE_SIZES_KB:
            vals_list = dl.get(str(kb), [])
            means.append(np.mean(vals_list) if vals_list else float("nan"))
        ax.plot(
            FILE_SIZES_KB,
            means,
            color=YOUR_COLORS[key],
            linestyle="-",
            marker="o",
            markersize=5,
            label=YOUR_LABELS[key],
        )
    ax.set_xlabel("File size (KB)")
    ax.set_ylabel("Mean download time (ms)")
    ax.set_title("Download Time — Absolute")
    ax.legend(fontsize=7.5)
    ax.grid(True, alpha=0.3)

    # Right: normalized
    ax = axes[1]
    for name, vals in PAPER_DL.items():
        v = np.array(vals, dtype=float)
        ax.plot(
            PAPER_DL_SIZES,
            (v - v[0]) / (v[-1] - v[0]),
            color=PAPER_COLORS[name],
            linestyle="--",
            marker="^",
            markersize=5,
            label=f"Paper: {name}",
        )
    for key, d in results.items():
        dl = d.get("download_ms", {})
        means = []
        for kb in FILE_SIZES_KB:
            vals_list = dl.get(str(kb), [])
            means.append(np.mean(vals_list) if vals_list else float("nan"))
        v = np.array(means, dtype=float)
        span = v[-1] - v[0]
        if span > 0:
            ax.plot(
                FILE_SIZES_KB,
                (v - v[0]) / span,
                color=YOUR_COLORS[key],
                linestyle="-",
                marker="o",
                markersize=5,
                label=YOUR_LABELS[key],
            )
    ax.set_xlabel("File size (KB)")
    ax.set_ylabel("Normalized download time  (0=min, 1=max)")
    ax.set_title("Download Time — Normalized shape\n(key: non-linear growth?)")
    ax.legend(fontsize=7.5)
    ax.grid(True, alpha=0.3)

    plt.suptitle("Figure 12 Comparison — Download Time vs File Size", fontsize=12, y=1.02)
    plt.tight_layout()
    out = f"{OUT_DIR}/compare_download.png"
    plt.savefig(out, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")


# ─────────────────────────────────────────────────────────────────────────────
# Figure 4: Summary comparison table as figure
# ─────────────────────────────────────────────────────────────────────────────
def plot_summary_table():
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.axis("off")

    rows = []

    # RTT median
    paper_live_med = 55  # from digitized CDF
    paper_cr_med = 55
    paper_mahi_med = 46  # ~16.88% below live

    for key, d in results.items():
        rtts = sorted(d["rtt_ms"])
        med = statistics.median(rtts)
        p95 = rtts[int(0.95 * len(rtts))]
        p5 = rtts[int(0.05 * len(rtts))]
        spread = p95 - p5

        # TCT non-linearity: ratio TCT@200/TCT@1
        train = d.get("train", {})

        def tct_mean(s):
            e = train.get(str(s), {})
            v = e.get("tct_ms", []) if isinstance(e, dict) else []
            return statistics.mean(v) if v else float("nan")

        ratio = tct_mean(200) / tct_mean(1) if tct_mean(1) else float("nan")

        # Download slope: (250KB - 1KB) / 250KB mean
        dl = d.get("download_ms", {})
        d1 = np.mean(dl.get("1", [])) if dl.get("1") else float("nan")
        d250 = np.mean(dl.get("250", [])) if dl.get("250") else float("nan")
        dl_slope = (d250 - d1) if not np.isnan(d1) else float("nan")

        rows.append(
            [
                YOUR_LABELS[key],
                f"{med:.0f} ms",
                f"{spread:.0f} ms",
                f"{ratio:.2f}x",
                f"{d1:.0f} ms",
                f"{d250:.0f} ms",
                f"{dl_slope:.0f} ms",
            ]
        )

    # Add paper reference rows
    paper_tct_ratio_live = PAPER_TCT["Live"][-1] / PAPER_TCT["Live"][0]
    paper_tct_ratio_cr = PAPER_TCT["CellReplay"][-1] / PAPER_TCT["CellReplay"][0]
    paper_tct_ratio_mahi = PAPER_TCT["Mahimahi"][-1] / PAPER_TCT["Mahimahi"][0]

    paper_dl_live_slope = PAPER_DL["Live"][-1] - PAPER_DL["Live"][0]
    paper_dl_cr_slope = PAPER_DL["CellReplay"][-1] - PAPER_DL["CellReplay"][0]
    paper_dl_mahi_slope = PAPER_DL["Mahimahi"][-1] - PAPER_DL["Mahimahi"][0]

    paper_live_spread = 90 - 35  # p5→p95 from RTT CDF
    paper_cr_spread = 90 - 35
    paper_mahi_spread = 72 - 28

    rows_paper = [
        [
            "Paper: Live (T-Mobile cellular)",
            f"{paper_live_med} ms",
            f"{paper_live_spread} ms",
            f"{paper_tct_ratio_live:.2f}x",
            f"{PAPER_DL['Live'][0]} ms",
            f"{PAPER_DL['Live'][-1]} ms",
            f"{paper_dl_live_slope} ms",
        ],
        [
            "Paper: CellReplay",
            f"{paper_cr_med} ms",
            f"{paper_cr_spread} ms",
            f"{paper_tct_ratio_cr:.2f}x",
            f"{PAPER_DL['CellReplay'][0]} ms",
            f"{PAPER_DL['CellReplay'][-1]} ms",
            f"{paper_dl_cr_slope} ms",
        ],
        [
            "Paper: Mahimahi",
            f"{paper_mahi_med} ms",
            f"{paper_mahi_spread} ms",
            f"{paper_tct_ratio_mahi:.2f}x",
            f"{PAPER_DL['Mahimahi'][0]} ms",
            f"{PAPER_DL['Mahimahi'][-1]} ms",
            f"{paper_dl_mahi_slope} ms",
        ],
    ]

    all_rows = rows_paper + [["—"] * 7] + rows

    col_labels = [
        "Configuration",
        "RTT median",
        "RTT spread\n(p5→p95)",
        "TCT ratio\n(200pkt / 1pkt)",
        "DL time\n@ 1 KB",
        "DL time\n@ 250 KB",
        "DL slope\n(250−1 KB)",
    ]

    tbl = ax.table(
        cellText=all_rows,
        colLabels=col_labels,
        loc="center",
        cellLoc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8.5)
    tbl.scale(1, 1.6)

    # Color paper rows green/blue/purple, yours orange/red
    paper_row_colors = ["#d5f5d5", "#d5e8f5", "#ead5f5"]
    your_row_colors = ["#fff0e0", "#fff0e0", "#fff0e0", "#fff0e0"]
    for i, color in enumerate(paper_row_colors, start=1):
        for j in range(len(col_labels)):
            tbl[i, j].set_facecolor(color)
    for i, color in enumerate(your_row_colors, start=len(paper_row_colors) + 2):
        for j in range(len(col_labels)):
            tbl[i, j].set_facecolor(color)

    ax.set_title("Summary Comparison: Paper (T-Mobile) vs Your Results", fontsize=12, pad=10)
    plt.tight_layout()
    out = f"{OUT_DIR}/compare_summary_table.png"
    plt.savefig(out, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")


# ─────────────────────────────────────────────────────────────────────────────

print(f"Generating comparison figures → {OUT_DIR}/")
plot_rtt_comparison()
plot_tct_comparison()
plot_download_comparison()
plot_summary_table()
print("\nDone.")
print(
    """
Key things to look for:
  compare_rtt_cdf.png:
    LEFT  — Your netem_50ms/500ms RTTs cluster near paper's cellular range (~55-70ms)
    RIGHT — Shape comparison: does your RTT spread match paper's cellular spread?
            Paper Live/CellReplay show ~55ms spread (p5→p95); Mahimahi is narrower.

  compare_tct.png:
    RIGHT — Normalized shape: paper's Live/CellReplay show a concave-up curve
            (slow to fast transition). Mahimahi is nearly straight (linear BW).
            Your netem variants should show which pattern they match.

  compare_download.png:
    RIGHT — Normalized shape: paper shows sub-linear growth for small files
            (RTT-dominated) then linear (BW-dominated). Does your netem do that?

  compare_summary_table.png:
    Direct numbers — RTT median, RTT spread, TCT ratio, DL slope.
    Compare your rows to the paper's green rows.
"""
)
