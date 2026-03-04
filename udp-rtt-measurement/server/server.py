import socket
import asyncio
import csv
import os
from datetime import datetime

HOST = "0.0.0.0"  # Server IP address
PORT = 12345  # Server port
D = 10  # number of downlink packets
DOWNLINK_PACKET_SIZE = 1024  # Size of the downlink packet


async def handle_client(data, addr, server_socket: socket.socket, seen_clients: set):
    log_packet(len(data), addr)

    if addr not in seen_clients:
        seen_clients.add(addr)
        downlink_packet = b"Y" * DOWNLINK_PACKET_SIZE
        loop = asyncio.get_event_loop()
        for _ in range(D):
            await loop.run_in_executor(None, server_socket.sendto, downlink_packet, addr)


def log_packet(packet_size, source_address):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    with open(log_file, mode="a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([timestamp, packet_size, source_address])


async def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind((HOST, PORT))
    seen_clients = set()

    print(f"Server listening on {HOST}:{PORT}")

    while True:
        data, addr = await asyncio.get_event_loop().run_in_executor(None, server_socket.recvfrom, 1024)
        asyncio.create_task(handle_client(data[0], addr, server_socket, seen_clients))


if __name__ == "__main__":
    # Setup log file
    log_file = "logs/packet_log.csv"
    if not os.path.isfile(log_file):
        with open(log_file, mode="w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["Timestamp", "Packet Size", "Source Address"])

    asyncio.run(main())
