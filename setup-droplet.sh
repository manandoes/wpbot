#!/bin/bash
# Run this script on a fresh Ubuntu 22.04 DigitalOcean Droplet (as root)
# Usage: bash setup-droplet.sh

set -e

echo "=== 1. Update system ==="
apt-get update && apt-get upgrade -y

echo "=== 2. Install Docker ==="
apt-get install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "=== 3. Install git ==="
apt-get install -y git

echo "=== 4. Clone the repository ==="
# Replace with your actual git repo URL
read -p "Enter your git repo URL (or press Enter to skip and copy files manually): " REPO_URL
if [ -n "$REPO_URL" ]; then
  git clone "$REPO_URL" /opt/wpbot
  cd /opt/wpbot
else
  echo "Skipping clone. Copy your project files to /opt/wpbot and re-run from there."
  mkdir -p /opt/wpbot
  exit 0
fi

echo "=== 5. Create .env file ==="
echo "Enter your environment variables:"
read -p "DATABASE_URL (e.g. postgresql://user:pass@host:25060/db?sslmode=require): " DB_URL
read -p "GEMINI_API_KEY: " GEMINI_KEY

cat > /opt/wpbot/.env <<EOF
DATABASE_URL=$DB_URL
GEMINI_API_KEY=$GEMINI_KEY
WHATSAPP_WEB_SERVER_URL=http://whatsapp-node:3000
EOF

cat > /opt/wpbot/whatsapp-web-server/.env <<EOF
PYTHON_API_URL=http://python-api:8000
WHATSAPP_WEB_PORT=3000
EOF

echo "=== 6. Open firewall ports ==="
ufw allow 22/tcp    # SSH
ufw allow 8000/tcp  # FastAPI (Python bot)
ufw --force enable

echo "=== 7. Build and start containers ==="
cd /opt/wpbot
docker compose up -d --build

echo ""
echo "====================================================="
echo "  Deployment complete!"
echo "====================================================="
echo ""
echo "  Python API:      http://$(curl -s ifconfig.me):8000"
echo "  API docs:        http://$(curl -s ifconfig.me):8000/docs"
echo "  Health check:    http://$(curl -s ifconfig.me):8000/health"
echo ""
echo "  Next step: Scan the WhatsApp QR code"
echo "    docker logs wpbot-node --follow"
echo ""
echo "  Or get QR via API:"
echo "    curl http://localhost:8000/whatsapp/qr"
echo "====================================================="
