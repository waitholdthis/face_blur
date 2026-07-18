#!/usr/bin/env bash
# One-shot provisioning for a fresh Ubuntu 22.04/24.04 VPS (e.g. Hostinger KVM).
#
# Usage (as root on the VPS):
#   export DOMAIN=yourdomain.com
#   export REPO_URL=https://github.com/YOUR_USER/face_blur.git
#   bash setup-vps.sh
#
# Afterwards: edit /opt/faceblur/.env (go-live checklist at the top of the
# file), then run:  cd /opt/faceblur && docker compose up --build -d
set -euo pipefail

[ -n "${DOMAIN:-}" ] || { echo "Set DOMAIN=yourdomain.com first"; exit 1; }
[ -n "${REPO_URL:-}" ] || { echo "Set REPO_URL=https://github.com/YOU/face_blur.git first"; exit 1; }

echo "==> Installing Docker, Caddy, and ufw…"
apt-get update -y
apt-get install -y ca-certificates curl git ufw
# Docker (official convenience script — installs engine + compose plugin).
command -v docker >/dev/null 2>&1 || curl -fsSL https://get.docker.com | sh
# Caddy (official repo).
if ! command -v caddy >/dev/null 2>&1; then
  apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y && apt-get install -y caddy
fi

echo "==> Configuring firewall (SSH + HTTPS only)…"
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "==> Cloning the application to /opt/faceblur…"
if [ ! -d /opt/faceblur ]; then git clone "$REPO_URL" /opt/faceblur; fi
cd /opt/faceblur
[ -f .env ] || cp .env.example .env

echo "==> Pre-filling production values in .env…"
JWT=$(openssl rand -hex 32)
PG_PW=$(openssl rand -hex 16)
sed -i \
  -e "s|^ENVIRONMENT=.*|ENVIRONMENT=production|" \
  -e "s|^JWT_SECRET=.*|JWT_SECRET=${JWT}|" \
  -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${PG_PW}|" \
  -e "s|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=https://api.${DOMAIN}|" \
  -e "s|^CORS_ORIGINS=.*|CORS_ORIGINS=https://app.${DOMAIN}|" \
  .env
grep -q "^BIND_IP=" .env || echo "BIND_IP=127.0.0.1" >> .env

echo "==> Installing Caddyfile for app.${DOMAIN} and api.${DOMAIN}…"
sed "s/yourdomain.com/${DOMAIN}/g" deploy/Caddyfile > /etc/caddy/Caddyfile
systemctl reload caddy

echo ""
echo "Done. Two manual steps remain:"
echo "  1. Edit /opt/faceblur/.env and set ADMIN_PASSWORD to a strong password."
echo "  2. Launch:  cd /opt/faceblur && docker compose up --build -d"
echo ""
echo "Then visit https://app.${DOMAIN} (make sure both DNS A records point here)."
