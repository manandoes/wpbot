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

Or by hand in the database:

```bash
cd ~/wpbot && docker compose exec postgres psql -U wpbot -d wpbot
```

```sql
DELETE FROM conversations WHERE phone_number = '919876543210';
UPDATE contacts SET status = 'not_contacted' WHERE phone_number = '919876543210';
\q
```
