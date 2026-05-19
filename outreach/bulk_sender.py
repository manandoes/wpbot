"""
outreach/bulk_sender.py
Reads contacts from contacts.csv and sends the initial outreach message
to each one that hasn't been contacted yet.
"""

import logging
import os
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from db import SessionLocal
from db.models import Contact
from bot.conversation import initiate_conversation

logger = logging.getLogger(__name__)

# Path to contacts CSV (relative to project root)
CONTACTS_CSV = Path(__file__).parent.parent / "contacts.csv"

# Delay between messages to avoid WhatsApp spam detection
MESSAGE_DELAY_SECONDS = 2

FIRST_MESSAGE_TEMPLATE = (
    "Hey {name} 👋 I'm Arya! Quick question — do you work with Jira in your "
    "current role? I've got something that might save you a ton of time 😊"
)
FIRST_MESSAGE_NO_NAME = (
    "Hey there 👋 I'm Arya! Quick question — do you work with Jira in your "
    "current role? I've got something that might save you a ton of time 😊"
)


def run_bulk_outreach() -> dict:
    """
    Load contacts.csv, skip already-contacted numbers, and send the first
    outreach message to all new contacts.

    Returns:
        dict with keys: total, sent, skipped, failed
    """
    if not CONTACTS_CSV.exists():
        logger.error("contacts.csv not found at %s", CONTACTS_CSV)
        return {"error": f"contacts.csv not found at {CONTACTS_CSV}"}

    # ── Load CSV ───────────────────────────────────────────────────────────
    try:
        df = pd.read_csv(CONTACTS_CSV, dtype=str)
        df.columns = [c.strip().lower() for c in df.columns]
    except Exception as exc:
        logger.exception("Failed to read contacts.csv: %s", exc)
        return {"error": str(exc)}

    required_col = "phone_number"
    if required_col not in df.columns:
        logger.error("contacts.csv must contain a 'phone_number' column.")
        return {"error": "Missing 'phone_number' column in contacts.csv"}

    stats = {"total": len(df), "sent": 0, "skipped": 0, "failed": 0}

    db = SessionLocal()
    try:
        for _, row in df.iterrows():
            phone = str(row.get("phone_number", "")).strip().lstrip("+").replace(" ", "")
            name = str(row.get("name", "")).strip() if "name" in df.columns else ""

            if not phone:
                logger.warning("Empty phone number in CSV row — skipping.")
                stats["failed"] += 1
                continue

            # ── Skip if already contacted ──────────────────────────────────
            existing = (
                db.query(Contact).filter(Contact.phone_number == phone).first()
            )
            if existing and existing.status != "not_contacted":
                logger.info("Skipping already-contacted number: %s", phone)
                stats["skipped"] += 1
                continue

            # ── Build first message ────────────────────────────────────────
            first_name = name.split()[0] if name else ""
            if first_name:
                message = FIRST_MESSAGE_TEMPLATE.format(name=first_name)
            else:
                message = FIRST_MESSAGE_NO_NAME

            # ── Send message via conversation helper (persists history)
            sent = initiate_conversation(phone, name=name)

            if sent:
                stats["sent"] += 1
                logger.info("First message sent to %s (%s).", phone, name or "unknown")
            else:
                stats["failed"] += 1
                logger.warning("Failed to send first message to %s.", phone)

            # ── Throttle ───────────────────────────────────────────────────
            time.sleep(MESSAGE_DELAY_SECONDS)

    except Exception as exc:
        logger.exception("Unexpected error during bulk outreach: %s", exc)
    finally:
        db.close()

    logger.info(
        "Bulk outreach complete — total=%d sent=%d skipped=%d failed=%d",
        stats["total"],
        stats["sent"],
        stats["skipped"],
        stats["failed"],
    )
    return stats
