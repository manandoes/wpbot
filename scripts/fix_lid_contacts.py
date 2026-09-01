#!/usr/bin/env python3
"""
scripts/fix_lid_contacts.py — repoint rows stored under a WhatsApp address.

Before the gateway normalised ids at the edge, an incoming message from a
contact in LID mode was filed under its raw address ("125782630351089@lid")
instead of their mobile number. Those rows are unreachable: nothing can be sent
to a LID that has been stored as a phone number.

This script finds every contact / conversation / registration whose
phone_number is not plain digits, asks the running gateway what number each one
belongs to, and rewrites the rows — merging into the real contact when one
already exists. Rows the gateway cannot resolve are left untouched and listed.

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


def _bad_ids(db) -> list:
    """Every distinct phone_number in the DB that isn't a bare number."""
    found = set()
    for model in (Contact, Conversation, Registration):
        for (value,) in db.query(model.phone_number).distinct():
            if value and not DIGITS_ONLY.match(value):
                found.add(value)
    return sorted(found)


def _resolve(ids: list) -> dict:
    """Ask the gateway for the mobile number behind each address."""
    headers = {"Authorization": f"Bearer {GATEWAY_TOKEN}"} if GATEWAY_TOKEN else {}
    response = httpx.post(
        f"{GATEWAY_URL}/resolve", json={"ids": ids}, headers=headers, timeout=60.0
    )
    response.raise_for_status()
    return response.json().get("resolved", {})


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
        bad = _bad_ids(db)
        if not bad:
            print("Nothing to fix — every row is already keyed by a mobile number.")
            return

        print(f"Found {len(bad)} address(es) stored as phone numbers:")
        for value in bad:
            print(f"  {value}")

        resolved = _resolve(bad)
        unresolved = [v for v in bad if not resolved.get(v)]

        print("\nResolved:")
        for value in bad:
            print(f"  {value} → {resolved.get(value) or 'UNKNOWN'}")

        if input("\nType YES to rewrite these rows: ").strip() != "YES":
            print("Aborted.")
            return

        for value in bad:
            number = resolved.get(value)
            if number:
                _repoint(db, value, number)
                print(f"  {value} → {number}  done")

        print(f"\nDone. {len(bad) - len(unresolved)} fixed, {len(unresolved)} left alone.")
        for value in unresolved:
            print(f"  still unresolved: {value}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
