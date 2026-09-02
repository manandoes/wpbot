"""
bot/locks.py
Per-contact locks shared by every code path that can write to a contact.

Replies run on FastAPI's background threadpool and the registration follow-up
sweep runs on the scheduler thread, so the same contact can be touched from two
threads at once — an incoming "yes, I registered" landing while the 5-minute
check is mid-flight would otherwise advance the same registration twice. One
lock per number serialises them.

The registry lives here, rather than in conversation.py, so both conversation.py
and registration.py can use it without importing each other.
"""

import threading

_contact_locks: dict = {}
_locks_guard = threading.Lock()


def lock_for(phone_number: str) -> threading.Lock:
    """Return the lock for a phone number, creating it on first use."""
    with _locks_guard:
        return _contact_locks.setdefault(phone_number, threading.Lock())
