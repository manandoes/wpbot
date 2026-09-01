"""
admin/routes.py
Admin API endpoints — all protected by JWT except /admin/login.
"""

import time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from db import SessionLocal
from db.models import Contact, Conversation, Registration
from bot.whatsapp_web import (
    get_client_status,
    get_qr_code,
    normalize_phone,
    reconnect_client,
    send_message,
)

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
    SendMessageRequest,
    BulkSendRequest,
    BulkSendResult,
    BulkSendResultItem,
    UpdateStatusRequest,
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


@router.post("/whatsapp/reconnect")
def admin_whatsapp_reconnect(_: str = Depends(get_current_admin)):
    return reconnect_client()


# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------

def _upsert_contact_and_save(db, phone_number: str, name: Optional[str], message: str):
    """Upsert contact, save outgoing message to conversations, update status."""
    contact = db.query(Contact).filter(Contact.phone_number == phone_number).first()
    now = datetime.utcnow()
    if contact is None:
        contact = Contact(
            phone_number=phone_number,
            name=name or None,
            status="first_message_sent",
            last_contacted_at=now,
        )
        db.add(contact)
    else:
        if name and not contact.name:
            contact.name = name
        if contact.status == "not_contacted":
            contact.status = "first_message_sent"
        contact.last_contacted_at = now

    conv = Conversation(
        phone_number=phone_number,
        role="model",
        message=message,
        timestamp=now,
    )
    db.add(conv)
    db.commit()


@router.post("/send-message")
def admin_send_message(body: SendMessageRequest, _: str = Depends(get_current_admin)):
    # Store the contact under the same number the gateway dials, so a typed
    # "+91 99975 89540" cannot become a second row alongside "919997589540".
    phone_number = normalize_phone(body.phone_number)
    if not phone_number:
        raise HTTPException(status_code=400, detail="Not a valid phone number")

    success = send_message(phone_number, body.message)
    if not success:
        raise HTTPException(status_code=502, detail="Failed to send message via WhatsApp")
    db = SessionLocal()
    try:
        _upsert_contact_and_save(db, phone_number, None, body.message)
    finally:
        db.close()
    return {"success": True, "phone_number": phone_number}


@router.post("/bulk-send", response_model=BulkSendResult)
def admin_bulk_send(body: BulkSendRequest, _: str = Depends(get_current_admin)):
    results = []
    sent = 0
    failed = 0
    for i, contact in enumerate(body.contacts):
        if i > 0:
            time.sleep(1.5)
        try:
            ok = send_message(contact.phone_number, body.message)
            if ok:
                db = SessionLocal()
                try:
                    _upsert_contact_and_save(db, contact.phone_number, contact.name, body.message)
                finally:
                    db.close()
                results.append(BulkSendResultItem(phone_number=contact.phone_number, success=True))
                sent += 1
            else:
                results.append(BulkSendResultItem(
                    phone_number=contact.phone_number, success=False, error="Send failed"
                ))
                failed += 1
        except Exception as e:
            results.append(BulkSendResultItem(
                phone_number=contact.phone_number, success=False, error=str(e)
            ))
            failed += 1
    return BulkSendResult(total=len(body.contacts), sent=sent, failed=failed, results=results)


@router.patch("/contacts/{phone_number}/status")
def admin_update_status(
    phone_number: str,
    body: UpdateStatusRequest,
    _: str = Depends(get_current_admin),
):
    db = SessionLocal()
    try:
        contact = db.query(Contact).filter(Contact.phone_number == phone_number).first()
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")
        contact.status = body.status
        contact.last_contacted_at = datetime.utcnow()
        db.commit()
        return {"success": True, "phone_number": phone_number, "status": body.status}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Reset all
# ---------------------------------------------------------------------------

@router.delete("/reset-all")
def admin_reset_all(_: str = Depends(get_current_admin)):
    """
    Delete all conversation history and registrations for every contact,
    and reset all contact statuses to 'not_contacted'.
    """
    db = SessionLocal()
    try:
        conversations_deleted = db.query(Conversation).delete()
        registrations_deleted = db.query(Registration).delete()
        contacts_reset = db.query(Contact).update({"status": "not_contacted"})
        db.commit()
        return {
            "success": True,
            "conversations_deleted": conversations_deleted,
            "registrations_deleted": registrations_deleted,
            "contacts_reset": contacts_reset,
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Reset failed: {exc}")
    finally:
        db.close()
