"""
bot/whatsapp_web.py
Handles communication with the whatsapp-web.js Node.js server.

This replaces the Meta Cloud API integration with a local WhatsApp Web connection.
"""

import logging
import os
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# WhatsApp Web server configuration
WHATSAPP_WEB_SERVER_URL = os.getenv("WHATSAPP_WEB_SERVER_URL", "http://localhost:3000")
TIMEOUT = 10.0


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
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(f"{WHATSAPP_WEB_SERVER_URL}/status")
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        logger.error("Failed to get WhatsApp Web client status: %s", exc)
        return {
            "ready": False,
            "phone_number": None,
            "error": str(exc),
        }


def restart_session() -> dict:
    """
    Wipe the WhatsApp session on the Node.js server and force a fresh QR.
    """
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(f"{WHATSAPP_WEB_SERVER_URL}/restart-session")
            return response.json()
    except Exception as exc:
        logger.error("Failed to restart WhatsApp session: %s", exc)
        return {"success": False, "error": str(exc)}


def get_qr_code() -> Optional[str]:
    """
    Get the QR code for scanning if not authenticated.
    
    Returns:
        QR code string if pending, None otherwise.
    """
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(f"{WHATSAPP_WEB_SERVER_URL}/qr")
            if response.status_code == 200:
                data = response.json()
                return data.get("qr")
            return None
    except Exception as exc:
        logger.warning("Could not retrieve QR code: %s", exc)
        return None


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
    try:
        payload = {
            "phone_number": phone_number,
            "base64_data": base64_data,
            "mimetype": mimetype,
            "caption": caption,
            "filename": filename,
        }
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.post(
                f"{WHATSAPP_WEB_SERVER_URL}/send-base64-media",
                json=payload,
            )
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
    try:
        payload = {
            "phone_number": phone_number,
            "message_text": message_text,
        }
        
        if media_url:
            payload["media_url"] = media_url

        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.post(
                f"{WHATSAPP_WEB_SERVER_URL}/send",
                json=payload,
            )
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
        phone_number = payload.get("phone_number", "").strip()
        message_text = payload.get("message_text", "").strip()
        timestamp = payload.get("timestamp")
        contact_name = payload.get("contact_name", "")
        has_media = bool(payload.get("has_media", False))
        media_data = payload.get("media_data", "")
        media_mimetype = payload.get("media_mimetype", "")
        media_filename = payload.get("media_filename", "attachment")

        if not phone_number:
            logger.warning("Received message with missing phone number.")
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
