# WhatsApp Web Server

This directory contains the Node.js gateway server that interfaces with WhatsApp Web.

## What is this?

This Node.js server uses **whatsapp-web.js** to:
- Connect to WhatsApp Web in a headless browser (Puppeteer)
- Receive and parse incoming WhatsApp messages
- Forward messages to the Python FastAPI backend
- Send replies back via WhatsApp Web

## Quick Start

```bash
# 1. Install dependencies
npm install

# 2. Create .env (copy from .env.example)
cp .env.example .env

# 3. Start the server
npm start

# 4. Scan the QR code that appears in the terminal
# 5. Wait for: ✅ WhatsApp Web client is ready!
```

## API Endpoints

### Health Check
```
GET /health
→ Check if server is running
```

### Status
```
GET /status
→ Check if WhatsApp Web client is authenticated
```

### Send Message
```
POST /send
Body: {
  "phone_number": "919876543210",
  "message_text": "Hello!",
  "media_url": "https://..." (optional)
}
```

### QR Code
```
GET /qr
→ Get the QR code for authentication (if not authenticated yet)
```

### Webhook (from Python)
```
POST /webhook/from-python
→ Receive calls from Python backend (for testing)
```

## Configuration

Edit `.env` to change:
- `PYTHON_API_URL` - URL of the Python FastAPI backend (default: http://localhost:8000)
- `WHATSAPP_WEB_PORT` - Port to run on (default: 3000)
- `NODE_ENV` - Environment (development or production)

## Logs

Watch the terminal output for:
- 🔄 Initialization
- 📱 QR code for scanning
- ✅ Ready confirmation
- 📨 Incoming messages
- 📤 Outgoing messages

## Troubleshooting

**"Cannot find Chrome/Chromium"**
```bash
npm reinstall whatsapp-web.js
```

**"This session is already connected"**
```bash
# Kill all node processes
pkill -f node
# Delete session
rm -rf .wwebjs_auth/
```

**"WhatsApp Web Updated"** (message not received)
```bash
# Update whatsapp-web.js
npm update whatsapp-web.js
```

## Files

- `server.js` - Main server code
- `package.json` - Node.js dependencies
- `.env` - Configuration (create from .env.example)
- `.wwebjs_auth/` - Session folder (auto-created, git-ignored)

## Session Management

The server stores WhatsApp Web session data in `.wwebjs_auth/` directory:
- Auto-created on first run
- Persists across server restarts
- Delete to force re-authentication

## Performance

- **Memory:** ~100-200 MB (Puppeteer + browser)
- **CPU:** Low when idle, moderate during message processing
- **Startup time:** 5-10 seconds to fully initialize
- **Message latency:** 1-3 seconds per message

## Production Deployment

**Important:** WhatsApp Web requires a persistent browser, so:
- ❌ Won't work on Vercel/Netlify/serverless
- ✅ Works on VPS/EC2/DigitalOcean/Docker

### Docker

```bash
docker build -t wpbot-whatsapp-web .
docker run -p 3000:3000 -e PYTHON_API_URL=http://host.docker.internal:8000 wpbot-whatsapp-web
```

## Security Notes

⚠️ **Important:**
- Don't expose this server to the public internet without authentication
- The phone number used here will be the bot's sender
- Each account can only be logged in once
- WhatsApp may flag/ban accounts sending too many messages too fast

## Links

- Python Backend: See `../main_whatsapp_web.py`
- Full Documentation: See `../WHATSAPP_WEB_INTEGRATION.md`
- Quick Start Guide: See `../QUICKSTART_WHATSAPP_WEB.md`
