#!/bin/bash

# ===========================================
# ISP Portal - Health Check Script
# ===========================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================="
echo "  ISP Portal Health Check"
echo "  $(date)"
echo "========================================="
echo ""

# Check Docker containers
echo "Docker Containers:"
echo "-----------------------------------------"

CONTAINERS=(
    "traefik"
    "isp-backend"
    "postgres"
    "redis"
    "mongo"
    "genieacs-cwmp"
    "genieacs-nbi"
    "genieacs-ui"
    "prometheus"
    "grafana"
)

ALL_HEALTHY=true

for container in "${CONTAINERS[@]}"; do
    STATUS=$(docker inspect --format='{{.State.Status}}' $container 2>/dev/null || echo "not found")
    HEALTH=$(docker inspect --format='{{.State.Health.Status}}' $container 2>/dev/null || echo "N/A")
    
    if [ "$STATUS" == "running" ]; then
        echo -e "  $container: ${GREEN}$STATUS${NC} (health: $HEALTH)"
    else
        echo -e "  $container: ${RED}$STATUS${NC}"
        ALL_HEALTHY=false
    fi
done

echo ""

# Check endpoints
echo "Endpoint Health:"
echo "-----------------------------------------"

check_endpoint() {
    local name=$1
    local url=$2
    local expected_code=${3:-200}
    
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$url" 2>/dev/null || echo "000")
    
    if [ "$HTTP_CODE" == "$expected_code" ]; then
        echo -e "  $name: ${GREEN}OK${NC} ($HTTP_CODE)"
    else
        echo -e "  $name: ${RED}FAIL${NC} ($HTTP_CODE)"
        ALL_HEALTHY=false
    fi
}

check_endpoint "Backend Health" "http://localhost:8000/health"
check_endpoint "Prometheus" "http://localhost:9090/-/healthy"
check_endpoint "Grafana" "http://localhost:3000/api/health"

echo ""

# Check disk space
echo "Disk Space:"
echo "-----------------------------------------"
df -h / | awk 'NR==2 {print "  Used: "$3" / "$2" ("$5")"}'

DISK_USAGE=$(df / | awk 'NR==2 {print $5}' | tr -d '%')
if [ "$DISK_USAGE" -gt 80 ]; then
    echo -e "  ${YELLOW}WARNING: Disk usage above 80%${NC}"
fi

echo ""

# Check memory
echo "Memory:"
echo "-----------------------------------------"
free -h | awk 'NR==2 {print "  Used: "$3" / "$2}'

echo ""

# Check database connections
echo "Database Connections:"
echo "-----------------------------------------"
PG_CONNECTIONS=$(docker exec postgres psql -U ispportal -d ispportal -t -c "SELECT count(*) FROM pg_stat_activity;" 2>/dev/null | tr -d ' ')
echo "  PostgreSQL: $PG_CONNECTIONS active connections"

REDIS_CLIENTS=$(docker exec redis redis-cli INFO clients 2>/dev/null | grep connected_clients | cut -d: -f2 | tr -d '\r')
echo "  Redis: $REDIS_CLIENTS connected clients"

echo ""

# Summary
echo "========================================="
if [ "$ALL_HEALTHY" = true ]; then
    echo -e "  Overall Status: ${GREEN}HEALTHY${NC}"
else
    echo -e "  Overall Status: ${RED}UNHEALTHY${NC}"
fi
echo "========================================="

# Exit with appropriate code
if [ "$ALL_HEALTHY" = true ]; then
    exit 0
else
    exit 1
fi
