import os
import socket
import time
import csv
from dotenv import load_dotenv


class UDPClient:
    def __init__(self, server_ip, server_port, packet_size, interval):
        self.server_ip = server_ip
        self.server_port = server_port
        self.packet_size = packet_size
        self.interval = interval
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rtt_log_file = os.path.join(os.path.dirname(__file__), "logs", "rtt_log.csv")
        os.makedirs(os.path.dirname(self.rtt_log_file), exist_ok=True)

    def send_packets(self, U):
        first_packet = "@" * self.packet_size
        packet = "X" * self.packet_size
        while True:
            t_first_sent = None
            for _ in range(U):
                if t_first_sent is None:
                    t_first_sent = time.time()
                    self.sock.sendto(first_packet.encode(), (self.server_ip, self.server_port))
                else:
                    self.sock.sendto(packet.encode(), (self.server_ip, self.server_port))
            self.receive_response(t_first_sent)
            time.sleep(self.interval / 1000.0)

    def receive_response(self, t_first_sent):
        self.sock.settimeout(10.0)
        downlink_arrivals = []
        try:
            # Receive first downlink packet
            self.sock.recvfrom(65535)
            t_first_received = time.time()
            downlink_arrivals.append(t_first_received)

            # Receive remaining downlink packets with a shorter timeout
            self.sock.settimeout(2.0)
            while True:
                try:
                    self.sock.recvfrom(65535)
                    downlink_arrivals.append(time.time())
                except socket.timeout:
                    break

            rtt = (t_first_received - t_first_sent) * 1000
            print(f"RTT: {rtt:.2f} ms | Downlink packets received: {len(downlink_arrivals)}")
            self.log_train(t_first_sent, rtt, downlink_arrivals)

        except socket.timeout:
            print("Request timed out.")

    def log_train(self, t_first_sent, rtt, downlink_arrivals):
        with open(self.rtt_log_file, mode="a", newline="") as file:
            writer = csv.writer(file)
            writer.writerow([t_first_sent, rtt] + downlink_arrivals)


if __name__ == "__main__":
    load_dotenv()
    SERVER_IP = os.getenv("SERVER_IP", "127.0.0.1")
    print(f"Using server IP: {SERVER_IP}")

    SERVER_PORT = 5000  # Replace with the server's port
    PACKET_SIZE = 1024  # Size of the packet train
    INTERVAL = 100  # Interval in milliseconds
    U = 10  # Number of packets in the train

    client = UDPClient(SERVER_IP, SERVER_PORT, PACKET_SIZE, INTERVAL)
    client.send_packets(U)
