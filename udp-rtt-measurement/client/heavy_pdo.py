import os
import socket
import time
import threading
from dotenv import load_dotenv

SERVER_PORT = 5000
PACKET_SIZE = 1400
SATURATOR_PORT = 5001
DURATION = 60  # ← 60 second recording window

os.makedirs("logs", exist_ok=True)
down_heavy_pdo_file = os.path.join("logs", "down-heavy-pdo.txt")

recording_start_time = None
stop_flag = threading.Event()


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def ms_since_start(t: float) -> float:
    return round((t - recording_start_time) * 1000)


# ──────────────────────────────────────────────
# Sender thread
# ──────────────────────────────────────────────


def send_heavy(sock, server_ip):
    pkt = b"#" + b"\x00" * (PACKET_SIZE - 1)
    print("[SENDER] Saturating uplink...")

    while not stop_flag.is_set():
        sock.sendto(pkt, (server_ip, SERVER_PORT))
        time.sleep(0.0001)


# ──────────────────────────────────────────────
# Receiver thread
# ──────────────────────────────────────────────


def receive_heavy(sock):
    print("[RECEIVER] Listening for downlink heavy packets...")
    sock.settimeout(1.0)

    pkt_count = 0
    with open(down_heavy_pdo_file, "a") as f:
        while not stop_flag.is_set():
            try:
                data, addr = sock.recvfrom(65535)
                print(f"[RECEIVER] Got packet from {addr}, len={len(data)}, first_byte={data[0:1]!r}")
                if data[0:1] == b"#":
                    arrival_time = time.time()
                    ts_ms = ms_since_start(arrival_time)
                    pkt_count += 1
                    print(f"[RECEIVER] Heavy packet #{pkt_count} accepted, ts={ts_ms}ms")
                    f.write(f"{ts_ms}\n")
                    f.flush()
                else:
                    print(f"[RECEIVER] Packet ignored (unexpected first byte: {data[0:1]!r})")
            except socket.timeout:
                continue
            except Exception as e:
                print(f"[WARN] Receive error: {e}")
                continue

    print("[RECEIVER] Stopped.")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────


def main():
    global recording_start_time

    load_dotenv()
    SERVER_IP = os.getenv("SERVER_IP", "127.0.0.1")
    print(f"Saturator targeting server: {SERVER_IP}:{SERVER_PORT}")
    print(f"Duration: {DURATION}s")
    print(f"Output → {down_heavy_pdo_file}\n")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", SATURATOR_PORT))

    recording_start_time = time.time()
    print(f"Recording started at {round(recording_start_time)}")

    sender_thread = threading.Thread(target=send_heavy, args=(sock, SERVER_IP), daemon=True)
    receiver_thread = threading.Thread(target=receive_heavy, args=(sock,), daemon=True)

    sender_thread.start()
    receiver_thread.start()

    try:
        # ← Run for exactly DURATION seconds
        time.sleep(DURATION)
        print(f"\n{DURATION}s window complete — stopping saturator...")

    except KeyboardInterrupt:
        print("\nManually stopped before 60s window finished.")

    stop_flag.set()

    sender_thread.join(timeout=2)
    receiver_thread.join(timeout=2)

    sock.close()
    print(f"Saturator stopped.")
    print(f"Heavy PDO trace saved → {down_heavy_pdo_file}")


if __name__ == "__main__":
    main()
