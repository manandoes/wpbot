# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

WhatsApp Sales Bot — an outbound WhatsApp chatbot powered by **whatsapp-web.js** and **Google Gemini AI** (Gemini 3 Flash Live). It proactively reaches out to cold contacts, qualifies them, pitches the ₹99 *Jira with AI Masterclass* by Coach Yogesh Vats, handles objections, and drives bookings.

## Commands

### Run the bot
```bash
uvicorn main:app --reload --port 8000
```

### Start WhatsApp Web server (separate Node.js process)
```bash
cd whatsapp-web-server && npm start
```

### Trigger bulk outreach
```bash
curl -X POST http://localhost:8000/outreach/start
```

### Access API docs
Open `http://localhost:8000/docs` in browser

## Environment Variables

Required in `.env`:
- `DATABASE_URL` — PostgreSQL connection string (e.g., `postgresql://user:pass@host/db`)
- `GEMINI_API_KEY` — Google Gemini API key
- `WHATSAPP_WEB_SERVER_URL` — URL of Node.js whatsapp-web.js server (default: `http://localhost:3000`)
- `GATEWAY_TOKEN` — shared secret for the gateway's write endpoints; must match on both services. Blank is allowed locally; the gateway returns 503 on those endpoints when `NODE_ENV=production` and it is unset.
- `SEND_MESSAGE_API_KEY` — protects `POST /send-message`
- `WWEBJS_DATA_PATH` — directory for the WhatsApp session (blank = `whatsapp-web-server/`, which is the volume mount point in Docker)

## Architecture

```
main.py               # FastAPI entry point, webhook receiver
├── bot/
│   ├── gemini_agent.py    # Google Gemini AI integration (Arya persona)
│   ├── whatsapp_web.py   # Communicates with Node.js whatsapp-web.js server
│   ├── conversation.py   # Manages conversation state, orchestrates replies
│   ├── registration.py   # Post-confirmation registration form (no AI)
│   ├── followup.py       # Scheduler: 24-hour follow-ups + 5-minute check-ins
│   ├── history.py        # Shared read/write of the stored chat transcript
│   └── locks.py          # Per-contact locks shared by the reply and job paths
├── db/
│   ├── models.py          # SQLAlchemy: Contact, Registration, Conversation
│   └── __init__.py       # DB engine, session factory, column migrations
└── outreach/
    └── bulk_sender.py    # Reads contacts.csv, sends initial messages
```

### Data Flow
1. Bulk outreach → `outreach/bulk_sender.py` sends first message → contact saved as "first_message_sent"
2. 24-hour follow-up → `bot/followup.py` sends follow-up if no reply
3. Incoming message → `POST /webhook/whatsapp-web` → `handle_message()` loads history → `gemini_agent.get_reply()` generates response → reply saved to DB and sent via WhatsApp
4. Contact says yes → Gemini emits `[BOOKING_CONFIRMED]` → `bot/registration.py` takes over the chat

### Registration Flow (after the contact says yes)

Run by explicit rules in `bot/registration.py`, not by Gemini — the model must
not improvise about money, links, or whether someone has actually paid.

```
[BOOKING_CONFIRMED]  → thank-you + registration link            link_sent
+5 minutes           → "did you register?"   awaiting_registration_confirm
  ├─ yes             → "send the screenshot"        awaiting_screenshot
  │    ├─ screenshot → forward to admin, chat done          complete
  │    └─ no screenshot → name → email  awaiting_name → awaiting_email
  │                    → forward to admin, chat done         complete
  └─ not yet         → re-send link, check again in 5 min (max 3 nudges)
```

- A screenshot is accepted at any stage and completes the registration immediately.
- On completion the contact is marked `booked` and **the bot stops replying** — the details are forwarded to `ADMIN_PHONE` (919528913869) and a human takes over.
- A message the form cannot read as yes or no falls through to Gemini, so questions still get answered; the form resumes on the next clear reply.
- The 5-minute check-in is due-stamped in `registrations.followup_due_at` and swept every 30 s by the scheduler, so a restart between the link and the check-in does not drop it.

### Contact Status Flow
```
not_contacted → first_message_sent → in_conversation → booked
                                              ↓
                                    follow_up_sent
                                              ↓
                                    not_interested
```

## Key Files

- [bot/gemini_agent.py](bot/gemini_agent.py) — Contains the Arya persona system prompt in `SYSTEM_PROMPT` constant
- [bot/conversation.py](bot/conversation.py) — `handle_message()` is the main entry point for incoming messages
- [bot/registration.py](bot/registration.py) — the registration form: stages, message templates, the 5-minute check-in job, and `ADMIN_PHONE`
- [bot/whatsapp_web.py](bot/whatsapp_web.py) — `send_message()` sends via Node.js server, `parse_incoming()` parses webhooks
- [db/models.py](db/models.py) — `Contact`, `Registration` and `Conversation` SQLAlchemy models
- [whatsapp-web-server/](whatsapp-web-server/) — Node.js server running whatsapp-web.js (separate process)

## Notes

- The WhatsApp Web client runs as a separate Node.js process in `whatsapp-web-server/`
- Webhook must return 200 OK within 3 seconds — heavy work (Gemini call) is offloaded to FastAPI BackgroundTasks
- Both schedulers use APScheduler — they will fail silently in serverless environments
- `init_db()` runs `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` on startup: `create_all()` only creates missing tables, so a column added after the first deploy has to be listed in `_COLUMN_MIGRATIONS` in [db/__init__.py](db/__init__.py)
- Deployment is Docker Compose on a Google Cloud VM. `gcp-vm-setup.sh` provisions the VM from your laptop; `deploy.sh` runs on the VM to build and restart the stack. See [impcmds.md](impcmds.md) for day-to-day commands.
- The stack is three containers: `python-api`, `whatsapp-server`, and `nginx` (serves the built React dashboard and proxies the API on port 80). Postgres is managed externally (Supabase) via `DATABASE_URL`
- The WhatsApp gateway runs headless Chrome and needs ~2 GB RAM, which is why `gcp-vm-setup.sh` defaults to an `e2-standard-2` VM