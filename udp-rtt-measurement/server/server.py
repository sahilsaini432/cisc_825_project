import socket
import asyncio
import csv
import os
import signal
import select
from datetime import datetime

HOST = "0.0.0.0"  # Server IP address
PORT = 5000  # Server port
D = 10  # number of downlink packets
DOWNLINK_PACKET_SIZE = 1024  # Size of the downlink packet


async def handle_client(data, addr, server_socket: socket.socket):
    log_packet(len(data), addr)
    downlink_packet = b"Y" * DOWNLINK_PACKET_SIZE
    loop = asyncio.get_event_loop()
    for _ in range(D):
        await loop.run_in_executor(None, server_socket.sendto, downlink_packet, addr)


def log_packet(packet_size, source_address):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    with open(log_file, mode="a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([timestamp, packet_size, source_address])


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

    thread_stop = threading.Event()  # thread-safe stop flag for executor thread

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
            asyncio.create_task(handle_client(data, addr, server_socket))

    server_socket.close()
    print("Server stopped.")


if __name__ == "__main__":
    os.makedirs("logs", exist_ok=True)
    log_file = "logs/packet_log.csv"
    if not os.path.isfile(log_file):
        with open(log_file, mode="w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["Timestamp", "Packet Size", "Source Address"])

    asyncio.run(main())
