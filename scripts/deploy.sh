#!/bin/bash

# ===========================================
# ISP Portal - DigitalOcean Deployment Script
# ===========================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}  ISP Portal - DigitalOcean Deployment  ${NC}"
echo -e "${GREEN}=========================================${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Please run as root (sudo)${NC}"
    exit 1
fi

# Configuration
DOMAIN=${DOMAIN:-"yourdomain.com"}
EMAIL=${EMAIL:-"admin@yourdomain.com"}
INSTALL_DIR="/opt/isp-portal"

echo -e "${YELLOW}Configuration:${NC}"
echo "  Domain: $DOMAIN"
echo "  Email: $EMAIL"
echo "  Install Dir: $INSTALL_DIR"
echo ""

# ===========================================
# Step 1: Update system
# ===========================================
echo -e "${GREEN}[1/8] Updating system...${NC}"
apt-get update && apt-get upgrade -y

# ===========================================
# Step 2: Install Docker
# ===========================================
echo -e "${GREEN}[2/8] Installing Docker...${NC}"

if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
    
    # Add current user to docker group
    usermod -aG docker $SUDO_USER 2>/dev/null || true
else
    echo "Docker already installed"
fi

# Install Docker Compose
if ! command -v docker-compose &> /dev/null; then
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
else
    echo "Docker Compose already installed"
fi

# ===========================================
# Step 3: Install additional tools
# ===========================================
echo -e "${GREEN}[3/8] Installing additional tools...${NC}"
apt-get install -y \
    git \
    curl \
    htop \
    ncdu \
    ufw \
    fail2ban \
    apache2-utils  # For htpasswd

# ===========================================
# Step 4: Configure firewall
# ===========================================
echo -e "${GREEN}[4/8] Configuring firewall...${NC}"

ufw --force reset
ufw default deny incoming
ufw default allow outgoing

# SSH
ufw allow 22/tcp

# HTTP/HTTPS
ufw allow 80/tcp
ufw allow 443/tcp

# TR-069 CWMP
ufw allow 7547/tcp

# Enable firewall
ufw --force enable

echo "Firewall rules applied"

# ===========================================
# Step 5: Configure fail2ban
# ===========================================
echo -e "${GREEN}[5/8] Configuring fail2ban...${NC}"

cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3

[traefik-auth]
enabled = true
port = http,https
filter = traefik-auth
logpath = /var/log/traefik/access.log
maxretry = 5
EOF

# Create Traefik filter
cat > /etc/fail2ban/filter.d/traefik-auth.conf << 'EOF'
[Definition]
failregex = ^.*\"clientAddr\":\"<HOST>:.*\"ClientAuthFailed\".*$
ignoreregex =
EOF

systemctl restart fail2ban

# ===========================================
# Step 6: Create installation directory
# ===========================================
echo -e "${GREEN}[6/8] Setting up application...${NC}"

mkdir -p $INSTALL_DIR
cd $INSTALL_DIR

# Copy files (assuming they're in current directory or git clone)
# git clone https://github.com/yourusername/isp-portal.git .

# Create required directories
mkdir -p traefik/dynamic
mkdir -p monitoring/grafana/{dashboards,datasources}
mkdir -p genieacs/ext
mkdir -p scripts

# ===========================================
# Step 7: Generate secrets and configure
# ===========================================
echo -e "${GREEN}[7/8] Generating secrets...${NC}"

# Generate secure passwords
POSTGRES_PASSWORD=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32)
REDIS_PASSWORD=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32)
SECRET_KEY=$(openssl rand -hex 32)
GRAFANA_PASSWORD=$(openssl rand -base64 16 | tr -dc 'a-zA-Z0-9' | head -c 16)

# Generate Traefik dashboard password
TRAEFIK_PASSWORD=$(openssl rand -base64 12)
TRAEFIK_USERS=$(htpasswd -nb admin "$TRAEFIK_PASSWORD" | sed -e 's/\$/\$\$/g')

# Create .env file
cat > $INSTALL_DIR/.env << EOF
# ===========================================
# ISP Portal - Production Configuration
# Generated on $(date)
# ===========================================

# Domain Configuration
DOMAIN=$DOMAIN

# DigitalOcean API Token (for DNS challenges)
DO_AUTH_TOKEN=${DO_AUTH_TOKEN:-your_digitalocean_api_token}

# Database Configuration
POSTGRES_USER=ispportal
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
POSTGRES_DB=ispportal

# Redis Configuration
REDIS_PASSWORD=$REDIS_PASSWORD

# Application Secret Key
SECRET_KEY=$SECRET_KEY

# UISP Configuration
UISP_URL=${UISP_URL:-https://your-uisp-server.com}
UISP_API_KEY=${UISP_API_KEY:-your_uisp_api_key}

# Traefik Dashboard Auth
TRAEFIK_USERS=$TRAEFIK_USERS

# Grafana Credentials
GRAFANA_USER=admin
GRAFANA_PASSWORD=$GRAFANA_PASSWORD

# DigitalOcean Spaces (for backups)
DO_SPACES_BUCKET=${DO_SPACES_BUCKET:-your-backup-bucket}
DO_SPACES_KEY=${DO_SPACES_KEY:-your_spaces_access_key}
DO_SPACES_SECRET=${DO_SPACES_SECRET:-your_spaces_secret_key}
DO_SPACES_REGION=${DO_SPACES_REGION:-nyc3}
EOF

chmod 600 $INSTALL_DIR/.env

# Save credentials to a secure file
cat > $INSTALL_DIR/CREDENTIALS.txt << EOF
===========================================
ISP Portal Credentials
Generated on $(date)
KEEP THIS FILE SECURE AND DELETE AFTER NOTING
===========================================

Traefik Dashboard:
  URL: https://traefik.$DOMAIN
  User: admin
  Password: $TRAEFIK_PASSWORD

Grafana:
  URL: https://grafana.$DOMAIN
  User: admin
  Password: $GRAFANA_PASSWORD

GenieACS (TR-069):
  URL: https://acs.$DOMAIN
  (Uses Traefik auth - same as above)

PostgreSQL:
  User: ispportal
  Password: $POSTGRES_PASSWORD
  Database: ispportal

Redis:
  Password: $REDIS_PASSWORD

API Secret Key: $SECRET_KEY

===========================================
EOF

chmod 600 $INSTALL_DIR/CREDENTIALS.txt

echo -e "${YELLOW}Credentials saved to: $INSTALL_DIR/CREDENTIALS.txt${NC}"
echo -e "${RED}IMPORTANT: Save these credentials securely and delete the file!${NC}"

# ===========================================
# Step 8: Start services
# ===========================================
echo -e "${GREEN}[8/8] Starting services...${NC}"

cd $INSTALL_DIR

# Pull images first
docker-compose pull

# Start services
docker-compose up -d

# Wait for services to start
echo "Waiting for services to start..."
sleep 30

# Check service status
docker-compose ps

echo ""
echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}  Deployment Complete!                   ${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""
echo "Services:"
echo "  API:        https://api.$DOMAIN"
echo "  Traefik:    https://traefik.$DOMAIN"
echo "  Grafana:    https://grafana.$DOMAIN"
echo "  GenieACS:   https://acs.$DOMAIN"
echo "  Prometheus: https://prometheus.$DOMAIN"
echo ""
echo "TR-069 CWMP URL (configure in routers):"
echo "  http://$DOMAIN:7547"
echo ""
echo -e "${YELLOW}Don't forget to:${NC}"
echo "  1. Update DNS records to point to this server"
echo "  2. Configure your UISP URL and API key in .env"
echo "  3. Configure your DigitalOcean API token for SSL"
echo "  4. Save the credentials from CREDENTIALS.txt"
echo "  5. Delete CREDENTIALS.txt after saving passwords"
echo ""
echo -e "${GREEN}View logs: docker-compose logs -f${NC}"
