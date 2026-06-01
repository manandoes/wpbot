const express = require('express');
const bodyParser = require('body-parser');
const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const axios = require('axios');
const fs = require('fs');
const path = require('path');
require('dotenv').config();

const app = express();
app.use(bodyParser.json());

const PYTHON_API_URL = process.env.PYTHON_API_URL || 'http://localhost:8000';
const WEBHOOK_PATH = '/webhook/whatsapp-web';
const SERVER_PORT = process.env.WHATSAPP_WEB_PORT || 3000;
const SESSION_NAME = 'wpbot-session';

let clientReady = false;
let clientQRCode = null;
let client;

function createClient() {
  const c = new Client({
    authStrategy: new LocalAuth({ clientId: SESSION_NAME }),
    puppeteer: {
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
      headless: true,
    },
  });

  c.on('qr', (qr) => {
    console.log('\n📱 QR Code received. Scan with WhatsApp:');
    qrcode.generate(qr, { small: true });
    clientQRCode = qr;
  });

  c.on('ready', () => {
    console.log('✅ WhatsApp Web client is ready!');
    clientReady = true;
    clientQRCode = null;
  });

  c.on('auth_failure', (msg) => {
    console.error('❌ Authentication failed:', msg);
    clientReady = false;
  });

  c.on('disconnected', (reason) => {
    console.warn('⚠️  Client disconnected:', reason);
    clientReady = false;
  });

  c.on('message', async (message) => {
    try {
      console.log(`📨 Incoming message from ${message.from}: ${message.body}`);

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

      if (message.hasMedia) {
        try {
          const media = await message.downloadMedia();
          payload.has_media = true;
          payload.media_data = media.data;
          payload.media_mimetype = media.mimetype;
          payload.media_filename = media.filename || 'attachment';
          console.log(`📎 Media downloaded: ${media.mimetype}`);
        } catch (mediaErr) {
          console.error('⚠️  Failed to download media:', mediaErr.message);
        }
      }

      if (!payload.message_text && !payload.has_media) {
        console.log('⏭️  Skipping message with no text or media.');
        return;
      }

      console.log(`📤 Forwarding to Python API: ${PYTHON_API_URL}${WEBHOOK_PATH}`);

      try {
        await axios.post(`${PYTHON_API_URL}${WEBHOOK_PATH}`, payload, { timeout: 10000 });
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

  return c;
}

// ─────────────────────────────────────────────────────────────────────────
// API Endpoints
// ─────────────────────────────────────────────────────────────────────────

app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    service: 'whatsapp-web-gateway',
    client_ready: clientReady,
    timestamp: new Date().toISOString(),
  });
});

app.get('/status', (req, res) => {
  res.json({
    ready: clientReady,
    phone_number: clientReady ? client.info.pushname : null,
    qr_pending: clientQRCode ? true : false,
    timestamp: new Date().toISOString(),
  });
});

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

    const chatId = phone_number.includes('@') ? phone_number : `${phone_number}@c.us`;

    console.log(`📤 Sending message to ${phone_number}`);

    let result;
    if (media_url) {
      const media = await MessageMedia.fromUrl(media_url);
      result = await client.sendMessage(chatId, media, { caption: message_text });
    } else {
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
    res.status(500).json({ success: false, error: error.message });
  }
});

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

app.get('/qr', (req, res) => {
  if (!clientQRCode) {
    return res.status(400).json({
      success: false,
      error: 'No QR code pending. Client may already be authenticated.',
    });
  }
  res.json({ success: true, qr: clientQRCode });
});

app.post('/reconnect', async (req, res) => {
  console.log('🔄 Reconnect requested — destroying current client...');
  try {
    clientReady = false;
    clientQRCode = null;
    await client.destroy();
  } catch (e) {
    console.warn('⚠️  Error destroying client (may already be down):', e.message);
  }

  // Delete saved session so a fresh QR is generated
  const authDir = path.join(__dirname, '.wwebjs_auth');
  if (fs.existsSync(authDir)) {
    fs.rmSync(authDir, { recursive: true, force: true });
    console.log('🗑️  Cleared saved session.');
  }

  const cacheDir = path.join(__dirname, '.wwebjs_cache');
  if (fs.existsSync(cacheDir)) {
    fs.rmSync(cacheDir, { recursive: true, force: true });
    console.log('🗑️  Cleared session cache.');
  }

  console.log('🔄 Reinitializing WhatsApp client...');
  client = createClient();
  client.initialize();

  res.json({ success: true, message: 'Reconnecting. Scan the new QR code.' });
});

app.post('/webhook/from-python', (req, res) => {
  console.log('📨 Webhook from Python:', req.body);
  res.json({ status: 'received' });
});

// ─────────────────────────────────────────────────────────────────────────
// Server Startup
// ─────────────────────────────────────────────────────────────────────────

app.listen(SERVER_PORT, () => {
  console.log(`🚀 WhatsApp Web Gateway listening on port ${SERVER_PORT}`);
  console.log(`📡 Python API URL: ${PYTHON_API_URL}`);
  console.log(`🔗 Webhook path: ${WEBHOOK_PATH}`);
});

console.log('🔄 Initializing WhatsApp Web client...');
client = createClient();
client.initialize();

process.on('SIGINT', () => {
  console.log('\n🛑 Shutting down...');
  client.destroy();
  process.exit(0);
});
