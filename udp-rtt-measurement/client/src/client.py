import socket
import time
import csv

class UDPClient:
    def __init__(self, server_ip, server_port, packet_size, interval):
        self.server_ip = server_ip
        self.server_port = server_port
        self.packet_size = packet_size
        self.interval = interval
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rtt_log_file = 'logs/rtt_log.csv'

    def send_packets(self):
        packet_train = 'X' * self.packet_size
        while True:
            start_time = time.time()
            self.sock.sendto(packet_train.encode(), (self.server_ip, self.server_port))
            print(f'Sent packet train at {start_time}')
            self.receive_response(start_time)
            time.sleep(self.interval / 1000.0)

    def receive_response(self, start_time):
        self.sock.settimeout(1.0)  # Set a timeout for receiving
        try:
            response, _ = self.sock.recvfrom(1024)
            end_time = time.time()
            rtt = (end_time - start_time) * 1000  # RTT in milliseconds
            print(f'Received response: {response.decode()} at {end_time}, RTT: {rtt:.2f} ms')
            self.log_rtt(rtt)
        except socket.timeout:
            print('Request timed out.')

    def log_rtt(self, rtt):
        with open(self.rtt_log_file, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([time.time(), rtt])

if __name__ == '__main__':
    SERVER_IP = '127.0.0.1'  # Replace with the server's IP address
    SERVER_PORT = 12345       # Replace with the server's port
    PACKET_SIZE = 1024        # Size of the packet train
    INTERVAL = 100            # Interval in milliseconds

    client = UDPClient(SERVER_IP, SERVER_PORT, PACKET_SIZE, INTERVAL)
    client.send_packets()