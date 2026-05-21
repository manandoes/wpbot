/**
 * WhatsApp Web Gateway Server
 * 
 * This Node.js server uses whatsapp-web.js to handle WhatsApp Web communication.
 * It exposes REST API endpoints for the Python FastAPI backend to:
 * - Send messages
 * - Receive webhook notifications for incoming messages
 * - Get client status
 */

const express = require('express');
const bodyParser = require('body-parser');
const fs = require('fs');
const path = require('path');
const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const axios = require('axios');
require('dotenv').config();

const app = express();
app.use(bodyParser.json());

// ─────────────────────────────────────────────────────────────────────────
// Configuration
// ─────────────────────────────────────────────────────────────────────────

const PYTHON_API_URL = process.env.PYTHON_API_URL || 'http://localhost:8000';
const WEBHOOK_PATH = '/webhook/whatsapp-web';
const SERVER_PORT = process.env.WHATSAPP_WEB_PORT || 3000;
const SESSION_NAME = 'wpbot-session';

// ─────────────────────────────────────────────────────────────────────────
// WhatsApp Client Setup
// ─────────────────────────────────────────────────────────────────────────

const client = new Client({
  authStrategy: new LocalAuth({ clientId: SESSION_NAME }),
  puppeteer: {
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
    headless: true,
  },
});

let clientReady = false;
let clientQRCode = null;

client.on('qr', (qr) => {
  console.log('\n📱 QR Code received. Scan with WhatsApp:');
  qrcode.generate(qr, { small: true });
  clientQRCode = qr;
});

client.on('ready', () => {
  console.log('✅ WhatsApp Web client is ready!');
  clientReady = true;
  clientQRCode = null;
});

client.on('auth_failure', (msg) => {
  console.error('❌ Authentication failed:', msg);
  clientReady = false;
});

client.on('disconnected', (reason) => {
  console.warn('⚠️  Client disconnected:', reason);
  clientReady = false;
});

client.on('message', async (message) => {
  try {
    console.log(`📨 Incoming message from ${message.from}: ${message.body}`);

    // Get contact info
    const contact = await message.getContact();
    const phoneNumber = message.from.replace('@c.us', '');
    const contactName = contact.name || contact.pushname || phoneNumber;

    const payload = {
      phone_number: phoneNumber,
      message_text: message.body || '',
      timestamp: message.timestamp,
      contact_name: contactName,
      message_id: message.id.id,
      has_media: false,
    };

    // Download media if present (e.g. payment screenshot)
    if (message.hasMedia) {
      try {
        const media = await message.downloadMedia();
        payload.has_media = true;
        payload.media_data = media.data;           // base64 string
        payload.media_mimetype = media.mimetype;
        payload.media_filename = media.filename || 'attachment';
        console.log(`📎 Media downloaded: ${media.mimetype}`);
      } catch (mediaErr) {
        console.error('⚠️  Failed to download media:', mediaErr.message);
      }
    }

    // Skip messages with no text and no media
    if (!payload.message_text && !payload.has_media) {
      console.log('⏭️  Skipping message with no text or media.');
      return;
    }

    console.log(`📤 Forwarding to Python API: ${PYTHON_API_URL}${WEBHOOK_PATH}`);

    try {
      await axios.post(`${PYTHON_API_URL}${WEBHOOK_PATH}`, payload, {
        timeout: 10000,
      });
      console.log('✅ Message forwarded successfully');
    } catch (error) {
      console.error(
        '❌ Failed to forward message to Python API:',
        error.response?.status,
        error.response?.data || error.message
      );
    }
  } catch (error) {
    console.error('Error processing incoming message:', error);
  }
});

// ─────────────────────────────────────────────────────────────────────────
// API Endpoints
// ─────────────────────────────────────────────────────────────────────────

/**
 * GET /health
 * Health check endpoint
 */
app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    service: 'whatsapp-web-gateway',
    client_ready: clientReady,
    timestamp: new Date().toISOString(),
  });
});

/**
 * GET /status
 * Get WhatsApp client status
 */
app.get('/status', (req, res) => {
  res.json({
    ready: clientReady,
    phone_number: clientReady ? client.info.pushname : null,
    qr_pending: clientQRCode ? true : false,
    timestamp: new Date().toISOString(),
  });
});

/**
 * POST /send
 * Send a WhatsApp message
 * 
 * Body: {
 *   "phone_number": "919876543210",
 *   "message_text": "Hello there!",
 *   "media_url": "https://..." (optional)
 * }
 */
app.post('/send', async (req, res) => {
  try {
    if (!clientReady) {
      return res.status(503).json({
        success: false,
        error: 'WhatsApp client not ready. Please scan QR code.',
      });
    }

    const { phone_number, message_text, media_url } = req.body;

    if (!phone_number || !message_text) {
      return res.status(400).json({
        success: false,
        error: 'phone_number and message_text are required',
      });
    }

    // Format phone number for WhatsApp (ensure it has @c.us suffix)
    const chatId = phone_number.includes('@') 
      ? phone_number 
      : `${phone_number}@c.us`;

    console.log(`📤 Sending message to ${phone_number}`);

    let result;
    if (media_url) {
      // Send message with media
      const media = await MessageMedia.fromUrl(media_url);
      result = await client.sendMessage(chatId, media, {
        caption: message_text,
      });
    } else {
      // Send text message
      result = await client.sendMessage(chatId, message_text);
    }

    console.log(`✅ Message sent successfully. ID: ${result.id.id}`);

    res.json({
      success: true,
      message_id: result.id.id,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error('Error sending message:', error);
    res.status(500).json({
      success: false,
      error: error.message,
    });
  }
});

/**
 * POST /webhook/from-python
 * Receive incoming messages from Python backend
 * (Useful for testing or forwarding between services)
 */
app.post('/webhook/from-python', (req, res) => {
  console.log('📨 Webhook from Python:', req.body);
  res.json({ status: 'received' });
});

/**
 * POST /send-base64-media
 * Send a WhatsApp message with base64-encoded media (e.g. forwarding a payment screenshot)
 *
 * Body: {
 *   "phone_number": "919876543210",
 *   "base64_data": "<base64 string>",
 *   "mimetype": "image/jpeg",
 *   "filename": "screenshot.jpg",   (optional)
 *   "caption": "Payment proof"      (optional)
 * }
 */
app.post('/send-base64-media', async (req, res) => {
  try {
    if (!clientReady) {
      return res.status(503).json({ success: false, error: 'WhatsApp client not ready.' });
    }

    const { phone_number, base64_data, mimetype, filename, caption } = req.body;

    if (!phone_number || !base64_data || !mimetype) {
      return res.status(400).json({
        success: false,
        error: 'phone_number, base64_data, and mimetype are required',
      });
    }

    const chatId = phone_number.includes('@') ? phone_number : `${phone_number}@c.us`;
    const media = new MessageMedia(mimetype, base64_data, filename || 'attachment');
    const result = await client.sendMessage(chatId, media, { caption: caption || '' });

    console.log(`✅ Media sent to ${phone_number}. ID: ${result.id.id}`);
    res.json({ success: true, message_id: result.id.id, timestamp: new Date().toISOString() });
  } catch (error) {
    console.error('Error sending base64 media:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

/**
 * GET /qr
 * Get QR code as text (for scanning)
 */
app.get('/qr', (req, res) => {
  if (!clientQRCode) {
    return res.status(400).json({
      success: false,
      error: 'No QR code pending. Client may already be authenticated.',
    });
  }
  res.json({
    success: true,
    qr: clientQRCode,
  });
});

/**
 * POST /restart-session
 * Wipe the saved session and reinitialise the client so a fresh QR is generated.
 */
app.post('/restart-session', async (req, res) => {
  console.log('🔄 restart-session requested — wiping session and reinitialising...');
  clientReady = false;
  clientQRCode = null;

  try {
    await client.destroy();
  } catch (e) {
    console.warn('Warning during client.destroy():', e.message);
  }

  const sessionPath = path.join(__dirname, '.wwebjs_auth', `session-${SESSION_NAME}`);
  if (fs.existsSync(sessionPath)) {
    fs.rmSync(sessionPath, { recursive: true, force: true });
    console.log('🗑️  Session data deleted:', sessionPath);
  }

  try {
    await client.initialize();
    console.log('🔄 Client reinitialised — QR will appear shortly');
    res.json({ success: true, message: 'Session wiped. Scan the new QR code.' });
  } catch (e) {
    console.error('Error reinitialising client:', e.message);
    res.status(500).json({ success: false, error: e.message });
  }
});

// ─────────────────────────────────────────────────────────────────────────
// Server Startup
// ─────────────────────────────────────────────────────────────────────────

app.listen(SERVER_PORT, () => {
  console.log(`🚀 WhatsApp Web Gateway listening on port ${SERVER_PORT}`);
  console.log(`📡 Python API URL: ${PYTHON_API_URL}`);
  console.log(`🔗 Webhook path: ${WEBHOOK_PATH}`);
});

// Initialize WhatsApp client
console.log('🔄 Initializing WhatsApp Web client...');
client.initialize();

// Graceful shutdown
process.on('SIGINT', () => {
  console.log('\n🛑 Shutting down...');
  client.destroy();
  process.exit(0);
});
