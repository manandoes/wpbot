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
// WHATSAPP_WEB_PORT is what docker-compose sets; PORT is honoured too so the
// container works unchanged behind a host that injects it.
const SERVER_PORT = process.env.PORT || process.env.WHATSAPP_WEB_PORT || 3000;
const SESSION_NAME = 'wpbot-session';

// Exact WhatsApp Web build served to the browser (see webVersionCache below).
// Overridable so a broken pin can be swapped without a code change; the value
// must name a file in wppconnect-team/wa-version's html/ directory.
const WEB_VERSION = process.env.WWEBJS_WEB_VERSION || '2.3000.1046540740-alpha';

// Where the WhatsApp login is persisted. Defaults to the project directory,
// which inside the container is /app — the path docker-compose mounts the
// whatsapp_session volume onto, so the session survives rebuilds.
//
// LocalAuth writes to `<dataPath>/session-<clientId>`, so AUTH_DIR must include
// the `.wwebjs_auth` segment to keep the on-disk layout identical to the
// default (and to whatever session is already stored locally).
const DATA_PATH = process.env.WWEBJS_DATA_PATH || __dirname;
const AUTH_DIR = path.join(DATA_PATH, '.wwebjs_auth');

// Shared secret required by the write endpoints. Defence in depth: these sit
// on the compose-internal network, but a published port or an opened VM
// firewall would otherwise expose an unauthenticated WhatsApp relay.
const GATEWAY_TOKEN = process.env.GATEWAY_TOKEN || '';

// docker-compose sets NODE_ENV=production for the deployed gateway; without it
// we assume a developer's laptop and allow a blank token.
const IS_PRODUCTION = process.env.NODE_ENV === 'production';

let clientReady = false;
let clientQRCode = null;
let client;

// -------------------------------------------------------------------------
// Inbound de-duplication
//
// WhatsApp Web re-delivers messages whenever the page reloads and re-syncs,
// and the 'message' event fires once per live client if a second one ever
// attaches to the same session. Forwarding the same message twice makes the
// bot answer it twice, so remember the ids already sent to Python. Ids are
// unique per message, and the set is bounded so a long-running gateway cannot
// grow it without limit.
// -------------------------------------------------------------------------

const SEEN_LIMIT = 5000;
const seenMessages = new Set();

function messageKey(message) {
  return (message.id && (message.id._serialized || message.id.id)) || '';
}

function alreadySeen(message) {
  const key = messageKey(message);
  if (!key) return false; // nothing to key on - let it through rather than drop it
  if (seenMessages.has(key)) return true;

  seenMessages.add(key);
  if (seenMessages.size > SEEN_LIMIT) {
    // Sets iterate in insertion order, so this evicts the oldest id.
    seenMessages.delete(seenMessages.values().next().value);
  }
  return false;
}

function createClient() {
  const c = new Client({
    authStrategy: new LocalAuth({ clientId: SESSION_NAME, dataPath: AUTH_DIR }),
    // Pin the WhatsApp Web build. With the default { type: 'local' } cache the
    // page loads whatever build WhatsApp is currently shipping, and when they
    // roll one out mid-load the page reloads while Client.inject() is still
    // evaluating — the execution context is destroyed under it and initialize()
    // rejects with a puppeteer ProtocolError. Serving one fixed build removes
    // that race. Bump WEB_VERSION when WhatsApp breaks compatibility.
    webVersionCache: {
      type: 'remote',
      remotePath: `https://raw.githubusercontent.com/wppconnect-team/wa-version/main/html/${WEB_VERSION}.html`,
    },
    puppeteer: {
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        // Containers get a tiny /dev/shm; without this Chrome crashes mid-session.
        '--disable-dev-shm-usage',
        '--disable-gpu',
        '--no-first-run',
        '--disable-extensions',
      ],
      headless: true,
      // The image installs system Chromium and points PUPPETEER_EXECUTABLE_PATH
      // at it; without that, puppeteer falls back to its own bundled download.
      ...(process.env.PUPPETEER_EXECUTABLE_PATH
        ? { executablePath: process.env.PUPPETEER_EXECUTABLE_PATH }
        : {}),
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
    watchPage(c);
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

      if (message.from.endsWith('@g.us')) {
        console.log('⏭️  Group message — ignoring.');
        return;
      }

      if (alreadySeen(message)) {
        console.log(`Duplicate delivery of ${messageKey(message)} - ignoring.`);
        return;
      }

      const contact = await message.getContact();
      const phoneNumber = await toPhoneNumber(message.from, contact);

      // Everything downstream keys on the mobile number, so a message whose
      // sender we cannot resolve is dropped rather than filed under an
      // unusable address.
      if (!phoneNumber) {
        console.error(`❌ Could not resolve ${message.from} to a mobile number — dropping message.`);
        return;
      }

      const contactName = contact.name || contact.pushname || phoneNumber;

      const payload = {
        phone_number: phoneNumber,
        message_text: message.body || '',
        timestamp: message.timestamp,
        contact_name: contactName,
        message_id: messageKey(message), // serialized id - Python de-duplicates on it
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
// Send resilience
//
// WhatsApp Web reloads its page periodically (and after a dropped socket). Any
// sendMessage() in flight during that reload dies with "Execution context was
// destroyed" / "Target closed". The page recovers on its own and the client
// re-emits 'ready', so the fix is to notice the reload, wait for the next
// 'ready', and retry the send instead of failing the request.
// ─────────────────────────────────────────────────────────────────────────

const READY_TIMEOUT_MS = 60000;
const SEND_ATTEMPTS = 3;

// How far back to look for an identical message when deciding whether a failed
// send actually went out. Comfortably longer than the retry backoff.
const DUPLICATE_WINDOW_SECONDS = 120;

// How long to let a send settle into the chat history before asking WhatsApp
// whether it actually landed.
const DELIVERY_SETTLE_MS = 1500;

const TRANSIENT_ERRORS = [
  'Execution context was destroyed',
  'Target closed',
  'Session closed',
  'Protocol error',
  'detached Frame',
];

function isTransient(error) {
  const msg = (error && error.message) || '';
  return TRANSIENT_ERRORS.some((pattern) => msg.includes(pattern));
}

// Flip clientReady off as soon as the page starts navigating, so a send issued
// mid-reload waits instead of throwing. whatsapp-web.js re-emits 'ready' once
// the page is usable again.
function watchPage(c) {
  const page = c.pupPage;
  if (!page || page.__wpbotWatched) return;
  page.__wpbotWatched = true;

  page.on('framenavigated', (frame) => {
    if (frame === page.mainFrame() && clientReady) {
      console.warn('⚠️  WhatsApp Web page reloaded — pausing sends until ready.');
      clientReady = false;
    }
  });
}

function waitForReady(timeoutMs = READY_TIMEOUT_MS) {
  if (clientReady) return Promise.resolve();

  console.log('⏳ Waiting for WhatsApp client to become ready...');
  const deadline = Date.now() + timeoutMs;

  return new Promise((resolve, reject) => {
    const check = () => {
      if (clientReady) return resolve();
      if (Date.now() > deadline) {
        return reject(new Error('CLIENT_NOT_READY: timed out waiting for WhatsApp client'));
      }
      setTimeout(check, 500);
    };
    check();
  });
}

function statusFor(error) {
  if (error.message.startsWith('CLIENT_NOT_READY')) return 503;
  if (error.message.startsWith('CHAT_UNRESOLVED')) return 422;
  return 500;
}

function errorTextFor(error) {
  if (error.message.startsWith('CLIENT_NOT_READY')) {
    return 'WhatsApp client not ready. Please scan QR code.';
  }
  return error.message;
}

// ─────────────────────────────────────────────────────────────────────────
// Address translation
//
// Outside this file a contact is *always* their bare mobile number — that is
// what the webhook payload carries, what the database keys on, and what /send
// expects. WhatsApp itself no longer works that way: a user has both a phone
// address ('<number>@c.us') and a LID ('<opaque>@lid'), incoming messages now
// arrive from the LID, and only one of the two has a real chat behind it. This
// section is the only place that knows about either form; it converts to a
// plain number on the way in and back to a chat address on the way out.
// ─────────────────────────────────────────────────────────────────────────

const phoneByAddress = new Map(); // '<lid>@lid' → '919876543210'
const lidByPhone = new Map();     // '919876543210' → '<lid>@lid'

function digitsOnly(value) {
  return String(value || '').replace(/\D/g, '');
}

function remember(lid, phone) {
  if (!lid || !phone) return;
  phoneByAddress.set(lid, phone);
  lidByPhone.set(phone, lid);
}

// Turn any WhatsApp address into a bare mobile number. Returns null when the
// number genuinely cannot be determined — callers must drop the message rather
// than fall back to a LID, because a LID stored as a phone number poisons the
// contact record and can never be dialled back.
async function toPhoneNumber(address, contact) {
  const raw = String(address || '').trim();
  if (!raw) return null;

  if (!raw.endsWith('@lid')) return digitsOnly(raw.split('@')[0]) || null;

  const cached = phoneByAddress.get(raw);
  if (cached) return cached;

  // contact.id is the authoritative field: whatsapp-web.js rewrites it to the
  // phone address whenever WhatsApp knows the number behind a LID. contact.number
  // is *not* rewritten - for a LID contact it holds the LID's own digits, which
  // are indistinguishable from a phone number once the '@lid' is stripped. That
  // is how cold inbound contacts ended up filed under unreachable 15-digit ids
  // and never got a reply, so read the id and refuse anything still a LID.
  const idAddress = String((contact && contact.id && contact.id._serialized) || '');
  if (idAddress && !idAddress.endsWith('@lid')) {
    const fromId = digitsOnly(idAddress.split('@')[0]);
    if (fromId) {
      remember(raw, fromId);
      return fromId;
    }
  }

  try {
    await waitForReady();
    const [mapping] = await client.getContactLidAndPhone([raw]);
    const phone = digitsOnly(mapping && mapping.pn);
    if (phone) {
      remember(raw, phone);
      return phone;
    }
  } catch (error) {
    console.warn(`⚠️  Could not resolve ${raw} to a number: ${error.message}`);
  }

  return null;
}

// The one address WhatsApp keys this contact's conversation under.
//
// A contact has two addresses - their phone ('<number>@c.us') and their LID
// ('<opaque>@lid') - but only ever one chat, which may be stored under either.
// Guessing wrong and falling through to the other address is what posted every
// message twice, so ask WhatsApp which chat it actually has and send there once.
// The LID never leaves this process.
async function chatAddressFor(phoneNumber) {
  const phone = digitsOnly(phoneNumber);
  if (!phone) throw new Error(`CHAT_UNRESOLVED: '${phoneNumber}' is not a phone number`);

  const primary = `${phone}@c.us`;

  const cached = lidByPhone.get(phone);
  if (cached) return cached;

  try {
    await waitForReady();
    const [mapping] = await client.getContactLidAndPhone([primary]);
    const lid = mapping && mapping.lid;
    if (lid) {
      // WhatsApp has a LID for this contact, which means the conversation is
      // filed under it - sending to the phone address resolves no chat at all.
      remember(lid, phone);
      return lid;
    }
  } catch (error) {
    console.warn(`⚠️  Could not look up the chat address for ${phone}: ${error.message}`);
  }

  // No LID: an ordinary contact whose chat is keyed by their number.
  return primary;
}

// Every address the same conversation may be filed under. Used only to check
// whether a message landed - never to send to more than one of them.
function knownAddresses(phoneNumber) {
  const phone = digitsOnly(phoneNumber);
  const addresses = [`${phone}@c.us`];
  const lid = lidByPhone.get(phone);
  if (lid) addresses.push(lid);
  return addresses;
}

// Whether an identical outgoing message is already sitting in a chat.
//
// Neither an empty send result nor a transient failure tells us whether the
// message left: whatsapp-web.js reads the sent message back out of WhatsApp's
// store by a key it builds itself, and comes up empty for a LID-addressed chat
// even though the send was accepted. So ask WhatsApp what is actually in the
// chat - a copy sitting there means resending would post it twice.
//
// This reads the message store directly rather than going through
// Client#getChatById, because building a Chat model throws on exactly the
// LID-addressed chats this check exists for.
async function findRecentlySent(chatId, content, options) {
  const body = typeof content === 'string' ? content : (options && options.caption) || '';
  if (!body) return null; // media with no caption - nothing to match on

  const cutoff = Math.floor(Date.now() / 1000) - DUPLICATE_WINDOW_SECONDS;

  try {
    return await client.pupPage.evaluate(
      (chatId, body, cutoff) => {
        const Msg = window.require('WAWebCollections').Msg;
        const all = Msg.getModelsArray ? Msg.getModelsArray() : Array.from(Msg.models || []);
        const hit = all.find(
          (m) =>
            m.id &&
            m.id.fromMe &&
            m.id.remote &&
            m.id.remote._serialized === chatId &&
            m.t >= cutoff &&
            m.body === body
        );
        // MsgKey exposes no _serialized on every build; toString() always
        // yields the serialized form.
        return hit ? { id: { _serialized: String(hit.id), id: hit.id.id } } : null;
      },
      chatId,
      body,
      cutoff
    );
  } catch (error) {
    console.warn(`⚠️  Could not check ${chatId} for an already-sent copy: ${error.message}`);
    return null;
  }
}

// Whether an identical message is already sitting in any of a contact's chats.
// The candidate addresses are two views of one conversation, so a copy under
// either of them means the send landed.
async function confirmDelivered(chatIds, content, options) {
  // A just-sent message takes a moment to show up in the chat's history.
  await new Promise((r) => setTimeout(r, DELIVERY_SETTLE_MS));

  for (const chatId of chatIds) {
    const found = await findRecentlySent(chatId, content, options);
    if (found) return found;
  }
  return null;
}

async function sendWithRetry(chatId, content, options) {
  let lastError;

  for (let attempt = 1; attempt <= SEND_ATTEMPTS; attempt++) {
    await waitForReady();

    if (attempt > 1) {
      const already = await findRecentlySent(chatId, content, options);
      if (already) {
        console.log(`Message already delivered to ${chatId} despite the error - not resending.`);
        return already;
      }
    }

    try {
      // May resolve with undefined, which is ambiguous: either no chat could be
      // opened and nothing was sent, or the send did go out and whatsapp-web.js
      // could not read the stored message back (it looks the sent message up by
      // a key it builds itself, which WhatsApp does not always file it under).
      // Only the caller can tell those apart, so hand the empty result up
      // instead of guessing here.
      return options
        ? await client.sendMessage(chatId, content, options)
        : await client.sendMessage(chatId, content);
    } catch (error) {
      lastError = error;
      if (!isTransient(error)) throw error;

      console.warn(
        `⚠️  Send failed (attempt ${attempt}/${SEND_ATTEMPTS}): ${error.message}`
      );
      // Give the page a beat to finish reloading before the next attempt.
      await new Promise((r) => setTimeout(r, 2000 * attempt));
    }
  }

  throw lastError;
}

// Send to a contact, identified by their mobile number.
//
// Exactly one send goes out. The old code tried the phone address and then fell
// through to the LID whenever the first send came back empty - but an empty
// result does not mean nothing was sent, so that fallthrough posted a second
// copy of a message the contact had already received. The chat is now resolved
// up front, and an empty result is checked against WhatsApp's own history
// rather than assumed to be a failure.
async function sendToContact(phoneNumber, content, options) {
  const phone = digitsOnly(phoneNumber);
  const chatId = await chatAddressFor(phoneNumber);

  console.log(`📤 Sending message to ${phone}`);

  const sent = await sendWithRetry(chatId, content, options);
  if (sent) return sent;

  const delivered = await confirmDelivered(knownAddresses(phone), content, options);
  if (delivered) {
    console.log(`Message to ${phone} landed despite an empty send result - not resending.`);
    return delivered;
  }

  // Report the failure against the number, never against an internal address.
  throw new Error(`CHAT_UNRESOLVED: WhatsApp could not open a chat for ${phone}`);
}

// ─────────────────────────────────────────────────────────────────────────
// API Endpoints
// ─────────────────────────────────────────────────────────────────────────

/**
 * Guards every endpoint that can send messages or touch the session.
 *
 * These sit on the compose-internal network, so this is defence in depth: it
 * keeps the gateway safe if the port is ever published or the VM firewall is
 * opened up by mistake.
 */
function requireToken(req, res, next) {
  if (!GATEWAY_TOKEN) {
    // Fail closed in production. Skipping the check because the operator
    // forgot to set the secret is exactly the mistake that turns this into an
    // open WhatsApp relay, so refuse to serve the endpoint instead.
    if (IS_PRODUCTION) {
      return res.status(503).json({
        success: false,
        error: 'Gateway misconfigured: GATEWAY_TOKEN is not set. Write endpoints are disabled.',
      });
    }
    return next(); // not configured — local dev
  }

  const header = req.get('authorization') || '';
  const presented = header.startsWith('Bearer ') ? header.slice(7) : req.get('x-gateway-token');
  if (presented !== GATEWAY_TOKEN) {
    return res.status(401).json({ success: false, error: 'Unauthorized' });
  }
  next();
}

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
    phone_number: clientReady && client.info ? client.info.pushname : null,
    qr_pending: clientQRCode ? true : false,
    timestamp: new Date().toISOString(),
  });
});

app.post('/send', requireToken, async (req, res) => {
  try {
    const { phone_number, message_text, media_url } = req.body;

    if (!phone_number || !message_text) {
      return res.status(400).json({
        success: false,
        error: 'phone_number and message_text are required',
      });
    }

    let result;
    if (media_url) {
      const media = await MessageMedia.fromUrl(media_url);
      result = await sendToContact(phone_number, media, { caption: message_text });
    } else {
      result = await sendToContact(phone_number, message_text);
    }

    const messageId = result.id._serialized || result.id.id;
    console.log(`✅ Message sent successfully. ID: ${messageId}`);

    res.json({
      success: true,
      message_id: messageId,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error('Error sending message:', error);
    res.status(statusFor(error)).json({ success: false, error: errorTextFor(error) });
  }
});

app.post('/send-base64-media', requireToken, async (req, res) => {
  try {
    const { phone_number, base64_data, mimetype, filename, caption } = req.body;

    if (!phone_number || !base64_data || !mimetype) {
      return res.status(400).json({
        success: false,
        error: 'phone_number, base64_data, and mimetype are required',
      });
    }

    const media = new MessageMedia(mimetype, base64_data, filename || 'attachment');
    const result = await sendToContact(phone_number, media, { caption: caption || '' });

    const messageId = result.id._serialized || result.id.id;
    console.log(`✅ Media sent. ID: ${messageId}`);
    res.json({ success: true, message_id: messageId, timestamp: new Date().toISOString() });
  } catch (error) {
    console.error('Error sending base64 media:', error);
    res.status(statusFor(error)).json({ success: false, error: errorTextFor(error) });
  }
});

/**
 * Translate WhatsApp addresses ('…@lid', '…@c.us') into mobile numbers.
 *
 * Only needed to repair rows written before the gateway normalised ids at the
 * edge — see scripts/fix_lid_contacts.py. Responds with { "<id>": "<number>" },
 * the number being null when WhatsApp cannot tell us.
 */
app.post('/resolve', requireToken, async (req, res) => {
  const ids = Array.isArray(req.body.ids) ? req.body.ids : [];
  if (!ids.length) {
    return res.status(400).json({ success: false, error: 'ids must be a non-empty array' });
  }

  try {
    const resolved = {};
    for (const id of ids) {
      resolved[id] = await toPhoneNumber(id, null);
    }
    res.json({ success: true, resolved });
  } catch (error) {
    console.error('Error resolving ids:', error);
    res.status(statusFor(error)).json({ success: false, error: errorTextFor(error) });
  }
});

app.get('/qr', requireToken, (req, res) => {
  if (!clientQRCode) {
    return res.status(400).json({
      success: false,
      error: 'No QR code pending. Client may already be authenticated.',
    });
  }
  res.json({ success: true, qr: clientQRCode });
});

app.post('/reconnect', requireToken, async (req, res) => {
  console.log('🔄 Reconnect requested — destroying current client...');
  try {
    clientReady = false;
    clientQRCode = null;
    await client.destroy();
  } catch (e) {
    console.warn('⚠️  Error destroying client (may already be down):', e.message);
  }

  // Delete saved session so a fresh QR is generated
  if (fs.existsSync(AUTH_DIR)) {
    fs.rmSync(AUTH_DIR, { recursive: true, force: true });
    console.log('🗑️  Cleared saved session.');
  }

  const cacheDir = path.join(__dirname, '.wwebjs_cache');
  if (fs.existsSync(cacheDir)) {
    fs.rmSync(cacheDir, { recursive: true, force: true });
    console.log('🗑️  Cleared session cache.');
  }

  console.log('🔄 Reinitializing WhatsApp client...');
  startClient();

  res.json({ success: true, message: 'Reconnecting. Scan the new QR code.' });
});

app.post('/webhook/from-python', requireToken, (req, res) => {
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

  if (GATEWAY_TOKEN) {
    console.log('🔐 Gateway token configured — write endpoints are protected.');
  } else if (IS_PRODUCTION) {
    console.error(
      '🚨 GATEWAY_TOKEN is NOT set in production. /send, /qr and /reconnect ' +
      'will return 503 until it is. Set it on this service to match the API.'
    );
  } else {
    console.warn('⚠️  GATEWAY_TOKEN not set — auth disabled (local dev only).');
  }
});

/**
 * Bring the client up, retrying transient browser-side failures.
 *
 * initialize() returns a promise, and an unhandled rejection is fatal on
 * modern Node — a ProtocolError from a page reload used to take the whole
 * gateway down with it, losing the HTTP server too. These failures are
 * usually transient, so back off and rebuild the client instead of exiting.
 */
// Only one client may be live at a time. Two clients on the same session each
// receive every incoming message, so the bot would reply to each message twice.
// A /reconnect while a retry chain is still backing off used to do exactly
// that, so every start claims a generation and stale chains bow out.
let clientGeneration = 0;
let retryTimer = null;

async function startClient(attempt = 1, generation = null) {
  if (generation === null) {
    // A fresh start (boot or /reconnect) supersedes any chain still retrying.
    generation = ++clientGeneration;
    if (retryTimer) {
      clearTimeout(retryTimer);
      retryTimer = null;
    }
  } else if (generation !== clientGeneration) {
    console.log('Superseded by a newer client - abandoning this retry chain.');
    return;
  }

  console.log(
    attempt === 1
      ? '🔄 Initializing WhatsApp Web client...'
      : `🔄 Reinitializing WhatsApp Web client (attempt ${attempt})...`
  );

  // Held locally as well as globally: a /reconnect during initialize() swaps
  // the global out from under us, and the cleanup below must tear down *this*
  // client rather than whichever one is current by then.
  const c = createClient();
  client = c;

  try {
    await c.initialize();
  } catch (err) {
    console.error(`❌ WhatsApp client failed to initialize: ${err?.message || err}`);

    // Drop the half-built browser so the retry starts from a clean profile
    // lock; destroy() itself throws if the process is already gone.
    try {
      await c.destroy();
    } catch (_) { /* already gone */ }

    // A /reconnect may have started a newer client while initialize() was
    // running; leave that one alone rather than racing it with a retry.
    if (generation !== clientGeneration) return;

    clientReady = false;

    const delayMs = Math.min(60000, 5000 * 2 ** (attempt - 1));
    console.log(`⏳ Retrying in ${Math.round(delayMs / 1000)}s...`);
    retryTimer = setTimeout(() => startClient(attempt + 1, generation), delayMs);
  }
}

startClient();

// A rejected promise that reaches the top level would otherwise exit the
// process and take the HTTP server with it. The gateway is more useful alive
// and reporting client_ready=false than gone.
process.on('unhandledRejection', (reason) => {
  console.error('⚠️  Unhandled rejection:', reason?.stack || reason);
});

process.on('SIGINT', () => {
  console.log('\n🛑 Shutting down...');
  client.destroy();
  process.exit(0);
});
