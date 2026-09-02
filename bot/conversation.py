"""
bot/conversation.py
Manages per-contact conversation state and orchestrates Gemini replies.
"""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from db import SessionLocal
from db.models import Contact, Registration
from bot import gemini_agent
from bot import registration
from bot import whatsapp_web as whatsapp
from bot.history import load_history, save_message
from bot.locks import lock_for

logger = logging.getLogger(__name__)

ADMIN_PHONE = registration.ADMIN_PHONE

_DONE_SIGNAL = "[DONE]"
_BOOKING_SIGNAL = "[BOOKING_CONFIRMED]"


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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Replies are produced on FastAPI's background threadpool, so two messages from
# the same contact arriving together are handled concurrently: both would read
# the history before either saved its reply, and the contact would receive two
# overlapping answers at once. One lock per number serialises them, so the
# second message is answered in the light of the first exchange. The same lock
# is taken by the registration check-in job — see bot/locks.py.


def handle_message(
    phone_number: str,
    incoming_text: str,
    has_media: bool = False,
    media_data: str = "",
    media_mimetype: str = "",
) -> None:
    """
    Full pipeline for an incoming WhatsApp message.
    Routes to the registration form if a booking is in progress,
    otherwise runs the normal Gemini AI conversation.

    Serialised per contact — see bot/locks.py.
    """
    with lock_for(phone_number):
        _handle_message(phone_number, incoming_text, has_media, media_data, media_mimetype)


def _handle_message(
    phone_number: str,
    incoming_text: str,
    has_media: bool,
    media_data: str,
    media_mimetype: str,
) -> None:
    db: Session = SessionLocal()
    try:
        # ── Contact record ─────────────────────────────────────────────────
        contact = _get_or_create_contact(db, phone_number)

        # Read the transcript before the new message joins it — Gemini is given
        # the incoming text separately, so a history containing it too would
        # replay the turn twice.
        history = load_history(db, phone_number)

        if incoming_text:
            save_message(db, phone_number, role="user", message=incoming_text)

        # ── Registration flow takes priority ──────────────────────────────
        # It claims only the messages it can act on; a question asked while the
        # form is open falls through to the AI so the contact still gets an
        # answer, and the form picks up again on their next clear reply.
        reg = db.query(Registration).filter(Registration.phone_number == phone_number).first()
        if reg and registration.handle_message(
            db, contact, reg, incoming_text, has_media, media_data, media_mimetype
        ):
            return

        # ── Normal AI conversation flow ────────────────────────────────────
        # Media without text is ignored here — only the registration form has
        # anything to do with an image.
        if not incoming_text:
            return

        # ── Generate Gemini reply ──────────────────────────────────────────
        reply = gemini_agent.get_reply(history, incoming_text, contact_status=contact.status)

        # ── Detect signals ─────────────────────────────────────────────────
        mark_not_interested = _DONE_SIGNAL in reply
        booking_confirmed = _BOOKING_SIGNAL in reply

        reply = reply.replace(_DONE_SIGNAL, "").replace(_BOOKING_SIGNAL, "").strip()

        # ── Persist bot reply ──────────────────────────────────────────────
        save_message(db, phone_number, role="model", message=reply)

        # ── Update contact status ──────────────────────────────────────────
        if mark_not_interested:
            contact.status = "not_interested"
        elif contact.status in ("not_contacted", "first_message_sent", "follow_up_sent", "not_interested"):
            contact.status = "in_conversation"
        contact.last_contacted_at = datetime.utcnow()
        db.commit()

        logger.info(
            "Handled message from %s | status=%s | reply_len=%d",
            phone_number,
            contact.status,
            len(reply),
        )

        # ── Send reply ─────────────────────────────────────────────────────
        whatsapp.send_message(phone_number, reply)

        # ── Start registration flow if user just confirmed booking ─────────
        # registration.start() is a no-op when one is already open, so a second
        # [BOOKING_CONFIRMED] cannot restart the form or reset the check-in.
        if booking_confirmed:
            registration.start(db, contact)

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


def initiate_conversation(phone_number: str, name: str = "") -> bool:
    """
    Proactively initiate a conversation with a phone number.

    Sends the first outreach message, persists it to the DB, and updates
    the contact status so further replies are handled as part of the
    ongoing conversation.

    Returns True on successful send, False otherwise.
    """
    db: Session = SessionLocal()
    try:
        contact = _get_or_create_contact(db, phone_number)

        first_name = name.split()[0] if name else ""
        if first_name:
            message = (
                f"Hi {first_name}, Yogesh Vats here. "
                "Quick question — do you currently use JIRA in your work for tasks, sprints, or project tracking?"
            )
        else:
            message = (
                "Hi, Yogesh Vats here. "
                "Quick question — do you currently use JIRA in your work for tasks, sprints, or project tracking?"
            )

        sent = False
        try:
            sent = whatsapp.send_message(phone_number, message)
        except Exception as exc:
            logger.exception("Failed to send initial message to %s: %s", phone_number, exc)

        if sent:
            _save_message(db, phone_number, role="model", message=message)
            contact.status = "first_message_sent"
            contact.last_contacted_at = datetime.utcnow()
            db.commit()
            logger.info("Initiated conversation with %s", phone_number)
            return True
        else:
            logger.warning("Could not send initial message to %s", phone_number)
            return False

    except Exception as exc:
        logger.exception("Error initiating conversation for %s: %s", phone_number, exc)
        return False
    finally:
        db.close()
