#!/usr/bin/env python3
"""
Replay PDO cellular trace files using tc netem.
Dynamically updates bandwidth every 500ms to match real trace data.

Supports both formats:
  - Heavy format: one timestamp (ms) per line
  - Delay-light format: base_ts  prop_delay  offset1  offset2 ...

Usage:
  sudo python3 replay_trace.py --iface enp0s3 \
      --up up-heavy-pdo.txt \
      --down down-heavy-pdo.txt

  sudo python3 replay_trace.py --iface enp0s3 \
      --up up-delay-light-pdo.txt \
      --down down-delay-light-pdo.txt
"""

import argparse
import subprocess
import time
import sys
import signal

WINDOW_MS = 500  # bandwidth measurement window (ms)
BYTES_PER_PKT = 1500  # mahimahi convention: 1 delivery = 1500 bytes
MIN_RATE_KBPS = 10  # floor to avoid setting 0 which breaks tc


# ── Trace parsing ──────────────────────────────────────────────────────────────


def parse_heavy(path):
    """One timestamp (ms) per line."""
    timestamps = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                timestamps.append(int(line))
    return sorted(timestamps), 0  # no propagation delay in this format


def parse_delay_light(path):
    """base  prop_delay  offset1  offset2 ..."""
    timestamps = []
    delays = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            vals = list(map(int, line.split()))
            if len(vals) < 3:
                continue
            base, prop = vals[0], vals[1]
            delays.append(prop)
            for offset in vals[2:]:
                timestamps.append(base + offset)
    avg_delay = int(sum(delays) / len(delays)) if delays else 0
    return sorted(timestamps), avg_delay


def detect_format(path):
    with open(path) as f:
        first = f.readline().strip()
    return "heavy" if len(first.split()) == 1 else "delay_light"


def load_trace(path):
    fmt = detect_format(path)
    if fmt == "heavy":
        print(f"  [{path}] detected format: heavy (one timestamp per line)")
        return parse_heavy(path)
    else:
        print(f"  [{path}] detected format: delay-light (multi-column)")
        return parse_delay_light(path)


def compute_bw_schedule(timestamps, window_ms=WINDOW_MS):
    """Return list of (time_offset_ms, rate_kbps) tuples."""
    if not timestamps:
        return []
    t_start = timestamps[0]
    t_end = timestamps[-1]
    schedule = []
    t = t_start
    while t < t_end:
        count = sum(1 for ts in timestamps if t <= ts < t + window_ms)
        bw_kbps = max(MIN_RATE_KBPS, (count * BYTES_PER_PKT * 8) / window_ms)
        schedule.append((t - t_start, int(bw_kbps)))
        t += window_ms
    return schedule


# ── tc helpers ─────────────────────────────────────────────────────────────────


def run(cmd, check=True):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        # Ignore "already exists" errors during setup
        if "already exists" not in result.stderr and "RTNETLINK answers: File exists" not in result.stderr:
            print(f"  [warn] {cmd!r} → {result.stderr.strip()}")
    return result


def setup_egress(iface, delay_ms, rate_kbps):
    """Set up netem on egress (uplink from this machine)."""
    run(f"tc qdisc del dev {iface} root 2>/dev/null", check=False)
    run(f"tc qdisc add dev {iface} root handle 1: netem " f"delay {delay_ms}ms rate {rate_kbps}kbit")
    print(f"  Egress (uplink) netem ready on {iface}: delay={delay_ms}ms rate={rate_kbps}kbps")


def update_egress(iface, delay_ms, rate_kbps):
    run(f"tc qdisc change dev {iface} root handle 1: netem " f"delay {delay_ms}ms rate {rate_kbps}kbit")


def setup_ingress(iface, delay_ms, rate_kbps):
    """Set up rate limiting on ingress (downlink) using IFB device."""
    run("modprobe ifb", check=False)
    run("ip link add ifb0 type ifb 2>/dev/null", check=False)
    run("ip link set dev ifb0 up")

    # Redirect ingress of iface → ifb0
    run(f"tc qdisc del dev {iface} ingress 2>/dev/null", check=False)
    run(f"tc qdisc add dev {iface} handle ffff: ingress")
    run(
        f"tc filter add dev {iface} parent ffff: protocol ip u32 "
        f"match u32 0 0 action mirred egress redirect dev ifb0"
    )

    # Apply netem on ifb0
    run("tc qdisc del dev ifb0 root 2>/dev/null", check=False)
    run(f"tc qdisc add dev ifb0 root handle 1: netem " f"delay {delay_ms}ms rate {rate_kbps}kbit")
    print(f"  Ingress (downlink) netem ready on ifb0: delay={delay_ms}ms rate={rate_kbps}kbps")


def update_ingress(delay_ms, rate_kbps):
    run(f"tc qdisc change dev ifb0 root handle 1: netem " f"delay {delay_ms}ms rate {rate_kbps}kbit")


def teardown(iface):
    print("\nCleaning up tc rules...")
    run(f"tc qdisc del dev {iface} root 2>/dev/null", check=False)
    run(f"tc qdisc del dev {iface} ingress 2>/dev/null", check=False)
    run(f"tc qdisc del dev ifb0 root 2>/dev/null", check=False)
    run("ip link set dev ifb0 down 2>/dev/null", check=False)
    run("ip link del ifb0 2>/dev/null", check=False)
    print("Done.")


# ── Main ───────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Replay PDO trace files via tc netem")
    parser.add_argument("--iface", required=True, help="Network interface (e.g. enp0s3)")
    parser.add_argument("--up", required=True, help="Uplink trace file")
    parser.add_argument("--down", required=True, help="Downlink trace file")
    parser.add_argument(
        "--window", type=int, default=WINDOW_MS, help=f"Bandwidth window in ms (default: {WINDOW_MS})"
    )
    args = parser.parse_args()

    print("\nLoading traces...")
    up_ts, up_delay = load_trace(args.up)
    down_ts, down_delay = load_trace(args.down)

    delay_ms = max(up_delay, down_delay)
    print(f"  Propagation delay: {delay_ms} ms")

    up_sched = compute_bw_schedule(up_ts, args.window)
    down_sched = compute_bw_schedule(down_ts, args.window)

    print(f"\n  Uplink:   {len(up_sched)} windows, " f"avg {sum(r for _,r in up_sched)//len(up_sched)} kbps")
    print(
        f"  Downlink: {len(down_sched)} windows, " f"avg {sum(r for _,r in down_sched)//len(down_sched)} kbps"
    )

    # Setup
    print(f"\nSetting up tc netem on {args.iface}...")
    setup_egress(args.iface, delay_ms, up_sched[0][1])
    setup_ingress(args.iface, delay_ms, down_sched[0][1])

    # Cleanup on Ctrl+C
    def on_exit(sig, frame):
        teardown(args.iface)
        sys.exit(0)

    signal.signal(signal.SIGINT, on_exit)
    signal.signal(signal.SIGTERM, on_exit)

    # Replay loop
    print(f"\nReplaying trace ({args.window}ms windows)... Press Ctrl+C to stop.\n")
    up_i = 0
    down_i = 0
    start = time.time()

    while up_i < len(up_sched) or down_i < len(down_sched):
        elapsed_ms = (time.time() - start) * 1000

        if up_i < len(up_sched) and elapsed_ms >= up_sched[up_i][0]:
            rate = up_sched[up_i][1]
            update_egress(args.iface, delay_ms, rate)
            print(f"  t={elapsed_ms/1000:.2f}s  UP={rate:6d} kbps", end="")
            up_i += 1
        else:
            print(f"  t={elapsed_ms/1000:.2f}s  UP=  (same)", end="")

        if down_i < len(down_sched) and elapsed_ms >= down_sched[down_i][0]:
            rate = down_sched[down_i][1]
            update_ingress(delay_ms, rate)
            print(f"  DOWN={rate:6d} kbps")
            down_i += 1
        else:
            print(f"  DOWN=  (same)")

        time.sleep(args.window / 1000)

    teardown(args.iface)


if __name__ == "__main__":
    if __import__("os").geteuid() != 0:
        print("Error: must run as root (sudo)")
        sys.exit(1)
    main()
