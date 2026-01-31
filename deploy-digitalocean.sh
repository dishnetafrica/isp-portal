#!/usr/bin/env bash
set -e

echo "========================================="
echo "  ISP Portal - Production Deployment     "
echo "  GoDaddy DNS / UISP Compatible          "
echo "========================================="

INSTALL_DIR="/opt/isp-portal"
SERVER_IP=$(curl -s ifconfig.me)

# -----------------------------
# 1. Inputs
# -----------------------------
read -p "Enter ROOT domain (example: dishnetafrica.com): " ROOT_DOMAIN
read -p "Enter UISP CRM URL (example: https://crm.dishnetafrica.com): " UISP_URL

PORTAL_DOMAIN="isp.${ROOT_DOMAIN}"
API_DOMAIN="isp-api.${ROOT_DOMAIN}"
ACS_DOMAIN="acs.${ROOT_DOMAIN}"
GRAFANA_DOMAIN="grafana.${ROOT_DOMAIN}"

echo ""
echo "Configuration:"
echo " Customer Portal : https://${PORTAL_DOMAIN}"
echo " Backend API     : https://${API_DOMAIN}"
echo " ACS (TR-069)    : https://${ACS_DOMAIN}"
echo " Grafana         : https://${GRAFANA_DOMAIN}"
echo " UISP CRM        : ${UISP_URL}"
echo " Server IP       : ${SERVER_IP}"
echo ""

# -----------------------------
# 2. System prep
# -----------------------------
echo "[1/5] System preparation..."
apt update -y
apt install -y curl git ufw ca-certificates docker.io docker-compose-plugin
systemctl enable docker
systemctl start docker

# -----------------------------
# 3. Firewall
# -----------------------------
echo "[2/5] Firewall configuration..."
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 7547/tcp
ufw allow 7557/tcp
ufw --force enable

# -----------------------------
# 4. Environment validation
# -----------------------------
echo "[3/5] Validating environment..."
if [ ! -f ".env" ]; then
  echo "ERROR: .env file not found"
  exit 1
fi

export PORTAL_DOMAIN API_DOMAIN ACS_DOMAIN GRAFANA_DOMAIN UISP_URL

# -----------------------------
# 5. Start services
# -----------------------------
echo "[4/5] Starting services..."
docker compose down || true
docker compose pull
docker compose up -d

echo ""
echo "========================================="
echo " Deployment completed successfully"
echo ""
echo " Portal  : https://${PORTAL_DOMAIN}"
echo " API     : https://${API_DOMAIN}"
echo " ACS     : https://${ACS_DOMAIN}"
echo " Grafana : https://${GRAFANA_DOMAIN}"
echo "========================================="

docker compose ps
