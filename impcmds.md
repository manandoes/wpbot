## Wipe the previous WhatsApp session (get a fresh QR)

The gateway clears `.wwebjs_auth` / `.wwebjs_cache` on the mounted disk and
re-initialises itself:

```bash
curl -X POST -H "Authorization: Bearer $GATEWAY_TOKEN" \
  https://wpbot-whatsapp.onrender.com/reconnect
```

Then fetch the new QR (or read it off the gateway's logs):

```bash
curl -H "Authorization: Bearer $GATEWAY_TOKEN" \
  https://wpbot-whatsapp.onrender.com/qr
```

## Deploy

Render auto-deploys on push to `main`. To force one:
Render Dashboard → service → **Manual Deploy** → *Deploy latest commit*.

## Delete history of a specific user

Easiest — the API does all three steps at once:

```bash
curl -X DELETE https://wpbot-api.onrender.com/contact/919876543210/reset
```

Or by hand against the database. Grab the **External Database URL** from
Render Dashboard → `wpbot-db` → Connections:

```bash
psql "<external-database-url>"
```

```sql
DELETE FROM conversations WHERE phone_number = '919876543210';
UPDATE contacts SET status = 'not_contacted' WHERE phone_number = '919876543210';
\q
```

## Logs

Render Dashboard → service → **Logs**, or with the Render CLI:

```bash
render logs -r wpbot-whatsapp --tail
```
