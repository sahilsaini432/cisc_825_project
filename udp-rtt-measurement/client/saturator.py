#!/usr/bin/env python3
"""
CellReplay saturator — heavy workload (Laptop B, Phone 2).

Continuously blasts "#" MTU-sized packets to the server for the full
recording duration. Server echoes one "#" back per received packet.
We log the arrival timestamp of each echo as a downlink heavy PDO.

Output: down-heavy-pdo.txt
  Format: one integer timestamp (ms from recording start) per line.
  Matches server.py's up-heavy-pdo.txt format exactly.

  Example:
    0
    8
    17
    25
    ...

Usage:
  python3 saturator.py --server 192.168.1.100
  python3 saturator.py --server 192.168.1.100 --duration 60 --rate 200
"""

import socket
import time
import argparse
import os
import threading
import signal
import sys

SERVER_PORT = 5000
PKT_SIZE = 1400  # MTU-sized, matches server DOWNLINK_PACKET_SIZE
DEFAULT_RATE = 500  # packets per second to send (overestimate max BW by ~25%)


def run(server_ip: str, duration_s: int, rate_pps: int, out_file: str):
    send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    recv_sock.bind(("0.0.0.0", 0))
    recv_sock.settimeout(0.1)

    pkt = b"#" + b"\x00" * (PKT_SIZE - 1)

    recording_start = time.time()
    deadline = recording_start + duration_s
    arrivals = []  # absolute timestamps of received "#" echoes
    stop = threading.Event()

    def on_exit(sig, frame):
        stop.set()

    signal.signal(signal.SIGINT, on_exit)
    signal.signal(signal.SIGTERM, on_exit)

    os.makedirs(os.path.dirname(out_file) if os.path.dirname(out_file) else ".", exist_ok=True)

    print(f"Saturator starting: rate={rate_pps} pkt/s, " f"duration={duration_s}s, pkt_size={PKT_SIZE}B")
    print(f"Server: {server_ip}:{SERVER_PORT}")
    print(f"Output: {out_file}")
    print()

    # ── Sender thread ──────────────────────────────────────────────────────
    # Sends # packets at the target rate continuously
    def sender():
        interval = 1.0 / rate_pps
        sent = 0
        while not stop.is_set() and time.time() < deadline:
            send_sock.sendto(pkt, (server_ip, SERVER_PORT))
            sent += 1
            if sent % 500 == 0:
                elapsed = time.time() - recording_start
                print(f"  t={elapsed:.1f}s  sent={sent}  received={len(arrivals)}")
            time.sleep(interval)

    sender_thread = threading.Thread(target=sender, daemon=True)
    sender_thread.start()

    # ── Receiver loop ──────────────────────────────────────────────────────
    # Receives # echoes from server and logs arrival times
    while not stop.is_set() and time.time() < deadline:
        try:
            data, _ = recv_sock.recvfrom(PKT_SIZE + 64)
            t = time.time()
            if data[0:1] == b"#":
                arrivals.append(t)
        except socket.timeout:
            continue

    stop.set()
    sender_thread.join(timeout=2)
    send_sock.close()
    recv_sock.close()

    # ── Write output file ──────────────────────────────────────────────────
    # Format: one integer ms timestamp per line, relative to recording start
    with open(out_file, "w") as f:
        for t in arrivals:
            ms = int((t - recording_start) * 1000)
            f.write(f"{ms}\n")

    print(f"\nDone.")
    print(f"  Received {len(arrivals)} downlink heavy PDOs → {out_file}")
    if arrivals:
        duration_actual = arrivals[-1] - arrivals[0]
        avg_rate_kbps = len(arrivals) * PKT_SIZE * 8 / duration_actual / 1000
        print(f"  Duration: {duration_actual:.1f}s")
        print(f"  Avg downlink rate: {avg_rate_kbps:.0f} kbps")


def main():
    parser = argparse.ArgumentParser(description="CellReplay heavy workload saturator")
    parser.add_argument("--server", required=True, help="Server IP address")
    parser.add_argument(
        "--duration", type=int, default=60, help="Recording duration in seconds (default: 60)"
    )
    parser.add_argument(
        "--rate",
        type=int,
        default=DEFAULT_RATE,
        help=f"Send rate in packets/sec (default: {DEFAULT_RATE}). "
        f"Set ~25%% above expected max link rate. "
        f"500 pkt/s = ~6 Mbps.",
    )
    parser.add_argument(
        "--out", default="down-heavy-pdo.txt", help="Output file (default: down-heavy-pdo.txt)"
    )
    args = parser.parse_args()

    run(args.server, args.duration, args.rate, args.out)


if __name__ == "__main__":
    main()
