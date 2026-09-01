#!/usr/bin/env bash
# gcp-vm-setup.sh — One-time script to provision a GCE VM and deploy wpbot.
# Run this LOCALLY on your machine (not on the server).
#
# Prerequisites:
#   1. gcloud CLI installed: https://cloud.google.com/sdk/docs/install
#   2. Authenticated: gcloud auth login
#   3. Project set: gcloud config set project <your-project-id>
#   4. .env filled in (cp .env.example .env && edit it)
#
# Usage: bash gcp-vm-setup.sh
set -euo pipefail

# ── Config (override via environment variables) ───────────────────────────────
PROJECT="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
ZONE="${GCP_ZONE:-us-central1-a}"
INSTANCE="${GCP_INSTANCE:-wpbot}"
MACHINE="${GCP_MACHINE:-e2-standard-2}"   # 2 vCPU, 8 GB RAM (Chromium needs ~2 GB)
DISK_SIZE="50GB"
REPO_URL="${GCP_REPO_URL:-}"

# ── Validation ────────────────────────────────────────────────────────────────
command -v gcloud >/dev/null 2>&1 || {
    echo "❌  gcloud CLI not found."
    echo "    Install it: https://cloud.google.com/sdk/docs/install"
    exit 1
}

if [ -z "$PROJECT" ]; then
    echo "❌  No GCP project set."
    echo "    Run: gcloud config set project <your-project-id>"
    echo "    Or:  export GCP_PROJECT=<your-project-id>"
    exit 1
fi

if [ ! -f .env ]; then
    echo "❌  .env file not found."
    echo "    cp .env.example .env && nano .env"
    exit 1
fi

if grep -q "change_me" .env 2>/dev/null; then
    echo "⚠️   WARNING: .env still has placeholder values."
    echo "    Update POSTGRES_PASSWORD, ADMIN_PASSWORD, JWT_SECRET before continuing."
    read -rp "Continue anyway? [y/N] " yn
    [[ "$yn" =~ ^[Yy]$ ]] || exit 1
fi

if [ -z "$REPO_URL" ]; then
    read -rp "Enter your git repo URL (e.g. https://github.com/you/wpbot): " REPO_URL
fi

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║         WPBot — Google Cloud VM Setup                ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  Project:  $PROJECT"
echo "  Zone:     $ZONE"
echo "  Instance: $INSTANCE ($MACHINE)"
echo "  Repo:     $REPO_URL"
echo ""

# ── 1. Enable required APIs ───────────────────────────────────────────────────
echo "🔧  Enabling Compute Engine API..."
gcloud services enable compute.googleapis.com --project="$PROJECT" --quiet

# ── 2. Create the VM ──────────────────────────────────────────────────────────
if gcloud compute instances describe "$INSTANCE" \
        --zone="$ZONE" --project="$PROJECT" &>/dev/null; then
    echo "✅  Instance '$INSTANCE' already exists — skipping creation."
else
    echo "🖥️   Creating GCE instance..."
    gcloud compute instances create "$INSTANCE" \
        --project="$PROJECT" \
        --zone="$ZONE" \
        --machine-type="$MACHINE" \
        --image-family=debian-12 \
        --image-project=debian-cloud \
        --boot-disk-size="$DISK_SIZE" \
        --boot-disk-type=pd-ssd \
        --tags=http-server,https-server \
        --scopes=cloud-platform

    echo "⏳  Waiting 30s for VM to boot..."
    sleep 30
fi

# ── 3. Firewall rules ─────────────────────────────────────────────────────────
if ! gcloud compute firewall-rules describe allow-http \
        --project="$PROJECT" &>/dev/null; then
    echo "🔒  Creating firewall rule for HTTP (port 80)..."
    gcloud compute firewall-rules create allow-http \
        --project="$PROJECT" \
        --allow=tcp:80 \
        --target-tags=http-server \
        --description="Allow HTTP for wpbot"
fi

if ! gcloud compute firewall-rules describe allow-https \
        --project="$PROJECT" &>/dev/null; then
    echo "🔒  Creating firewall rule for HTTPS (port 443)..."
    gcloud compute firewall-rules create allow-https \
        --project="$PROJECT" \
        --allow=tcp:443 \
        --target-tags=https-server \
        --description="Allow HTTPS for wpbot"
fi

# ── 4. Install Docker on the VM ───────────────────────────────────────────────
echo "🐳  Installing Docker on the VM..."
gcloud compute ssh "$INSTANCE" \
    --zone="$ZONE" --project="$PROJECT" \
    --command="
        set -e
        if command -v docker &>/dev/null; then
            echo 'Docker already installed.'
        else
            curl -fsSL https://get.docker.com | sudo sh
            sudo usermod -aG docker \$USER
            echo 'Docker installed.'
        fi
        sudo apt-get install -y git 2>/dev/null || true
    "

# ── 5. Clone the repo ─────────────────────────────────────────────────────────
echo "📦  Cloning repository..."
gcloud compute ssh "$INSTANCE" \
    --zone="$ZONE" --project="$PROJECT" \
    --command="
        if [ -d ~/wpbot/.git ]; then
            echo 'Repo already cloned.'
        else
            git clone '$REPO_URL' ~/wpbot
        fi
    "

# ── 6. Copy .env to the VM ────────────────────────────────────────────────────
echo "🔑  Copying .env to VM..."
# Use /tmp/ — pscp on Windows can't expand ~ in remote paths
gcloud compute scp .env "$INSTANCE":/tmp/wpbot_env \
    --zone="$ZONE" --project="$PROJECT"
gcloud compute ssh "$INSTANCE" \
    --zone="$ZONE" --project="$PROJECT" \
    --command="mv /tmp/wpbot_env ~/wpbot/.env"

# ── 7. Run deploy.sh on the VM ───────────────────────────────────────────────
echo "🚀  Running deploy.sh on VM..."
gcloud compute ssh "$INSTANCE" \
    --zone="$ZONE" --project="$PROJECT" \
    --command="cd ~/wpbot && bash deploy.sh"

# ── Done ──────────────────────────────────────────────────────────────────────
EXTERNAL_IP=$(gcloud compute instances describe "$INSTANCE" \
    --zone="$ZONE" --project="$PROJECT" \
    --format="get(networkInterfaces[0].accessConfigs[0].natIP)")

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   ✅  Setup complete!                                 ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  Dashboard:  http://$EXTERNAL_IP"
echo "  API docs:   http://$EXTERNAL_IP/docs"
echo ""
echo "SSH into the VM:"
echo "  gcloud compute ssh $INSTANCE --zone=$ZONE --project=$PROJECT"
echo ""
echo "To redeploy after a code push:"
echo "  gcloud compute ssh $INSTANCE --zone=$ZONE --project=$PROJECT \\"
echo "      --command='cd ~/wpbot && bash deploy.sh'"
