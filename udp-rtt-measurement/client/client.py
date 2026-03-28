#!/usr/bin/env python3
"""
CellReplay client — light workload (Laptop A, Phone 1).

Every G ms:
  1. Sends U back-to-back MTU-sized packets to server (first "@", rest "X")
  2. Receives D=75 packets back from server (first "@", rest "Y")
  3. Computes one-way base delay = (t_first_downlink_received - t_first_uplink_sent) / 2
  4. Records downlink PDO offsets (relative arrival times within the train)

Output: down-delay-light-pdo.txt
  Format per line (one line per train):
    time_ms   delay_ms   0   offset_1   offset_2   ...   offset_{D-1}

  - time_ms   : when uplink train was sent (ms from recording start)
  - delay_ms  : one-way base delay = RTT/2 (ms, integer)
  - offsets   : arrival time of each downlink packet minus arrival of first (ms, integer)

Usage:
  python3 client.py --server 192.168.1.100
  python3 client.py --server 192.168.1.100 --U 25 --G 50 --duration 60
"""

import socket
import time
import argparse
import os
import signal
import sys

SERVER_PORT = 5000
PKT_SIZE = 1400  # MTU-sized, matches server DOWNLINK_PACKET_SIZE
D = 75  # Must match server.py hardcoded D
INTRA_TRAIN_TIMEOUT_S = 0.05  # 50ms timeout for packets within a train
INTER_TRAIN_TIMEOUT_S = 0.5  # 500ms timeout waiting for first downlink packet


def make_pkt(marker: bytes) -> bytes:
    return marker + b"\x00" * (PKT_SIZE - 1)


def run(server_ip: str, U: int, G_ms: int, duration_s: int, out_file: str):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 0))

    recording_start = None
    train_count = 0
    stop = False

    def on_exit(sig, frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, on_exit)
    signal.signal(signal.SIGTERM, on_exit)

    os.makedirs(os.path.dirname(out_file) if os.path.dirname(out_file) else ".", exist_ok=True)

    print(f"Client starting: U={U} pkts/train, G={G_ms}ms gap, D={D} downlink, " f"duration={duration_s}s")
    print(f"Server: {server_ip}:{SERVER_PORT}")
    print(f"Output: {out_file}")
    print()

    deadline = time.time() + duration_s

    while not stop and time.time() < deadline:
        train_send_time = time.time()

        if recording_start is None:
            recording_start = train_send_time

        # ── Send U uplink packets ──────────────────────────────────────────
        # First packet: "@" (signals new train to server)
        # Rest:         "X" (subsequent train packets)
        for i in range(U):
            marker = b"@" if i == 0 else b"X"
            sock.sendto(make_pkt(marker), (server_ip, SERVER_PORT))

        # ── Receive D downlink packets ─────────────────────────────────────
        # Server sends back D packets: first "@", rest "Y"
        # We wait for first "@" with a longer timeout, then collect
        # remaining "Y" packets with a short intra-train timeout.
        downlink_arrivals = []

        # Wait for first "@" downlink packet
        sock.settimeout(INTER_TRAIN_TIMEOUT_S)
        try:
            while True:
                data, _ = sock.recvfrom(PKT_SIZE + 64)
                t = time.time()
                if data[0:1] == b"@":
                    downlink_arrivals.append(t)
                    break
                # Ignore stray packets (e.g. leftover Y from previous train)
        except socket.timeout:
            print(f"  [train {train_count}] WARN: timed out waiting for first downlink packet")
            time.sleep(max(0, G_ms / 1000 - (time.time() - train_send_time)))
            continue

        # Collect remaining D-1 "Y" packets with short intra-train timeout
        sock.settimeout(INTRA_TRAIN_TIMEOUT_S)
        try:
            while len(downlink_arrivals) < D:
                data, _ = sock.recvfrom(PKT_SIZE + 64)
                t = time.time()
                if data[0:1] in (b"@", b"Y"):
                    downlink_arrivals.append(t)
        except socket.timeout:
            pass  # Partial train is fine — log what we received

        if not downlink_arrivals:
            train_count += 1
            time.sleep(max(0, G_ms / 1000 - (time.time() - train_send_time)))
            continue

        # ── Compute delay and PDO offsets ──────────────────────────────────
        t0_down = downlink_arrivals[0]
        delay_ms = int((t0_down - train_send_time) / 2 * 1000)  # RTT/2
        time_ms = int((train_send_time - recording_start) * 1000)
        offsets = [int((t - t0_down) * 1000) for t in downlink_arrivals]

        # ── Write to file ──────────────────────────────────────────────────
        # Format: time_ms   delay_ms   0   off_1   off_2   ...
        offset_str = "   ".join(str(o) for o in offsets)
        with open(out_file, "a") as f:
            f.write(f"{time_ms}   {delay_ms}   {offset_str}\n")

        train_count += 1
        if train_count % 20 == 0:
            elapsed = time.time() - recording_start
            print(
                f"  t={elapsed:.1f}s  train={train_count}  "
                f"delay={delay_ms}ms  pkts_received={len(downlink_arrivals)}/{D}"
            )

        # ── Sleep until next train ─────────────────────────────────────────
        elapsed_in_cycle = time.time() - train_send_time
        sleep_s = max(0, G_ms / 1000 - elapsed_in_cycle)
        time.sleep(sleep_s)

    sock.close()
    print(f"\nDone. Recorded {train_count} trains → {out_file}")


def main():
    parser = argparse.ArgumentParser(description="CellReplay light workload client")
    parser.add_argument("--server", required=True, help="Server IP address")
    parser.add_argument(
        "--U", type=int, default=25, help="Uplink packets per train (default: 25, paper Table 2)"
    )
    parser.add_argument(
        "--G", type=int, default=50, help="Gap between trains in ms (default: 50ms, stationary)"
    )
    parser.add_argument(
        "--duration", type=int, default=60, help="Recording duration in seconds (default: 60)"
    )
    parser.add_argument(
        "--out", default="down-delay-light-pdo.txt", help="Output file (default: down-delay-light-pdo.txt)"
    )
    args = parser.parse_args()

    run(args.server, args.U, args.G, args.duration, args.out)


if __name__ == "__main__":
    main()
