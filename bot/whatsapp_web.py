"""
bot/whatsapp_web.py
Handles communication with the whatsapp-web.js Node.js server.

This replaces the Meta Cloud API integration with a local WhatsApp Web connection.
"""

import logging
import os
import re
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# WhatsApp Web server configuration
WHATSAPP_WEB_SERVER_URL = os.getenv("WHATSAPP_WEB_SERVER_URL", "http://localhost:3000")
TIMEOUT = 10.0

# Shared secret for the gateway's write endpoints. On Render the gateway is
# reachable over the public internet, so this is what stops anyone else from
# sending messages through it. Must match GATEWAY_TOKEN on the Node service.
GATEWAY_TOKEN = os.getenv("GATEWAY_TOKEN", "")

_auth_headers = {"Authorization": f"Bearer {GATEWAY_TOKEN}"} if GATEWAY_TOKEN else {}


def normalize_phone(value: str) -> str:
    """
    Reduce any identifier to the bare mobile number this project keys on.

    Contacts are identified by their number everywhere — the DB, the dashboard,
    the gateway's /send. WhatsApp's own address forms must never get that far:
    the digits of a "…@c.us" are the number, but a "…@lid" is opaque and can
    never be dialled, so it is rejected outright instead of being stripped to
    meaningless digits.

    Returns "" when the value cannot be used as a phone number.
    """
    raw = str(value or "").strip()
    if raw.endswith("@lid"):
        return ""
    return re.sub(r"\D", "", raw.split("@")[0])


# Persistent client — reuses TCP connections across calls
_http = httpx.Client(timeout=TIMEOUT, headers=_auth_headers)


# ---------------------------------------------------------------------------
# Client Status
# ---------------------------------------------------------------------------

def get_client_status() -> dict:
    """
    Get the status of the WhatsApp Web client.

    Returns:
        dict with keys: ready, phone_number, qr_pending
    """
    try:
        response = _http.get(f"{WHATSAPP_WEB_SERVER_URL}/status")
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        logger.error("Failed to get WhatsApp Web client status: %s", exc)
        return {
            "ready": False,
            "phone_number": None,
            "error": str(exc),
        }


def get_qr_code() -> Optional[str]:
    """
    Get the QR code for scanning if not authenticated.

    Returns:
        QR code string if pending, None otherwise.
    """
    try:
        response = _http.get(f"{WHATSAPP_WEB_SERVER_URL}/qr")
        if response.status_code == 200:
            data = response.json()
            return data.get("qr")
        return None
    except Exception as exc:
        logger.warning("Could not retrieve QR code: %s", exc)
        return None


def reconnect_client() -> dict:
    """
    Tell the Node.js server to destroy its current client, delete the saved
    session, and reinitialise so a fresh QR code is generated.
    """
    try:
        response = _http.post(f"{WHATSAPP_WEB_SERVER_URL}/reconnect", timeout=30.0)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        logger.error("Failed to reconnect WhatsApp client: %s", exc)
        return {"success": False, "message": str(exc)}


# ---------------------------------------------------------------------------
# Outbound — Send Messages
# ---------------------------------------------------------------------------

def send_media_base64(
    phone_number: str,
    base64_data: str,
    mimetype: str,
    caption: str = "",
    filename: str = "attachment",
) -> bool:
    """
    Send a WhatsApp message with base64-encoded media via the Node.js server.
    Used to forward payment screenshots to the admin number.
    """
    phone_number = normalize_phone(phone_number)
    if not phone_number:
        logger.error("Refusing to send media — not a usable phone number.")
        return False

    try:
        payload = {
            "phone_number": phone_number,
            "base64_data": base64_data,
            "mimetype": mimetype,
            "caption": caption,
            "filename": filename,
        }
        response = _http.post(f"{WHATSAPP_WEB_SERVER_URL}/send-base64-media", json=payload)
        response.raise_for_status()
        data = response.json()
        if data.get("success"):
            logger.info("Media sent to %s", phone_number)
            return True
        else:
            logger.error("Media send failed: %s", data.get("error"))
            return False
    except Exception as exc:
        logger.exception("Error sending media to %s: %s", phone_number, exc)
        return False


def send_message(phone_number: str, message_text: str, media_url: Optional[str] = None) -> bool:
    """
    Send a WhatsApp message via the whatsapp-web.js server.

    Args:
        phone_number: Recipient phone number (e.g., "919876543210").
        message_text: The text body to send.
        media_url: Optional URL to media file to attach.

    Returns:
        True on success, False on failure.
    """
    phone_number = normalize_phone(phone_number)
    if not phone_number:
        logger.error("Refusing to send message — not a usable phone number.")
        return False

    try:
        payload = {
            "phone_number": phone_number,
            "message_text": message_text,
        }

        if media_url:
            payload["media_url"] = media_url

        response = _http.post(f"{WHATSAPP_WEB_SERVER_URL}/send", json=payload)
        response.raise_for_status()
        data = response.json()

        if data.get("success"):
            logger.info(
                "Message sent to %s | message_id=%s",
                phone_number,
                data.get("message_id", "unknown"),
            )
            return True
        else:
            logger.error("Send failed: %s", data.get("error"))
            return False

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
    Parse an incoming WhatsApp Web webhook payload from the Node.js server.

    Accepts messages that have text, media, or both.
    Returns None only if phone_number is missing or both text and media are absent.
    """
    try:
        phone_number = normalize_phone(payload.get("phone_number", ""))
        message_text = payload.get("message_text", "").strip()
        timestamp = payload.get("timestamp")
        contact_name = payload.get("contact_name", "")
        has_media = bool(payload.get("has_media", False))
        media_data = payload.get("media_data", "")
        media_mimetype = payload.get("media_mimetype", "")
        media_filename = payload.get("media_filename", "attachment")

        if not phone_number:
            logger.warning(
                "Received message with no usable phone number (%r) — ignoring.",
                payload.get("phone_number", ""),
            )
            return None

        if not message_text and not has_media:
            logger.warning("Received message with no text or media — ignoring.")
            return None

        return {
            "phone_number": phone_number,
            "message_text": message_text,
            "timestamp": timestamp,
            "contact_name": contact_name,
            "has_media": has_media,
            "media_data": media_data,
            "media_mimetype": media_mimetype,
            "media_filename": media_filename,
        }

    except (KeyError, TypeError) as exc:
        logger.error("Failed to parse incoming WhatsApp payload: %s", exc)
        return None
