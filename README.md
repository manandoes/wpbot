# WhatsApp Sales Bot — Jira with AI Masterclass

An outbound WhatsApp chatbot powered by **whatsapp-web.js** (Node.js) and **Google Gemini AI (gemini-2.0-flash)**. It proactively reaches out to cold contacts, qualifies them, pitches the ₹99 *Jira with AI Masterclass* by Coach Yogesh Vats, handles objections, and drives bookings.

---

## Project Structure

```
wpbot/
├── main.py                        # FastAPI app, webhook receiver
├── bot/
│   ├── gemini_agent.py            # Gemini AI integration (Arya persona)
│   ├── whatsapp_web.py            # Communicates with Node.js whatsapp-web.js server
│   ├── conversation.py            # Conversation state management
│   ├── followup.py                # 24-hour follow-up scheduler
│   └── __init__.py
├── db/
│   ├── models.py                  # SQLAlchemy: Contact, Conversation, Registration
│   └── __init__.py                # DB engine, session factory
├── outreach/
│   ├── bulk_sender.py             # Reads contacts.csv, sends initial messages
│   └── __init__.py
├── fine_tune/                     # Gemini fine-tuning scripts and data
├── scripts/
│   ├── send_test_incoming.py      # Simulate an incoming webhook message
│   └── test_integration.py       # End-to-end integration health check
├── whatsapp-web-server/           # Node.js server running whatsapp-web.js
│   ├── server.js
│   └── package.json
├── src/trigger/                   # Trigger.dev task definitions
├── contacts.csv                   # Contact list (gitignored — never commit)
├── .env                           # API keys (gitignored — never commit)
├── .env.example                   # Template for environment variables
├── requirements.txt
├── vercel.json
└── trigger.config.ts
```

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL database
- Google Gemini API key

---

## Setup

### 1. Install Python dependencies

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Install Node.js dependencies

```bash
cd whatsapp-web-server
npm install
```

### 3. Configure environment variables

```bash
cp .env.example .env
# Fill in your values in .env
```

Required variables:

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `GEMINI_API_KEY` | Google Gemini API key |
| `WHATSAPP_WEB_SERVER_URL` | URL of the Node.js server (default: `http://localhost:3000`) |

### 4. Prepare contacts

Create `contacts.csv` (gitignored):

```csv
name,phone_number
Ravi Sharma,919876543210
Priya Mehta,919812345678
```

> Phone number format: country code + number, no `+` or spaces (e.g. `919876543210` for India).

---

## Running the Bot

Start both servers — they must run simultaneously:

**Terminal 1 — Node.js WhatsApp Web server:**
```bash
cd whatsapp-web-server && npm start
```

On first run, scan the QR code printed to console with WhatsApp on your phone.

**Terminal 2 — Python FastAPI server:**
```bash
uvicorn main:app --reload --port 8000
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/whatsapp/status` | WhatsApp Web client status |
| `GET` | `/whatsapp/qr` | Get QR code for authentication |
| `POST` | `/webhook/whatsapp-web` | Receive messages from Node.js server |
| `POST` | `/outreach/start` | Trigger bulk outreach from contacts.csv |
| `DELETE` | `/contact/{phone}/reset` | Reset a contact's conversation history |
| `GET` | `/docs` | Interactive API docs (Swagger UI) |

### Trigger bulk outreach

```bash
curl -X POST http://localhost:8000/outreach/start
```

---

## How It Works

```
contacts.csv → bulk_sender.py → sends first WhatsApp message → Contact: "first_message_sent"
                                                                        │
                                                               24 hours, no reply?
                                                                        │
                                                               followup.py sends follow-up
                                                                        │
Contact replies → Node.js webhook → POST /webhook/whatsapp-web → BackgroundTask
                                                                        │
                                                               handle_message() loads history
                                                                        │
                                                               Gemini (Arya persona) generates reply
                                                                        │
                                                               Reply saved to DB + sent via WhatsApp
```

### Contact Status Flow

```
not_contacted → first_message_sent → in_conversation → booked
                        ↓                    ↓
                 follow_up_sent        not_interested
```

---

## Development Scripts

```bash
# Simulate an incoming message (bot must be running)
python scripts/send_test_incoming.py 919876543210 "Hi, I'm interested"

# Run end-to-end integration health check
python scripts/test_integration.py
```

---

## Notes

- Webhook must return `200 OK` within 3 seconds — Gemini calls are offloaded to `BackgroundTasks`
- The follow-up scheduler uses APScheduler — it will skip gracefully in serverless environments
- `contacts.csv` is gitignored because it contains real phone numbers
