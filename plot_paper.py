#!/usr/bin/env python3
"""
Generate paper-style figures directly from CellReplay trace files.
No live network tests required — all data is extracted from the traces.

Replicates:
  Figure 10 top    — RTT CDF
  Figure 10 bottom — Mean TCT vs train size
  Figure 5         — Relative packet arrival times within a train
  Figure 12        — Mean file download time vs file size

Also simulates what tc netem produces with the same traces,
so you can compare CellReplay vs netem on the same graph.

Usage:
  python3 plot_from_traces.py \\
    --up-light   up-delay-light-pdo.txt \\
    --down-light down-delay-light-pdo.txt \\
    --up-heavy   up-heavy-pdo.txt \\
    --down-heavy down-heavy-pdo.txt \\
    --out-dir    figures/

Output:
  figures/fig10_rtt_cdf.png
  figures/fig10_tct_vs_size.png
  figures/fig5_rel_arrivals.png
  figures/fig12_download_time.png
"""

import argparse
import os
import random
import statistics
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

# Paper train sizes (§3.2)
TRAIN_SIZES = [1, 10, 25, 50, 75, 100, 150, 200]
# Paper file sizes (§5.6)
FILE_SIZES_KB = [1, 10, 50, 100, 250]
# Bytes per PDO (mahimahi/CellReplay convention)
PDO_BYTES = 1500
# Number of simulated downloads per file size
N_SIM_DL = 200

# Paper-style plot settings
plt.rcParams.update(
    {
        "font.size": 11,
        "axes.labelsize": 12,
        "axes.titlesize": 12,
        "legend.fontsize": 9,
        "lines.linewidth": 2,
        "figure.dpi": 150,
    }
)

COLORS = {
    "cellreplay": "#1f77b4",  # blue  — matches paper "CellReplay" line
    "netem": "#d62728",  # red   — tc netem
    "mahimahi": "#9467bd",  # purple
    "live": "#2ca02c",  # green
}


# ── Trace loading ──────────────────────────────────────────────────────────────


def load_delay_light(path):
    """
    Returns list of dicts:
      { 'base': int, 'delay_ms': int, 'offsets': [int, ...] }
    base     = train send timestamp (ms)
    delay_ms = one-way propagation delay (ms)  [RTT = 2 * delay_ms]
    offsets  = relative packet arrival times within the train (ms)
    """
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            vals = list(map(int, line.split()))
            if len(vals) < 3:
                continue
            rows.append(
                {
                    "base": vals[0],
                    "delay_ms": vals[1],
                    "offsets": vals[2:],
                }
            )
    return rows


def load_heavy(path):
    """Returns sorted list of absolute timestamps (ms)."""
    timestamps = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                timestamps.append(int(line))
    return sorted(timestamps)


# ── Data extraction ────────────────────────────────────────────────────────────


def extract_rtts(down_light_rows):
    """RTT = 2 * one-way prop delay (col2) for each train."""
    return [r["delay_ms"] * 2 for r in down_light_rows if r["delay_ms"] > 0]


def extract_tct(down_light_rows, down_heavy_ts, train_size):
    """
    For each recorded train, estimate how long it takes to deliver
    train_size packets.

    - If train_size <= len(offsets): use offsets[N-1] directly.
    - If train_size >  len(offsets): extrapolate remaining packets
      at the heavy PDO rate.
    """
    # Average gap between heavy PDOs (ms per packet)
    if len(down_heavy_ts) > 1:
        heavy_gap_ms = (down_heavy_ts[-1] - down_heavy_ts[0]) / (len(down_heavy_ts) - 1)
    else:
        heavy_gap_ms = 10.0

    tcts = []
    for r in down_light_rows:
        offs = r["offsets"]
        if not offs:
            continue
        if train_size <= len(offs):
            tcts.append(offs[train_size - 1])
        else:
            extra_pkts = train_size - len(offs)
            tcts.append(offs[-1] + extra_pkts * heavy_gap_ms)
    return tcts


def extract_rel_arrivals(down_light_rows, train_size):
    """
    Mean relative arrival time for each packet position [0..train_size-1],
    averaged across all recorded trains.
    """
    per_position = [[] for _ in range(train_size)]
    for r in down_light_rows:
        offs = r["offsets"]
        for i in range(min(train_size, len(offs))):
            per_position[i].append(offs[i])
    means = [statistics.mean(v) if v else 0.0 for v in per_position]
    return means


def simulate_download_cellreplay(down_heavy_ts, file_size_kb, n_sim=N_SIM_DL):
    """
    Simulate downloading file_size_kb KB using the recorded heavy PDO schedule.
    Picks n_sim random starting points to capture variability.
    Each PDO delivers PDO_BYTES bytes.
    Returns list of download times in ms.
    """
    pkts_needed = -(-file_size_kb * 1024 // PDO_BYTES)  # ceil
    times = []
    max_start = len(down_heavy_ts) - pkts_needed
    if max_start <= 0:
        # Tile the trace if not enough PDOs
        tiled = down_heavy_ts[:]
        while len(tiled) < pkts_needed + n_sim:
            gap = tiled[-1] - tiled[0] + 10
            tiled += [t + gap for t in down_heavy_ts]
        down_heavy_ts = tiled
        max_start = len(down_heavy_ts) - pkts_needed

    for _ in range(n_sim):
        i = random.randint(0, max_start)
        t = down_heavy_ts[i + pkts_needed - 1] - down_heavy_ts[i]
        times.append(t)
    return times


def simulate_download_netem(file_size_kb, avg_rate_kbps, prop_delay_ms, n_sim=N_SIM_DL):
    """
    tc netem model: fixed rate + fixed delay.
    No variability (netem uses a fixed average — that's the whole point
    the paper makes about Mahimahi-style approaches).
    Small jitter added to model real netem behavior.
    """
    size_bits = file_size_kb * 1024 * 8
    tx_ms = size_bits / avg_rate_kbps
    total_ms = tx_ms + prop_delay_ms
    # Minimal jitter (netem is deterministic at fixed settings)
    jitter = np.random.normal(0, total_ms * 0.02, n_sim)
    return [max(1, total_ms + j) for j in jitter]


def netem_fixed_rtt(avg_rtt_ms, n_samples, jitter_pct=0.05):
    """
    tc netem RTT: fixed delay, so CDF is a near-vertical line.
    Paper shows Mahimahi does this and it's clearly wrong.
    """
    jitter = np.random.normal(0, avg_rtt_ms * jitter_pct, n_samples)
    return [max(1, avg_rtt_ms + j) for j in jitter]


def netem_tct(train_size, avg_rate_kbps, prop_delay_ms):
    """
    tc netem TCT: purely linear with train size (fixed bandwidth).
    Paper Figure 4 shows the dashed 'BW line' — this is exactly that.
    """
    size_bits = train_size * PDO_BYTES * 8
    return size_bits / avg_rate_kbps  # ms (no delay since TCT is relative)


# ── Plotting ───────────────────────────────────────────────────────────────────


def plot_rtt_cdf(cellreplay_rtts, netem_rtts, out_path):
    """Figure 10 top: CDF of packet RTTs."""
    fig, ax = plt.subplots(figsize=(5, 4))

    for rtts, label, color, ls in [
        (cellreplay_rtts, "CellReplay (from traces)", COLORS["cellreplay"], "-"),
        (netem_rtts, "tc netem (fixed delay)", COLORS["netem"], "--"),
    ]:
        s = np.sort(rtts)
        cdf = np.arange(1, len(s) + 1) / len(s)
        ax.plot(s, cdf, color=color, linestyle=ls, linewidth=2, label=label)

    ax.set_xlabel("Packet RTT (ms)")
    ax.set_ylabel("CDF")
    ax.set_title("Packet RTT CDF\n(Figure 10 top)")
    ax.set_ylim(0, 1)
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()
    print(f"  Saved: {out_path}")


def plot_tct(cellreplay_tcts, netem_tcts_linear, out_path):
    """Figure 10 bottom: Mean TCT vs train size."""
    fig, ax = plt.subplots(figsize=(5, 4))

    sizes = TRAIN_SIZES
    cr_means = [statistics.mean(cellreplay_tcts[n]) for n in sizes]
    nt_means = [netem_tcts_linear[n] for n in sizes]

    ax.plot(
        sizes,
        cr_means,
        color=COLORS["cellreplay"],
        marker="o",
        linewidth=2,
        markersize=6,
        label="CellReplay (from traces)",
    )
    ax.plot(
        sizes,
        nt_means,
        color=COLORS["netem"],
        marker="s",
        linewidth=2,
        markersize=6,
        linestyle="--",
        label="tc netem (fixed BW line)",
    )

    ax.set_xlabel("Train size (N packets)")
    ax.set_ylabel("Train completion time (ms)")
    ax.set_title("Mean TCT vs Train Size\n(Figure 10 bottom)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()
    print(f"  Saved: {out_path}")


def plot_rel_arrivals(down_light_rows, out_path):
    """Figure 5: Mean relative arrival time per packet sequence number."""
    fig, ax = plt.subplots(figsize=(5, 4))

    plot_sizes = [10, 50, 100, 200]
    colors_sz = plt.cm.viridis(np.linspace(0.1, 0.9, len(plot_sizes)))

    for n, color in zip(plot_sizes, colors_sz):
        means = extract_rel_arrivals(down_light_rows, n)
        ax.plot(range(len(means)), means, color=color, linewidth=1.8, label=f"N={n}")

    ax.set_xlabel("Packet sequence number")
    ax.set_ylabel("Relative arrival time (ms)")
    ax.set_title("Relative Arrival Time per Packet\n(Figure 5 style)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()
    print(f"  Saved: {out_path}")


def plot_download(cr_dl_times, nt_dl_times, out_path):
    """Figure 12: Mean file download time vs file size with 95% CI."""
    fig, ax = plt.subplots(figsize=(5, 4))

    sizes = FILE_SIZES_KB

    for times_dict, label, color, ls in [
        (cr_dl_times, "CellReplay (from traces)", COLORS["cellreplay"], "-"),
        (nt_dl_times, "tc netem (fixed rate)", COLORS["netem"], "--"),
    ]:
        means, ci_lo, ci_hi = [], [], []
        for kb in sizes:
            t = times_dict[kb]
            m = np.mean(t)
            ci = 1.96 * np.std(t) / np.sqrt(len(t))
            means.append(m)
            ci_lo.append(m - ci)
            ci_hi.append(m + ci)

        ax.plot(sizes, means, color=color, linestyle=ls, marker="o", linewidth=2, markersize=6, label=label)
        ax.fill_between(sizes, ci_lo, ci_hi, color=color, alpha=0.15)

    ax.set_xlabel("File size (KB)")
    ax.set_ylabel("Download time (ms)")
    ax.set_title("Mean File Download Time\n(Figure 12)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()
    print(f"  Saved: {out_path}")


# ── Main ───────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Generate paper figures directly from CellReplay trace files"
    )
    parser.add_argument("--up-light", required=True)
    parser.add_argument("--down-light", required=True)
    parser.add_argument("--up-heavy", required=True)
    parser.add_argument("--down-heavy", required=True)
    parser.add_argument("--out-dir", default="figures")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    os.makedirs(args.out_dir, exist_ok=True)

    # Load traces
    print("Loading traces...")
    down_light = load_delay_light(args.down_light)
    up_light = load_delay_light(args.up_light)
    down_heavy = load_heavy(args.down_heavy)
    up_heavy = load_heavy(args.up_heavy)
    print(f"  down-light: {len(down_light)} trains")
    print(f"  up-light:   {len(up_light)} trains")
    print(f"  down-heavy: {len(down_heavy)} PDOs")
    print(f"  up-heavy:   {len(up_heavy)} PDOs")

    # Compute shared stats
    avg_rtt_ms = statistics.mean(r["delay_ms"] * 2 for r in down_light if r["delay_ms"] > 0)
    prop_delay_ms = avg_rtt_ms / 2
    heavy_gap_ms = (down_heavy[-1] - down_heavy[0]) / (len(down_heavy) - 1)
    avg_heavy_kbps = PDO_BYTES * 8 / heavy_gap_ms

    print(f"\nDerived parameters:")
    print(f"  Avg RTT:           {avg_rtt_ms:.1f} ms")
    print(f"  Prop delay:        {prop_delay_ms:.1f} ms")
    print(f"  Heavy avg rate:    {avg_heavy_kbps:.0f} kbps")

    # ── Extract CellReplay data ──
    print("\nExtracting CellReplay data from traces...")

    cr_rtts = extract_rtts(down_light)
    print(f"  RTT samples:    {len(cr_rtts)}  " f"(median={statistics.median(cr_rtts):.1f}ms)")

    cr_tcts = {}
    for n in TRAIN_SIZES:
        cr_tcts[n] = extract_tct(down_light, down_heavy, n)
    print(f"  TCT extracted for train sizes: {TRAIN_SIZES}")

    cr_dl = {}
    for kb in FILE_SIZES_KB:
        cr_dl[kb] = simulate_download_cellreplay(down_heavy, kb)
    print(f"  Download simulations: {N_SIM_DL} per file size")

    # ── Simulate tc netem ──
    print("\nSimulating tc netem (fixed delay + fixed rate)...")

    nt_rtts = netem_fixed_rtt(avg_rtt_ms, len(cr_rtts))
    print(f"  Fixed RTT: {avg_rtt_ms:.1f} ms")

    nt_tcts = {n: netem_tct(n, avg_heavy_kbps, prop_delay_ms) for n in TRAIN_SIZES}
    print(f"  Fixed BW line: {avg_heavy_kbps:.0f} kbps")

    nt_dl = {}
    for kb in FILE_SIZES_KB:
        nt_dl[kb] = simulate_download_netem(kb, avg_heavy_kbps, prop_delay_ms)

    # ── Plot ──
    print(f"\nGenerating figures → {args.out_dir}/")

    plot_rtt_cdf(cr_rtts, nt_rtts, os.path.join(args.out_dir, "fig10_rtt_cdf.png"))

    plot_tct(cr_tcts, nt_tcts, os.path.join(args.out_dir, "fig10_tct_vs_size.png"))

    plot_rel_arrivals(down_light, os.path.join(args.out_dir, "fig5_rel_arrivals.png"))

    plot_download(cr_dl, nt_dl, os.path.join(args.out_dir, "fig12_download_time.png"))

    print("\nDone.")
    print("\nKey insight visible in figures:")
    print("  RTT CDF:  CellReplay shows variability; netem is a near-vertical line")
    print("  TCT:      CellReplay is non-linear (light→heavy transition);")
    print("            netem is a straight 'BW line' — the bias the paper exposes")
    print("  Download: netem underestimates small files, overestimates large ones")


if __name__ == "__main__":
    main()
