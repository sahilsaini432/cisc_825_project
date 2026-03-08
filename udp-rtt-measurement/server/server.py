import socket
import asyncio
import csv
import os
import signal
import select
import time
from datetime import datetime

HOST = "0.0.0.0"  # Server IP address
PORT = 5000  # Server port
D = 10  # number of downlink packets
DOWNLINK_PACKET_SIZE = 1024  # Size of the downlink packet

# Per-client train state: addr -> list of arrival timestamps
uplink_trains = {}

# Heavy client log: addr -> list of arrival timestamps
heavy_arrivals = {}


async def handle_packet(data, addr, server_socket: socket.socket):
    arrival_time = time.time()
    marker = data[0:1]

    if marker == b"@":
        # First packet in an uplink train — start a new train
        if addr in uplink_trains and uplink_trains[addr]:
            log_uplink_train(addr, uplink_trains[addr])
        uplink_trains[addr] = [arrival_time]

        # Send D downlink packets
        first_packet = b"@" * DOWNLINK_PACKET_SIZE
        downlink_packet = b"Y" * DOWNLINK_PACKET_SIZE
        loop = asyncio.get_event_loop()
        for i in range(D):
            pkt = first_packet if i == 0 else downlink_packet
            await loop.run_in_executor(None, server_socket.sendto, pkt, addr)

    elif marker == b"X":
        # Subsequent packet in an uplink train
        if addr in uplink_trains:
            uplink_trains[addr].append(arrival_time)

    elif marker == b"#":
        # Heavy/saturator client packet
        if addr not in heavy_arrivals:
            heavy_arrivals[addr] = []
        heavy_arrivals[addr].append(arrival_time)

    else:
        print(f"Unknown packet marker from {addr}: {marker}")


def log_uplink_train(addr, arrivals):
    """Log a completed uplink train's arrival times."""
    with open(uplink_log_file, mode="a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([addr[0], addr[1]] + arrivals)


def flush_heavy_logs():
    """Write out all heavy client arrival logs."""
    with open(heavy_log_file, mode="a", newline="") as file:
        writer = csv.writer(file)
        for addr, arrivals in heavy_arrivals.items():
            writer.writerow([addr[0], addr[1]] + arrivals)
    heavy_arrivals.clear()


def receive_with_select(server_socket, stop_event):
    """Use select to wait for data without blocking forever."""
    while not stop_event.is_set():
        ready = select.select([server_socket], [], [], 1.0)  # 1s timeout
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
        print("\nShutting down server...")
        thread_stop.set()
        stop_event.set()

    loop.add_signal_handler(signal.SIGINT, shutdown)
    loop.add_signal_handler(signal.SIGTERM, shutdown)

    print(f"Server listening on {HOST}:{PORT}")
    print("Press Ctrl+C to stop the server.")

    while not stop_event.is_set():
        data, addr = await loop.run_in_executor(None, receive_with_select, server_socket, thread_stop)
        if data is not None:
            print(f"Received {len(data)} bytes from {addr}")
            asyncio.create_task(handle_packet(data, addr, server_socket))

    # Flush any remaining train/heavy logs before exiting
    for addr, arrivals in uplink_trains.items():
        if arrivals:
            log_uplink_train(addr, arrivals)
    flush_heavy_logs()

    server_socket.close()
    print("Server stopped.")


if __name__ == "__main__":
    os.makedirs("logs", exist_ok=True)

    uplink_log_file = "logs/uplink_train_log.csv"
    heavy_log_file = "logs/heavy_log.csv"

    asyncio.run(main())
