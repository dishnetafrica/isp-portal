# ISP Customer Portal - DigitalOcean Deployment

Complete ISP customer portal for managing Starlink, MikroTik, and TR-069 devices with UISP billing integration.

## 🚀 Quick Start

### Prerequisites

- DigitalOcean Droplet (recommended: 4GB RAM, 2 vCPUs)
- Domain name with DNS managed by DigitalOcean (for automatic SSL)
- UISP server for billing integration

### One-Command Deployment

```bash
# Clone the repository
git clone https://github.com/yourusername/isp-portal.git
cd isp-portal

# Run deployment script
sudo DOMAIN=yourdomain.com EMAIL=admin@yourdomain.com ./scripts/deploy.sh
```

## 📋 Features

### Device Management
- **Starlink**: View status, configure WiFi, reboot, stow/unstow
- **MikroTik**: WiFi config, hotspot users, voucher generation, active sessions
- **TR-069 (D-Link/TP-Link)**: WiFi settings, remote reboot, firmware updates

### Billing Integration
- UISP authentication (customers use their UISP login)
- View invoices and payment history
- Check account balance and services

### Hotspot Management
- Create hotspot users
- Generate vouchers with presets
- View active sessions
- Disconnect users
- Print voucher formats (thermal, A4, card)

## 🏗️ Architecture

```
                                    ┌─────────────────┐
                                    │   Mobile App    │
                                    │  (Flutter/RN)   │
                                    └────────┬────────┘
                                             │
                                    ┌────────▼────────┐
                                    │    Traefik      │
                                    │  (SSL/Routing)  │
                                    └────────┬────────┘
                                             │
        ┌────────────────────────────────────┼────────────────────────────────────┐
        │                                    │                                    │
┌───────▼───────┐                   ┌────────▼────────┐                  ┌────────▼────────┐
│   Backend     │                   │    GenieACS     │                  │    Grafana      │
│   (FastAPI)   │                   │   (TR-069 ACS)  │                  │   (Monitoring)  │
└───────┬───────┘                   └────────┬────────┘                  └────────┬────────┘
        │                                    │                                    │
┌───────▼───────┐                   ┌────────▼────────┐                  ┌────────▼────────┐
│  PostgreSQL   │                   │    MongoDB      │                  │   Prometheus    │
└───────────────┘                   └─────────────────┘                  └─────────────────┘
```

## 🔧 Configuration

### Environment Variables

Edit `.env` file after deployment:

```bash
# Domain Configuration
DOMAIN=yourdomain.com

# DigitalOcean API Token (for SSL)
DO_AUTH_TOKEN=your_token_here

# UISP Configuration
UISP_URL=https://your-uisp-server.com
UISP_API_KEY=your_api_key

# Backup Storage (DigitalOcean Spaces)
DO_SPACES_BUCKET=your-bucket
DO_SPACES_KEY=your_key
DO_SPACES_SECRET=your_secret
DO_SPACES_REGION=nyc3
```

### DNS Configuration

Create the following DNS records pointing to your Droplet IP:

| Type | Name | Value |
|------|------|-------|
| A | @ | YOUR_DROPLET_IP |
| A | api | YOUR_DROPLET_IP |
| A | traefik | YOUR_DROPLET_IP |
| A | grafana | YOUR_DROPLET_IP |
| A | acs | YOUR_DROPLET_IP |
| A | prometheus | YOUR_DROPLET_IP |

### TR-069 Device Configuration

Configure your D-Link/TP-Link routers with:

- **ACS URL**: `http://yourdomain.com:7547`
- **Username**: (leave empty or configure in GenieACS)
- **Password**: (leave empty or configure in GenieACS)

## 📱 API Endpoints

### Authentication
```
POST /api/auth/login          # Login with UISP credentials
GET  /api/auth/me             # Get current user info
POST /api/auth/refresh        # Refresh access token
```

### Device Detection
```
POST /api/devices/detect      # Auto-detect connected device
GET  /api/devices/supported   # List supported device types
```

### Starlink
```
GET  /api/starlink/status     # Get dish status
GET  /api/starlink/wifi       # Get WiFi settings
PUT  /api/starlink/wifi       # Update WiFi settings
POST /api/starlink/reboot     # Reboot dish
POST /api/starlink/stow       # Stow dish
```

### MikroTik
```
POST /api/mikrotik/system/info           # Get system info
POST /api/mikrotik/wifi                  # Get WiFi settings
PUT  /api/mikrotik/wifi                  # Update WiFi
POST /api/mikrotik/hotspot/users         # List hotspot users
POST /api/mikrotik/hotspot/users/create  # Create user
POST /api/mikrotik/hotspot/vouchers      # Generate vouchers
POST /api/mikrotik/hotspot/active        # Active sessions
```

### TR-069
```
GET  /api/tr069/devices                  # List devices
GET  /api/tr069/devices/{id}/status      # Device status
GET  /api/tr069/devices/{id}/wifi        # WiFi settings
PUT  /api/tr069/devices/{id}/wifi        # Update WiFi
POST /api/tr069/devices/{id}/reboot      # Reboot device
```

### Billing
```
GET /api/billing/balance      # Account balance
GET /api/billing/invoices     # List invoices
GET /api/billing/services     # Active services
GET /api/billing/usage        # Data usage
```

## 🛠️ Management Commands

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend

# Last 100 lines
docker-compose logs --tail=100 backend
```

### Restart Services
```bash
# All services
docker-compose restart

# Specific service
docker-compose restart backend
```

### Database Access
```bash
# PostgreSQL
docker exec -it postgres psql -U ispportal -d ispportal

# MongoDB
docker exec -it mongo mongo genieacs
```

### Backup
```bash
./scripts/backup.sh
```

### Health Check
```bash
./scripts/health-check.sh
```

## 📊 Monitoring

### Grafana Dashboards

Access: `https://grafana.yourdomain.com`

Pre-configured dashboards:
- API Performance
- Container Resources
- Database Metrics
- Network Traffic

### Prometheus Metrics

Access: `https://prometheus.yourdomain.com`

### Log Aggregation

Logs are collected via Loki and viewable in Grafana.

## 🔒 Security

### Implemented Security Measures

- [x] SSL/TLS via Let's Encrypt
- [x] Rate limiting on API endpoints
- [x] Fail2ban for SSH and HTTP auth
- [x] UFW firewall configuration
- [x] JWT authentication
- [x] Password hashing
- [x] Security headers via Traefik
- [x] Docker network isolation

### Security Recommendations

1. Change all default passwords
2. Enable 2FA on DigitalOcean account
3. Regular security updates
4. Monitor access logs
5. Implement IP whitelisting for admin access

## 🐛 Troubleshooting

### Container Won't Start
```bash
docker-compose logs [service-name]
```

### Database Connection Issues
```bash
docker exec -it postgres pg_isready
```

### TR-069 Devices Not Connecting
1. Check firewall allows port 7547
2. Verify ACS URL in device settings
3. Check GenieACS logs: `docker-compose logs genieacs-cwmp`

### SSL Certificate Issues
```bash
# Check Traefik logs
docker-compose logs traefik

# Verify DNS propagation
dig api.yourdomain.com
```

## 📄 License

MIT License - See LICENSE file for details.

## 🤝 Support

- GitHub Issues: [Create Issue](https://github.com/yourusername/isp-portal/issues)
- Documentation: [Wiki](https://github.com/yourusername/isp-portal/wiki)
