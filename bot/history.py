"""
bot/history.py
Reading and writing the stored chat transcript.

Shared by the AI conversation and the registration form so that both halves of
a chat land in the same table — the admin dashboard reads this transcript, and
a registration whose questions and answers were missing from it would look like
the bot had gone silent.
"""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from db.models import Conversation

logger = logging.getLogger(__name__)

HISTORY_LIMIT = 20


def load_history(db: Session, phone_number: str) -> list:
    """
    Load the most recent conversation rows for a phone number, oldest first.

    Call this *before* persisting the message being handled — the incoming text
    is passed to Gemini separately, so having it in the history too would
    duplicate the turn.
    """
    rows = (
        db.query(Conversation)
        .filter(Conversation.phone_number == phone_number)
        .order_by(Conversation.timestamp.desc())
        .limit(HISTORY_LIMIT)
        .all()
    )
    rows.reverse()
    return [{"role": row.role, "message": row.message} for row in rows]


def save_message(db: Session, phone_number: str, role: str, message: str) -> None:
    """Persist a single message. role is "user" (incoming) or "model" (outgoing)."""
    db.add(
        Conversation(
            phone_number=phone_number,
            role=role,
            message=message,
            timestamp=datetime.utcnow(),
        )
    )
    db.commit()
