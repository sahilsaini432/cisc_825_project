#!/usr/bin/env python3
"""
Generate a netem-compatible delay distribution table (.dist file)
from CellReplay light PDO traces (column 2 = one-way propagation delay).

netem distribution format:
  - 1024 signed 16-bit integers stored as a text table
  - tc loads it via: tc qdisc ... netem delay <mean>ms <jitter>ms
                                               distribution <file>
  - actual_delay = mean + jitter * table[rand_idx] / 32768
  - So the table encodes: (observed_delay - mean) / jitter * 32768
    quantized across 1024 uniformly-spaced CDF points

Usage:
  python3 generate_netem_dist.py \\
      --up-light   up-delay-light-pdo.txt \\
      --down-light down-delay-light-pdo.txt \\
      --out-dir    .

Output:
  ./up_delay.dist    (for uplink netem rule)
  ./down_delay.dist  (for downlink netem rule)
  Prints mean and jitter values to use in tc commands
"""

import argparse
import os
import statistics
import struct


# ── Parse light PDO file ───────────────────────────────────────────────────────


def extract_delays(path):
    """
    Read a delay-light PDO file and return all one-way delay values (ms).
    Each row: base_ts  prop_delay  offset1  offset2 ...
    Column 2 (prop_delay) is the one-way propagation delay per train.
    """
    delays = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            vals = line.split()
            if len(vals) < 3:
                continue
            try:
                delays.append(int(vals[1]))
            except ValueError:
                continue
    if not delays:
        raise ValueError(f"No delay values found in {path}")
    return delays


# ── Build netem distribution table ────────────────────────────────────────────


def build_dist_table(delays, n_points=1024):
    """
    Convert a list of delay values into a netem 1024-point distribution table.

    Steps:
      1. Sort delays to get the empirical CDF
      2. Sample 1024 quantile points uniformly from the CDF
      3. Compute mean and jitter (= max deviation from mean)
      4. Encode each quantile as: int16( (value - mean) / jitter * 32767 )

    Returns (table, mean_ms, jitter_ms) where table is list of 1024 ints.
    """
    sorted_delays = sorted(delays)
    n = len(sorted_delays)

    # Sample 1024 evenly-spaced quantile points
    quantiles = []
    for i in range(n_points):
        # Map i -> index in sorted array (0-indexed)
        idx = int(i / (n_points - 1) * (n - 1))
        quantiles.append(sorted_delays[idx])

    mean_ms = statistics.mean(delays)
    # jitter = max absolute deviation from mean (ensures all values fit in table)
    jitter_ms = max(abs(q - mean_ms) for q in quantiles)
    if jitter_ms < 1:
        jitter_ms = 1  # floor at 1ms to avoid division by zero

    # Encode: scale each quantile point to [-32767, 32767]
    table = []
    for q in quantiles:
        scaled = (q - mean_ms) / jitter_ms * 32767
        clamped = max(-32767, min(32767, int(round(scaled))))
        table.append(clamped)

    return table, mean_ms, jitter_ms


def write_dist_file(table, path):
    """
    Write netem distribution table in the text format that tc expects.
    Format: lines of 8 space-separated int16 values.
    Total: 1024 values = 128 lines.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        for i in range(0, len(table), 8):
            line = "  ".join(f"{v:6d}" for v in table[i : i + 8])
            f.write(line + "\n")
    print(f"  Written: {path}  ({len(table)} entries)")


# ── Stats display ──────────────────────────────────────────────────────────────


def print_stats(label, delays, mean_ms, jitter_ms):
    s = sorted(delays)
    n = len(s)
    print(f"\n  [{label}]")
    print(f"    Samples : {n}")
    print(f"    Min     : {s[0]} ms")
    print(f"    Median  : {s[n//2]} ms")
    print(f"    Mean    : {mean_ms:.1f} ms")
    print(f"    P95     : {s[int(n*0.95)]} ms")
    print(f"    Max     : {s[-1]} ms")
    print(f"    Jitter  : {jitter_ms:.1f} ms  (used as netem jitter param)")


# ── Main ───────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Generate netem .dist files from CellReplay light PDO traces"
    )
    parser.add_argument("--up-light", required=True, help="up-delay-light-pdo.txt")
    parser.add_argument("--down-light", required=True, help="down-delay-light-pdo.txt")
    parser.add_argument("--out-dir", default=".", help="Output directory for .dist files (default: .)")
    args = parser.parse_args()

    print("Reading light PDO delay values...")
    up_delays = extract_delays(args.up_light)
    down_delays = extract_delays(args.down_light)

    print("Building distribution tables...")
    up_table, up_mean, up_jitter = build_dist_table(up_delays)
    down_table, down_mean, down_jitter = build_dist_table(down_delays)

    print_stats("uplink", up_delays, up_mean, up_jitter)
    print_stats("downlink", down_delays, down_mean, down_jitter)

    up_out = os.path.join(args.out_dir, "up_delay.dist")
    down_out = os.path.join(args.out_dir, "down_delay.dist")

    print("\nWriting distribution files...")
    write_dist_file(up_table, up_out)
    write_dist_file(down_table, down_out)

    print("\n" + "=" * 60)
    print("Use these values in replay_trace.py --dist mode:")
    print(f"  Uplink   mean={up_mean:.0f}ms  jitter={up_jitter:.0f}ms  dist={up_out}")
    print(f"  Downlink mean={down_mean:.0f}ms  jitter={down_jitter:.0f}ms  dist={down_out}")
    print("=" * 60)
    print("\nOr manually with tc:")
    print(f"  tc qdisc add dev <iface> root netem \\")
    print(f"      delay {up_mean:.0f}ms {up_jitter:.0f}ms \\")
    print(f"      distribution {up_out}")
    print(f"\n  tc qdisc add dev ifb0 root netem \\")
    print(f"      delay {down_mean:.0f}ms {down_jitter:.0f}ms \\")
    print(f"      distribution {down_out}")


if __name__ == "__main__":
    main()
