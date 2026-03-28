#!/usr/bin/env python3
"""
CellReplay benchmark client.
Works with the updated server.py (no echo_server.py needed).

All test traffic goes to:
  UDP port 5000  — RTT probe (marker 'R') + variable train (marker 'T')
  TCP port 5001  — file download (cmd 'D') + file upload (cmd 'U')

Usage:
  # Baseline (no emulation):
  python3 run_tests.py --server 192.168.1.100 --label baseline

  # Under netem emulation (run netem_replay.py in another terminal first):
  python3 run_tests.py --server 192.168.1.100 --label netem

  # Skip individual tests:
  python3 run_tests.py --server 192.168.1.100 --label baseline --skip-rtt
  python3 run_tests.py --server 192.168.1.100 --label baseline --skip-train
  python3 run_tests.py --server 192.168.1.100 --label baseline --skip-download
  python3 run_tests.py --server 192.168.1.100 --label baseline --skip-upload
"""

import socket
import struct
import time
import json
import argparse
import random

UDP_PORT = 5000
TCP_PORT = 5001
PKT_SIZE = 1400

RTT_INTERVAL_MS = 50
RTT_DURATION_S = 60
TRAIN_SIZES = [1, 10, 25, 50, 75, 100, 150, 200]
TRAIN_GAP_MS = 100
TRAINS_PER_SIZE = 30
FILE_SIZES_KB = [1, 10, 50, 100, 250]
DOWNLOADS_PER_SIZE = 20
UPLOADS_PER_SIZE = 20


def run_rtt_test(server_ip, duration_s=RTT_DURATION_S):
    """Send 'R' packets every 50ms, server echoes back, measure RTT."""
    print(f"\n[RTT test] {duration_s}s, one packet every {RTT_INTERVAL_MS}ms...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.5)
    payload_size = PKT_SIZE - 13
    rtts = []
    seq = 0
    deadline = time.time() + duration_s

    while time.time() < deadline:
        send_ts = time.time()
        pkt = b"R" + struct.pack("!Id", seq, send_ts) + b"\x00" * payload_size
        try:
            sock.sendto(pkt, (server_ip, UDP_PORT))
            data, _ = sock.recvfrom(PKT_SIZE + 64)
            recv_ts = time.time()
            if data[0:1] == b"R":
                rtts.append((recv_ts - send_ts) * 1000)
        except socket.timeout:
            pass
        seq += 1
        time.sleep(max(0, RTT_INTERVAL_MS / 1000 - (time.time() - send_ts)))

    sock.close()
    if rtts:
        s = sorted(rtts)
        print(f"  {len(rtts)} samples  median={s[len(s)//2]:.1f}ms  " f"min={s[0]:.1f}ms  max={s[-1]:.1f}ms")
    else:
        print("  WARNING: no samples — is server.py running?")
    return rtts


def run_train_test(server_ip):
    """Send 'T'+N to server, receive N packets back, measure TCT."""
    print(f"\n[Train test] sizes={TRAIN_SIZES}, {TRAINS_PER_SIZE} repeats each...")
    results = {n: {"tct_ms": [], "rel_arrivals": []} for n in TRAIN_SIZES}

    order = []
    for n in TRAIN_SIZES:
        order.extend([n] * TRAINS_PER_SIZE)
    random.shuffle(order)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 0))
    completed = 0

    for n in order:
        req = b"T" + struct.pack("!H", n)
        send_ts = time.time()
        sock.sendto(req, (server_ip, UDP_PORT))

        arrivals = []
        sock.settimeout(0.05)
        deadline = time.time() + max(0.5, n * 0.01 + 0.3)

        while len(arrivals) < n and time.time() < deadline:
            try:
                data, _ = sock.recvfrom(PKT_SIZE + 64)
                if data[0:1] == b"T":
                    arrivals.append(time.time())
            except socket.timeout:
                continue

        if len(arrivals) == n:
            t0 = arrivals[0]
            rel = [(t - t0) * 1000 for t in arrivals]
            tct = (arrivals[-1] - send_ts) * 1000
            results[n]["rel_arrivals"].append(rel)
            results[n]["tct_ms"].append(tct)
            completed += 1

        time.sleep(TRAIN_GAP_MS / 1000)

    sock.close()
    print(f"  Completed {completed}/{len(order)} trains")
    for n in TRAIN_SIZES:
        tcts = results[n]["tct_ms"]
        if tcts:
            print(f"  N={n:3d}: mean TCT={sum(tcts)/len(tcts):.1f}ms  ({len(tcts)})")
        else:
            print(f"  N={n:3d}: no data")
    return results


def run_download_test(server_ip):
    """TCP connect to port 5001, send 'D'+4-byte size, receive data, measure time."""
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
            sock.settimeout(15)
            sock.connect((server_ip, TCP_PORT))
            t0 = time.time()
            # Command byte 'D' + 4-byte size
            sock.sendall(b"D" + struct.pack("!I", size_bytes))
            received = 0
            while received < size_bytes:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                received += len(chunk)
            t1 = time.time()
            sock.close()
            if received == size_bytes:
                results[kb].append((t1 - t0) * 1000)
            time.sleep(0.05)
        except Exception as e:
            print(f"  [warn] {kb}KB download: {e}")

    for kb in FILE_SIZES_KB:
        times = results[kb]
        if times:
            print(f"  {kb:4d}KB: mean={sum(times)/len(times):.1f}ms  ({len(times)})")
        else:
            print(f"  {kb:4d}KB: no data")
    return results


def run_upload_test(server_ip):
    """TCP connect to port 5001, send 'U'+4-byte size, upload data, wait for 'OK' ack."""
    print(f"\n[Upload test] sizes={FILE_SIZES_KB}KB, {UPLOADS_PER_SIZE} each...")
    results = {kb: [] for kb in FILE_SIZES_KB}

    order = []
    for kb in FILE_SIZES_KB:
        order.extend([kb] * UPLOADS_PER_SIZE)
    random.shuffle(order)

    # Pre-generate payload to avoid allocation overhead during timing
    payload = b"B" * 65536

    for kb in order:
        size_bytes = kb * 1024
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(30)
            sock.connect((server_ip, TCP_PORT))
            t0 = time.time()
            # Command byte 'U' + 4-byte size
            sock.sendall(b"U" + struct.pack("!I", size_bytes))
            sent = 0
            while sent < size_bytes:
                to_send = min(len(payload), size_bytes - sent)
                sock.sendall(payload[:to_send])
                sent += to_send
            # Wait for server ack
            ack = b""
            while len(ack) < 2:
                chunk = sock.recv(2 - len(ack))
                if not chunk:
                    break
                ack += chunk
            t1 = time.time()
            sock.close()
            if ack == b"OK":
                results[kb].append((t1 - t0) * 1000)
            else:
                print(f"  [warn] {kb}KB upload: bad ack {ack!r}")
            time.sleep(0.05)
        except Exception as e:
            print(f"  [warn] {kb}KB upload: {e}")

    for kb in FILE_SIZES_KB:
        times = results[kb]
        if times:
            print(f"  {kb:4d}KB: mean={sum(times)/len(times):.1f}ms  ({len(times)})")
        else:
            print(f"  {kb:4d}KB: no data")
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--skip-rtt", action="store_true")
    parser.add_argument("--skip-train", action="store_true")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--skip-upload", action="store_true")
    parser.add_argument("--rtt-duration", type=int, default=RTT_DURATION_S)
    args = parser.parse_args()

    print(f"\nBenchmark → {args.server}  label={args.label}")
    print(f"  UDP {UDP_PORT} (RTT+train)   TCP {TCP_PORT} (download+upload)\n")

    results = {"label": args.label, "server": args.server, "timestamp": time.time()}

    if not args.skip_rtt:
        results["rtt_ms"] = run_rtt_test(args.server, args.rtt_duration)
    if not args.skip_train:
        tr = run_train_test(args.server)
        results["train"] = {
            str(n): {"tct_ms": v["tct_ms"], "rel_arrivals": v["rel_arrivals"]} for n, v in tr.items()
        }
    if not args.skip_download:
        results["download_ms"] = {
            str(kb): times for kb, times in run_download_test(server_ip=args.server).items()
        }
    if not args.skip_upload:
        results["upload_ms"] = {
            str(kb): times for kb, times in run_upload_test(server_ip=args.server).items()
        }

    out = f"results_{args.label}.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved → {out}")


if __name__ == "__main__":
    main()
