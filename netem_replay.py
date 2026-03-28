#!/usr/bin/env python3
"""
Replay CellReplay PDO trace files using tc netem.
Dynamically updates bandwidth every 500ms to match real trace data.

Usage:
  # Run in foreground (Ctrl+C to stop):
  sudo python3 netem_replay.py --iface enp0s3 \
      --up up-heavy-pdo.txt --down down-heavy-pdo.txt

  # Run in background for N seconds then auto-cleanup:
  sudo python3 netem_replay.py --iface enp0s3 \
      --up up-delay-light-pdo.txt --down down-delay-light-pdo.txt \
      --duration 60

Supports both CellReplay trace formats:
  Heavy:       one timestamp (ms) per line
  Delay-light: base_ts  prop_delay  offset1  offset2 ...
"""

import argparse
import subprocess
import time
import sys
import signal

WINDOW_MS = 500
BYTES_PER_PKT = 1500
MIN_RATE_KBPS = 10


# ── Trace parsing ──────────────────────────────────────────────────────────────


def detect_format(path):
    with open(path) as f:
        first = f.readline().strip()
    return "heavy" if len(first.split()) == 1 else "delay_light"


def parse_heavy(path):
    timestamps = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                timestamps.append(int(line))
    return sorted(timestamps), 0


def parse_delay_light(path):
    timestamps, delays = [], []
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


def load_trace(path):
    fmt = detect_format(path)
    label = path.split("/")[-1]
    if fmt == "heavy":
        print(f"  [{label}] format: heavy")
        return parse_heavy(path)
    else:
        print(f"  [{label}] format: delay-light")
        return parse_delay_light(path)


def compute_bw_schedule(timestamps, window_ms=WINDOW_MS):
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
        if "already exists" not in result.stderr and "File exists" not in result.stderr:
            print(f"  [warn] {cmd!r} → {result.stderr.strip()}")
    return result


def setup_egress(iface, delay_ms, rate_kbps):
    run(f"tc qdisc del dev {iface} root 2>/dev/null", check=False)
    run(f"tc qdisc add dev {iface} root handle 1: netem " f"delay {delay_ms}ms rate {rate_kbps}kbit")
    print(f"  Egress  (uplink):   delay={delay_ms}ms  rate={rate_kbps}kbps")


def update_egress(iface, delay_ms, rate_kbps):
    run(f"tc qdisc change dev {iface} root handle 1: netem " f"delay {delay_ms}ms rate {rate_kbps}kbit")


def setup_ingress(iface, delay_ms, rate_kbps):
    run("modprobe ifb", check=False)
    run("ip link add ifb0 type ifb 2>/dev/null", check=False)
    run("ip link set dev ifb0 up")
    run(f"tc qdisc del dev {iface} ingress 2>/dev/null", check=False)
    run(f"tc qdisc add dev {iface} handle ffff: ingress")
    run(
        f"tc filter add dev {iface} parent ffff: protocol ip u32 "
        f"match u32 0 0 action mirred egress redirect dev ifb0"
    )
    run("tc qdisc del dev ifb0 root 2>/dev/null", check=False)
    run(f"tc qdisc add dev ifb0 root handle 1: netem " f"delay {delay_ms}ms rate {rate_kbps}kbit")
    print(f"  Ingress (downlink): delay={delay_ms}ms  rate={rate_kbps}kbps")


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


# ── Replay loop ────────────────────────────────────────────────────────────────


def replay(iface, up_sched, down_sched, delay_ms, duration_s=None, quiet=False):
    up_i = down_i = 0
    start = time.time()

    def log(msg):
        if not quiet:
            print(msg)

    while up_i < len(up_sched) or down_i < len(down_sched):
        elapsed_ms = (time.time() - start) * 1000

        if duration_s and (time.time() - start) >= duration_s:
            break

        changed = False
        if up_i < len(up_sched) and elapsed_ms >= up_sched[up_i][0]:
            update_egress(iface, delay_ms, up_sched[up_i][1])
            up_rate = up_sched[up_i][1]
            up_i += 1
            changed = True
        else:
            up_rate = up_sched[up_i - 1][1] if up_i > 0 else 0

        if down_i < len(down_sched) and elapsed_ms >= down_sched[down_i][0]:
            update_ingress(delay_ms, down_sched[down_i][1])
            down_rate = down_sched[down_i][1]
            down_i += 1
            changed = True
        else:
            down_rate = down_sched[down_i - 1][1] if down_i > 0 else 0

        if changed:
            log(f"  t={elapsed_ms/1000:5.1f}s  UP={up_rate:6d} kbps  DOWN={down_rate:6d} kbps")

        time.sleep(WINDOW_MS / 1000)


# ── Main ───────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Replay CellReplay traces via tc netem")
    parser.add_argument("--iface", required=True, help="Network interface (e.g. enp0s3)")
    parser.add_argument("--up", required=True, help="Uplink trace file")
    parser.add_argument("--down", required=True, help="Downlink trace file")
    parser.add_argument("--duration", type=int, help="Stop after N seconds (optional)")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-window output")
    parser.add_argument(
        "--window", type=int, default=WINDOW_MS, help=f"Bandwidth window ms (default: {WINDOW_MS})"
    )
    args = parser.parse_args()

    print("\nLoading traces...")
    up_ts, up_delay = load_trace(args.up)
    down_ts, down_delay = load_trace(args.down)
    delay_ms = max(up_delay, down_delay)
    print(f"  Propagation delay: {delay_ms} ms")

    up_sched = compute_bw_schedule(up_ts, args.window)
    down_sched = compute_bw_schedule(down_ts, args.window)

    avg_up = sum(r for _, r in up_sched) // len(up_sched)
    avg_down = sum(r for _, r in down_sched) // len(down_sched)
    print(f"  Uplink:   {len(up_sched)} windows, avg {avg_up} kbps")
    print(f"  Downlink: {len(down_sched)} windows, avg {avg_down} kbps")

    print(f"\nSetting up tc netem on {args.iface}...")
    setup_egress(args.iface, delay_ms, up_sched[0][1])
    setup_ingress(args.iface, delay_ms, down_sched[0][1])

    def on_exit(sig, frame):
        teardown(args.iface)
        sys.exit(0)

    signal.signal(signal.SIGINT, on_exit)
    signal.signal(signal.SIGTERM, on_exit)

    dur_str = f"{args.duration}s" if args.duration else "until trace ends"
    print(f"\nReplaying ({dur_str})... Ctrl+C to stop.\n")

    replay(args.iface, up_sched, down_sched, delay_ms, duration_s=args.duration, quiet=args.quiet)

    teardown(args.iface)


if __name__ == "__main__":
    if __import__("os").geteuid() != 0:
        print("Error: must run as root (sudo)")
        sys.exit(1)
    main()
