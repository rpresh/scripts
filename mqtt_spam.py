# vibe coded somethign to spam numbers at a mqtt broker for a ctf


import subprocess
import time
import sys

# --- Configuration ---
BROKER = "mqtt.eclipseprojects.io"
TOPIC = "test/topic/numbers"
START = 0
END = 1800  # 180.0 * 10
DELAY = 0.1 # Seconds between messages

def main():
    print(f"Publishing via mosquitto_pub to {BROKER}...")

    # Loop from 0 to 1800 (integers) to avoid floating point errors
    for i in range(START, END + 1):
        # Convert to float (e.g. 15 -> 1.5)
        val = i / 10.0
        payload = str(val)

        # Construct the shell command
        # -h: host, -t: topic, -m: message
        cmd = [
            "mosquitto_pub",
            "-h", BROKER,
            "-t", TOPIC,
            "-m", payload
        ]

        try:
            # Run the command and wait for it to finish
            # capture_output=True keeps your console clean (optional)
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"Sent: {payload}")
            else:
                print(f"Error sending {payload}: {result.stderr}")

        except FileNotFoundError:
            print("Error: 'mosquitto_pub' not found. Please install mosquitto-clients.")
            sys.exit(1)
        
        time.sleep(DELAY)

    print("Done.")

if __name__ == "__main__":
    main()