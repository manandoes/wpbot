"""
main.py - UPDATED FOR WHATSAPP-WEB.JS INTEGRATION
FastAPI application — entry point for the WhatsApp sales bot.

This version uses whatsapp-web.js (Node.js) instead of Meta Cloud API.

Endpoints:
  GET  /health                       → Health check
  GET  /whatsapp/status              → WhatsApp Web client status
  GET  /whatsapp/qr                  → Get QR code for authentication
  POST /webhook/whatsapp-web         → Receive messages from Node.js server
  POST /outreach/start               → Trigger bulk outreach from contacts.csv
  POST /send-message                 → Send a single WhatsApp message (API key protected)
"""

import logging
import os
import threading
from collections import OrderedDict

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from db import init_db, SessionLocal
from db.models import Contact, Conversation, Registration
from bot.conversation import handle_message
from bot.whatsapp_web import (
    parse_incoming,
    get_client_status,
    get_qr_code,
    normalize_phone,
    send_message,
)
from bot.followup import start_scheduler, stop_scheduler
from outreach.bulk_sender import run_bulk_outreach
from admin.routes import router as admin_router

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

load_dotenv()

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="WhatsApp Sales Bot — Jira with AI Masterclass (WhatsApp Web Edition)",
    description=(
        "Outbound WhatsApp chatbot powered by whatsapp-web.js + Google Gemini AI "
        "for promoting Coach Yogesh Vats' Jira with AI Masterclass."
    ),
    version="2.0.0",
)

_cors_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router, prefix="/admin")


# ---------------------------------------------------------------------------
# Lifecycle events
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def on_startup() -> None:
    """Initialise the DB and start the follow-up scheduler on app start."""
    logger.info("Starting up WhatsApp Sales Bot (WhatsApp Web Edition)…")
    init_db()
    try:
        start_scheduler()
    except Exception as e:
        # APScheduler cannot run in serverless environments — skip gracefully
        logger.warning("Scheduler skipped (serverless environment): %s", e)
    
    # Check WhatsApp Web client status
    status = get_client_status()
    if status.get("ready"):
        logger.info("✅ WhatsApp Web client is ready: %s", status.get("phone_number"))
    else:
        logger.warning("⚠️  WhatsApp Web client not ready. Please scan QR code.")
    
    logger.info("Bot ready.")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    """Gracefully stop the scheduler on app shutdown."""
    stop_scheduler()
    logger.info("Bot shut down cleanly.")


# ---------------------------------------------------------------------------
# Routes — Health & Status
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Utility"])
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "service": "whatsapp-sales-bot-web"}


@app.get("/whatsapp/status", tags=["WhatsApp"])
async def whatsapp_status():
    """Get WhatsApp Web client status."""
    status = get_client_status()
    
    if not status.get("ready"):
        qr = get_qr_code()
        if qr:
            logger.info("QR code available for scanning")
            return {
                **status,
                "message": "Please scan the QR code to authenticate",
                "qr_available": True,
            }
    
    return status


@app.get("/whatsapp/qr", tags=["WhatsApp"])
async def get_qr():
    """
    Get QR code for WhatsApp Web authentication.
    
    Use this endpoint to retrieve the QR code if authentication is pending.
    """
    qr = get_qr_code()
    
    if not qr:
        return JSONResponse(
            content={
                "success": False,
                "message": "No QR code pending. Client may already be authenticated.",
            },
            status_code=400,
        )
    
    return {
        "success": True,
        "qr": qr,
        "instructions": "Scan this QR code with WhatsApp to authenticate the bot.",
    }


# ---------------------------------------------------------------------------
# Routes — Webhooks
# ---------------------------------------------------------------------------

# The gateway drops repeat deliveries it can see, but a retried HTTP POST or a
# gateway restart mid-forward can still land the same message here twice — and
# each copy would produce its own Gemini reply. Message ids are unique per
# message, so remembering the ones already accepted makes the webhook
# idempotent. Bounded, and guarded because BackgroundTasks run on a threadpool.
_SEEN_MESSAGE_LIMIT = 5000
_seen_message_ids: "OrderedDict[str, None]" = OrderedDict()
_seen_lock = threading.Lock()


def _already_handled(message_id: str) -> bool:
    """True if this message id has been accepted before. Records it if not."""
    if not message_id:
        return False  # nothing to key on — better to answer than to drop

    with _seen_lock:
        if message_id in _seen_message_ids:
            return True
        _seen_message_ids[message_id] = None
        while len(_seen_message_ids) > _SEEN_MESSAGE_LIMIT:
            _seen_message_ids.popitem(last=False)
    return False


@app.post("/webhook/whatsapp-web", tags=["WhatsApp"])
async def receive_message_from_web(request: Request, background_tasks: BackgroundTasks):
    """
    Receive incoming WhatsApp messages from the Node.js whatsapp-web.js server.

    IMPORTANT: Must return 200 OK within 3 seconds.
    All heavy work (Gemini call + reply) is offloaded to BackgroundTasks.
    """
    try:
        payload = await request.json()
    except Exception as e:
        logger.warning("Received non-JSON webhook payload: %s", e)
        return JSONResponse(content={"status": "ignored"}, status_code=200)

    # ── Parse the incoming message ─────────────────────────────────────────
    parsed = parse_incoming(payload)

    if parsed is None:
        logger.debug("Ignoring unparseable message: %s", payload)
        return JSONResponse(content={"status": "ignored"}, status_code=200)

    if _already_handled(parsed["message_id"]):
        logger.info("Duplicate delivery of message %s — ignoring.", parsed["message_id"])
        return JSONResponse(content={"status": "duplicate"}, status_code=200)

    phone_number = parsed["phone_number"]
    message_text = parsed["message_text"]
    contact_name = parsed.get("contact_name", phone_number)
    has_media = parsed.get("has_media", False)
    media_data = parsed.get("media_data", "")
    media_mimetype = parsed.get("media_mimetype", "")

    logger.info(
        "Incoming message from %s (%s): %.80s%s",
        contact_name,
        phone_number,
        message_text,
        " [+media]" if has_media else "",
    )

    # ── Queue reply in background (keeps response time < 3s) ──────────────
    background_tasks.add_task(handle_message, phone_number, message_text, has_media, media_data, media_mimetype)

    return JSONResponse(content={"status": "received"}, status_code=200)


# ---------------------------------------------------------------------------
# Routes — Outreach
# ---------------------------------------------------------------------------

@app.post("/outreach/start", tags=["Outreach"])
async def start_outreach(background_tasks: BackgroundTasks):
    """
    Trigger bulk outreach from contacts.csv.

    Runs in a background task to avoid HTTP timeout for large contact lists.
    Returns immediately with a 202 Accepted response.
    """
    logger.info("Outreach trigger received — starting bulk sender in background.")
    background_tasks.add_task(_run_outreach_background)
    return JSONResponse(
        content={
            "status": "accepted",
            "message": "Bulk outreach started. Check server logs for progress.",
        },
        status_code=202,
    )


@app.delete("/contact/{phone_number}/reset", tags=["Utility"])
async def reset_contact(phone_number: str):
    """
    Delete all conversation history for a phone number and reset their status to not_contacted.

    This clears:
    - All messages in the conversations table
    - Any in-progress registration
    - Resets contact status to 'not_contacted'

    The bot will treat the user as a fresh contact on their next message.
    """
    db = SessionLocal()
    try:
        conversations_deleted = db.query(Conversation).filter(Conversation.phone_number == phone_number).delete()
        registrations_deleted = db.query(Registration).filter(Registration.phone_number == phone_number).delete()

        contact = db.query(Contact).filter(Contact.phone_number == phone_number).first()
        if contact:
            contact.status = "not_contacted"

        db.commit()
        logger.info("Reset contact %s: deleted %d messages, %d registrations", phone_number, conversations_deleted, registrations_deleted)

        return {
            "success": True,
            "phone_number": phone_number,
            "conversations_deleted": conversations_deleted,
            "registrations_deleted": registrations_deleted,
            "contact_status": "not_contacted" if contact else "not_found",
        }
    except Exception as exc:
        db.rollback()
        logger.exception("Error resetting contact %s: %s", phone_number, exc)
        raise HTTPException(status_code=500, detail=f"Failed to reset contact: {exc}")
    finally:
        db.close()


class SendMessageRequest(BaseModel):
    phone_number: str
    message: str
    api_key: str


@app.post("/send-message", tags=["Utility"])
async def send_single_message(body: SendMessageRequest):
    """
    Send a single WhatsApp message to a phone number.
    Requires api_key matching the SEND_MESSAGE_API_KEY environment variable.
    phone_number format: country code + number, e.g. "919876543210"
    """
    expected_key = os.getenv("SEND_MESSAGE_API_KEY", "")
    if not expected_key or body.api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    phone_number = normalize_phone(body.phone_number)
    if not phone_number:
        raise HTTPException(status_code=400, detail="Not a valid phone number")

    success = send_message(phone_number, body.message)
    if not success:
        raise HTTPException(status_code=502, detail="Failed to send message via WhatsApp")

    return {"success": True, "phone_number": phone_number}


def _run_outreach_background() -> None:
    """Wrapper so bulk outreach errors are caught and logged."""
    try:
        stats = run_bulk_outreach()
        logger.info("Outreach complete: %s", stats)
    except Exception as exc:
        logger.exception("Unhandled error in bulk outreach: %s", exc)
