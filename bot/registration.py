"""
bot/registration.py
The post-confirmation registration flow — deterministic, no AI.

Once a contact says yes to the masterclass, the conversation stops being a
sales conversation and becomes a short form, so it is run by explicit rules
rather than by Gemini: the model must not improvise about money, links, or
whether someone has actually paid.

Flow:

    (contact confirms)  → thank-you + registration link          [link_sent]
    +5 minutes          → "did you register?"    [awaiting_registration_confirm]
    they say yes        → "send the screenshot"       [awaiting_screenshot]
    no screenshot       → name, then email    [awaiting_name → awaiting_email]
    collected           → forward to admin, chat done             [complete]

A screenshot is accepted at any point from link_sent onwards — people often
send it before being asked — and short-circuits straight to complete.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from db import SessionLocal
from db.models import Contact, Registration
from bot import whatsapp_web as whatsapp
from bot.history import save_message
from bot.locks import lock_for

logger = logging.getLogger(__name__)

ADMIN_PHONE = "919528913869"

# The link the Gemini prompts hand out. Kept identical to the one in
# gemini_agent.py's system prompts so the follow-ups never point somewhere else.
REGISTRATION_LINK = "https://coachyogeshvats.com/2-hours-live-masterclass/"

# How long to wait after sending the link before asking whether they registered.
FOLLOWUP_DELAY_MINUTES = 5

# A contact who keeps saying "not yet" is nudged this many times in total and
# then left alone — the bot goes back to answering normally instead of asking
# the same question forever.
MAX_FOLLOWUPS = 3

# ── Stages ─────────────────────────────────────────────────────────────────
STAGE_LINK_SENT = "link_sent"
STAGE_AWAITING_CONFIRM = "awaiting_registration_confirm"
STAGE_AWAITING_SCREENSHOT = "awaiting_screenshot"
STAGE_AWAITING_NAME = "awaiting_name"
STAGE_AWAITING_EMAIL = "awaiting_email"
STAGE_COMPLETE = "complete"

# Registrations created by the previous version of this flow sit in
# "awaiting_payment", which is what "awaiting_screenshot" is now called.
_LEGACY_STAGES = {"awaiting_payment": STAGE_AWAITING_SCREENSHOT}


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

THANK_YOU_TEMPLATE = (
    "Thank you so much! 🙏 Here's your registration link:\n"
    f"{REGISTRATION_LINK}\n\n"
    "It's just ₹99 — complete the payment and your seat is locked in. "
    "See you in the session! 🎉"
)

FOLLOWUP_TEMPLATE = "Hey! Just checking in — were you able to complete the registration? 😊"

NUDGE_TEMPLATE = (
    "No rush at all! Here's the link again whenever you're ready:\n"
    f"{REGISTRATION_LINK}"
)

ASK_SCREENSHOT_TEMPLATE = (
    "Awesome, welcome aboard! 🎉 Could you share a screenshot of the "
    "registration / payment confirmation so I can verify it?"
)

RE_ASK_SCREENSHOT_TEMPLATE = (
    "Please send the confirmation screenshot as an image 📸\n"
    'Don\'t have it? Just say "no screenshot" and I\'ll take your details instead.'
)

ASK_NAME_TEMPLATE = "No problem at all! 😊 What's the full name you registered with?"

ASK_EMAIL_TEMPLATE = "Got it! And the email ID you used to register?"

BAD_EMAIL_TEMPLATE = (
    "That doesn't look like an email address 😅 Could you send the email ID "
    "you registered with?"
)

DONE_TEMPLATE = (
    "Perfect, thank you! ✅ Your details are with our team — we'll verify the "
    "registration and send you the joining link before the session. See you there! 🙌"
)


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------

def _send(db: Session, phone_number: str, text: str) -> bool:
    """
    Message the contact and record it in the transcript.

    The form's questions belong in the same chat log as the AI's replies, so
    the dashboard shows one continuous conversation rather than going quiet the
    moment someone says yes. Admin hand-offs deliberately do not go through
    here — they are not part of the contact's chat.
    """
    save_message(db, phone_number, role="model", message=text)
    return whatsapp.send_message(phone_number, text)


# ---------------------------------------------------------------------------
# Intent matching
# ---------------------------------------------------------------------------

def _words(text: str) -> set:
    """Lowercased word set, punctuation stripped — for exact short-answer matches."""
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text.lower())
    return set(cleaned.split())


_YES_WORDS = {
    "yes", "yess", "yeah", "yep", "yup", "ya", "yaa", "yh", "y", "sure",
    "haan", "haa", "han", "ha", "hn", "ji", "bilkul", "done", "ok", "okay", "k",
}

_NO_WORDS = {
    "no", "nope", "nah", "na", "nahi", "nai", "nhi", "not", "later",
}

_YES_PHRASES = (
    "registered", "register kar", "registration done", "registration complete",
    "paid", "payment done", "payment ho", "payment complete", "kar liya",
    "kar diya", "ho gaya", "hogaya", "ho gya", "hogya", "done bhai", "all done",
    "i have registered", "just registered", "completed",
)

_NO_PHRASES = (
    "not yet", "nahi kiya", "nahi hua", "abhi nahi", "abhi tak nahi", "not done",
    "haven't", "havent", "have not", "will do", "karunga", "karti hu", "karta hu",
    "baad me", "baad mein", "not able", "couldn't", "couldnt", "failed",
)

_NO_SCREENSHOT_PHRASES = (
    "no screenshot", "no ss", "don't have", "dont have", "do not have",
    "nahi hai", "nhi hai", "not have", "deleted", "lost", "can't find",
    "cant find", "cannot find", "not available", "nahi mil", "no image",
    "no photo", "didn't take", "didnt take", "no proof",
)


def _contains(text: str, phrases: tuple) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in phrases)


def _is_affirmative(text: str) -> bool:
    """True for a plain yes — "yes", "haan", "done", "payment ho gaya"."""
    if not text:
        return False
    if _contains(text, _NO_PHRASES):      # "not done" also contains "done"
        return False
    return bool(_words(text) & _YES_WORDS) or _contains(text, _YES_PHRASES)


def _is_negative(text: str) -> bool:
    """True for a plain no — "no", "not yet", "abhi nahi"."""
    if not text:
        return False
    if _contains(text, _NO_PHRASES):
        return True
    return bool(_words(text) & _NO_WORDS)


def _says_registered(text: str) -> bool:
    """
    True only for an unprompted claim of having registered.

    Stricter than _is_affirmative: while the link is still fresh a bare "ok"
    means "ok, got the link", not "ok, I've paid", so it must not skip ahead to
    asking for a screenshot.
    """
    if not text or _contains(text, _NO_PHRASES):
        return False
    return _contains(text, _YES_PHRASES)


def _says_no_screenshot(text: str) -> bool:
    """True when they are telling us they cannot produce the screenshot."""
    if not text:
        return False
    return _contains(text, _NO_SCREENSHOT_PHRASES) or _is_negative(text)


# ---------------------------------------------------------------------------
# Admin hand-off
# ---------------------------------------------------------------------------

_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "application/pdf": "pdf",
}


def _notify_admin(reg: Registration, contact: Contact, proof: str) -> None:
    """Send the collected registration details to the admin number."""
    name = reg.reg_name or contact.name or "(not provided)"
    email = reg.reg_email or "(not provided)"
    text = (
        "🎉 New Masterclass Registration!\n\n"
        f"📱 Phone: +{reg.phone_number}\n"
        f"👤 Name: {name}\n"
        f"📧 Email: {email}\n"
        f"🧾 Proof: {proof}"
    )
    whatsapp.send_message(ADMIN_PHONE, text)


def _forward_screenshot(reg: Registration, media_data: str, media_mimetype: str) -> None:
    """Forward the confirmation image itself to the admin number."""
    extension = _EXTENSIONS.get((media_mimetype or "").lower(), "jpg")
    whatsapp.send_media_base64(
        ADMIN_PHONE,
        media_data,
        media_mimetype,
        caption=f"Registration confirmation from +{reg.phone_number}",
        filename=f"registration_confirmation.{extension}",
    )


def _complete(
    db: Session,
    contact: Contact,
    reg: Registration,
    proof: str,
    media_data: str = "",
    media_mimetype: str = "",
) -> None:
    """
    Close the registration: mark the chat done, forward everything to the admin,
    and thank the contact.

    The DB is committed before anything is sent, so a send that fails cannot
    leave the contact stuck in a stage that would re-ask for details they have
    already given.
    """
    reg.reg_stage = STAGE_COMPLETE
    reg.followup_due_at = None
    contact.status = "booked"
    contact.last_contacted_at = datetime.utcnow()
    db.commit()

    _notify_admin(reg, contact, proof)
    if media_data:
        _forward_screenshot(reg, media_data, media_mimetype)

    _send(db, reg.phone_number, DONE_TEMPLATE)
    logger.info(
        "Registration complete for %s (name=%s, email=%s, proof=%s) — chat marked done.",
        reg.phone_number, reg.reg_name, reg.reg_email, proof,
    )


# ---------------------------------------------------------------------------
# Starting the flow
# ---------------------------------------------------------------------------

def start(db: Session, contact: Contact) -> Registration:
    """
    Begin the registration flow for a contact who has just said yes.

    Sends the thank-you message with the link and arms the 5-minute check.
    Safe to call twice — an existing registration is returned untouched.
    """
    phone_number = contact.phone_number
    existing = db.query(Registration).filter(Registration.phone_number == phone_number).first()
    if existing:
        return existing

    reg = Registration(
        phone_number=phone_number,
        reg_stage=STAGE_LINK_SENT,
        followup_due_at=datetime.utcnow() + timedelta(minutes=FOLLOWUP_DELAY_MINUTES),
        followup_count=0,
    )
    db.add(reg)
    db.commit()

    _send(db, phone_number, THANK_YOU_TEMPLATE)
    logger.info(
        "Registration started for %s — check-in due in %d minutes.",
        phone_number, FOLLOWUP_DELAY_MINUTES,
    )
    return reg


def _arm_followup(db: Session, reg: Registration) -> None:
    """Schedule (or re-schedule) the check-in, unless we have nudged enough."""
    if (reg.followup_count or 0) >= MAX_FOLLOWUPS:
        reg.followup_due_at = None
        logger.info("Check-in cap reached for %s — no further nudges.", reg.phone_number)
    else:
        reg.followup_due_at = datetime.utcnow() + timedelta(minutes=FOLLOWUP_DELAY_MINUTES)
    db.commit()


# ---------------------------------------------------------------------------
# Incoming messages
# ---------------------------------------------------------------------------

def handle_message(
    db: Session,
    contact: Contact,
    reg: Registration,
    incoming_text: str,
    has_media: bool,
    media_data: str,
    media_mimetype: str,
) -> bool:
    """
    Advance the registration for one incoming message.

    Returns True when the message was consumed by the form, False when it
    should fall through to the normal Gemini conversation instead — a question
    while the link is still fresh, or an answer we could not read as yes or no.

    Called with the contact's lock already held.
    """
    stage = _LEGACY_STAGES.get(reg.reg_stage, reg.reg_stage)
    phone_number = contact.phone_number
    text = (incoming_text or "").strip()

    # A confirmation image is the whole point of the form — accept it in any
    # stage, however far along the questions have got.
    if has_media and media_data and stage != STAGE_COMPLETE:
        _complete(db, contact, reg, "screenshot", media_data, media_mimetype)
        return True

    if stage == STAGE_LINK_SENT:
        # The 5-minute check has not fired yet. Only an explicit "I've
        # registered" jumps the queue; anything else (questions, small talk)
        # goes to the AI so the contact still gets a real answer.
        if _says_registered(text):
            reg.reg_stage = STAGE_AWAITING_SCREENSHOT
            reg.followup_due_at = None
            db.commit()
            _send(db, phone_number, ASK_SCREENSHOT_TEMPLATE)
            return True
        return False

    if stage == STAGE_AWAITING_CONFIRM:
        if _is_affirmative(text):
            reg.reg_stage = STAGE_AWAITING_SCREENSHOT
            reg.followup_due_at = None
            db.commit()
            _send(db, phone_number, ASK_SCREENSHOT_TEMPLATE)
            return True

        if _is_negative(text):
            # Not yet — back to waiting, and check in once more later.
            reg.reg_stage = STAGE_LINK_SENT
            _arm_followup(db, reg)
            _send(db, phone_number, NUDGE_TEMPLATE)
            return True

        # Neither yes nor no — probably a question. Let the AI field it; the
        # stage stays put so the next clear answer still lands here.
        return False

    if stage == STAGE_AWAITING_SCREENSHOT:
        if _says_no_screenshot(text):
            reg.reg_stage = STAGE_AWAITING_NAME
            db.commit()
            _send(db, phone_number, ASK_NAME_TEMPLATE)
            return True

        _send(db, phone_number, RE_ASK_SCREENSHOT_TEMPLATE)
        return True

    if stage == STAGE_AWAITING_NAME:
        if not text:
            _send(db, phone_number, ASK_NAME_TEMPLATE)
            return True
        reg.reg_name = text
        reg.reg_stage = STAGE_AWAITING_EMAIL
        db.commit()
        _send(db, phone_number, ASK_EMAIL_TEMPLATE)
        return True

    if stage == STAGE_AWAITING_EMAIL:
        if "@" not in text:
            _send(db, phone_number, BAD_EMAIL_TEMPLATE)
            return True
        reg.reg_email = text
        db.commit()
        _complete(db, contact, reg, "name + email (no screenshot)")
        return True

    # STAGE_COMPLETE — the chat is done; the admin takes it from here.
    logger.info("Message from %s after registration completed — not replying.", phone_number)
    return True


# ---------------------------------------------------------------------------
# The 5-minute check-in (scheduler job)
# ---------------------------------------------------------------------------

def _claim(db: Session, reg: Registration) -> bool:
    """
    Move the registration to awaiting_registration_confirm *before* messaging,
    and report whether this runner is the one that got it.

    Same reasoning as the 24-hour follow-up claim: marking it only after a
    successful send leaves a window in which a second API process, or an
    overlapping run, sends the same check-in again.
    """
    claimed = (
        db.query(Registration)
        .filter(
            Registration.id == reg.id,
            Registration.reg_stage == STAGE_LINK_SENT,
            Registration.followup_due_at.isnot(None),
        )
        .update(
            {
                "reg_stage": STAGE_AWAITING_CONFIRM,
                "followup_due_at": None,
                "followup_count": Registration.followup_count + 1,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    return bool(claimed)


def send_due_followups() -> None:
    """
    Ask everyone whose 5 minutes are up whether they registered.

    Runs on the scheduler. The due time lives in the database rather than in an
    in-process timer, so a restart between sending the link and the check-in
    does not silently drop the follow-up.
    """
    now = datetime.utcnow()
    db: Session = SessionLocal()
    try:
        due = (
            db.query(Registration)
            .filter(
                Registration.reg_stage == STAGE_LINK_SENT,
                Registration.followup_due_at.isnot(None),
                Registration.followup_due_at <= now,
            )
            .all()
        )
        if not due:
            return

        logger.info("Registration check-in: %d due.", len(due))

        for reg in due:
            with lock_for(reg.phone_number):
                previous_due = reg.followup_due_at
                if not _claim(db, reg):
                    logger.info("Check-in for %s already claimed — skipping.", reg.phone_number)
                    continue

                if _send(db, reg.phone_number, FOLLOWUP_TEMPLATE):
                    logger.info("Registration check-in sent to %s.", reg.phone_number)
                else:
                    # Put it back so the next sweep retries.
                    db.query(Registration).filter(Registration.id == reg.id).update(
                        {
                            "reg_stage": STAGE_LINK_SENT,
                            "followup_due_at": previous_due,
                            "followup_count": Registration.followup_count - 1,
                        },
                        synchronize_session=False,
                    )
                    db.commit()
                    logger.warning("Failed registration check-in to %s.", reg.phone_number)

    except Exception as exc:
        logger.exception("Error in registration check-in job: %s", exc)
    finally:
        db.close()
