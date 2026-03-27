import os
import socket
import time
from dotenv import load_dotenv


class UDPClient:
    def __init__(self, server_ip, server_port, packet_size, interval, U, D):
        self.server_ip = server_ip
        self.server_port = server_port
        self.packet_size = packet_size  # Should be 1400 (MTU-sized)
        self.interval = interval  # G in ms — gap between trains
        self.U = U  # Uplink packets per train
        self.D = D  # Downlink packets expected back
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Output trace file (client owns the downlink side)
        self.down_light_pdo_file = os.path.join("logs", "down-delay-light-pdo.txt")
        os.makedirs("logs", exist_ok=True)

        # Recording start time — all timestamps relative to this
        self.recording_start_time = None

    # ──────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────

    def ms_since_start(self, t: float) -> float:
        """Absolute time → ms relative to recording start."""
        return round((t - self.recording_start_time) * 1000, 3)

    def compute_pdos(self, arrivals: list) -> list:
        """
        Convert absolute downlink arrival times into relative PDOs (ms).
        First value is always 0.0 (first packet is the reference).
        e.g. [1.000, 1.003, 1.005] → [0.0, 3.0, 5.0]
        """
        t0 = arrivals[0]
        return [round((t - t0) * 1000, 3) for t in arrivals]

    # ──────────────────────────────────────────────
    # Send & receive one train
    # ──────────────────────────────────────────────

    def send_train(self):
        """Send U uplink packets — first marked '@', rest marked 'X'."""
        first_pkt = b"@" + b"\x00" * (self.packet_size - 1)
        other_pkt = b"X" + b"\x00" * (self.packet_size - 1)

        t_first_sent = None
        for i in range(self.U):
            if i == 0:
                t_first_sent = time.time()
                self.sock.sendto(first_pkt, (self.server_ip, self.server_port))
            else:
                self.sock.sendto(other_pkt, (self.server_ip, self.server_port))

        return t_first_sent

    def receive_downlink_train(self):
        self.sock.settimeout(10.0)  # first packet — can afford to wait longer
        downlink_arrivals = []

        try:
            # Wait for first downlink packet
            while True:
                data, _ = self.sock.recvfrom(65535)
                if data[0:1] == b"@":
                    downlink_arrivals.append(time.time())
                    break

            # ← Reduce to 50ms — all D packets arrive back-to-back
            self.sock.settimeout(0.05)
            while len(downlink_arrivals) < self.D:
                try:
                    self.sock.recvfrom(65535)
                    downlink_arrivals.append(time.time())
                except socket.timeout:
                    break

        except socket.timeout:
            print("[WARN] Timed out waiting for downlink train.")

        return downlink_arrivals

    # ──────────────────────────────────────────────
    # Trace writer
    # ──────────────────────────────────────────────

    def log_train(self, t_first_sent: float, downlink_arrivals: list):
        """
        Write ONE completed train to the downlink light PDO trace file.

        Output format (one line per train):
            time_ms   delay_ms   0.0   pdo_1   pdo_2   ...   pdo_{D-1}

        - time_ms   : send time of train's first uplink packet, relative to recording start (ms)
        - delay_ms  : one-way base delay = RTT / 2
                      RTT = (first downlink arrival) - (first uplink send time)
        - 0.0       : PDO of first downlink packet is always 0 (it's the reference)
        - pdo_i     : downlink_arrival[i] - downlink_arrival[0], in ms

        Example lines:
            0.0     22.5   0.0   2.1   4.3
            50.3    21.8   0.0   1.9   3.8   5.2
        """
        if not downlink_arrivals:
            print("[WARN] No downlink arrivals — skipping log for this train.")
            return

        time_ms = self.ms_since_start(t_first_sent)
        rtt_ms = (downlink_arrivals[0] - t_first_sent) * 1000
        delay_ms = round(rtt_ms / 2, 3)  # One-way delay
        pdos = self.compute_pdos(downlink_arrivals)  # [0.0, 2.1, 4.3, ...]

        with open(self.down_light_pdo_file, "a") as f:
            pdo_str = "   ".join(f"{round(p)}" for p in pdos)
            f.write(f"{round(time_ms)}   {round(delay_ms)}   {pdo_str}\n")

        print(
            f"Train @ {round(time_ms)}ms | delay={round(delay_ms)}ms | "
            f"DL pkts={len(downlink_arrivals)} | PDOs={pdos}"
        )

    # ──────────────────────────────────────────────
    # Main recording loop
    # ──────────────────────────────────────────────

    def record(self, duration_sec):
        """
        Run the packet train probing workload for the full recording session.
        Sends one train every G ms (self.interval).
        """
        print(f"Starting recording | U={self.U} | D={self.D} | G={self.interval}ms")
        print(f"Output → {self.down_light_pdo_file}\n")

        self.recording_start_time = time.time()
        train_count = 0

        try:
            while time.time() - self.recording_start_time < duration_sec:
                t_train_start = time.time()

                # 1. Send uplink train
                t_first_sent = self.send_train()

                # 2. Receive downlink train + record PDOs + delay
                downlink_arrivals = self.receive_downlink_train()
                self.log_train(t_first_sent, downlink_arrivals)

                train_count += 1

                # 3. Sleep for the remainder of the G ms interval
                elapsed = (time.time() - t_train_start) * 1000
                sleep_ms = self.interval - elapsed
                if sleep_ms > 0:
                    time.sleep(sleep_ms / 1000.0)

        except KeyboardInterrupt:
            print(f"\nRecording stopped after {train_count} trains.")
            print(f"Trace saved → {self.down_light_pdo_file}")
        print(f"Recording complete — 60s window finished.")


if __name__ == "__main__":
    load_dotenv()
    SERVER_IP = os.getenv("SERVER_IP", "127.0.0.1")
    print(f"Connecting to server: {SERVER_IP}:5000\n")

    # ── Parameters (from Table 2 in paper) ──
    # Example: T-Mobile stationary-good
    U = 25  # Uplink packets per train
    D = 75  # Downlink packets per train (server sends these back)
    G = 50  # Gap between trains (ms)
    PACKET_SIZE = 1400  # MTU-sized packets
    DURATION = 60

    client = UDPClient(server_ip=SERVER_IP, server_port=5000, packet_size=PACKET_SIZE, interval=G, U=U, D=D)
    client.record(DURATION)
