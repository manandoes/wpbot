#!/usr/bin/env bash
# deploy.sh — Run this ON the GCE VM to deploy or update wpbot.
# Called automatically by gcp-vm-setup.sh, or manually after SSH'ing in.
# Usage: bash deploy.sh
set -euo pipefail

# Use sudo docker compose if the current user is not in the docker group yet
if docker compose version &>/dev/null 2>&1; then
    COMPOSE="docker compose"
else
    COMPOSE="sudo docker compose"
fi

echo ""
echo "╔══════════════════════════════════════╗"
echo "║        WPBot — Deploy Script         ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 1. Prerequisites ──────────────────────────────────────────────────────────
command -v docker >/dev/null 2>&1 || { echo "❌  docker not found. Run gcp-vm-setup.sh first."; exit 1; }
$COMPOSE version >/dev/null 2>&1   || { echo "❌  docker compose not found."; exit 1; }

if [ ! -f .env ]; then
    echo "❌  .env not found."
    echo "    cp .env.example .env && nano .env"
    exit 1
fi

if grep -q "change_me" .env 2>/dev/null; then
    echo "⚠️   WARNING: .env still has placeholder values."
    echo "    Update DATABASE_URL, ADMIN_PASSWORD, JWT_SECRET, GATEWAY_TOKEN before going live."
    echo ""
fi

# ── 2. Pull latest code ───────────────────────────────────────────────────────
echo "📥  Pulling latest code..."
git pull origin "$(git rev-parse --abbrev-ref HEAD)"
echo ""

# ── 3. Build images ───────────────────────────────────────────────────────────
echo "🔨  Building Docker images (first run takes a few minutes)..."
$COMPOSE build --parallel
echo ""

# ── 4. Start / restart services ───────────────────────────────────────────────
echo "🚀  Starting services..."
$COMPOSE up -d --remove-orphans
echo ""

# ── 5. Status ─────────────────────────────────────────────────────────────────
echo "📊  Service status:"
$COMPOSE ps
echo ""

# Fetch GCE external IP from instance metadata (falls back to ifconfig.me)
EXTERNAL_IP=$(curl -sf -H "Metadata-Flavor: Google" \
    "http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip" \
    2>/dev/null || curl -sf ifconfig.me 2>/dev/null || echo "<your-vm-ip>")

echo "✅  Deployment complete."
echo "    Dashboard:  http://$EXTERNAL_IP"
echo "    API docs:   http://$EXTERNAL_IP/docs"
echo ""
echo "Useful commands:"
echo "  $COMPOSE logs -f              — tail all logs"
echo "  $COMPOSE logs -f python-api   — API logs"
echo "  $COMPOSE restart python-api   — restart a single service"
echo "  $COMPOSE down                 — stop everything"
