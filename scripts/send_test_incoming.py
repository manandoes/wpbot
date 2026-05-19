"""
send_test_incoming.py

Send a synthetic incoming WhatsApp message to the Python webhook
`/webhook/whatsapp-web` to test AI reply handling.

Usage:
  python send_test_incoming.py [phone_number] [message_text]

Defaults:
  phone_number: 919000000000
  message_text: "Hi, this is a test message"
"""

import sys
import time
import httpx

PYTHON_API = "http://localhost:8000"

def main():
    phone = sys.argv[1] if len(sys.argv) > 1 else "919000000000"
    text = sys.argv[2] if len(sys.argv) > 2 else "Hi, this is a test message"

    payload = {
        "phone_number": phone,
        "message_text": text,
        "timestamp": int(time.time()),
        "contact_name": "Test User",
        "message_id": "test-msg-1234",
    }

    url = f"{PYTHON_API}/webhook/whatsapp-web"
    print(f"Posting test message to {url} -> {phone}: {text}")

    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(url, json=payload)
            print("Response status:", r.status_code)
            try:
                print("Response body:", r.json())
            except Exception:
                print("Response text:", r.text)
    except Exception as exc:
        print("Error sending test webhook:", exc)
        return 1

    print("Done. Check Node.js and Python logs for processing and outgoing replies.")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
