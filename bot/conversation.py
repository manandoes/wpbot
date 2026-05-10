"""
bot/conversation.py
Manages per-contact conversation state and orchestrates Gemini replies.
"""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from db import SessionLocal
from db.models import Contact, Conversation
from bot import gemini_agent
from bot import whatsapp

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_or_create_contact(db: Session, phone_number: str) -> Contact:
    """Return an existing Contact record or create a new one (status: not_contacted)."""
    contact = db.query(Contact).filter(Contact.phone_number == phone_number).first()
    if not contact:
        contact = Contact(phone_number=phone_number, status="not_contacted")
        db.add(contact)
        db.commit()
        db.refresh(contact)
        logger.info("New contact created: %s", phone_number)
    return contact


def _load_history(db: Session, phone_number: str) -> list:
    """Load all conversation rows for a phone number, ordered by timestamp."""
    rows = (
        db.query(Conversation)
        .filter(Conversation.phone_number == phone_number)
        .order_by(Conversation.timestamp.asc())
        .all()
    )
    return [{"role": row.role, "message": row.message} for row in rows]


def _save_message(db: Session, phone_number: str, role: str, message: str) -> None:
    """Persist a single message to the Conversation table."""
    entry = Conversation(
        phone_number=phone_number,
        role=role,
        message=message,
        timestamp=datetime.utcnow(),
    )
    db.add(entry)
    db.commit()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def handle_message(phone_number: str, incoming_text: str) -> None:
    """
    Full pipeline for an incoming WhatsApp message:
      1. Load conversation history
      2. Save the user's message
      3. Ask Gemini for a reply
      4. Save the bot's reply
      5. Update contact status
      6. Send the reply via WhatsApp

    This function is designed to run in a FastAPI BackgroundTask so the
    webhook endpoint can return 200 OK immediately.
    """
    db: Session = SessionLocal()
    try:
        # ── Contact record ─────────────────────────────────────────────────
        contact = _get_or_create_contact(db, phone_number)

        # ── Load existing history ──────────────────────────────────────────
        history = _load_history(db, phone_number)

        # ── Persist incoming message ───────────────────────────────────────
        _save_message(db, phone_number, role="user", message=incoming_text)

        # ── Generate Gemini reply ──────────────────────────────────────────
        reply = gemini_agent.get_reply(history, incoming_text)

        # ── Persist bot reply ──────────────────────────────────────────────
        _save_message(db, phone_number, role="model", message=reply)

        # ── Update contact status ──────────────────────────────────────────
        if contact.status in ("not_contacted", "first_message_sent", "follow_up_sent"):
            contact.status = "in_conversation"
        contact.last_contacted_at = datetime.utcnow()
        db.commit()

        logger.info(
            "Handled message from %s | status=%s | reply_len=%d",
            phone_number,
            contact.status,
            len(reply),
        )

        # ── Send reply via WhatsApp ────────────────────────────────────────
        whatsapp.send_message(phone_number, reply)

    except Exception as exc:
        logger.exception("Error in handle_message for %s: %s", phone_number, exc)
    finally:
        db.close()


def mark_booked(phone_number: str) -> None:
    """Utility to manually mark a contact as booked (e.g., via webhook from payment gateway)."""
    db: Session = SessionLocal()
    try:
        contact = db.query(Contact).filter(Contact.phone_number == phone_number).first()
        if contact:
            contact.status = "booked"
            contact.last_contacted_at = datetime.utcnow()
            db.commit()
            logger.info("Contact %s marked as booked.", phone_number)
    finally:
        db.close()


def mark_not_interested(phone_number: str) -> None:
    """Utility to manually mark a contact as not interested."""
    db: Session = SessionLocal()
    try:
        contact = db.query(Contact).filter(Contact.phone_number == phone_number).first()
        if contact:
            contact.status = "not_interested"
            contact.last_contacted_at = datetime.utcnow()
            db.commit()
            logger.info("Contact %s marked as not_interested.", phone_number)
    finally:
        db.close()
