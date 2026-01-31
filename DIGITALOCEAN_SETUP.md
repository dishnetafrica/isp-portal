# DigitalOcean Droplet Setup Guide

Complete guide for deploying ISP Portal on DigitalOcean.

## 📋 Prerequisites Checklist

- [ ] DigitalOcean account
- [ ] Domain name
- [ ] UISP server running
- [ ] 10 minutes of time

---

## Step 1: Create DigitalOcean API Token

1. Go to: https://cloud.digitalocean.com/account/api/tokens
2. Click **"Generate New Token"**
3. Name it: `isp-portal`
4. Select: **Read + Write** permissions
5. Copy and save the token securely

---

## Step 2: Point Domain to DigitalOcean DNS

### If your domain is NOT on DigitalOcean:

1. Go to: https://cloud.digitalocean.com/networking/domains
2. Click **"Add Domain"**
3. Enter your domain (e.g., `example.com`)
4. At your domain registrar, update nameservers to:
   ```
   ns1.digitalocean.com
   ns2.digitalocean.com
   ns3.digitalocean.com
   ```
5. Wait 24-48 hours for DNS propagation

### If your domain is already on DigitalOcean:
You're ready! The deployment script will auto-create DNS records.

---

## Step 3: Create Droplet

### Option A: Via Web Console

1. Go to: https://cloud.digitalocean.com/droplets/new
2. Choose:
   - **Region**: Closest to your customers
   - **Image**: Ubuntu 22.04 (LTS) x64
   - **Size**: Basic → Regular → **$24/mo (4GB RAM, 2 vCPUs)** minimum
   - **Authentication**: SSH keys (recommended)
3. Enable:
   - [x] Monitoring
   - [x] IPv6
4. Click **Create Droplet**
5. Note the IP address

### Option B: Via CLI

```bash
# Install doctl
brew install doctl  # macOS
# or: snap install doctl  # Linux

# Authenticate
doctl auth init

# Create Droplet
doctl compute droplet create isp-portal \
  --region nyc3 \
  --size s-2vcpu-4gb \
  --image ubuntu-22-04-x64 \
  --ssh-keys YOUR_SSH_KEY_ID \
  --enable-monitoring \
  --enable-ipv6

# Get IP address
doctl compute droplet list
```

---

## Step 4: Deploy ISP Portal

### Connect to your Droplet:

```bash
ssh root@YOUR_DROPLET_IP
```

### Download and deploy:

```bash
# Download deployment package
wget https://github.com/yourusername/isp-portal/releases/latest/download/isp-portal.tar.gz
tar -xzf isp-portal.tar.gz
cd isp-portal

# Make scripts executable
chmod +x scripts/*.sh

# Run DigitalOcean-specific deployment
sudo ./scripts/deploy-digitalocean.sh
```

### You'll be prompted for:
1. Your domain name
2. DigitalOcean API token
3. UISP server URL

The script will automatically:
- Install Docker
- Create DNS records
- Configure cloud firewall
- Generate secure passwords
- Start all services
- Install DO monitoring agent

---

## Step 5: Verify Deployment

### Check services are running:
```bash
docker compose ps
```

All containers should show "Up" status.

### Check SSL certificates:
```bash
# Wait 2-5 minutes for SSL, then:
curl -I https://api.yourdomain.com
```

Should return `HTTP/2 200` with valid SSL.

### View credentials:
```bash
cat /opt/isp-portal/CREDENTIALS.txt
```

---

## Step 6: Configure UISP API Key (Optional)

For advanced billing features:

1. In UISP: Go to **System → Security → App Keys**
2. Create new key with read permissions
3. Add to configuration:

```bash
nano /opt/isp-portal/.env
# Add: UISP_API_KEY=your_key_here

# Restart backend
docker compose restart backend
```

---

## Step 7: (Optional) Setup Backups to Spaces

### Create Spaces bucket:
1. Go to: https://cloud.digitalocean.com/spaces
2. Click **"Create a Space"**
3. Choose region, name it (e.g., `isp-portal-backups`)
4. Settings: **Restrict File Listing** (private)

### Create Spaces access keys:
1. Go to: https://cloud.digitalocean.com/account/api/spaces
2. Click **"Generate New Key"**
3. Note the Key and Secret

### Configure backups:
```bash
nano /opt/isp-portal/.env

# Add:
DO_SPACES_BUCKET=isp-portal-backups
DO_SPACES_KEY=your_access_key
DO_SPACES_SECRET=your_secret_key
DO_SPACES_REGION=nyc3
```

### Setup automatic daily backups:
```bash
# Add cron job
(crontab -l 2>/dev/null; echo "0 3 * * * /opt/isp-portal/scripts/backup.sh >> /var/log/isp-backup.log 2>&1") | crontab -
```

---

## 🔧 Useful Commands

### View logs:
```bash
cd /opt/isp-portal
docker compose logs -f              # All services
docker compose logs -f backend      # Just backend
docker compose logs -f genieacs-cwmp # TR-069 logs
```

### Restart services:
```bash
docker compose restart              # All
docker compose restart backend      # Just one
```

### Update deployment:
```bash
cd /opt/isp-portal
git pull  # or download new version
docker compose pull
docker compose up -d
```

### Health check:
```bash
./scripts/health-check.sh
```

### Manual backup:
```bash
./scripts/backup.sh
```

---

## 🌐 Access URLs

| Service | URL | Description |
|---------|-----|-------------|
| API | `https://api.yourdomain.com` | Backend API |
| Traefik | `https://traefik.yourdomain.com` | Proxy dashboard |
| Grafana | `https://grafana.yourdomain.com` | Monitoring |
| GenieACS | `https://acs.yourdomain.com` | TR-069 management |
| Prometheus | `https://prometheus.yourdomain.com` | Metrics |
| TR-069 CWMP | `http://yourdomain.com:7547` | Router config URL |

---

## 🔥 Firewall Ports

The deployment automatically configures:

| Port | Protocol | Description |
|------|----------|-------------|
| 22 | TCP | SSH |
| 80 | TCP | HTTP (redirects to HTTPS) |
| 443 | TCP | HTTPS |
| 7547 | TCP | TR-069 CWMP |

---

## 💰 Cost Estimate

| Resource | Monthly Cost |
|----------|--------------|
| Droplet (4GB/2vCPU) | $24 |
| Spaces (250GB) | $5 |
| **Total** | **~$29/month** |

For larger deployments:
- 8GB Droplet: $48/month
- Managed PostgreSQL: +$15/month (optional, recommended for production)

---

## 🆘 Troubleshooting

### SSL not working:
```bash
# Check Traefik logs
docker compose logs traefik | grep -i error

# Verify DNS propagation
dig api.yourdomain.com
```

### Can't connect to services:
```bash
# Check if containers are running
docker compose ps

# Check firewall
ufw status
doctl compute firewall list
```

### TR-069 devices not connecting:
```bash
# Check CWMP logs
docker compose logs genieacs-cwmp

# Verify port is open
nc -zv yourdomain.com 7547
```

---

## 📞 Support

- GitHub Issues: [Create Issue](https://github.com/yourusername/isp-portal/issues)
- DigitalOcean Support: https://www.digitalocean.com/support
