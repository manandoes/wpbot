#!/usr/bin/env python3
"""
scripts/fix_lid_contacts.py — repoint rows stored under a WhatsApp address.

Before the gateway normalised ids at the edge, an incoming message from a
contact in LID mode was filed under its raw address ("125782630351089@lid")
instead of their mobile number. Those rows are unreachable: nothing can be sent
to a LID that has been stored as a phone number.

This script finds every contact / conversation / registration that is keyed by
something other than a real mobile number, asks the running gateway what number
each one belongs to, and rewrites the rows — merging into the real contact when
one already exists. Rows the gateway cannot resolve are left untouched and
listed.

Two shapes of damage are detected: a raw address ("125782630351089@lid"), and
the bare digits of a LID ("125782630351089"), which a later bug wrote and which
no amount of looking can tell apart from a phone number — see _repair_plan.

Run from the project root, with the gateway up and logged in:
    python scripts/fix_lid_contacts.py
"""

import os
import re
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

from db import SessionLocal                                    # noqa: E402
from db.models import Contact, Conversation, Registration      # noqa: E402

load_dotenv()

GATEWAY_URL = os.getenv("WHATSAPP_WEB_SERVER_URL", "http://localhost:3000")
GATEWAY_TOKEN = os.getenv("GATEWAY_TOKEN", "")
DIGITS_ONLY = re.compile(r"^\d+$")
RESOLVE_BATCH = 50


def _all_ids(db) -> list:
    """Every distinct phone_number stored anywhere in the DB."""
    found = set()
    for model in (Contact, Conversation, Registration):
        for (value,) in db.query(model.phone_number).distinct():
            if value:
                found.add(value)
    return sorted(found)


def _resolve(ids: list) -> dict:
    """
    Ask the gateway for the mobile number behind each address.

    Sent in batches: an id WhatsApp has never seen costs a round trip to check,
    so one request for a whole contact list would outlive any sane timeout.
    """
    headers = {"Authorization": f"Bearer {GATEWAY_TOKEN}"} if GATEWAY_TOKEN else {}
    resolved = {}

    for start in range(0, len(ids), RESOLVE_BATCH):
        batch = ids[start:start + RESOLVE_BATCH]
        response = httpx.post(
            f"{GATEWAY_URL}/resolve", json={"ids": batch}, headers=headers, timeout=120.0
        )
        response.raise_for_status()
        resolved.update(response.json().get("resolved", {}))

    return resolved


def _repair_plan(db) -> tuple:
    """
    Map every mis-keyed phone_number to the mobile number it belongs to.

    Two shapes of damage, from two different bugs:

    * "125782630351089@lid" — the raw address, written before the gateway
      normalised ids at the edge. Obvious on sight.
    * "125782630351089" — the *digits* of a LID, written while the gateway
      trusted whatsapp-web.js's contact.number. Indistinguishable from a real
      number by inspection, so every bare-digit id is checked against WhatsApp
      too: asking about "<digits>@lid" comes back with a number only when those
      digits really are a LID.

    Returns (plan, unresolved) — {stored id: real number}, and the mis-keyed
    ids WhatsApp could not resolve.
    """
    stored = _all_ids(db)
    addresses = [v for v in stored if not DIGITS_ONLY.match(v)]
    digits = [v for v in stored if DIGITS_ONLY.match(v)]

    resolved = _resolve(addresses) if addresses else {}
    plan = {v: resolved[v] for v in addresses if resolved.get(v)}
    unresolved = [v for v in addresses if not resolved.get(v)]

    # A bare id WhatsApp recognises as a LID is one of the poisoned rows.
    if digits:
        probed = _resolve([f"{v}@lid" for v in digits])
        for value in digits:
            number = probed.get(f"{value}@lid")
            if number and number != value:
                plan[value] = number

    return plan, unresolved


def _repoint(db, old: str, new: str) -> None:
    """Move every row keyed by `old` onto `new`, merging duplicate contacts."""
    db.query(Conversation).filter(Conversation.phone_number == old).update(
        {"phone_number": new}
    )

    stale_contact = db.query(Contact).filter(Contact.phone_number == old).first()
    real_contact = db.query(Contact).filter(Contact.phone_number == new).first()
    if stale_contact and real_contact:
        # The number already has a contact row — keep it, and carry over the
        # name and the more recent activity from the address-keyed duplicate.
        if stale_contact.name and not real_contact.name:
            real_contact.name = stale_contact.name
        if stale_contact.last_contacted_at > real_contact.last_contacted_at:
            real_contact.last_contacted_at = stale_contact.last_contacted_at
            real_contact.status = stale_contact.status
        db.delete(stale_contact)
    elif stale_contact:
        stale_contact.phone_number = new

    stale_reg = db.query(Registration).filter(Registration.phone_number == old).first()
    real_reg = db.query(Registration).filter(Registration.phone_number == new).first()
    if stale_reg and real_reg:
        db.delete(stale_reg)     # a registration already exists for the number
    elif stale_reg:
        stale_reg.phone_number = new

    db.commit()


def main() -> None:
    db = SessionLocal()
    try:
        plan, unresolved = _repair_plan(db)

        if not plan and not unresolved:
            print("Nothing to fix — every row is already keyed by a mobile number.")
            return

        print(f"Found {len(plan) + len(unresolved)} mis-keyed id(s):")
        for value, number in sorted(plan.items()):
            print(f"  {value} → {number}")
        for value in unresolved:
            print(f"  {value} → UNKNOWN")

        if not plan:
            print("\nNone of them could be resolved — nothing to rewrite.")
            return

        if input("\nType YES to rewrite these rows: ").strip() != "YES":
            print("Aborted.")
            return

        for value, number in sorted(plan.items()):
            _repoint(db, value, number)
            print(f"  {value} → {number}  done")

        print(f"\nDone. {len(plan)} fixed, {len(unresolved)} left alone.")
        for value in unresolved:
            print(f"  still unresolved: {value}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
