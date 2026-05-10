"""
db/models.py
SQLAlchemy ORM models for the WhatsApp sales bot.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text
from db import Base


class Contact(Base):
    """
    Tracks every outbound contact and their current conversation state.

    Status flow:
        not_contacted → first_message_sent → in_conversation
                                           → follow_up_sent
                                           → booked
                                           → not_interested
    """

    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=True)
    phone_number = Column(String(20), unique=True, index=True, nullable=False)
    status = Column(String(50), default="not_contacted", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_contacted_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<Contact phone={self.phone_number} status={self.status}>"


class Conversation(Base):
    """
    Stores the full chat history for each contact.

    role is either "user" (incoming) or "model" (Gemini / bot outgoing).
    """

    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), index=True, nullable=False)
    role = Column(String(10), nullable=False)   # "user" | "model"
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<Conversation phone={self.phone_number} role={self.role}>"
