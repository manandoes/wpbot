"""
bot/followup.py
APScheduler-based follow-up job — runs every 24 hours and sends a single
follow-up message to contacts who haven't replied within 24 hours.
"""

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from db import SessionLocal
from db.models import Contact
from bot.whatsapp_web import send_message

logger = logging.getLogger(__name__)

FOLLOW_UP_DELAY_HOURS = 24

# Sent to contacts who never replied to the first message
FOLLOW_UP_TEMPLATE = (
    "Hey {name} 👋 Just checking in — did you get a chance to look at the "
    "Jira + AI Masterclass? Seats are filling up fast and it's only ₹99 😊\n"
    "👉 https://rzp.io/rzp/2-hour-live-ai-masterclass"
)

# Sent the next day to contacts who said they weren't interested
RE_ENGAGE_TEMPLATE = (
    "Hey {name} 👋 No pressure at all! Just leaving this here in case — "
    "Jira with AI Masterclass, ₹99, super practical 2-hour live session. "
    "Whenever you feel like it: https://rzp.io/rzp/2-hour-live-ai-masterclass 😊"
)


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------

def send_followups() -> None:
    """
    Two follow-up passes per run:

    1. "No reply" pass — status first_message_sent, no reply for 24 h.
       Sends a reminder and moves status to follow_up_sent.

    2. "Not interested" pass — status not_interested, 24 h since last contact.
       Sends a soft re-engagement message and moves status to follow_up_sent
       so they are not messaged again unless they reply.
    """
    cutoff = datetime.utcnow() - timedelta(hours=FOLLOW_UP_DELAY_HOURS)
    db = SessionLocal()
    try:
        # ── Pass 1: no reply to first message ─────────────────────────────
        no_reply = (
            db.query(Contact)
            .filter(
                Contact.status == "first_message_sent",
                Contact.last_contacted_at <= cutoff,
            )
            .all()
        )
        logger.info("Follow-up job (no reply): %d contacts.", len(no_reply))

        for contact in no_reply:
            name = contact.name.split()[0] if contact.name else "there"
            success = send_message(contact.phone_number, FOLLOW_UP_TEMPLATE.format(name=name))
            if success:
                contact.status = "follow_up_sent"
                contact.last_contacted_at = datetime.utcnow()
                db.commit()
                logger.info("Follow-up (no reply) sent to %s.", contact.phone_number)
            else:
                logger.warning("Failed follow-up (no reply) to %s.", contact.phone_number)

        # ── Pass 2: said not interested — re-engage next day ──────────────
        not_interested = (
            db.query(Contact)
            .filter(
                Contact.status == "not_interested",
                Contact.last_contacted_at <= cutoff,
            )
            .all()
        )
        logger.info("Follow-up job (not interested): %d contacts.", len(not_interested))

        for contact in not_interested:
            name = contact.name.split()[0] if contact.name else "there"
            success = send_message(contact.phone_number, RE_ENGAGE_TEMPLATE.format(name=name))
            if success:
                contact.status = "follow_up_sent"
                contact.last_contacted_at = datetime.utcnow()
                db.commit()
                logger.info("Re-engage follow-up sent to %s.", contact.phone_number)
            else:
                logger.warning("Failed re-engage follow-up to %s.", contact.phone_number)

    except Exception as exc:
        logger.exception("Error in send_followups job: %s", exc)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Scheduler lifecycle
# ---------------------------------------------------------------------------

_scheduler = BackgroundScheduler()


def start_scheduler() -> None:
    """Start the APScheduler background scheduler."""
    _scheduler.add_job(
        func=send_followups,
        trigger=IntervalTrigger(hours=FOLLOW_UP_DELAY_HOURS),
        id="follow_up_job",
        name="Send 24-hour follow-ups",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        "Follow-up scheduler started — running every %d hours.", FOLLOW_UP_DELAY_HOURS
    )


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler (called on app shutdown)."""
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Follow-up scheduler stopped.")
