#!/usr/bin/env python3
"""
reset_all_contacts.py — Full database wipe for a fresh outreach run.

Deletes:
  - All rows in `conversations`
  - All rows in `registrations`
  - Resets every contact's status to 'not_contacted'

Run from the project root:
    python reset_all_contacts.py
"""

from db import SessionLocal
from db.models import Contact, Conversation, Registration


def reset():
    db = SessionLocal()
    try:
        conv_count = db.query(Conversation).count()
        reg_count = db.query(Registration).count()
        contact_count = db.query(Contact).count()

        print(f"About to wipe:")
        print(f"  conversations : {conv_count} rows")
        print(f"  registrations : {reg_count} rows")
        print(f"  contacts      : {contact_count} rows (status → not_contacted)")
        confirm = input("\nType YES to confirm: ").strip()
        if confirm != "YES":
            print("Aborted.")
            return

        db.query(Conversation).delete()
        db.query(Registration).delete()
        db.query(Contact).update({"status": "not_contacted"})
        db.commit()

        print("\nDone.")
        print(f"  Deleted {conv_count} conversation rows.")
        print(f"  Deleted {reg_count} registration rows.")
        print(f"  Reset {contact_count} contact statuses to not_contacted.")
    except Exception as exc:
        db.rollback()
        print(f"Error — rolled back: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    reset()
