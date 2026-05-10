"""
main.py
FastAPI application — entry point for the WhatsApp sales bot.

Endpoints:
  GET  /webhook          → Meta webhook verification challenge
  POST /webhook          → Incoming WhatsApp messages
  POST /outreach/start   → Trigger bulk outreach from contacts.csv
  GET  /health           → Health check
"""

import logging
import os

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from dotenv import load_dotenv

from db import init_db
from bot.conversation import handle_message
from bot.whatsapp import parse_incoming
from bot.followup import start_scheduler, stop_scheduler
from outreach.bulk_sender import run_bulk_outreach

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

VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="WhatsApp Sales Bot — Jira with AI Masterclass",
    description=(
        "Outbound WhatsApp chatbot powered by Meta Cloud API + Google Gemini AI "
        "for promoting Coach Yogesh Vats' Jira with AI Masterclass."
    ),
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# Lifecycle events
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def on_startup() -> None:
    """Initialise the DB and start the follow-up scheduler on app start."""
    logger.info("Starting up WhatsApp Sales Bot…")
    init_db()
    start_scheduler()
    logger.info("Bot ready.")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    """Gracefully stop the scheduler on app shutdown."""
    stop_scheduler()
    logger.info("Bot shut down cleanly.")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Utility"])
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "service": "whatsapp-sales-bot"}


# ── Webhook verification (GET) ──────────────────────────────────────────────

@app.get("/webhook", tags=["WhatsApp"])
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """
    Meta webhook verification handshake.
    Meta sends: hub.mode=subscribe, hub.verify_token, hub.challenge
    We must return hub.challenge as plain text if the token matches.
    """
    logger.info("Webhook verification request received. mode=%s", hub_mode)

    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        logger.info("Webhook verified successfully.")
        return PlainTextResponse(content=hub_challenge, status_code=200)

    logger.warning(
        "Webhook verification failed. token_match=%s",
        hub_verify_token == VERIFY_TOKEN,
    )
    raise HTTPException(status_code=403, detail="Verification token mismatch.")


# ── Incoming messages (POST) ────────────────────────────────────────────────

@app.post("/webhook", tags=["WhatsApp"])
async def receive_message(request: Request, background_tasks: BackgroundTasks):
    """
    Receive incoming WhatsApp messages from Meta.

    IMPORTANT: Must return 200 OK within 3 seconds.
    All heavy work (Gemini call + reply) is offloaded to BackgroundTasks.
    """
    try:
        payload = await request.json()
    except Exception:
        logger.warning("Received non-JSON webhook payload — ignoring.")
        return JSONResponse(content={"status": "ignored"}, status_code=200)

    # ── Parse the incoming message ─────────────────────────────────────────
    parsed = parse_incoming(payload)

    if parsed is None:
        # Status updates, delivery receipts, unsupported types → ignore silently
        return JSONResponse(content={"status": "ignored"}, status_code=200)

    phone_number = parsed["phone_number"]
    message_text = parsed["message_text"]

    logger.info("Incoming message from %s: %.80s", phone_number, message_text)

    # ── Queue reply in background (keeps response time < 3s) ──────────────
    background_tasks.add_task(handle_message, phone_number, message_text)

    return JSONResponse(content={"status": "received"}, status_code=200)


# ── Outreach trigger ────────────────────────────────────────────────────────

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


def _run_outreach_background() -> None:
    """Wrapper so bulk outreach errors are caught and logged."""
    try:
        stats = run_bulk_outreach()
        logger.info("Outreach complete: %s", stats)
    except Exception as exc:
        logger.exception("Unhandled error in bulk outreach: %s", exc)
