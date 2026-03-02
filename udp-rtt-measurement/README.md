# UDP RTT Measurement Project

This project implements a client-server architecture for measuring Round Trip Time (RTT) using UDP packets. The server is written in Python, while the client can be implemented in either Python or Android.

## Project Structure

```
udp-rtt-measurement
├── server
│   ├── src
│   │   ├── server.py          # Main UDP server implementation
│   │   ├── logger.py          # Logging functionality for packet arrival times
│   │   └── utils.py           # Utility functions for the server
│   ├── logs
│   │   └── packet_log.csv     # Logs of packet arrival times
│   └── requirements.txt        # Python dependencies for the server
├── client
│   ├── python
│   │   ├── src
│   │   │   ├── client.py      # Client implementation for sending packets
│   │   │   ├── packet.py      # Packet structure and serialization
│   │   │   └── utils.py       # Utility functions for the client
│   │   ├── logs
│   │   │   └── rtt_log.csv    # Logs of RTT measurements
│   │   └── requirements.txt    # Python dependencies for the client
│   └── android
│       ├── app
│       │   └── src
│       │       └── main
│       │           ├── java
│       │           │   └── com
│       │           │       └── udprtt
│       │           │           ├── MainActivity.java  # Main activity for the Android app
│       │           │           ├── UdpClient.java     # UDP client functionality
│       │           │           ├── PacketSender.java  # Manages sending of packet trains
│       │           │           └── RttLogger.java     # Handles logging of RTT measurements
│       │           └── res
│       │               └── layout
│       │                   └── activity_main.xml      # Layout for the main activity
│       ├── build.gradle        # Build configuration for the Android project
│       └── AndroidManifest.xml  # Application metadata and permissions
├── config
│   └── settings.json           # Configuration settings for server and client
└── README.md                   # Project documentation
```

## Setup Instructions

### Server

1. Navigate to the `server` directory.
2. Install the required Python packages using:
   ```
   pip install -r requirements.txt
   ```
3. Run the server:
   ```
   python src/server.py
   ```

### Client

#### Python Client

1. Navigate to the `client/python` directory.
2. Install the required Python packages using:
   ```
   pip install -r requirements.txt
   ```
3. Run the client:
   ```
   python src/client.py
   ```

#### Android Client

1. Open the Android project in Android Studio.
2. Sync the project with Gradle files.
3. Run the application on an Android device or emulator.

## Usage

- The server listens for incoming UDP packets and logs their arrival times.
- The client sends packet trains of size `U` every `G` milliseconds and records the arrival times to compute RTT.

## Logging

- Packet arrival times are logged in `server/logs/packet_log.csv` for the server and `client/python/logs/rtt_log.csv` for the client.

## License

This project is licensed under the MIT License. See the LICENSE file for more details.