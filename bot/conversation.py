"""
bot/conversation.py
Manages per-contact conversation state and orchestrates Gemini replies.
"""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from db import SessionLocal
from db.models import Contact, Conversation, Registration
from bot import gemini_agent
from bot import whatsapp_web as whatsapp

logger = logging.getLogger(__name__)

ADMIN_PHONE = "919528913869"

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
# Registration form (deterministic — no AI)
# ---------------------------------------------------------------------------

def _notify_admin(reg: Registration) -> None:
    """Send a text summary of the new registration to the admin number."""
    text = (
        f"🎉 New Masterclass Registration!\n\n"
        f"📱 Phone: +{reg.phone_number}\n"
        f"👤 Name: {reg.reg_name}\n"
        f"📧 Email: {reg.reg_email}"
    )
    whatsapp.send_message(ADMIN_PHONE, text)


def _handle_registration_step(
    db: Session,
    contact: Contact,
    reg: Registration,
    incoming_text: str,
    has_media: bool,
    media_data: str,
    media_mimetype: str,
) -> None:
    """
    Deterministic registration form.  Advances through stages:
      awaiting_name → awaiting_email → awaiting_payment → complete
    """
    phone_number = contact.phone_number

    if reg.reg_stage == "awaiting_name":
        if not incoming_text:
            whatsapp.send_message(phone_number, "Bhai naam toh bata! 😄 What's your full name?")
            return
        reg.reg_name = incoming_text.strip()
        reg.reg_stage = "awaiting_email"
        db.commit()
        whatsapp.send_message(phone_number, "Got it! 🙌 What's your email address?")

    elif reg.reg_stage == "awaiting_email":
        if not incoming_text:
            whatsapp.send_message(phone_number, "Email address please? 😊")
            return
        reg.reg_email = incoming_text.strip()
        reg.reg_stage = "awaiting_payment"
        db.commit()
        whatsapp.send_message(
            phone_number,
            "Perfect! Last step — please send a screenshot of your payment confirmation 📸",
        )

    elif reg.reg_stage == "awaiting_payment":
        if not has_media:
            whatsapp.send_message(
                phone_number,
                "I need the payment screenshot 📸 Please send the image (not text)!",
            )
            return
        # Forward details + screenshot to admin
        _notify_admin(reg)
        whatsapp.send_media_base64(
            ADMIN_PHONE,
            media_data,
            media_mimetype,
            caption=f"Payment screenshot from +{reg.phone_number} ({reg.reg_name})",
            filename="payment_screenshot.jpg",
        )
        # Complete registration
        reg.reg_stage = "complete"
        contact.status = "booked"
        contact.last_contacted_at = datetime.utcnow()
        db.commit()
        whatsapp.send_message(
            phone_number,
            "Thank you. We have received your payment screenshot and will verify it shortly. You will be added to the community once confirmed.",
        )
        logger.info("Registration complete for %s (%s, %s)", phone_number, reg.reg_name, reg.reg_email)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

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
    """
    db: Session = SessionLocal()
    try:
        # ── Contact record ─────────────────────────────────────────────────
        contact = _get_or_create_contact(db, phone_number)

        # ── Registration flow takes priority ──────────────────────────────
        reg = db.query(Registration).filter(Registration.phone_number == phone_number).first()
        if reg and reg.reg_stage != "complete":
            _handle_registration_step(db, contact, reg, incoming_text, has_media, media_data, media_mimetype)
            return

        # ── Normal AI conversation flow ────────────────────────────────────
        history = _load_history(db, phone_number)

        # Only save / reply if there's text (media without text during AI phase is ignored)
        if not incoming_text:
            return

        # ── Persist incoming message ───────────────────────────────────────
        _save_message(db, phone_number, role="user", message=incoming_text)

        # ── Generate Gemini reply ──────────────────────────────────────────
        reply = gemini_agent.get_reply(history, incoming_text, contact_status=contact.status)

        # ── Detect signals ─────────────────────────────────────────────────
        mark_not_interested = _DONE_SIGNAL in reply
        booking_confirmed = _BOOKING_SIGNAL in reply

        reply = reply.replace(_DONE_SIGNAL, "").replace(_BOOKING_SIGNAL, "").strip()

        # ── Persist bot reply ──────────────────────────────────────────────
        _save_message(db, phone_number, role="model", message=reply)

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
        if booking_confirmed:
            existing_reg = db.query(Registration).filter(Registration.phone_number == phone_number).first()
            if not existing_reg:
                new_reg = Registration(phone_number=phone_number, reg_stage="awaiting_name")
                db.add(new_reg)
                db.commit()
                whatsapp.send_message(
                    phone_number,
                    "Yayyy, welcome to the masterclass family! 🎉 "
                    "Quick thing — what's your full name? (Needed for the group invite)",
                )
                logger.info("Registration flow started for %s", phone_number)

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
