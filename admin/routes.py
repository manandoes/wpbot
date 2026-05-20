"""
admin/routes.py
Admin API endpoints — all protected by JWT except /admin/login.
"""

import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from db import SessionLocal
from db.models import Contact, Conversation
from bot.whatsapp_web import get_client_status, get_qr_code

from .auth import create_access_token, get_current_admin, verify_password
from .schemas import (
    LoginRequest,
    TokenResponse,
    StatsResponse,
    StatusBreakdown,
    ContactsResponse,
    ContactItem,
    ConversationResponse,
    MessageItem,
)

router = APIRouter(tags=["Admin"])

_ALL_STATUSES = [
    "not_contacted",
    "first_message_sent",
    "in_conversation",
    "booked",
    "not_interested",
    "follow_up_sent",
]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest):
    if not verify_password(body.password):
        raise HTTPException(status_code=401, detail="Incorrect password")
    return TokenResponse(access_token=create_access_token())


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@router.get("/stats", response_model=StatsResponse)
def get_stats(_: str = Depends(get_current_admin)):
    db = SessionLocal()
    try:
        total_contacts = db.query(Contact).count()

        breakdown_raw = {s: 0 for s in _ALL_STATUSES}
        for contact in db.query(Contact).all():
            if contact.status in breakdown_raw:
                breakdown_raw[contact.status] += 1

        booked = breakdown_raw.get("booked", 0)
        conversion_rate = round((booked / total_contacts * 100) if total_contacts else 0.0, 2)

        total_conversations = db.query(Conversation).count()

        cutoff = datetime.utcnow() - timedelta(hours=24)
        contacts_last_24h = (
            db.query(Contact).filter(Contact.last_contacted_at >= cutoff).count()
        )

        return StatsResponse(
            total_contacts=total_contacts,
            status_breakdown=StatusBreakdown(**breakdown_raw),
            conversion_rate=conversion_rate,
            total_conversations=total_conversations,
            contacts_last_24h=contacts_last_24h,
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------

@router.get("/contacts", response_model=ContactsResponse)
def list_contacts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    _: str = Depends(get_current_admin),
):
    db = SessionLocal()
    try:
        q = db.query(Contact)

        if search:
            like = f"%{search}%"
            q = q.filter(
                Contact.phone_number.ilike(like) | Contact.name.ilike(like)
            )

        if status and status in _ALL_STATUSES:
            q = q.filter(Contact.status == status)

        total = q.count()
        contacts = (
            q.order_by(Contact.last_contacted_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return ContactsResponse(
            total=total,
            page=page,
            page_size=page_size,
            contacts=[
                ContactItem(
                    id=c.id,
                    name=c.name,
                    phone_number=c.phone_number,
                    status=c.status,
                    created_at=c.created_at.isoformat(),
                    last_contacted_at=c.last_contacted_at.isoformat(),
                )
                for c in contacts
            ],
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------

@router.get("/contacts/{phone_number}/conversation", response_model=ConversationResponse)
def get_conversation(phone_number: str, _: str = Depends(get_current_admin)):
    db = SessionLocal()
    try:
        contact = db.query(Contact).filter(Contact.phone_number == phone_number).first()

        messages = (
            db.query(Conversation)
            .filter(Conversation.phone_number == phone_number)
            .order_by(Conversation.timestamp.asc())
            .all()
        )

        return ConversationResponse(
            phone_number=phone_number,
            contact_name=contact.name if contact else None,
            contact_status=contact.status if contact else "unknown",
            messages=[
                MessageItem(
                    id=m.id,
                    role=m.role,
                    message=m.message,
                    timestamp=m.timestamp.isoformat(),
                )
                for m in messages
            ],
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# WhatsApp status (proxied with auth)
# ---------------------------------------------------------------------------

@router.get("/whatsapp/status")
def admin_whatsapp_status(_: str = Depends(get_current_admin)):
    status = get_client_status()
    if not status.get("ready"):
        qr = get_qr_code()
        if qr:
            return {**status, "qr_available": True}
    return status


@router.get("/whatsapp/qr")
def admin_whatsapp_qr(_: str = Depends(get_current_admin)):
    qr = get_qr_code()
    if not qr:
        return JSONResponse(
            content={"success": False, "message": "No QR code pending."},
            status_code=400,
        )
    return {"success": True, "qr": qr}
