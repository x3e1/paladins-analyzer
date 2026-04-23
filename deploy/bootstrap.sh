#!/usr/bin/env bash
# One-shot bring-up for Oracle Cloud Ubuntu 22.04 ARM (Phase A).
# Idempotent: safe to re-run to update.
#
# Usage from your laptop:
#   ssh ubuntu@<PUBLIC_IP> "curl -fsSL https://raw.githubusercontent.com/x3e1/paladins-analyzer/main/deploy/bootstrap.sh | bash"

set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

REPO_URL="https://github.com/x3e1/paladins-analyzer.git"
REPO_DIR="${HOME}/paladins-analyzer"
PORT=3000

echo "[1/5] apt install docker + git + netfilter-persistent"
sudo -E apt-get update -qq
sudo -E apt-get install -y -qq docker.io docker-compose-plugin git netfilter-persistent

echo "[2/5] open port ${PORT} in host iptables (Oracle default REJECT chain)"
if ! sudo iptables -C INPUT -p tcp --dport "${PORT}" -j ACCEPT 2>/dev/null; then
  sudo iptables -I INPUT -p tcp --dport "${PORT}" -j ACCEPT
  sudo netfilter-persistent save
fi

echo "[3/5] add ubuntu to docker group (effective next login; using sudo for now)"
sudo usermod -aG docker ubuntu || true

echo "[4/5] clone or update repo"
if [ -d "${REPO_DIR}/.git" ]; then
  git -C "${REPO_DIR}" pull --ff-only
else
  git clone "${REPO_URL}" "${REPO_DIR}"
fi

echo "[5/5] docker compose up -d --build"
cd "${REPO_DIR}"
[ -f .env ] || cp .env.example .env
sudo docker compose up -d --build

echo ""
echo "--- status ---"
sudo docker compose ps
echo ""
sleep 3
if curl -fsS --max-time 10 "http://localhost:${PORT}/" >/dev/null; then
  echo "OK — http://localhost:${PORT}/ responded"
else
  echo "(still starting — wait 30 s and curl again)"
fi
PUB=$(curl -fsS --max-time 5 https://api.ipify.org || echo "<VM_PUBLIC_IP>")
echo ""
echo "Verify from your laptop:  http://${PUB}:${PORT}/"
