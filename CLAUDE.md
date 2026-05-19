# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

WhatsApp Sales Bot — an outbound WhatsApp chatbot powered by **whatsapp-web.js** and **Google Gemini AI** (gemini-2.0-flash). It proactively reaches out to cold contacts, qualifies them, pitches the ₹99 *Jira with AI Masterclass* by Coach Yogesh Vats, handles objections, and drives bookings.

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

## Architecture

```
main.py               # FastAPI entry point, webhook receiver
├── bot/
│   ├── gemini_agent.py    # Google Gemini AI integration (Arya persona)
│   ├── whatsapp_web.py   # Communicates with Node.js whatsapp-web.js server
│   ├── conversation.py   # Manages conversation state, orchestrates replies
│   └── followup.py       # 24-hour follow-up scheduler
├── db/
│   ├── models.py          # SQLAlchemy: Contact, Conversation
│   └── __init__.py       # DB engine, session factory
└── outreach/
    └── bulk_sender.py    # Reads contacts.csv, sends initial messages
```

### Data Flow
1. Bulk outreach → `outreach/bulk_sender.py` sends first message → contact saved as "first_message_sent"
2. 24-hour follow-up → `bot/followup.py` sends follow-up if no reply
3. Incoming message → `POST /webhook/whatsapp-web` → `handle_message()` loads history → `gemini_agent.get_reply()` generates response → reply saved to DB and sent via WhatsApp

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
- [bot/whatsapp_web.py](bot/whatsapp_web.py) — `send_message()` sends via Node.js server, `parse_incoming()` parses webhooks
- [db/models.py](db/models.py) — `Contact` and `Conversation` SQLAlchemy models
- [whatsapp-web-server/](whatsapp-web-server/) — Node.js server running whatsapp-web.js (separate process)

## Notes

- The WhatsApp Web client runs as a separate Node.js process in `whatsapp-web-server/`
- Webhook must return 200 OK within 3 seconds — heavy work (Gemini call) is offloaded to FastAPI BackgroundTasks
- Follow-up scheduler uses APScheduler — will fail silently in serverless environments