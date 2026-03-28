#!/usr/bin/env python3
"""
Generate paper-style figures from benchmark results.
Replicates Figure 10 and Figure 12 from the CellReplay paper (NSDI'25).

Usage:
  python3 plot_paper.py results_baseline.json results_netem.json

Output:
  fig10_rtt_cdf.png       - CDF of packet RTTs        (Figure 10 top)
  fig10_tct_vs_size.png   - Mean TCT vs train size     (Figure 10 bottom)
  fig12_download_time.png - Mean download time vs size (Figure 12)
"""

import json
import sys
import argparse
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Paper-style colors and markers matching Figure 10/12
STYLES = {
    "baseline": dict(color="#2ca02c", linestyle="-", marker="o", label="Baseline (no emulation)"),
    "netem": dict(color="#d62728", linestyle="--", marker="s", label="tc netem (CellReplay traces)"),
    "live": dict(color="#1f77b4", linestyle="-", marker="^", label="Live"),
    "cellreplay": dict(color="#ff7f0e", linestyle=":", marker="D", label="CellReplay"),
    "mahimahi": dict(color="#9467bd", linestyle="-.", marker="v", label="Mahimahi"),
}


def get_style(label):
    label_lower = label.lower()
    for key in STYLES:
        if key in label_lower:
            return STYLES[key]
    # Default style for unknown labels
    return dict(color="gray", linestyle="-", marker="x", label=label)


# ── Figure 10 top: RTT CDF ────────────────────────────────────────────────────


def plot_rtt_cdf(all_results, out_path="fig10_rtt_cdf.png"):
    fig, ax = plt.subplots(figsize=(5, 4))

    for res in all_results:
        rtts = res.get("rtt_ms", [])
        if not rtts:
            continue
        sorted_rtts = np.sort(rtts)
        cdf = np.arange(1, len(sorted_rtts) + 1) / len(sorted_rtts)
        style = get_style(res["label"])
        ax.plot(
            sorted_rtts,
            cdf,
            color=style["color"],
            linestyle=style["linestyle"],
            linewidth=2,
            label=style["label"],
        )

    ax.set_xlabel("Packet RTT (ms)", fontsize=12)
    ax.set_ylabel("CDF", fontsize=12)
    ax.set_title("Packet RTT CDF\n(replicating Figure 10 top)", fontsize=12)
    ax.legend(fontsize=9)
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])

    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"Saved: {out_path}")


# ── Figure 10 bottom: TCT vs train size ───────────────────────────────────────


def plot_tct(all_results, out_path="fig10_tct_vs_size.png"):
    fig, ax = plt.subplots(figsize=(5, 4))

    for res in all_results:
        train = res.get("train", {})
        if not train:
            continue

        sizes = sorted(int(k) for k in train.keys())
        mean_tcts = []
        for n in sizes:
            tcts = train[str(n)]["tct_ms"]
            mean_tcts.append(np.mean(tcts) if tcts else 0)

        style = get_style(res["label"])
        ax.plot(
            sizes,
            mean_tcts,
            color=style["color"],
            linestyle=style["linestyle"],
            marker=style["marker"],
            linewidth=2,
            markersize=6,
            label=style["label"],
        )

    ax.set_xlabel("Train size (N packets)", fontsize=12)
    ax.set_ylabel("Train completion time (ms)", fontsize=12)
    ax.set_title("Mean TCT vs Train Size\n(replicating Figure 10 bottom)", fontsize=12)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"Saved: {out_path}")


# ── Figure 12: File download time vs size ─────────────────────────────────────


def plot_download(all_results, out_path="fig12_download_time.png"):
    fig, ax = plt.subplots(figsize=(5, 4))

    for res in all_results:
        dl = res.get("download_ms", {})
        if not dl:
            continue

        sizes_kb = sorted(int(k) for k in dl.keys())
        means = []
        ci_low = []
        ci_high = []

        for kb in sizes_kb:
            times = dl[str(kb)]
            if not times:
                means.append(0)
                ci_low.append(0)
                ci_high.append(0)
                continue
            m = np.mean(times)
            se = np.std(times) / np.sqrt(len(times)) * 1.96  # 95% CI
            means.append(m)
            ci_low.append(m - se)
            ci_high.append(m + se)

        style = get_style(res["label"])
        ax.plot(
            sizes_kb,
            means,
            color=style["color"],
            linestyle=style["linestyle"],
            marker=style["marker"],
            linewidth=2,
            markersize=6,
            label=style["label"],
        )
        ax.fill_between(sizes_kb, ci_low, ci_high, color=style["color"], alpha=0.15)

    ax.set_xlabel("File size (KB)", fontsize=12)
    ax.set_ylabel("Download time (ms)", fontsize=12)
    ax.set_title("Mean File Download Time\n(replicating Figure 12)", fontsize=12)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"Saved: {out_path}")


# ── Bonus: per-packet relative arrival time (Figure 5 style) ──────────────────


def plot_rel_arrivals(all_results, out_path="fig5_rel_arrivals.png"):
    """Mean relative arrival time per packet position, like paper Figure 5."""
    fig, ax = plt.subplots(figsize=(5, 4))
    plot_sizes = [10, 50, 100, 200]

    for res in all_results:
        train = res.get("train", {})
        if not train:
            continue
        style = get_style(res["label"])

        for n in plot_sizes:
            arrivals_list = train.get(str(n), {}).get("rel_arrivals", [])
            if not arrivals_list:
                continue
            # Mean rel arrival time per packet index
            max_len = max(len(a) for a in arrivals_list)
            means = []
            for i in range(max_len):
                vals = [a[i] for a in arrivals_list if i < len(a)]
                means.append(np.mean(vals))
            ax.plot(
                range(max_len), means, color=style["color"], linewidth=1.5, label=f"{style['label']} N={n}"
            )

    ax.set_xlabel("Packet sequence number", fontsize=12)
    ax.set_ylabel("Relative arrival time (ms)", fontsize=12)
    ax.set_title("Relative Arrival Time per Packet\n(replicating Figure 5)", fontsize=12)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"Saved: {out_path}")


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "results", nargs="+", help="JSON result files (e.g. results_baseline.json results_netem.json)"
    )
    parser.add_argument("--out-dir", default=".", help="Output directory for figures")
    args = parser.parse_args()

    all_results = []
    for path in args.results:
        with open(path) as f:
            data = json.load(f)
        print(f"Loaded: {path}  (label={data['label']})")
        all_results.append(data)

    import os

    os.makedirs(args.out_dir, exist_ok=True)
    prefix = args.out_dir + "/"

    print("\nGenerating figures...")
    plot_rtt_cdf(all_results, prefix + "fig10_rtt_cdf.png")
    plot_tct(all_results, prefix + "fig10_tct_vs_size.png")
    plot_download(all_results, prefix + "fig12_download_time.png")
    plot_rel_arrivals(all_results, prefix + "fig5_rel_arrivals.png")

    print("\nDone. All figures saved.")


if __name__ == "__main__":
    main()
