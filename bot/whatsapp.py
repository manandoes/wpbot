"""
bot/whatsapp.py
Handles all communication with the Meta WhatsApp Business Cloud API.
"""

import logging
import os
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
API_VERSION = "v18.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}/{PHONE_NUMBER_ID}/messages"


# ---------------------------------------------------------------------------
# Outbound
# ---------------------------------------------------------------------------

def send_message(phone_number: str, message_text: str) -> bool:
    """
    Send a plain-text WhatsApp message via the Meta Cloud API.

    Args:
        phone_number: Recipient phone number in E.164 format without '+' (e.g. "919876543210").
        message_text: The text body to send.

    Returns:
        True on success, False on failure.
    """
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        logger.error("WHATSAPP_TOKEN or WHATSAPP_PHONE_NUMBER_ID not set in .env")
        return False

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone_number,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": message_text,
        },
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(BASE_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            logger.info(
                "Message sent to %s | message_id=%s",
                phone_number,
                data.get("messages", [{}])[0].get("id", "unknown"),
            )
            return True

    except httpx.HTTPStatusError as exc:
        logger.error(
            "HTTP error sending message to %s: %s — %s",
            phone_number,
            exc.response.status_code,
            exc.response.text,
        )
    except httpx.RequestError as exc:
        logger.error("Network error sending message to %s: %s", phone_number, exc)
    except Exception as exc:
        logger.exception("Unexpected error sending message to %s: %s", phone_number, exc)

    return False


# ---------------------------------------------------------------------------
# Inbound — Webhook parsing
# ---------------------------------------------------------------------------

def parse_incoming(payload: dict) -> Optional[dict]:
    """
    Parse an incoming WhatsApp Cloud API webhook payload.

    Returns a dict with keys: phone_number, message_text, timestamp
    Returns None if the payload is a status update, delivery receipt,
    or any non-message event that should be silently ignored.
    """
    try:
        entry = payload.get("entry", [])
        if not entry:
            return None

        changes = entry[0].get("changes", [])
        if not changes:
            return None

        value = changes[0].get("value", {})

        # ── Ignore status updates (sent / delivered / read) ────────────────
        if "statuses" in value:
            logger.debug("Ignoring WhatsApp status update.")
            return None

        messages = value.get("messages", [])
        if not messages:
            return None

        msg = messages[0]

        # ── Only handle text messages ──────────────────────────────────────
        if msg.get("type") != "text":
            logger.debug("Ignoring non-text message of type: %s", msg.get("type"))
            return None

        phone_number = msg.get("from", "")
        message_text = msg.get("text", {}).get("body", "").strip()
        timestamp = msg.get("timestamp", "")

        if not phone_number or not message_text:
            logger.warning("Received message with missing phone or body.")
            return None

        return {
            "phone_number": phone_number,
            "message_text": message_text,
            "timestamp": timestamp,
        }

    except (KeyError, IndexError, TypeError) as exc:
        logger.error("Failed to parse incoming WhatsApp payload: %s", exc)
        return None
