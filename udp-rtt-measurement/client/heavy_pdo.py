import os
import socket
import time
import threading
from dotenv import load_dotenv

SERVER_PORT = 5000
PACKET_SIZE = 1400  # MTU-sized, matching paper
SATURATOR_PORT = 5001  # Separate port so server knows it's the saturator

# Output file
os.makedirs("logs", exist_ok=True)
down_heavy_pdo_file = os.path.join("logs", "down-heavy-pdo.txt")

# Recording start time — all timestamps relative to this
recording_start_time = None

# Flag to stop both threads cleanly
stop_flag = threading.Event()


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def ms_since_start(t: float) -> float:
    """Absolute time → ms relative to recording start."""
    return round((t - recording_start_time) * 1000, 3)


# ──────────────────────────────────────────────
# Sender thread — blasts # packets continuously
# ──────────────────────────────────────────────


def send_heavy(sock, server_ip):
    """
    Continuously send MTU-sized '#' packets to the server as fast as possible.
    No sleep — goal is to saturate the uplink and keep network in heavy mode.
    """
    pkt = b"#" + b"\x00" * (PACKET_SIZE - 1)
    print("[SENDER] Saturating uplink...")

    while not stop_flag.is_set():
        sock.sendto(pkt, (server_ip, SERVER_PORT))


# ──────────────────────────────────────────────
# Receiver thread — logs downlink heavy PDOs
# ──────────────────────────────────────────────


def receive_heavy(sock):
    """
    Receive '#' packets sent back by the server and log their arrival times.

    Output format (one line per packet):
        timestamp_ms

    - timestamp_ms : arrival time relative to recording start (ms)
    - This is a continuous stream — NOT grouped into trains

    Example:
        0.0
        1.3
        2.7
        3.9
        ...
    """
    print("[RECEIVER] Listening for downlink heavy packets...")
    sock.settimeout(1.0)  # Short timeout so stop_flag is checked regularly

    with open(down_heavy_pdo_file, "a") as f:
        while not stop_flag.is_set():
            try:
                data, _ = sock.recvfrom(65535)

                # Only log packets marked as '#' (heavy response from server)
                if data[0:1] == b"#":
                    arrival_time = time.time()
                    ts_ms = ms_since_start(arrival_time)
                    f.write(f"{ts_ms:.3f}\n")
                    f.flush()  # Write immediately — don't buffer

            except socket.timeout:
                continue  # Just check stop_flag and loop again
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
    import os

    SERVER_IP = os.getenv("SERVER_IP", "127.0.0.1")
    print(f"Saturator targeting server: {SERVER_IP}:{SERVER_PORT}")
    print(f"Output → {down_heavy_pdo_file}\n")

    # Single UDP socket for both send and receive
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", SATURATOR_PORT))  # Bind so server knows our port

    recording_start_time = time.time()
    print(f"Recording started at {recording_start_time:.3f}\n")

    # Start sender and receiver on separate threads
    sender_thread = threading.Thread(target=send_heavy, args=(sock, SERVER_IP), daemon=True)
    receiver_thread = threading.Thread(target=receive_heavy, args=(sock,), daemon=True)

    sender_thread.start()
    receiver_thread.start()

    try:
        # Run until Ctrl+C
        while True:
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\nStopping saturator...")
        stop_flag.set()

    sender_thread.join(timeout=2)
    receiver_thread.join(timeout=2)

    sock.close()
    print(f"Saturator stopped.")
    print(f"Heavy PDO trace saved → {down_heavy_pdo_file}")


if __name__ == "__main__":
    main()
