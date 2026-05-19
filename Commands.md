# WhatsApp Bot — Terminal Command Reference

All commands assume both servers are running. Replace `919876543210` with a real number (country code + number, no `+`).

---

## 1. Start the Servers

**Node.js WhatsApp Web server** (terminal 1)
```bash
cd whatsapp-web-server && npm start
```

**Python FastAPI server** (terminal 2)
```bash
uvicorn main:app --reload --port 8000
```

---

## 2. Health & Status

**Check Python API health**
```bash
curl http://localhost:8000/health
```

**Check WhatsApp connection status** (shows phone number if connected)
```bash
curl http://localhost:8000/whatsapp/status
```

**Check Node.js server health**
```bash
curl http://localhost:3000/health
```

**Get QR code data** (if not yet authenticated)
```bash
curl http://localhost:3000/qr
```

---

## 3. Send a Single Message (no AI, direct send)

Sends a plain text message directly through the WhatsApp Web server, bypassing the AI agent.

```bash
curl -X POST http://localhost:3000/send \
  -H "Content-Type: application/json" \
  -d "{\"phone_number\": \"919876543210\", \"message_text\": \"Hello from the bot!\"}"
```

**PowerShell:**
```powershell
Invoke-WebRequest -Method POST http://localhost:3000/send `
  -ContentType "application/json" `
  -Body '{"phone_number": "919193477848", "message_text": "Hello from the Yogesh!"}'
```

**Send a message with an image:**
```bash
curl -X POST http://localhost:3000/send \
  -H "Content-Type: application/json" \
  -d "{\"phone_number\": \"919876543210\", \"message_text\": \"Check this out!\", \"media_url\": \"https://example.com/image.jpg\"}"
```

---

## 4. Bulk Outreach (send first message to all contacts in contacts.csv)

Reads `contacts.csv`, skips already-contacted numbers, and sends the opening message to everyone else. Runs in the background — check server logs for progress.

```bash
curl -X POST http://localhost:8000/outreach/start
```

**PowerShell:**
```powershell
Invoke-WebRequest -Method POST http://localhost:8000/outreach/start
```

**contacts.csv format required:**
```
phone_number,name
919876543210,Rahul
919123456789,Priya
```

---

## 5. Apply AI Agent to a Specific Contact

Simulates an incoming message from a contact, which triggers the full Gemini AI pipeline — loads conversation history, generates a reply, and sends it back to the contact.

```bash
curl -X POST http://localhost:8000/webhook/whatsapp-web \
  -H "Content-Type: application/json" \
  -d "{\"phone_number\": \"919876543210\", \"message_text\": \"Tell me more about the course\", \"contact_name\": \"Rahul\"}"
```

**PowerShell:**
```powershell
Invoke-WebRequest -Method POST http://localhost:8000/webhook/whatsapp-web `
  -ContentType "application/json" `
  -Body '{"phone_number": "919876543210", "message_text": "Tell me more about the course", "contact_name": "Rahul"}'
```

> The AI reply is sent automatically to `919876543210` via WhatsApp. The conversation is saved to the database.

---

## 6. Initiate AI Conversation with One Contact (no CSV needed)

To start the bot's outreach conversation with a single number, add it to a temporary one-row CSV and trigger outreach:

```bash
echo "phone_number,name" > contacts_single.csv
echo "919876543210,Rahul" >> contacts_single.csv
```

Then temporarily rename it and trigger:
```bash
# Back up current contacts.csv, run outreach with single contact
mv contacts.csv contacts_backup.csv
mv contacts_single.csv contacts.csv
curl -X POST http://localhost:8000/outreach/start
# Restore after a few seconds
mv contacts.csv contacts_single.csv
mv contacts_backup.csv contacts.csv
```

---

## 7. Reset WhatsApp Session (switch accounts)

1. Stop the Node.js server (Ctrl+C)
2. Delete saved session:
```powershell
Remove-Item -Recurse -Force "whatsapp-web-server\.wwebjs_auth"
Remove-Item -Recurse -Force "whatsapp-web-server\.wwebjs_cache"
```
3. Restart the server — scan the new QR code with the new account:
```bash
cd whatsapp-web-server && npm start
```

---

## 8. API Docs (Interactive UI)

Open in browser while the Python server is running:
```
http://localhost:8000/docs
```
