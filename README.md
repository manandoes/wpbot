# WhatsApp Sales Bot — Jira with AI Masterclass 🚀

An outbound WhatsApp chatbot powered by **Meta WhatsApp Business Cloud API** and **Google Gemini AI (gemini-2.0-flash)** that proactively reaches out to cold contacts, qualifies them, pitches the ₹99 *Jira with AI Masterclass* by Coach Yogesh Vats, handles objections, and drives bookings.

---

## Project Structure

```
wpbot/
├── main.py                  # FastAPI app, webhook receiver
├── bot/
│   ├── __init__.py
│   ├── gemini_agent.py      # Gemini AI integration (Arya persona)
│   ├── whatsapp.py          # Meta Cloud API: send & parse messages
│   ├── conversation.py      # Conversation state management
│   └── followup.py          # 24-hour follow-up scheduler
├── db/
│   ├── __init__.py
│   └── models.py            # SQLAlchemy models: Contact, Conversation
├── outreach/
│   ├── __init__.py
│   └── bulk_sender.py       # Load contacts.csv and send first message
├── contacts.csv             # Your contact list: name, phone_number
├── .env                     # API keys (never commit this!)
├── requirements.txt
└── README.md
```

---

## Prerequisites

- Python 3.11+
- A **Meta WhatsApp Business** account with Cloud API access
- A **Google Gemini API key**
- A publicly accessible HTTPS URL for the webhook (use [ngrok](https://ngrok.com/) for local dev)

---

## Setup

### 1. Clone and install dependencies

```bash
cd wpbot
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure environment variables

Copy `.env` and fill in your credentials:

```bash
# .env
WHATSAPP_TOKEN=your_meta_whatsapp_api_token
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
WHATSAPP_VERIFY_TOKEN=any_secret_string_you_choose
GEMINI_API_KEY=your_google_gemini_api_key
DATABASE_URL=sqlite:///./bot.db
```

### 3. Get a Gemini API key

1. Visit [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. Sign in with your Google account
3. Click **Create API Key**
4. Copy and paste it into `.env` as `GEMINI_API_KEY`

### 4. Get Meta WhatsApp Business API credentials

1. Go to [developers.facebook.com](https://developers.facebook.com) and create a new App (Business type)
2. Add the **WhatsApp** product to your app
3. Under **WhatsApp → Getting Started**, find your:
   - **Temporary Access Token** → `WHATSAPP_TOKEN`
   - **Phone Number ID** → `WHATSAPP_PHONE_NUMBER_ID`
4. For production, generate a **Permanent System User Token** via Business Manager

### 5. Configure the webhook

1. Start the bot: `uvicorn main:app --reload --port 8000`
2. Expose it publicly with ngrok:
   ```bash
   ngrok http 8000
   ```
3. Copy the ngrok HTTPS URL (e.g., `https://abc123.ngrok.io`)
4. In your Meta App Dashboard → **WhatsApp → Configuration**:
   - **Callback URL**: `https://abc123.ngrok.io/webhook`
   - **Verify Token**: the value you set as `WHATSAPP_VERIFY_TOKEN` in `.env`
   - Subscribe to the **messages** webhook field
5. Click **Verify and Save** — Meta will call your `GET /webhook` endpoint

### 6. Prepare your contacts

Edit `contacts.csv`:

```csv
name,phone_number
Ravi Sharma,919876543210
Priya Mehta,919812345678
```

> **Phone number format**: country code + number, no `+` or spaces (e.g., `919876543210` for India).

### 7. Run the bot

```bash
uvicorn main:app --reload
```

### 8. Trigger bulk outreach

```bash
curl -X POST http://localhost:8000/outreach/start
```

Or open `http://localhost:8000/docs` and call `POST /outreach/start` from the Swagger UI.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/webhook` | Meta webhook verification challenge |
| `POST` | `/webhook` | Receive incoming WhatsApp messages |
| `POST` | `/outreach/start` | Trigger bulk outreach from CSV |
| `GET` | `/health` | Health check |
| `GET` | `/docs` | Interactive API docs (Swagger UI) |

---

## How It Works

```
Outreach CSV → bulk_sender.py → send first WhatsApp message → Contact saved as "first_message_sent"
                                                                      │
                                                              24 hours with no reply?
                                                                      │
                                                              followup.py sends ONE follow-up
                                                                      │
Contact replies → /webhook POST → parse_incoming() → BackgroundTask → conversation.py
                                                                            │
                                                               Load history from DB
                                                                            │
                                                               Gemini (Arya persona) generates reply
                                                                            │
                                                               Save to DB, update status
                                                                            │
                                                               send_message() → WhatsApp
```

## Contact Status Flow

```
not_contacted → first_message_sent → in_conversation → booked
                         ↓                                ↓
                  follow_up_sent                  not_interested
```

---

## Important Notes

- ⚠️ **WhatsApp policy**: First outbound messages to users who haven't messaged you must use Meta-approved **Message Templates**. Free-form text is only allowed within a 24-hour window after a user messages you. For cold outreach, submit a template to Meta for approval first.
- 🔑 **Never commit `.env`** — add it to `.gitignore`
- 📝 Logs are written to stdout — pipe to a file or use a log aggregator in production
- 🔄 The follow-up scheduler runs in-process. For production, consider Celery + Redis or a dedicated task queue.

---

## Environment Variables Reference

| Variable | Description |
|----------|-------------|
| `WHATSAPP_TOKEN` | Meta WhatsApp Cloud API bearer token |
| `WHATSAPP_PHONE_NUMBER_ID` | Your WhatsApp Business phone number ID |
| `WHATSAPP_VERIFY_TOKEN` | Custom secret string for webhook verification |
| `GEMINI_API_KEY` | Google Gemini API key from AI Studio |
| `DATABASE_URL` | SQLAlchemy DB URL (default: `sqlite:///./bot.db`) |
