#!/bin/bash

# ===========================================
# ISP Portal - DigitalOcean Spaces Backup Script
# ===========================================

set -e

# Load environment variables
source /opt/isp-portal/.env 2>/dev/null || true

BACKUP_DIR="/opt/backups"
DATE=$(date +%Y%m%d_%H%M%S)
INSTALL_DIR="/opt/isp-portal"
RETENTION_DAYS=7

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}Starting backup at $(date)${NC}"

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup PostgreSQL
echo "Backing up PostgreSQL..."
docker exec postgres pg_dump -U ispportal ispportal | gzip > $BACKUP_DIR/postgres_$DATE.sql.gz
echo "  Created: postgres_$DATE.sql.gz"

# Backup MongoDB (GenieACS)
echo "Backing up MongoDB..."
docker exec mongo mongodump --archive --gzip > $BACKUP_DIR/mongo_$DATE.archive.gz
echo "  Created: mongo_$DATE.archive.gz"

# Backup Redis
echo "Backing up Redis..."
docker exec redis redis-cli -a "$REDIS_PASSWORD" BGSAVE 2>/dev/null || true
sleep 5
docker cp redis:/data/dump.rdb $BACKUP_DIR/redis_$DATE.rdb 2>/dev/null || true
echo "  Created: redis_$DATE.rdb"

# Backup configuration files
echo "Backing up configuration..."
tar -czf $BACKUP_DIR/config_$DATE.tar.gz \
    -C $INSTALL_DIR \
    .env \
    docker-compose.yml \
    traefik \
    monitoring \
    genieacs 2>/dev/null || true
echo "  Created: config_$DATE.tar.gz"

# Create combined backup
echo "Creating combined backup archive..."
tar -czf $BACKUP_DIR/full_backup_$DATE.tar.gz \
    -C $BACKUP_DIR \
    postgres_$DATE.sql.gz \
    mongo_$DATE.archive.gz \
    redis_$DATE.rdb \
    config_$DATE.tar.gz 2>/dev/null || true

# Upload to DigitalOcean Spaces
if [ -n "$DO_SPACES_BUCKET" ] && [ -n "$DO_SPACES_KEY" ]; then
    echo -e "${YELLOW}Uploading to DigitalOcean Spaces...${NC}"
    
    SPACES_ENDPOINT="${DO_SPACES_REGION}.digitaloceanspaces.com"
    
    # Upload using s3cmd
    if command -v s3cmd &> /dev/null; then
        s3cmd put $BACKUP_DIR/full_backup_$DATE.tar.gz \
            s3://$DO_SPACES_BUCKET/backups/full_backup_$DATE.tar.gz \
            --acl-private
        echo "  Uploaded to: s3://$DO_SPACES_BUCKET/backups/full_backup_$DATE.tar.gz"
        
        # Clean old backups from Spaces
        echo "Cleaning old backups from Spaces..."
        CUTOFF_DATE=$(date -d "$RETENTION_DAYS days ago" +%Y%m%d)
        s3cmd ls s3://$DO_SPACES_BUCKET/backups/ | while read -r line; do
            FILE_DATE=$(echo "$line" | grep -oP '\d{8}' | head -1)
            if [ -n "$FILE_DATE" ] && [ "$FILE_DATE" -lt "$CUTOFF_DATE" ]; then
                FILE_PATH=$(echo "$line" | awk '{print $4}')
                echo "  Deleting old backup: $FILE_PATH"
                s3cmd del "$FILE_PATH"
            fi
        done
    else
        echo "  s3cmd not found, skipping Spaces upload"
    fi
else
    echo "  Spaces not configured, skipping upload"
fi

# Cleanup old local backups
echo "Cleaning up old local backups..."
find $BACKUP_DIR -type f -name "*.gz" -mtime +$RETENTION_DAYS -delete
find $BACKUP_DIR -type f -name "*.rdb" -mtime +$RETENTION_DAYS -delete

# Remove individual backup files (keep only combined)
rm -f $BACKUP_DIR/postgres_$DATE.sql.gz
rm -f $BACKUP_DIR/mongo_$DATE.archive.gz
rm -f $BACKUP_DIR/redis_$DATE.rdb
rm -f $BACKUP_DIR/config_$DATE.tar.gz

echo -e "${GREEN}Backup completed at $(date)${NC}"
echo "Local backup: $BACKUP_DIR/full_backup_$DATE.tar.gz"
ls -lh $BACKUP_DIR/full_backup_$DATE.tar.gz
