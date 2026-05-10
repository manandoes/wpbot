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
from bot.whatsapp import send_message

logger = logging.getLogger(__name__)

FOLLOW_UP_DELAY_HOURS = 24
FOLLOW_UP_TEMPLATE = (
    "Hey {name} 👋 Just checking in — did you get a chance to look at the "
    "Jira + AI Masterclass? Seats are filling up fast and it's only ₹99 😊\n"
    "👉 https://rzp.io/rzp/2-hour-live-ai-masterclass"
)


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------

def send_followups() -> None:
    """
    Identify contacts who:
      - have status "first_message_sent"
      - were last contacted more than FOLLOW_UP_DELAY_HOURS hours ago

    Send ONE follow-up message and update their status to "follow_up_sent".
    Never follow up more than once.
    """
    cutoff = datetime.utcnow() - timedelta(hours=FOLLOW_UP_DELAY_HOURS)
    db = SessionLocal()
    try:
        pending = (
            db.query(Contact)
            .filter(
                Contact.status == "first_message_sent",
                Contact.last_contacted_at <= cutoff,
            )
            .all()
        )

        logger.info("Follow-up job: found %d contacts to follow up with.", len(pending))

        for contact in pending:
            name = contact.name.split()[0] if contact.name else "there"
            message = FOLLOW_UP_TEMPLATE.format(name=name)

            success = send_message(contact.phone_number, message)
            if success:
                contact.status = "follow_up_sent"
                contact.last_contacted_at = datetime.utcnow()
                db.commit()
                logger.info("Follow-up sent to %s.", contact.phone_number)
            else:
                logger.warning(
                    "Failed to send follow-up to %s — will retry next cycle.",
                    contact.phone_number,
                )

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
