# Deploying wpbot on Render

Everything is described in [render.yaml](render.yaml). Render reads it as a
**Blueprint** and creates all three services plus the database in one go.

| Service | Type | What it runs |
|---|---|---|
| `wpbot-api` | Python web service | FastAPI (`main.py`) |
| `wpbot-whatsapp` | Node web service | whatsapp-web.js gateway + headless Chrome |
| `wpbot-dashboard` | Static site | React admin dashboard |
| `wpbot-db` | PostgreSQL | Contacts, conversations, registrations |

---

## Read this before you start

**The WhatsApp gateway cannot run on Render's free plan.** Two hard blockers:

1. **RAM.** whatsapp-web.js drives a real headless Chrome rendering WhatsApp
   Web — ~400–700 MB steady. Free *and* Starter instances are 512 MB, so the
   service OOM-restarts in a loop. `standard` (2 GB) is the first plan that
   works, which is why `render.yaml` sets it.
2. **Persistent disk.** The WhatsApp login is written to disk. Render's free
   filesystem is wiped on every deploy and restart, and disks are a paid-only
   feature. Without one you re-scan the QR code every restart.

A third issue affects free plans generally: services **spin down after 15
minutes with no inbound HTTP traffic**. WhatsApp's connection is an outbound
WebSocket, so it does not count — a free gateway would sleep and drop the
session.

`wpbot-api` and `wpbot-dashboard` are fine on free (the dashboard is a static
site, so it never sleeps at all). Only the gateway needs a paid plan.

**Rough monthly cost:** `standard` gateway (~$25) + 1 GB disk (~$0.25) + free
API/dashboard/db. Upgrade `wpbot-db` off `free` before it matters — Render
**deletes free Postgres databases after 30 days**.

---

## Deploy

### 1. Push this repo to GitHub

### 2. Create the Blueprint

Render Dashboard → **New** → **Blueprint** → select the repo → **Apply**.

Render will prompt for every var marked `sync: false`. On this first pass you
do not yet know the service URLs, so put placeholders in the three URL vars and
fix them in step 3. Fill in the real values for:

- `GEMINI_API_KEY`
- `ADMIN_PASSWORD`

`JWT_SECRET`, `SEND_MESSAGE_API_KEY` and `GATEWAY_TOKEN` are generated
automatically on `wpbot-api`.

### 3. Wire the service URLs

Render blueprints can't compose one service's URL into another's env var, so
set these by hand once the services exist. Their URLs follow the pattern
`https://<service-name>.onrender.com`.

| Service | Variable | Value |
|---|---|---|
| `wpbot-api` | `WHATSAPP_WEB_SERVER_URL` | `https://wpbot-whatsapp.onrender.com` |
| `wpbot-api` | `ALLOWED_ORIGINS` | `https://wpbot-dashboard.onrender.com` |
| `wpbot-whatsapp` | `PYTHON_API_URL` | `https://wpbot-api.onrender.com` |
| `wpbot-dashboard` | `VITE_API_URL` | `https://wpbot-api.onrender.com` |

### 4. Copy the gateway token

Open `wpbot-api` → Environment → reveal the generated `GATEWAY_TOKEN`, and
paste the same value into `wpbot-whatsapp`'s `GATEWAY_TOKEN`.

This secret is what stops strangers from sending WhatsApp messages through
your account. Under Docker these endpoints were on a private network; on
Render every service has a public URL, so the token is doing real work.

**This step is not optional.** The gateway fails closed in production: if
`GATEWAY_TOKEN` is unset there, `/send`, `/qr` and `/reconnect` all return
`503` and the bot cannot send anything. The startup log says so explicitly.
(Locally the token can stay blank — auth is skipped only off Render.)

### 5. Redeploy and scan the QR code

Redeploy both services so the new vars take effect (`VITE_API_URL` is baked
into the dashboard at build time, so it specifically needs a rebuild).

Then authenticate WhatsApp — the QR lives on the gateway's logs and API:

```bash
# Watch the gateway logs in the Render dashboard for the printed QR, or:
curl -H "Authorization: Bearer $GATEWAY_TOKEN" \
  https://wpbot-whatsapp.onrender.com/qr
```

The admin dashboard also renders it under the WhatsApp status page.

Scan with WhatsApp → Linked Devices. Because the session is on the mounted
disk, this survives future deploys and restarts.

### 6. Verify

```bash
curl https://wpbot-api.onrender.com/health
curl https://wpbot-api.onrender.com/whatsapp/status
```

---

## Follow-ups and the scheduler

`start_scheduler()` in [main.py](main.py) is in-process APScheduler. Render
restarts services on deploy and (on free plans) on wake-from-sleep, which
clears pending jobs — 24-hour follow-ups will fire unreliably.

The durable fix on Render is a **Cron Job** service hitting an endpoint on a
schedule instead of keeping timers in the web process.

## Local development

Unchanged — Docker is no longer involved:

```bash
# terminal 1
uvicorn main:app --reload --port 8000

# terminal 2
cd whatsapp-web-server && npm start

# terminal 3
cd dashboard && npm run dev
```

Copy `.env.example` to `.env` and fill it in. Leaving `GATEWAY_TOKEN` blank
locally disables the gateway auth check.
