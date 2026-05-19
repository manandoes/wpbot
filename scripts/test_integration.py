#!/usr/bin/env python3
"""
test_whatsapp_web_integration.py

Simple script to test the whatsapp-web.js integration.
Verifies both Node.js and Python servers are running and communicating.
"""

import requests
import time
import json
from typing import Dict, Any

# Configuration
PYTHON_API = "http://localhost:8000"
NODE_SERVER = "http://localhost:3000"

def print_header(title: str) -> None:
    """Print a formatted section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def test_python_health() -> bool:
    """Test Python API health."""
    print("[1/5] Testing Python API health...")
    try:
        response = requests.get(f"{PYTHON_API}/health", timeout=5)
        if response.status_code == 200:
            print("✅ Python API is running")
            print(f"   {response.json()}")
            return True
    except Exception as e:
        print(f"❌ Python API is not responding: {e}")
    return False

def test_node_health() -> bool:
    """Test Node.js server health."""
    print("\n[2/5] Testing Node.js server health...")
    try:
        response = requests.get(f"{NODE_SERVER}/health", timeout=5)
        if response.status_code == 200:
            print("✅ Node.js server is running")
            print(f"   {response.json()}")
            return True
    except Exception as e:
        print(f"❌ Node.js server is not responding: {e}")
    return False

def test_whatsapp_status() -> bool:
    """Check WhatsApp Web client status."""
    print("\n[3/5] Checking WhatsApp Web client status...")
    try:
        response = requests.get(f"{PYTHON_API}/whatsapp/status", timeout=5)
        if response.status_code == 200:
            status = response.json()
            print(f"✅ WhatsApp status retrieved:")
            print(f"   Ready: {status.get('ready')}")
            print(f"   Phone: {status.get('phone_number', 'N/A')}")
            print(f"   QR Pending: {status.get('qr_pending', False)}")
            
            if not status.get('ready'):
                print("\n⚠️  Client not ready! Instructions:")
                print("   1. Visit: http://localhost:3000/qr")
                print("   2. Scan the QR code with WhatsApp on your phone")
                print("   3. Wait 2-3 minutes for authentication")
                print("   4. Run this test again")
                return False
            return True
        else:
            print(f"❌ Unexpected response: {response.status_code}")
    except Exception as e:
        print(f"❌ Failed to check status: {e}")
    return False

def test_send_message(phone_number: str = None) -> bool:
    """Test sending a message."""
    print("\n[4/5] Testing message sending...")
    
    if not phone_number:
        print("⏭️  Skipping (no phone number provided)")
        print("   To test, run: python test_whatsapp_web_integration.py <phone_number>")
        return None
    
    try:
        payload = {
            "phone_number": phone_number,
            "message_text": "🤖 Test message from WhatsApp Web integration!",
        }
        
        print(f"   Sending to: {phone_number}")
        response = requests.post(f"{NODE_SERVER}/send", json=payload, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print(f"✅ Message sent successfully!")
                print(f"   Message ID: {data.get('message_id')}")
                return True
            else:
                print(f"❌ Send failed: {data.get('error')}")
                return False
        else:
            print(f"❌ Unexpected response: {response.status_code}")
            print(f"   {response.text}")
    except Exception as e:
        print(f"❌ Failed to send message: {e}")
    return False

def test_webhook_endpoint() -> bool:
    """Test webhook endpoint is ready."""
    print("\n[5/5] Checking webhook endpoint...")
    try:
        # Try to POST to the webhook (it should return 200 for test)
        payload = {
            "phone_number": "919876543210",
            "message_text": "Test webhook message",
            "timestamp": int(time.time()),
        }
        
        response = requests.post(
            f"{PYTHON_API}/webhook/whatsapp-web",
            json=payload,
            timeout=5,
        )
        
        if response.status_code == 200:
            print("✅ Webhook endpoint is ready")
            print(f"   {response.json()}")
            return True
        else:
            print(f"❌ Webhook returned: {response.status_code}")
    except Exception as e:
        print(f"❌ Webhook test failed: {e}")
    return False

def main():
    """Run all tests."""
    import sys
    
    print_header("WhatsApp Web Integration Test Suite")
    
    phone_number = sys.argv[1] if len(sys.argv) > 1 else None
    if phone_number:
        print(f"📱 Test phone number: {phone_number}")
    
    results = {
        "Python API": test_python_health(),
        "Node.js Server": test_node_health(),
        "WhatsApp Status": test_whatsapp_status(),
        "Send Message": test_send_message(phone_number),
        "Webhook": test_webhook_endpoint(),
    }
    
    print_header("Test Summary")
    
    for test_name, result in results.items():
        if result is None:
            status = "⏭️  SKIPPED"
        elif result:
            status = "✅ PASSED"
        else:
            status = "❌ FAILED"
        print(f"{status:12} - {test_name}")
    
    # Overall result
    passed = sum(1 for r in results.values() if r is True)
    total = len([r for r in results.values() if r is not None])
    
    print(f"\n{'='*60}")
    print(f"Result: {passed}/{total} tests passed")
    print(f"{'='*60}\n")
    
    if passed == total:
        print("🎉 All tests passed! Your integration is working correctly.")
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
    
    return 0 if passed == total else 1

if __name__ == "__main__":
    exit(main())
