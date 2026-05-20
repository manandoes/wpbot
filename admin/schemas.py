"""
admin/schemas.py
Pydantic models for admin API requests and responses.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel


class LoginRequest(BaseModel):
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class StatusBreakdown(BaseModel):
    not_contacted: int = 0
    first_message_sent: int = 0
    in_conversation: int = 0
    booked: int = 0
    not_interested: int = 0
    follow_up_sent: int = 0


class StatsResponse(BaseModel):
    total_contacts: int
    status_breakdown: StatusBreakdown
    conversion_rate: float
    total_conversations: int
    contacts_last_24h: int


class ContactItem(BaseModel):
    id: int
    name: Optional[str]
    phone_number: str
    status: str
    created_at: str
    last_contacted_at: str


class ContactsResponse(BaseModel):
    total: int
    page: int
    page_size: int
    contacts: List[ContactItem]


class MessageItem(BaseModel):
    id: int
    role: str
    message: str
    timestamp: str


class ConversationResponse(BaseModel):
    phone_number: str
    contact_name: Optional[str]
    contact_status: str
    messages: List[MessageItem]
