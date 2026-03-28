#!/usr/bin/env python3
"""
plot_all.py — Unified comparison plots

Combines:
  - Your measured results (results_*.json from run_tests.py)
  - Digitized data from the CellReplay paper (Figures 10, 12)

Produces 4 figures that mirror the paper's evaluation section:
  fig1_rtt_cdf.png         — Figure 10 top
  fig2_tct_vs_size.png     — Figure 10 bottom
  fig3_download_time.png   — Figure 12
  fig4_rel_arrivals.png    — Figure 5 style

Usage:
  python3 plot_all.py --out-dir figures/
"""

import argparse
import json
import os
import sys
import statistics
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

# ── Paper data ─────────────────────────────────────────────────────────────────
# Import from paper_data.py (must be in the same directory or on PYTHONPATH).
# paper_data.py contains digitized values from CellReplay NSDI '25,
# Figures 10, 11, 12, 13, 14 (T-Mobile + Verizon, stationary).
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

from paper_data import fig10_rtt_cdf, fig10_tct, fig12_download  # noqa: E402

# Map paper_data structures → names used by the plot functions below.
# All three use T-Mobile / stationary ("good") conditions to match the paper's
# primary evaluation environment (§5.4, §5.6).
OPERATOR = "T-Mobile"

PAPER_RTT_CDF = fig10_rtt_cdf[OPERATOR]  # {"Live": [...], "CellReplay": [...], "Mahimahi": [...]}

PAPER_TCT = {  # values as np.arrays for arithmetic convenience
    name: np.array(vals) for name, vals in fig10_tct[OPERATOR].items()
}
PAPER_TCT_SIZES = fig10_tct["train_sizes"]  # [1, 10, 25, 50, 75, 100, 150, 200]

PAPER_DL_SIZES = fig12_download["file_sizes_kb"]  # [1, 10, 50, 100, 150, 200, 250]
PAPER_DL = {name: np.array(fig12_download[OPERATOR][name]) for name in ["Live", "CellReplay", "Mahimahi"]}
PAPER_DL_CI = {
    name: np.array(fig12_download[OPERATOR][f"{name}_ci"]) for name in ["Live", "CellReplay", "Mahimahi"]
}

# ── Style ──────────────────────────────────────────────────────────────────────
plt.rcParams.update(
    {
        "font.size": 10,
        "axes.labelsize": 11,
        "axes.titlesize": 10,
        "legend.fontsize": 8,
        "lines.linewidth": 1.8,
        "figure.dpi": 150,
    }
)

# Paper lines: dashed, muted
PAPER_COLOR = {
    "Live": "#2ca02c",  # green
    "CellReplay": "#1f77b4",  # blue
    "Mahimahi": "#9467bd",  # purple
}
# Your lines: solid, vivid
YOUR_COLOR = {
    "baseline": "#d62728",  # red
    "netem_50ms": "#ff7f0e",  # orange
    "netem_500ms": "#8c564b",  # brown
    "netem_dist": "#e377c2",  # pink
}
YOUR_LABEL = {
    "baseline": "Yours — Ethernet baseline",
    "netem_50ms": "Yours — netem 50 ms idle",
    "netem_500ms": "Yours — netem 500 ms idle",
    "netem_dist": "Yours — netem + dist",
}
YOUR_MARKER = {
    "baseline": "o",
    "netem_50ms": "s",
    "netem_500ms": "^",
    "netem_dist": "D",
}

TRAIN_SIZES = [1, 10, 25, 50, 75, 100, 150, 200]
FILE_SIZES_KB = [1, 10, 50, 100, 250]

# ══════════════════════════════════════════════════════════════════════════════
# Loader
# ══════════════════════════════════════════════════════════════════════════════

RESULT_FILES = {
    "baseline": "results_baseline.json",
    "netem_50ms": "results_netem_50ms.json",
    "netem_500ms": "results_netem_500ms.json",
    "netem_dist": "results_netem_dist.json",
}


def load_results(data_dir="."):
    out = {}
    for key, fname in RESULT_FILES.items():
        path = os.path.join(data_dir, fname)
        if os.path.exists(path):
            with open(path) as f:
                out[key] = json.load(f)
        else:
            print(f"  [warn] {path} not found — skipping")
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Figure 1 — RTT CDF
# ══════════════════════════════════════════════════════════════════════════════
DESCRIPTION_RTT = """\
WHAT THIS SHOWS:
  The spread of individual packet round-trip times (RTTs).
  A wider, S-shaped curve = more variability (realistic).
  A near-vertical line = fixed/constant delay (unrealistic).

PAPER (dashed lines):
  • Live T-Mobile cellular: wide spread, 30–90 ms range.
  • CellReplay: closely matches the live curve — this is the goal.
  • Mahimahi: shifted LEFT (underestimates RTT by ~17%) and
    narrower — it collapses all the variability to a fixed delay.

YOUR DATA (solid lines):
  • Ethernet baseline: far left (~9 ms) — no cellular delay at all.
  • netem variants: RTT shifted right by the injected delay (~50–70 ms),
    but the curve is nearly vertical — netem also uses a fixed delay,
    so it has the same fundamental flaw as Mahimahi.
  • Ideal emulation would match both the median AND the spread of "Live".\
"""


def plot_rtt_cdf(results, out_path):
    fig, ax = plt.subplots(figsize=(6, 4.5))

    # Paper lines (dashed)
    for name, pts in PAPER_RTT_CDF.items():
        xs, ys = zip(*pts)
        ax.plot(
            xs, ys, color=PAPER_COLOR[name], linestyle="--", linewidth=1.8, label=f"Paper: {name} (T-Mobile)"
        )

    # Your lines (solid)
    for key, d in results.items():
        rtts = sorted(d["rtt_ms"])
        cdf = np.arange(1, len(rtts) + 1) / len(rtts)
        ax.plot(rtts, cdf, color=YOUR_COLOR[key], linestyle="-", linewidth=1.8, label=YOUR_LABEL[key])

    ax.set_xlabel("Packet RTT (ms)")
    ax.set_ylabel("CDF")
    ax.set_title("Fig 1 — RTT CDF\n(paper Fig 10 top)")
    ax.set_ylim(0, 1)
    ax.set_xlim(0, 250)
    ax.set_yticks(np.arange(0, 1.1, 0.2))

    # Legend: separate paper vs yours
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles, labels, fontsize=7.5, loc="lower right")
    ax.grid(True, alpha=0.3)

    # Annotation arrows
    ax.annotate(
        "Paper Live/CellReplay\n(wide S-curve = realistic)",
        xy=(62, 0.72),
        xytext=(110, 0.55),
        arrowprops=dict(arrowstyle="->", color=PAPER_COLOR["Live"]),
        fontsize=7.5,
        color=PAPER_COLOR["Live"],
    )
    ax.annotate(
        "Mahimahi: shifted left\n(RTT underestimated ~17%)",
        xy=(46, 0.58),
        xytext=(5, 0.40),
        arrowprops=dict(arrowstyle="->", color=PAPER_COLOR["Mahimahi"]),
        fontsize=7.5,
        color=PAPER_COLOR["Mahimahi"],
    )

    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight", dpi=720)
    plt.close()
    print(f"  Saved: {out_path}")
    print(DESCRIPTION_RTT)
    print()


# ══════════════════════════════════════════════════════════════════════════════
# Figure 2 — TCT vs Train Size
# ══════════════════════════════════════════════════════════════════════════════
DESCRIPTION_TCT = """\
WHAT THIS SHOWS:
  How long it takes to deliver N packets in a burst (train), as N grows.
  A straight line = bandwidth-only model (fixed rate).
  A curve that bends up = realistic: small trains travel fast (RTT-dominated),
  large trains hit bandwidth limits (BW-dominated).

PAPER (dashed lines):
  • Live T-Mobile: clearly non-linear — flat for small N, steeper for large N.
    This captures the light-PDO → heavy-PDO transition.
  • CellReplay: closely tracks the Live curve.
  • Mahimahi: nearly a straight line — it only uses heavy PDOs, so it
    over-estimates TCT for small trains and under-estimates for large ones.

YOUR DATA (solid lines):
  • Ethernet baseline: starts low (~9 ms), grows linearly — pure bandwidth,
    no cellular dynamics.
  • netem variants: start higher (injected delay), then grow linearly too —
    same straight-line problem as Mahimahi.\
"""


def plot_tct(results, out_path):
    fig, ax = plt.subplots(figsize=(6, 4.5))

    # Paper lines (dashed)
    for name, vals in PAPER_TCT.items():
        ax.plot(
            PAPER_TCT_SIZES,
            vals,
            color=PAPER_COLOR[name],
            linestyle="--",
            marker="^",
            markersize=5,
            linewidth=1.8,
            label=f"Paper: {name} (T-Mobile)",
        )

    # Your lines (solid)
    for key, d in results.items():
        train = d.get("train", {})
        means = []
        for s in TRAIN_SIZES:
            entry = train.get(str(s), {})
            vals = entry.get("tct_ms", []) if isinstance(entry, dict) else []
            means.append(statistics.mean(vals) if vals else float("nan"))
        ax.plot(
            TRAIN_SIZES,
            means,
            color=YOUR_COLOR[key],
            linestyle="-",
            marker=YOUR_MARKER[key],
            markersize=5,
            linewidth=1.8,
            label=YOUR_LABEL[key],
        )

    ax.set_xlabel("Train size (packets)")
    ax.set_ylabel("Mean TCT (ms)")
    ax.set_title("Fig 2 — Train Completion Time vs Train Size\n(paper Fig 10 bottom)")
    ax.legend(fontsize=7.5, loc="upper left")
    ax.grid(True, alpha=0.3)

    # Mark the light→heavy transition point (train size = 75 for T-Mobile)
    ax.axvline(75, color="gray", linestyle=":", linewidth=1, alpha=0.6)
    ax.text(77, ax.get_ylim()[0] + 5, "light→heavy\ntransition\n(T-Mobile)", fontsize=7, color="gray")

    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight", dpi=720)
    plt.close()
    print(f"  Saved: {out_path}")
    print(DESCRIPTION_TCT)
    print()


# ══════════════════════════════════════════════════════════════════════════════
# Figure 3 — Download Time vs File Size
# ══════════════════════════════════════════════════════════════════════════════
DESCRIPTION_DL = """\
WHAT THIS SHOWS:
  How long it takes to download files of different sizes over the network.
  Small files (1–10 KB) are dominated by RTT (latency).
  Large files (100–250 KB) are dominated by bandwidth.
  A realistic curve has a kink between these two regimes.

PAPER (dashed lines, T-Mobile):
  • Live: non-linear — flat start (RTT-limited), then climbing (BW-limited).
  • CellReplay: closely tracks Live — very small error (0.5–3.5%).
  • Mahimahi: shifted DOWN — consistently underestimates download time
    because it overestimates available bandwidth (errors 8.4–20.7%).

YOUR DATA (solid lines):
  • Ethernet baseline: very low and nearly flat — Ethernet is fast enough
    that bandwidth is almost never the bottleneck here.
  • netem variants: higher (injected delay adds to every transfer),
    growing more steeply with size (bandwidth cap is being hit).
  • The gap between netem and paper Live shows how much accuracy
    you would gain by using CellReplay-style emulation.\
"""


def plot_download(results, out_path):
    fig, ax = plt.subplots(figsize=(6, 4.5))

    # Paper lines (dashed, with CI shading)
    for name in ["Live", "CellReplay", "Mahimahi"]:
        vals = PAPER_DL[name]
        ci = PAPER_DL_CI[name]
        ax.plot(
            PAPER_DL_SIZES,
            vals,
            color=PAPER_COLOR[name],
            linestyle="--",
            marker="^",
            markersize=5,
            linewidth=1.8,
            label=f"Paper: {name} (T-Mobile)",
        )
        ax.fill_between(PAPER_DL_SIZES, vals - ci, vals + ci, color=PAPER_COLOR[name], alpha=0.10)

    # Your lines (solid, with CI shading)
    for key, d in results.items():
        dl = d.get("download_ms", {})
        means, lo, hi = [], [], []
        for kb in FILE_SIZES_KB:
            v = dl.get(str(kb), [])
            if v:
                m = np.mean(v)
                ci = 1.96 * np.std(v) / np.sqrt(len(v))
                means.append(m)
                lo.append(m - ci)
                hi.append(m + ci)
            else:
                means.append(np.nan)
                lo.append(np.nan)
                hi.append(np.nan)
        ax.plot(
            FILE_SIZES_KB,
            means,
            color=YOUR_COLOR[key],
            linestyle="-",
            marker=YOUR_MARKER[key],
            markersize=5,
            linewidth=1.8,
            label=YOUR_LABEL[key],
        )
        ax.fill_between(FILE_SIZES_KB, lo, hi, color=YOUR_COLOR[key], alpha=0.10)

    ax.set_xlabel("File size (KB)")
    ax.set_ylabel("Mean download time (ms)")
    ax.set_title("Fig 3 — File Download Time vs File Size\n(paper Fig 12, T-Mobile)")
    ax.legend(fontsize=7.5, loc="upper left")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight", dpi=720)
    plt.close()
    print(f"  Saved: {out_path}")
    print(DESCRIPTION_DL)
    print()


# ══════════════════════════════════════════════════════════════════════════════
# Figure 4 — Relative Packet Arrival Times Within a Train
# ══════════════════════════════════════════════════════════════════════════════
DESCRIPTION_REL = """\
WHAT THIS SHOWS:
  For a burst of N packets sent back-to-back, this shows how long each
  packet took to arrive relative to the first one in the burst.
  Flat line = all packets arrive together (pure bandwidth, no queueing).
  Stepped curve = packets arrive in clusters (cellular bursty delivery —
  the key pattern that CellReplay captures and Mahimahi misses).

YOUR DATA ONLY (paper doesn't show this for netem):
  Each sub-plot is a different train size (N=10, N=75).
  Each line is one of your netem configurations.
  • A nearly-flat line means your netem delivers all packets at the same
    rate (fixed bandwidth) — no burst clustering.
  • Real cellular would show steps and clusters here.\
"""


def plot_rel_arrivals(results, out_path):
    SHOW_SIZES = [10, 75]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

    for ax, sz in zip(axes, SHOW_SIZES):
        for key, d in results.items():
            train = d.get("train", {})
            entry = train.get(str(sz), {})
            rel = entry.get("rel_arrivals", []) if isinstance(entry, dict) else []
            if not rel:
                continue
            arr = np.array(rel)
            if arr.ndim != 2 or arr.shape[1] < sz:
                continue
            means = arr.mean(axis=0)
            ax.plot(
                range(sz), means, color=YOUR_COLOR[key], linestyle="-", linewidth=1.6, label=YOUR_LABEL[key]
            )

        ax.set_xlabel("Packet sequence number in train")
        ax.set_ylabel("Mean relative arrival time (ms)")
        ax.set_title(f"Train size N={sz}")
        ax.legend(fontsize=7.5)
        ax.grid(True, alpha=0.3)

        # Annotate what to expect from real cellular
        ax.text(
            0.97,
            0.05,
            "Real cellular would show\nsteps/clusters here",
            transform=ax.transAxes,
            fontsize=7.5,
            ha="right",
            va="bottom",
            color="gray",
            bbox=dict(boxstyle="round,pad=0.3", fc="lightyellow", alpha=0.8),
        )

    fig.suptitle(
        "Fig 4 — Relative Packet Arrival Times Within a Train\n"
        "(paper Fig 5 style — shows bursty delivery pattern)",
        y=1.02,
    )
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight", dpi=720)
    plt.close()
    print(f"  Saved: {out_path}")
    print(DESCRIPTION_REL)
    print()


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(description="Plot netem results + paper data")
    parser.add_argument(
        "--data-dir", default="/mnt/project", help="Directory containing results_*.json files"
    )
    parser.add_argument("--out-dir", default="figures_all")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    print("Loading results...")
    results = load_results(args.data_dir)
    print(f"  Loaded: {list(results.keys())}\n")

    plot_rtt_cdf(results, os.path.join(args.out_dir, "fig1_rtt_cdf.png"))
    plot_tct(results, os.path.join(args.out_dir, "fig2_tct_vs_size.png"))
    plot_download(results, os.path.join(args.out_dir, "fig3_download_time.png"))
    plot_rel_arrivals(results, os.path.join(args.out_dir, "fig4_rel_arrivals.png"))

    print("=" * 60)
    print("All figures saved to:", args.out_dir)
    print(
        """
OVERALL SUMMARY:
  Paper Live    = real T-Mobile 5G cellular (ground truth)
  Paper CellReplay = paper's emulator — closely tracks Live
  Paper Mahimahi   = naive emulator (fixed BW) — the paper's baseline

  Your Ethernet baseline = no emulation (fast wired link)
  Your netem variants    = tc netem emulation of cellular

  KEY TAKEAWAY:
    Your netem variants are doing the same thing as Mahimahi —
    applying a fixed delay + fixed bandwidth. They correctly add
    latency but they can't reproduce the bursty, non-linear
    delivery pattern that CellReplay captures via light/heavy PDOs.
    That's exactly the gap the paper addresses.
"""
    )


if __name__ == "__main__":
    main()
