class Packet:
    def __init__(self, sequence_number, timestamp):
        self.sequence_number = sequence_number
        self.timestamp = timestamp

    def serialize(self):
        return f"{self.sequence_number},{self.timestamp}".encode('utf-8')

    @staticmethod
    def deserialize(data):
        sequence_number, timestamp = data.decode('utf-8').split(',')
        return Packet(int(sequence_number), float(timestamp))