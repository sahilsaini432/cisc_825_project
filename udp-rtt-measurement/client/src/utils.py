def calculate_rtt(sent_time, received_time):
    return received_time - sent_time

def log_rtt_to_csv(rtt, log_file='logs/rtt_log.csv'):
    with open(log_file, 'a') as f:
        f.write(f"{rtt}\n")

def get_current_timestamp():
    from datetime import datetime
    return datetime.now().timestamp()