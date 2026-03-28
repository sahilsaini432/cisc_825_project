#!/usr/bin/env python3
"""
CellReplay benchmark server.
Run this on the remote server (or localhost for testing).

Ports:
  UDP 5001 - echo server (RTT test)
  UDP 5002 - train sender (TCT test)
  TCP 5003 - file download server
"""

import socket
import threading
import struct
import os
import time

UDP_ECHO_PORT = 5001
UDP_TRAIN_PORT = 5002
TCP_FILE_PORT = 5003
PKT_SIZE = 1400  # MTU-sized packets like the paper


def udp_echo_server():
    """Echoes every UDP packet back to sender (RTT test)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", UDP_ECHO_PORT))
    print(f"[echo]  UDP echo server listening on :{UDP_ECHO_PORT}")
    while True:
        data, addr = sock.recvfrom(4096)
        sock.sendto(data, addr)


def udp_train_server():
    """
    Train server: waits for a train request from client.
    Request format: struct { train_id(4B), train_size(4B) }
    Responds with train_size back-to-back 1400-byte packets.
    Each packet: struct { train_id(4B), seq(4B), send_ts_us(8B), payload }
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", UDP_TRAIN_PORT))
    print(f"[train] UDP train server listening on :{UDP_TRAIN_PORT}")

    while True:
        data, addr = sock.recvfrom(64)
        if len(data) < 8:
            continue
        train_id, train_size = struct.unpack("!II", data[:8])

        payload = b"X" * (PKT_SIZE - 16)  # 16 = header size
        for seq in range(train_size):
            ts_us = int(time.time() * 1e6)
            pkt = struct.pack("!IIQ", train_id, seq, ts_us) + payload
            sock.sendto(pkt, addr)


def tcp_file_server():
    """
    File download server.
    Client sends 4 bytes = requested file size in bytes.
    Server responds with exactly that many bytes then closes.
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", TCP_FILE_PORT))
    srv.listen(16)
    print(f"[file]  TCP file server listening on :{TCP_FILE_PORT}")

    def handle(conn, addr):
        try:
            raw = conn.recv(4)
            if len(raw) < 4:
                return
            size = struct.unpack("!I", raw)[0]
            sent = 0
            chunk = b"A" * 65536
            while sent < size:
                to_send = min(len(chunk), size - sent)
                conn.sendall(chunk[:to_send])
                sent += to_send
        finally:
            conn.close()

    while True:
        conn, addr = srv.accept()
        threading.Thread(target=handle, args=(conn, addr), daemon=True).start()


if __name__ == "__main__":
    threads = [
        threading.Thread(target=udp_echo_server, daemon=True),
        threading.Thread(target=udp_train_server, daemon=True),
        threading.Thread(target=tcp_file_server, daemon=True),
    ]
    for t in threads:
        t.start()

    print("\nAll servers running. Ctrl+C to stop.\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping.")
