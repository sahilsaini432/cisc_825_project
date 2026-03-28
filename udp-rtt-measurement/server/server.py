#!/usr/bin/env python3
"""
CellReplay server — handles both recording AND benchmark test traffic.

UDP Port 5000:
  '@' = first packet of uplink train    → respond with D=75 downlink packets
  'X' = subsequent uplink train packets → log arrival time
  '#' = heavy/saturator packet          → echo one '#' back
  'R' = RTT probe                       → echo straight back
  'T' = variable train request          → send N packets back (N in bytes 1-2)

TCP Port 5001:
  File download:  client sends b'D' + 4-byte uint32 size → server sends that many bytes
  File upload:    client sends b'U' + 4-byte uint32 size → client sends data → server acks with b'OK'

Recording output (logs/):
  up-delay-light-pdo.txt  — uplink light PDOs (one line per train)
  up-heavy-pdo.txt        — uplink heavy PDOs (one timestamp per packet)
"""

import socket
import asyncio
import os
import signal
import select
import time
import threading
import struct

HOST = "0.0.0.0"
UDP_PORT = 5000
TCP_PORT = 5001
D = 75  # Number of downlink packets to send back per light train
DOWNLINK_PACKET_SIZE = 1400

# Recording state
uplink_trains = {}
heavy_arrivals = []
recording_start_time = None


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def ms_since_start(t: float) -> float:
    return round((t - recording_start_time) * 1000, 3)


def compute_pdos(arrivals: list) -> list:
    t0 = arrivals[0]
    return [round((t - t0) * 1000, 3) for t in arrivals]


# ──────────────────────────────────────────────
# Trace writers
# ──────────────────────────────────────────────


def flush_uplink_train(arrivals: list):
    time_ms = ms_since_start(arrivals[0])
    pdos = compute_pdos(arrivals)
    with open(uplink_light_pdo_file, "a") as f:
        pdo_str = "   ".join(f"{round(p)}" for p in pdos)
        f.write(f"{round(time_ms)}   {pdo_str}\n")


def flush_heavy_pdos():
    if not heavy_arrivals:
        return
    with open(uplink_heavy_pdo_file, "a") as f:
        for t in heavy_arrivals:
            f.write(f"{round(ms_since_start(t))}\n")
    heavy_arrivals.clear()


# ──────────────────────────────────────────────
# UDP packet handler
# ──────────────────────────────────────────────


async def handle_packet(data: bytes, addr, sock: socket.socket):
    global recording_start_time

    arrival_time = time.time()
    loop = asyncio.get_event_loop()

    if recording_start_time is None:
        recording_start_time = arrival_time
        print(f"Recording started at {recording_start_time:.3f}")

    marker = data[0:1]

    if marker == b"@":
        # ── Light train: first packet ──
        if addr in uplink_trains and uplink_trains[addr]:
            flush_uplink_train(uplink_trains[addr])
        uplink_trains[addr] = [arrival_time]
        print(f"[RX] @ (train start) from {addr}")

        first_pkt = b"@" + b"\x00" * (DOWNLINK_PACKET_SIZE - 1)
        other_pkt = b"Y" + b"\x00" * (DOWNLINK_PACKET_SIZE - 1)
        for i in range(D):
            pkt = first_pkt if i == 0 else other_pkt
            await loop.run_in_executor(None, sock.sendto, pkt, addr)
        print(f"[TX] Sent {D} downlink packets to {addr}")

    elif marker == b"X":
        # ── Light train: subsequent packets ──
        if addr in uplink_trains:
            uplink_trains[addr].append(arrival_time)

    elif marker == b"#":
        # ── Heavy saturator packet ──
        heavy_arrivals.append(arrival_time)
        response = b"#" + b"\x00" * (DOWNLINK_PACKET_SIZE - 1)
        await loop.run_in_executor(None, sock.sendto, response, addr)

    elif marker == b"R":
        # ── RTT probe: echo straight back ──
        await loop.run_in_executor(None, sock.sendto, data, addr)

    elif marker == b"T":
        # ── Variable train request for benchmark test ──
        # Bytes 1-2: train size N (big-endian uint16)
        if len(data) < 3:
            return
        n = struct.unpack("!H", data[1:3])[0]
        n = max(1, min(n, 500))  # clamp to sane range
        print(f"[RX] T (train request N={n}) from {addr}")
        pkt = b"T" + b"\x00" * (DOWNLINK_PACKET_SIZE - 1)
        for _ in range(n):
            await loop.run_in_executor(None, sock.sendto, pkt, addr)

    else:
        print(f"[WARN] Unknown marker {marker} from {addr}")


# ──────────────────────────────────────────────
# TCP file server (download + upload)
# ──────────────────────────────────────────────


def tcp_file_server():
    """
    Protocol (first byte selects mode):
      b'D' + 4-byte uint32 size  → download: server sends `size` bytes then closes
      b'U' + 4-byte uint32 size  → upload:   client sends `size` bytes, server acks b'OK'
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, TCP_PORT))
    srv.listen(32)
    print(f"[file]  TCP server listening on :{TCP_PORT}  (D=download  U=upload)")

    def handle(conn, addr):
        try:
            conn.settimeout(30)

            # Read command byte + 4-byte size (5 bytes total)
            header = b""
            while len(header) < 5:
                chunk = conn.recv(5 - len(header))
                if not chunk:
                    return
                header += chunk

            cmd = header[0:1]
            size = struct.unpack("!I", header[1:5])[0]

            if cmd == b"D":
                # ── Download: send `size` bytes ──
                sent = 0
                payload = b"A" * 65536
                while sent < size:
                    to_send = min(len(payload), size - sent)
                    conn.sendall(payload[:to_send])
                    sent += to_send

            elif cmd == b"U":
                # ── Upload: receive `size` bytes, then ack ──
                received = 0
                while received < size:
                    chunk = conn.recv(min(65536, size - received))
                    if not chunk:
                        break
                    received += len(chunk)
                if received == size:
                    conn.sendall(b"OK")

            else:
                print(f"[file] unknown command byte {cmd!r} from {addr}")

        except Exception as e:
            print(f"[file] error from {addr}: {e}")
        finally:
            conn.close()

    while True:
        try:
            conn, addr = srv.accept()
            threading.Thread(target=handle, args=(conn, addr), daemon=True).start()
        except Exception:
            break


# ──────────────────────────────────────────────
# Main UDP loop
# ──────────────────────────────────────────────


def receive_with_select(server_socket, thread_stop):
    while not thread_stop.is_set():
        ready = select.select([server_socket], [], [], 1.0)
        if ready[0]:
            return server_socket.recvfrom(65535)
    return None, None


async def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, UDP_PORT))

    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()
    thread_stop = threading.Event()

    # Start TCP file server in background thread
    tcp_thread = threading.Thread(target=tcp_file_server, daemon=True)
    tcp_thread.start()

    def shutdown():
        print("\nShutting down — flushing remaining logs...")
        thread_stop.set()
        stop_event.set()

    loop.add_signal_handler(signal.SIGINT, shutdown)
    loop.add_signal_handler(signal.SIGTERM, shutdown)

    print(f"Server listening on UDP :{UDP_PORT} and TCP :{TCP_PORT}")
    print(f"Markers: @ X (light train)  # (heavy)  R (RTT echo)  T (variable train)")
    print("Waiting for packets... (Ctrl+C to stop)\n")

    while not stop_event.is_set():
        data, addr = await loop.run_in_executor(None, receive_with_select, server_socket, thread_stop)
        if data is not None:
            asyncio.create_task(handle_packet(data, addr, server_socket))

    # Flush on shutdown
    for addr, arrivals in uplink_trains.items():
        if arrivals:
            flush_uplink_train(arrivals)
    flush_heavy_pdos()

    server_socket.close()
    print("Server stopped.")
    print(f"  Light PDO trace → {uplink_light_pdo_file}")
    print(f"  Heavy PDO trace → {uplink_heavy_pdo_file}")


if __name__ == "__main__":
    os.makedirs("logs", exist_ok=True)
    uplink_light_pdo_file = "logs/up-delay-light-pdo.txt"
    uplink_heavy_pdo_file = "logs/up-heavy-pdo.txt"
    asyncio.run(main())
