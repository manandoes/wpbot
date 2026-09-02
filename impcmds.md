# wpbot — VM commands

New VM (created by `gcp-vm-setup.sh`):

```
INSTANCE = wpbot
ZONE     = us-central1-a
PROJECT  = you-tube-automation-493118
```

Override the name/zone by exporting `GCP_INSTANCE` / `GCP_ZONE` before running
the setup script.

## First-time provisioning (run locally, from the project root)

Requires an OPEN billing account on the project — Compute Engine refuses
otherwise.

```bash
bash gcp-vm-setup.sh
```

Creates the VM, opens ports 80/443, installs Docker, clones the repo, copies
`.env` up, and runs `deploy.sh`.

## Database connection string (important)

Supabase's direct host — `db.<ref>.supabase.co` — resolves to **IPv6 only**.
A default GCE VM is IPv4-only, so the API container cannot reach it and every
request fails on connect. Use the **Supavisor session pooler** instead, which
has an IPv4 address:

```
DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
```

Grab the exact string from Supabase → Project Settings → Database →
Connection string → **Session pooler**. Session mode (port 5432), not
transaction mode (6543) — `db/__init__.py` keeps a long-lived SQLAlchemy pool.

Check it from the VM before deploying:

```bash
getent hosts aws-0-<region>.pooler.supabase.com   # must print an IPv4 address
```

## SSH in

```bash
gcloud compute ssh wpbot --project=you-tube-automation-493118 --zone=us-central1-a
```

## Redeploy after a push

```bash
gcloud compute ssh wpbot --project=you-tube-automation-493118 --zone=us-central1-a \
    --command='cd ~/wpbot && bash deploy.sh'
```

## Scan the WhatsApp QR (first boot, and after wiping the session)

```bash
gcloud compute ssh wpbot --project=you-tube-automation-493118 --zone=us-central1-a \
    --command='cd ~/wpbot && docker compose logs -f whatsapp-server'
```

Scan with WhatsApp → Linked Devices. The session persists in the
`whatsapp_session` volume, so this is one-time.

## Wipe the previous session

```bash
cd ~/wpbot
docker compose down
docker volume rm wpbot_whatsapp_session wpbot_whatsapp_cache
docker compose up -d
```

## Logs

```bash
cd ~/wpbot
docker compose logs -f                  # everything
docker compose logs -f python-api       # API only
docker compose logs -f whatsapp-server  # gateway only
```

## Delete history of a specific user

Easiest — the API does all three steps at once:

```bash
curl -X DELETE http://<VM-IP>/contact/919876543210/reset
```

Or by hand in the database (Supabase — use the SQL editor in the dashboard, or
psql from the VM):

```bash
cd ~/wpbot && docker compose exec python-api python -c     "import os; print(os.environ['DATABASE_URL'])"   # the connection string
psql "$DATABASE_URL"
```

```sql
DELETE FROM conversations WHERE phone_number = '919876543210';
UPDATE contacts SET status = 'not_contacted' WHERE phone_number = '919876543210';
\q
```


## Edit .env file
nano ~/wpbot/.env
make changes
CTRl+O > enter > CTRL+X