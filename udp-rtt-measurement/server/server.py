import socket
import asyncio
import os
import signal
import select
import time

HOST = "0.0.0.0"
PORT = 5000
D = 75  # Number of downlink packets to send back
DOWNLINK_PACKET_SIZE = 1400  # MTU-sized packets (matching paper)

# Per-client train state: addr -> list of absolute arrival times (float seconds)
uplink_trains = {}

# Heavy PDO arrivals: list of absolute arrival times
heavy_arrivals = []

# Set when first packet ever arrives — all times are relative to this
recording_start_time = None


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def ms_since_start(t: float) -> float:
    """Absolute time → ms relative to recording start."""
    return round((t - recording_start_time) * 1000, 3)


def compute_pdos(arrivals: list) -> list:
    """
    Convert absolute arrival times of one train into relative PDOs (ms).
    First value is always 0.0 (first packet is the reference).
    e.g. [1.000, 1.003, 1.005] → [0.0, 3.0, 5.0]
    """
    t0 = arrivals[0]
    return [round((t - t0) * 1000, 3) for t in arrivals]


# ──────────────────────────────────────────────
# Packet handler
# ──────────────────────────────────────────────


async def handle_packet(data: bytes, addr, server_socket: socket.socket):
    global recording_start_time

    arrival_time = time.time()
    loop = asyncio.get_event_loop()

    # Set recording start on very first packet
    if recording_start_time is None:
        recording_start_time = arrival_time
        print(f"Recording started at {recording_start_time:.3f}")

    marker = data[0:1]

    if marker == b"@":
        # ── First packet of a NEW uplink train ──
        # Flush the previous completed train (if any) before starting new one
        if addr in uplink_trains and uplink_trains[addr]:
            flush_uplink_train(uplink_trains[addr])

        # Start fresh train with this packet's arrival time
        uplink_trains[addr] = [arrival_time]
        print(f"[RX] @ (train start) from {addr}")

        # Respond with D downlink packets (first marked "@", rest "Y")
        # Client uses the "@" marker to identify start of downlink train
        first_pkt = b"@" + b"\x00" * (DOWNLINK_PACKET_SIZE - 1)
        other_pkt = b"Y" + b"\x00" * (DOWNLINK_PACKET_SIZE - 1)
        for i in range(D):
            pkt = first_pkt if i == 0 else other_pkt
            await loop.run_in_executor(None, server_socket.sendto, pkt, addr)
        print(f"[TX] Sent {D} downlink packets to {addr}")

    elif marker == b"X":
        # ── Subsequent packet in the current uplink train ──
        if addr in uplink_trains:
            uplink_trains[addr].append(arrival_time)
            print(f"[RX] X (train pkt #{len(uplink_trains[addr])}) from {addr}")

    elif marker == b"#":
        # ── Heavy / saturator packet ──
        heavy_arrivals.append(arrival_time)
        print(f"[RX] # (heavy pkt #{len(heavy_arrivals)}) from {addr}")

        # Send one # packet back so saturator can log downlink heavy PDOs
        response = b"#" + b"\x00" * (DOWNLINK_PACKET_SIZE - 1)
        await loop.run_in_executor(None, server_socket.sendto, response, addr)

    else:
        print(f"[WARN] Unknown marker {marker} from {addr}")


# ──────────────────────────────────────────────
# Trace writers
# ──────────────────────────────────────────────


def flush_uplink_train(arrivals: list):
    """
    Write ONE completed train to the uplink light PDO trace file.

    Output format (one line per train):
        time_ms   0.0   pdo_1   pdo_2   ...   pdo_{U-1}

    - time_ms   : arrival time of train's first packet, relative to recording start (ms)
    - 0.0       : PDO of first packet is always 0 (it's the reference)
    - pdo_i     : arrival_time[i] - arrival_time[0], in ms

    Example line:
        0.0     0.0   3.2   5.1
        50.4    0.0   2.8   4.9   6.1
    """
    time_ms = ms_since_start(arrivals[0])
    pdos = compute_pdos(arrivals)  # [0.0, 3.2, 5.1, ...]

    with open(uplink_light_pdo_file, "a") as f:
        pdo_str = "   ".join(f"{round(p)}" for p in pdos)
        f.write(f"{round(time_ms)}   {pdo_str}\n")


def flush_heavy_pdos():
    """
    Write all heavy PDO arrivals to file.

    Output format (one line per packet):
        timestamp_ms

    - timestamp_ms : arrival time relative to recording start (ms)
    - These are NOT grouped into trains — it's a continuous saturated stream

    Example:
        0.0
        1.2
        2.5
        3.7
        ...
    """
    if not heavy_arrivals:
        return
    with open(uplink_heavy_pdo_file, "a") as f:
        for t in heavy_arrivals:
            f.write(f"{round(ms_since_start(t))}\n")
    heavy_arrivals.clear()


# ──────────────────────────────────────────────
# Main loop
# ──────────────────────────────────────────────


def receive_with_select(server_socket, thread_stop):
    """Non-blocking receive with 1s timeout so shutdown works cleanly."""
    while not thread_stop.is_set():
        ready = select.select([server_socket], [], [], 1.0)
        if ready[0]:
            return server_socket.recvfrom(65535)
    return None, None


async def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))

    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()
    import threading

    thread_stop = threading.Event()

    def shutdown():
        print("\nShutting down — flushing remaining logs...")
        thread_stop.set()
        stop_event.set()

    loop.add_signal_handler(signal.SIGINT, shutdown)
    loop.add_signal_handler(signal.SIGTERM, shutdown)

    print(f"Server listening on {HOST}:{PORT}")
    print("Waiting for packets... (Ctrl+C to stop)")

    while not stop_event.is_set():
        data, addr = await loop.run_in_executor(None, receive_with_select, server_socket, thread_stop)
        if data is not None:
            asyncio.create_task(handle_packet(data, addr, server_socket))

    # ── Graceful shutdown: flush everything ──
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

    # Output files (server only handles uplink side)
    uplink_light_pdo_file = "logs/up-delay-light-pdo.txt"  # time + PDOs per train
    uplink_heavy_pdo_file = "logs/up-heavy-pdo.txt"  # continuous heavy arrivals

    asyncio.run(main())
