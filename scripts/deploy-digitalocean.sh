#!/bin/bash

# ===========================================
# ISP Portal - DigitalOcean Specific Deployment
# Optimized for DO Droplets, Spaces, and DNS
# ===========================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=========================================${NC}"
echo -e "${BLUE}  ISP Portal - DigitalOcean Deployment  ${NC}"
echo -e "${BLUE}=========================================${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Please run as root (sudo)${NC}"
    exit 1
fi

# ===========================================
# CONFIGURATION - EDIT THESE VALUES
# ===========================================
DOMAIN=${DOMAIN:-""}
DO_AUTH_TOKEN=${DO_AUTH_TOKEN:-""}
UISP_URL=${UISP_URL:-""}
DO_SPACES_BUCKET=${DO_SPACES_BUCKET:-""}
DO_SPACES_KEY=${DO_SPACES_KEY:-""}
DO_SPACES_SECRET=${DO_SPACES_SECRET:-""}
DO_SPACES_REGION=${DO_SPACES_REGION:-"nyc3"}

# Validate required inputs
if [ -z "$DOMAIN" ]; then
    echo -e "${YELLOW}Enter your domain (e.g., isp.example.com):${NC}"
    read DOMAIN
fi

if [ -z "$DO_AUTH_TOKEN" ]; then
    echo -e "${YELLOW}Enter your DigitalOcean API Token:${NC}"
    echo "(Create at: https://cloud.digitalocean.com/account/api/tokens)"
    read -s DO_AUTH_TOKEN
    echo ""
fi

if [ -z "$UISP_URL" ]; then
    echo -e "${YELLOW}Enter your UISP Server URL (e.g., https://uisp.yourcompany.com):${NC}"
    read UISP_URL
fi

INSTALL_DIR="/opt/isp-portal"
DROPLET_IP=$(curl -s http://169.254.169.254/metadata/v1/interfaces/public/0/ipv4/address 2>/dev/null || hostname -I | awk '{print $1}')

echo ""
echo -e "${GREEN}Configuration:${NC}"
echo "  Domain: $DOMAIN"
echo "  Droplet IP: $DROPLET_IP"
echo "  UISP URL: $UISP_URL"
echo "  Install Dir: $INSTALL_DIR"
echo ""

# ===========================================
# Step 1: Update system & install dependencies
# ===========================================
echo -e "${GREEN}[1/10] Updating system...${NC}"
apt-get update && apt-get upgrade -y

apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    git \
    htop \
    ncdu \
    ufw \
    fail2ban \
    apache2-utils \
    jq \
    s3cmd

# ===========================================
# Step 2: Install Docker
# ===========================================
echo -e "${GREEN}[2/10] Installing Docker...${NC}"

if ! command -v docker &> /dev/null; then
    # Add Docker's official GPG key
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    # Add Docker repository
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    
    # Enable Docker service
    systemctl enable docker
    systemctl start docker
else
    echo "Docker already installed"
fi

# ===========================================
# Step 3: Configure DigitalOcean DNS
# ===========================================
echo -e "${GREEN}[3/10] Configuring DigitalOcean DNS...${NC}"

# Get the domain root (e.g., example.com from api.example.com)
DOMAIN_ROOT=$(echo $DOMAIN | rev | cut -d. -f1,2 | rev)

# Function to create/update DNS record
create_dns_record() {
    local name=$1
    local type=$2
    local data=$3
    
    # Check if record exists
    EXISTING=$(curl -s -X GET \
        -H "Authorization: Bearer $DO_AUTH_TOKEN" \
        -H "Content-Type: application/json" \
        "https://api.digitalocean.com/v2/domains/$DOMAIN_ROOT/records" | \
        jq -r ".domain_records[] | select(.name==\"$name\" and .type==\"$type\") | .id")
    
    if [ -n "$EXISTING" ] && [ "$EXISTING" != "null" ]; then
        echo "  Updating $name.$DOMAIN_ROOT -> $data"
        curl -s -X PUT \
            -H "Authorization: Bearer $DO_AUTH_TOKEN" \
            -H "Content-Type: application/json" \
            -d "{\"data\":\"$data\"}" \
            "https://api.digitalocean.com/v2/domains/$DOMAIN_ROOT/records/$EXISTING" > /dev/null
    else
        echo "  Creating $name.$DOMAIN_ROOT -> $data"
        curl -s -X POST \
            -H "Authorization: Bearer $DO_AUTH_TOKEN" \
            -H "Content-Type: application/json" \
            -d "{\"type\":\"$type\",\"name\":\"$name\",\"data\":\"$data\",\"ttl\":300}" \
            "https://api.digitalocean.com/v2/domains/$DOMAIN_ROOT/records" > /dev/null
    fi
}

# Determine subdomain prefix
if [ "$DOMAIN" == "$DOMAIN_ROOT" ]; then
    PREFIX="@"
else
    PREFIX=$(echo $DOMAIN | sed "s/\.$DOMAIN_ROOT$//")
fi

echo "Creating DNS records for $DOMAIN_ROOT..."

# Create A records
create_dns_record "$PREFIX" "A" "$DROPLET_IP"
create_dns_record "api" "A" "$DROPLET_IP"
create_dns_record "traefik" "A" "$DROPLET_IP"
create_dns_record "grafana" "A" "$DROPLET_IP"
create_dns_record "acs" "A" "$DROPLET_IP"
create_dns_record "prometheus" "A" "$DROPLET_IP"

echo "DNS records created. Allow 2-5 minutes for propagation."

# ===========================================
# Step 4: Configure DigitalOcean Cloud Firewall
# ===========================================
echo -e "${GREEN}[4/10] Configuring DigitalOcean Cloud Firewall...${NC}"

# Get Droplet ID
DROPLET_ID=$(curl -s http://169.254.169.254/metadata/v1/id 2>/dev/null || echo "")

if [ -n "$DROPLET_ID" ]; then
    # Create firewall rules via API
    FIREWALL_NAME="isp-portal-firewall"
    
    # Check if firewall exists
    EXISTING_FW=$(curl -s -X GET \
        -H "Authorization: Bearer $DO_AUTH_TOKEN" \
        -H "Content-Type: application/json" \
        "https://api.digitalocean.com/v2/firewalls" | \
        jq -r ".firewalls[] | select(.name==\"$FIREWALL_NAME\") | .id")
    
    FIREWALL_RULES='{
        "name": "'$FIREWALL_NAME'",
        "inbound_rules": [
            {"protocol": "tcp", "ports": "22", "sources": {"addresses": ["0.0.0.0/0", "::/0"]}},
            {"protocol": "tcp", "ports": "80", "sources": {"addresses": ["0.0.0.0/0", "::/0"]}},
            {"protocol": "tcp", "ports": "443", "sources": {"addresses": ["0.0.0.0/0", "::/0"]}},
            {"protocol": "tcp", "ports": "7547", "sources": {"addresses": ["0.0.0.0/0", "::/0"]}},
            {"protocol": "icmp", "sources": {"addresses": ["0.0.0.0/0", "::/0"]}}
        ],
        "outbound_rules": [
            {"protocol": "tcp", "ports": "all", "destinations": {"addresses": ["0.0.0.0/0", "::/0"]}},
            {"protocol": "udp", "ports": "all", "destinations": {"addresses": ["0.0.0.0/0", "::/0"]}},
            {"protocol": "icmp", "destinations": {"addresses": ["0.0.0.0/0", "::/0"]}}
        ],
        "droplet_ids": ['$DROPLET_ID']
    }'
    
    if [ -n "$EXISTING_FW" ] && [ "$EXISTING_FW" != "null" ]; then
        echo "  Updating existing firewall..."
        curl -s -X PUT \
            -H "Authorization: Bearer $DO_AUTH_TOKEN" \
            -H "Content-Type: application/json" \
            -d "$FIREWALL_RULES" \
            "https://api.digitalocean.com/v2/firewalls/$EXISTING_FW" > /dev/null
    else
        echo "  Creating cloud firewall..."
        curl -s -X POST \
            -H "Authorization: Bearer $DO_AUTH_TOKEN" \
            -H "Content-Type: application/json" \
            -d "$FIREWALL_RULES" \
            "https://api.digitalocean.com/v2/firewalls" > /dev/null
    fi
    echo "  Cloud firewall configured"
else
    echo "  Could not detect Droplet ID, skipping cloud firewall"
fi

# Also configure local UFW as backup
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 7547/tcp
ufw --force enable

# ===========================================
# Step 5: Configure fail2ban
# ===========================================
echo -e "${GREEN}[5/10] Configuring fail2ban...${NC}"

cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5
ignoreip = 127.0.0.1/8

[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 7200
EOF

systemctl restart fail2ban

# ===========================================
# Step 6: Configure DigitalOcean Spaces for backups
# ===========================================
echo -e "${GREEN}[6/10] Configuring DigitalOcean Spaces...${NC}"

if [ -n "$DO_SPACES_KEY" ] && [ -n "$DO_SPACES_SECRET" ]; then
    # Configure s3cmd for DO Spaces
    cat > /root/.s3cfg << EOF
[default]
access_key = $DO_SPACES_KEY
secret_key = $DO_SPACES_SECRET
host_base = ${DO_SPACES_REGION}.digitaloceanspaces.com
host_bucket = %(bucket)s.${DO_SPACES_REGION}.digitaloceanspaces.com
use_https = True
EOF
    chmod 600 /root/.s3cfg
    echo "  Spaces configured"
else
    echo "  Spaces not configured (optional)"
fi

# ===========================================
# Step 7: Setup application directory
# ===========================================
echo -e "${GREEN}[7/10] Setting up application...${NC}"

mkdir -p $INSTALL_DIR
cd $INSTALL_DIR

# If we're running from the deployment package, copy files
if [ -f "./docker-compose.yml" ]; then
    echo "  Using existing files"
else
    echo "  Downloading latest version..."
    # In production, you'd clone from your repo
    # git clone https://github.com/yourusername/isp-portal.git .
    echo "  Please copy your deployment files to $INSTALL_DIR"
fi

# Create required directories
mkdir -p traefik/dynamic
mkdir -p monitoring/grafana/{dashboards,datasources}
mkdir -p genieacs/ext
mkdir -p scripts
mkdir -p backend/app/{api,core}

# ===========================================
# Step 8: Generate secrets
# ===========================================
echo -e "${GREEN}[8/10] Generating secrets...${NC}"

POSTGRES_PASSWORD=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32)
REDIS_PASSWORD=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32)
SECRET_KEY=$(openssl rand -hex 32)
GRAFANA_PASSWORD=$(openssl rand -base64 16 | tr -dc 'a-zA-Z0-9' | head -c 16)
TRAEFIK_PASSWORD=$(openssl rand -base64 12 | tr -dc 'a-zA-Z0-9' | head -c 12)
TRAEFIK_USERS=$(htpasswd -nb admin "$TRAEFIK_PASSWORD" | sed -e 's/\$/\$\$/g')

# Create .env file
cat > $INSTALL_DIR/.env << EOF
# ===========================================
# ISP Portal - DigitalOcean Production Config
# Generated: $(date)
# Droplet IP: $DROPLET_IP
# ===========================================

# Domain Configuration
DOMAIN=$DOMAIN

# DigitalOcean API Token
DO_AUTH_TOKEN=$DO_AUTH_TOKEN

# Database Configuration  
POSTGRES_USER=ispportal
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
POSTGRES_DB=ispportal

# Redis Configuration
REDIS_PASSWORD=$REDIS_PASSWORD

# Application Secret Key
SECRET_KEY=$SECRET_KEY

# UISP Configuration
UISP_URL=$UISP_URL
UISP_API_KEY=

# Traefik Dashboard Auth
TRAEFIK_USERS=$TRAEFIK_USERS

# Grafana Credentials
GRAFANA_USER=admin
GRAFANA_PASSWORD=$GRAFANA_PASSWORD

# DigitalOcean Spaces (Backups)
DO_SPACES_BUCKET=$DO_SPACES_BUCKET
DO_SPACES_KEY=$DO_SPACES_KEY
DO_SPACES_SECRET=$DO_SPACES_SECRET
DO_SPACES_REGION=$DO_SPACES_REGION
EOF

chmod 600 $INSTALL_DIR/.env

# Save credentials
cat > $INSTALL_DIR/CREDENTIALS.txt << EOF
╔═══════════════════════════════════════════════════════════╗
║         ISP PORTAL - ACCESS CREDENTIALS                   ║
║         Generated: $(date)                  
╠═══════════════════════════════════════════════════════════╣
║                                                           ║
║  TRAEFIK DASHBOARD                                        ║
║  URL: https://traefik.$DOMAIN                             ║
║  User: admin                                              ║
║  Pass: $TRAEFIK_PASSWORD                                  ║
║                                                           ║
║  GRAFANA MONITORING                                       ║
║  URL: https://grafana.$DOMAIN                             ║
║  User: admin                                              ║
║  Pass: $GRAFANA_PASSWORD                                  ║
║                                                           ║
║  GENIEACS (TR-069)                                        ║
║  URL: https://acs.$DOMAIN                                 ║
║  Auth: Same as Traefik                                    ║
║                                                           ║
║  API ENDPOINT                                             ║
║  URL: https://api.$DOMAIN                                 ║
║                                                           ║
║  TR-069 CWMP URL (for routers)                           ║
║  URL: http://$DOMAIN:7547                                 ║
║                                                           ║
║  DATABASE (Internal)                                      ║
║  PostgreSQL Pass: $POSTGRES_PASSWORD                      ║
║  Redis Pass: $REDIS_PASSWORD                              ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝

⚠️  SAVE THESE CREDENTIALS SECURELY AND DELETE THIS FILE!
EOF

chmod 600 $INSTALL_DIR/CREDENTIALS.txt

# ===========================================
# Step 9: Install DigitalOcean monitoring agent
# ===========================================
echo -e "${GREEN}[9/10] Installing DO monitoring agent...${NC}"

curl -sSL https://repos.insights.digitalocean.com/install.sh | bash 2>/dev/null || true

# ===========================================
# Step 10: Start services
# ===========================================
echo -e "${GREEN}[10/10] Starting services...${NC}"

cd $INSTALL_DIR

# Pull images
echo "  Pulling Docker images..."
docker compose pull 2>/dev/null || docker-compose pull

# Start services
echo "  Starting containers..."
docker compose up -d 2>/dev/null || docker-compose up -d

# Wait for services
echo "  Waiting for services to initialize (60s)..."
sleep 60

# Check status
echo ""
echo "Container Status:"
docker compose ps 2>/dev/null || docker-compose ps

# ===========================================
# Final Output
# ===========================================
echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║          DEPLOYMENT COMPLETE! 🚀                          ║${NC}"
echo -e "${GREEN}╠═══════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║                                                           ║${NC}"
echo -e "${GREEN}║  Your ISP Portal is now running!                          ║${NC}"
echo -e "${GREEN}║                                                           ║${NC}"
echo -e "${GREEN}║  API:        https://api.$DOMAIN${NC}"
echo -e "${GREEN}║  Traefik:    https://traefik.$DOMAIN${NC}"
echo -e "${GREEN}║  Grafana:    https://grafana.$DOMAIN${NC}"
echo -e "${GREEN}║  GenieACS:   https://acs.$DOMAIN${NC}"
echo -e "${GREEN}║                                                           ║${NC}"
echo -e "${GREEN}║  TR-069 URL: http://$DOMAIN:7547${NC}"
echo -e "${GREEN}║                                                           ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}IMPORTANT NEXT STEPS:${NC}"
echo ""
echo "1. View credentials:"
echo "   cat $INSTALL_DIR/CREDENTIALS.txt"
echo ""
echo "2. Add your UISP API key:"
echo "   nano $INSTALL_DIR/.env"
echo "   # Set UISP_API_KEY=your_key"
echo "   docker compose restart backend"
echo ""
echo "3. Verify SSL certificates (may take 2-5 min):"
echo "   curl -I https://api.$DOMAIN"
echo ""
echo "4. View logs:"
echo "   docker compose logs -f"
echo ""
echo "5. Configure TR-069 devices with CWMP URL:"
echo "   http://$DOMAIN:7547"
echo ""
echo -e "${RED}⚠️  Don't forget to save and delete CREDENTIALS.txt!${NC}"
