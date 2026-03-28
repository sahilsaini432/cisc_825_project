#!/usr/bin/env python3
"""
CellReplay benchmark client.
Runs RTT, packet train, and file download tests matching paper methodology.
Saves results to JSON for plotting.

Usage:
  # Baseline (no emulation):
  python3 run_tests.py --server 192.168.1.100 --label baseline

  # Under tc netem emulation:
  python3 run_tests.py --server 192.168.1.100 --label netem

  # Results saved to: results_<label>.json
"""

import socket
import struct
import time
import json
import argparse
import random
import os

UDP_ECHO_PORT = 5001
UDP_TRAIN_PORT = 5002
TCP_FILE_PORT = 5003
PKT_SIZE = 1400

# Match paper exactly
RTT_INTERVAL_MS = 50  # send RTT probe every 50ms
RTT_DURATION_S = 60  # 60 second test
TRAIN_SIZES = [1, 10, 25, 50, 75, 100, 150, 200]
TRAIN_GAP_MS = 100  # 100ms gap between trains
TRAINS_PER_SIZE = 30  # repeat each train size 30 times
FILE_SIZES_KB = [1, 10, 50, 100, 250]
DOWNLOADS_PER_SIZE = 20


# ── RTT Test ──────────────────────────────────────────────────────────────────


def run_rtt_test(server_ip, duration_s=RTT_DURATION_S):
    """Send 1400-byte UDP packets every 50ms, measure round-trip time."""
    print(f"\n[RTT test] {duration_s}s, packet every {RTT_INTERVAL_MS}ms...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.5)
    payload = b"R" * (PKT_SIZE - 8)

    rtts = []
    seq = 0
    deadline = time.time() + duration_s

    while time.time() < deadline:
        send_ts = time.time()
        pkt = struct.pack("!Id", seq, send_ts) + payload
        try:
            sock.sendto(pkt, (server_ip, UDP_ECHO_PORT))
            data, _ = sock.recvfrom(4096)
            recv_ts = time.time()
            rtt_ms = (recv_ts - send_ts) * 1000
            rtts.append(rtt_ms)
        except socket.timeout:
            pass  # packet lost

        seq += 1
        elapsed = time.time() - send_ts
        sleep_s = max(0, RTT_INTERVAL_MS / 1000 - elapsed)
        time.sleep(sleep_s)

    sock.close()
    print(f"  Collected {len(rtts)} RTT samples")
    print(f"  Median RTT: {sorted(rtts)[len(rtts)//2]:.1f} ms")
    return rtts


# ── Train Test ────────────────────────────────────────────────────────────────


def run_train_test(server_ip):
    """
    For each train size N, send a request to server → server sends N packets back.
    Measure: relative arrival times per packet, and train completion time (TCT).
    Matches paper §3.2 exactly.
    """
    print(f"\n[Train test] sizes={TRAIN_SIZES}, {TRAINS_PER_SIZE} repeats each...")

    results = {n: {"tct_ms": [], "rel_arrivals": []} for n in TRAIN_SIZES}

    # Randomize order like the paper
    order = []
    for n in TRAIN_SIZES:
        order.extend([n] * TRAINS_PER_SIZE)
    random.shuffle(order)

    recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    recv_sock.bind(("0.0.0.0", 0))
    recv_sock.settimeout(0.5)
    my_port = recv_sock.getsockname()[1]

    req_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    train_id = 0
    for n in order:
        # Send train request
        req = struct.pack("!II", train_id, n)
        req_sock.sendto(req, (server_ip, UDP_TRAIN_PORT))
        send_ts = time.time()

        # Receive packets
        arrivals = {}
        deadline = time.time() + 2.0  # 2s timeout for whole train
        while len(arrivals) < n and time.time() < deadline:
            try:
                data, _ = recv_sock.recvfrom(4096)
                recv_ts = time.time()
                if len(data) < 16:
                    continue
                tid, seq, _ = struct.unpack("!IIQ", data[:16])
                if tid == train_id:
                    arrivals[seq] = recv_ts
            except socket.timeout:
                break

        if len(arrivals) == n:
            t0 = arrivals[0]
            rel = [(arrivals[i] - t0) * 1000 for i in range(n)]
            results[n]["rel_arrivals"].append(rel)

            # TCT: time from send to receiving last packet
            tct_ms = (arrivals[n - 1] - send_ts) * 1000
            results[n]["tct_ms"].append(tct_ms)

        train_id += 1
        time.sleep(TRAIN_GAP_MS / 1000)

    recv_sock.close()
    req_sock.close()

    for n in TRAIN_SIZES:
        tcts = results[n]["tct_ms"]
        if tcts:
            print(f"  N={n:3d}: mean TCT={sum(tcts)/len(tcts):.1f}ms  ({len(tcts)} trains)")

    return results


# ── File Download Test ────────────────────────────────────────────────────────


def run_download_test(server_ip):
    """
    Download files of varying sizes over TCP.
    Matches paper §5.6: randomized order, measure turnaround time.
    """
    print(f"\n[Download test] sizes={FILE_SIZES_KB}KB, {DOWNLOADS_PER_SIZE} each...")
    results = {kb: [] for kb in FILE_SIZES_KB}

    order = []
    for kb in FILE_SIZES_KB:
        order.extend([kb] * DOWNLOADS_PER_SIZE)
    random.shuffle(order)

    for kb in order:
        size_bytes = kb * 1024
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((server_ip, TCP_FILE_PORT))

            t0 = time.time()
            sock.sendall(struct.pack("!I", size_bytes))

            received = 0
            while received < size_bytes:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                received += len(chunk)
            t1 = time.time()

            sock.close()
            dl_ms = (t1 - t0) * 1000
            results[kb].append(dl_ms)
            time.sleep(0.05)  # 50ms between downloads like paper
        except Exception as e:
            print(f"  [warn] {kb}KB download failed: {e}")

    for kb in FILE_SIZES_KB:
        times = results[kb]
        if times:
            print(f"  {kb:4d}KB: mean={sum(times)/len(times):.1f}ms  ({len(times)} downloads)")

    return results


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", required=True, help="Server IP address")
    parser.add_argument("--label", required=True, help="Label for this run (e.g. baseline, netem)")
    parser.add_argument("--skip-rtt", action="store_true")
    parser.add_argument("--skip-train", action="store_true")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--rtt-duration", type=int, default=RTT_DURATION_S)
    args = parser.parse_args()

    results = {"label": args.label, "server": args.server, "timestamp": time.time()}

    if not args.skip_rtt:
        results["rtt_ms"] = run_rtt_test(args.server, args.rtt_duration)

    if not args.skip_train:
        train_results = run_train_test(args.server)
        # Convert to serializable format
        results["train"] = {
            str(n): {"tct_ms": v["tct_ms"], "rel_arrivals": v["rel_arrivals"]}
            for n, v in train_results.items()
        }

    if not args.skip_download:
        results["download_ms"] = {str(kb): times for kb, times in run_download_test(args.server).items()}

    out_file = f"results_{args.label}.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {out_file}")


if __name__ == "__main__":
    main()
