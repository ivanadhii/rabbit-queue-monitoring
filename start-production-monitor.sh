#!/bin/bash

# Production GPS Queue Monitoring Startup Script
# Remote monitoring of GPS tracking queues with Discord alerts only

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Script version and info
VERSION="2.0.0"
SCRIPT_NAME="GPS Production Monitor"

echo -e "${BLUE}GPS Production Monitor v${VERSION}${NC}"
echo -e "${BLUE}================================================${NC}"
echo -e "${CYAN}Remote GPS Queue Monitoring System${NC}"
echo -e "${CYAN}Production-ready | Read-only | Discord alerts only${NC}"
echo ""

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${RED}=> .env file not found!${NC}"
    echo -e "${YELLOW}Please create .env file with target RabbitMQ configuration${NC}"
    echo ""
    echo -e "${YELLOW}Required variables:${NC}"
    echo "  RABBITMQ_HOST=<target_server_ip>"
    echo "  RABBITMQ_USERNAME=<readonly_user>"  
    echo "  RABBITMQ_PASSWORD=<password>"
    echo "  DISCORD_WEBHOOK_URL=<webhook_url>"
    echo ""
    echo -e "${YELLOW}Optional variables:${NC}"
    echo "  RABBITMQ_PORT=15672"
    echo "  COLLECTION_INTERVAL=15"
    echo "  ALERT_COOLDOWN_MINUTES=5"
    echo "  TARGET_SYSTEM_NAME=GPS-Production-Server"
    echo ""
    exit 1
fi

# Load environment variables
source .env

# Validate required environment variables
echo -e "${YELLOW}=> Validating configuration...${NC}"

REQUIRED_VARS=(
    "RABBITMQ_HOST"
    "RABBITMQ_USERNAME"
    "RABBITMQ_PASSWORD"
    "DISCORD_WEBHOOK_URL"
)

MISSING_VARS=()
for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        MISSING_VARS+=("$var")
    fi
done

if [ ${#MISSING_VARS[@]} -ne 0 ]; then
    echo -e "${RED}=> Missing required environment variables:${NC}"
    printf '%s\n' "${MISSING_VARS[@]}"
    exit 1
fi

# Set default values for optional variables
export RABBITMQ_PORT=${RABBITMQ_PORT:-15672}
export COLLECTION_INTERVAL=${COLLECTION_INTERVAL:-15}
export ALERT_COOLDOWN_MINUTES=${ALERT_COOLDOWN_MINUTES:-5}
export TARGET_SYSTEM_NAME=${TARGET_SYSTEM_NAME:-GPS-Production-Server}
export MONITORING_MODE=${MONITORING_MODE:-remote}
export READ_ONLY_MODE=${READ_ONLY_MODE:-true}
export HEALTH_CHECK_PORT=${HEALTH_CHECK_PORT:-8080}

echo -e "${GREEN}=> Configuration validation passed${NC}"

# Display target configuration
echo ""
echo -e "${PURPLE}=> Target Configuration:${NC}"
echo -e "   • RabbitMQ Server: ${RABBITMQ_HOST}:${RABBITMQ_PORT}"
echo -e "   • Username: ${RABBITMQ_USERNAME}"
echo -e "   • Target Name: ${TARGET_SYSTEM_NAME}"
echo -e "   • Mode: ${MONITORING_MODE} (${READ_ONLY_MODE})"
echo -e "   • Collection Interval: ${COLLECTION_INTERVAL}s"
echo -e "   • Alert Cooldown: ${ALERT_COOLDOWN_MINUTES} minutes"

# Test connectivity
echo ""
echo -e "${YELLOW}=> Testing connectivity...${NC}"

# Test target RabbitMQ connectivity
echo -e "${CYAN}Testing RabbitMQ connection...${NC}"
if curl -s --connect-timeout 10 -u "${RABBITMQ_USERNAME}:${RABBITMQ_PASSWORD}" \
   "http://${RABBITMQ_HOST}:${RABBITMQ_PORT}/api/overview" > /dev/null 2>&1; then
    echo -e "${GREEN}=> Target RabbitMQ server reachable${NC}"
    
    # Get RabbitMQ version info
    RABBITMQ_INFO=$(curl -s -u "${RABBITMQ_USERNAME}:${RABBITMQ_PASSWORD}" \
                    "http://${RABBITMQ_HOST}:${RABBITMQ_PORT}/api/overview" | \
                    python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    version = data.get('rabbitmq_version', 'unknown')
    node = data.get('node', 'unknown')
    print(f'   Version: {version}, Node: {node}')
except:
    print('   Version info unavailable')
" 2>/dev/null)
    echo -e "${CYAN}${RABBITMQ_INFO}${NC}"
else
    echo -e "${RED}=> Cannot reach RabbitMQ at ${RABBITMQ_HOST}:${RABBITMQ_PORT}${NC}"
    echo -e "${RED}   Please check:${NC}"
    echo -e "${RED}   • Network connectivity to target server${NC}"
    echo -e "${RED}   • RabbitMQ management plugin enabled${NC}"
    echo -e "${RED}   • Credentials in .env file${NC}"
    echo -e "${RED}   • Firewall rules allow port ${RABBITMQ_PORT}${NC}"
    exit 1
fi

# Test Discord webhook
echo -e "${CYAN}Testing Discord webhook...${NC}"
if python3 -c "
import sys, os
sys.path.append('scripts')
try:
    from discord_sender import DiscordAlertSender
    sender = DiscordAlertSender('${DISCORD_WEBHOOK_URL}')
    success = sender.test_webhook()
    sys.exit(0 if success else 1)
except Exception as e:
    print(f'Error: {e}')
    sys.exit(1)
" 2>/dev/null; then
    echo -e "${GREEN}=> Discord webhook working${NC}"
else
    echo -e "${RED}❌ Discord webhook test failed${NC}"
    echo -e "${RED}   Check webhook URL in .env file${NC}"
    echo -e "${RED}   Monitoring will NOT work without Discord alerts${NC}"
    exit 1
fi

# Validate queue configuration
echo -e "${CYAN}Validating queue configuration...${NC}"

QUEUE_CONFIG_FILE=${QUEUE_CONFIG_FILE:-config/queues.json}

if [ ! -f "${QUEUE_CONFIG_FILE}" ]; then
    echo -e "${YELLOW}=> Queue config file not found, creating default...${NC}"
    mkdir -p config
    
    # Create default configuration
    cat > "${QUEUE_CONFIG_FILE}" << 'EOF'
{
  "queue_monitoring": {
    "queues": {
      "gps_queue": {
        "category": "CORE",
        "thresholds": {
          "high_backlog": 100,
          "critical_lag_seconds": 10,
          "no_consumers_alert": true
        },
        "description": "Real-time GPS position data"
      },
      "gps_history_queue": {
        "category": "SUPPORT",
        "thresholds": {
          "high_backlog": 2000,
          "critical_lag_seconds": 300,
          "no_consumers_alert": false
        },
        "description": "Historical GPS data storage"
      }
    }
  }
}
EOF
    echo -e "${GREEN}=> Default queue configuration created${NC}"
else
    # Validate JSON syntax
    if python3 -c "
import json, sys
try:
    with open('${QUEUE_CONFIG_FILE}', 'r') as f:
        config = json.load(f)
    
    queues = config.get('queue_monitoring', {}).get('queues', {})
    core_queues = [q for q, c in queues.items() if c.get('category') == 'CORE']
    support_queues = [q for q, c in queues.items() if c.get('category') == 'SUPPORT']
    
    print(f'=> Configuration valid: {len(queues)} queues total')
    if core_queues:
        core_list = ', '.join(core_queues[:3])
        if len(core_queues) > 3:
            core_list += f'... (+{len(core_queues)-3} more)'
        print(f'   • CORE queues: {len(core_queues)} ({core_list})')
    if support_queues:
        support_list = ', '.join(support_queues[:3])
        if len(support_queues) > 3:
            support_list += f'... (+{len(support_queues)-3} more)'
        print(f'   • SUPPORT queues: {len(support_queues)} ({support_list})')
    
except Exception as e:
    print(f'=> Configuration error: {e}')
    sys.exit(1)
" 2>/dev/null; then
        QUEUE_INFO=$(python3 -c "
import json
try:
    with open('${QUEUE_CONFIG_FILE}', 'r') as f:
        config = json.load(f)
    
    queues = config.get('queue_monitoring', {}).get('queues', {})
    core_queues = [q for q, c in queues.items() if c.get('category') == 'CORE']
    support_queues = [q for q, c in queues.items() if c.get('category') == 'SUPPORT']
    
    print(f'=> Configuration valid: {len(queues)} queues total')
    if core_queues:
        core_list = ', '.join(core_queues[:3])
        if len(core_queues) > 3:
            core_list += f'... (+{len(core_queues)-3} more)'
        print(f'   • CORE queues: {len(core_queues)} ({core_list})')
    if support_queues:
        support_list = ', '.join(support_queues[:3])
        if len(support_queues) > 3:
            support_list += f'... (+{len(support_queues)-3} more)'
        print(f'   • SUPPORT queues: {len(support_queues)} ({support_list})')
    
except Exception as e:
    print(f'=> Configuration error: {e}')
" 2>/dev/null)
        echo -e "${GREEN}${QUEUE_INFO}${NC}"
    else
        echo -e "${RED}=> Invalid queue configuration file${NC}"
        exit 1
    fi
fi

# Check target queues exist
echo -e "${CYAN}Checking target queues on server...${NC}"
QUEUE_CHECK=$(curl -s -u "${RABBITMQ_USERNAME}:${RABBITMQ_PASSWORD}" \
              "http://${RABBITMQ_HOST}:${RABBITMQ_PORT}/api/queues" | \
              python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    queue_names = [q['name'] for q in data]
    
    # Load target queues from config
    try:
        with open('${QUEUE_CONFIG_FILE}', 'r') as f:
            config = json.load(f)
        target_queues = list(config.get('queue_monitoring', {}).get('queues', {}).keys())
    except:
        target_queues = ['gps_queue', 'gps_history_queue']
    
    found_queues = [q for q in target_queues if q in queue_names]
    missing_queues = [q for q in target_queues if q not in queue_names]
    
    print(f'Found {len(found_queues)}/{len(target_queues)} target queues')
    
    if found_queues:
        print('=> Available queues:')
        for queue in found_queues[:5]:
            print(f'   • {queue}')
        if len(found_queues) > 5:
            print(f'   • ... and {len(found_queues) - 5} more')
    
    if missing_queues:
        print('=> Missing queues:')
        for queue in missing_queues:
            print(f'   • {queue}')
        print('   (These queues will be skipped during monitoring)')
    
except Exception as e:
    print(f'Error checking queues: {e}')
")

echo -e "${CYAN}${QUEUE_CHECK}${NC}"

# Create necessary directories
echo ""
echo -e "${YELLOW}=> Creating directories...${NC}"
mkdir -p logs config
echo -e "${GREEN}=> Directories created${NC}"

# Check Docker availability
echo ""
echo -e "${YELLOW}=> Checking Docker...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${RED}=> Docker not found. Please install Docker first.${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}=> Docker Compose not found. Please install Docker Compose first.${NC}"
    exit 1
fi

echo -e "${GREEN}=> Docker environment ready${NC}"

# Build and start services
echo ""
echo -e "${YELLOW}=> Building GPS monitoring container...${NC}"
docker-compose build --pull

echo ""
echo -e "${YELLOW}=> Starting production monitoring...${NC}"
docker-compose up -d

# Wait for service to be ready
echo ""
echo -e "${YELLOW}=> Waiting for GPS monitor to start...${NC}"

WAIT_TIMEOUT=60
COUNTER=0

while [ $COUNTER -lt $WAIT_TIMEOUT ]; do
    if curl -s http://localhost:${HEALTH_CHECK_PORT}/health > /dev/null 2>&1; then
        echo -e "${GREEN}=> GPS monitor is healthy!${NC}"
        break
    fi
    echo -n "."
    sleep 2
    COUNTER=$((COUNTER + 2))
done

if [ $COUNTER -ge $WAIT_TIMEOUT ]; then
    echo -e "${RED}=> GPS monitor failed to start within ${WAIT_TIMEOUT} seconds${NC}"
    echo -e "${YELLOW}Check logs: docker-compose logs gps-monitor${NC}"
    echo ""
    echo -e "${YELLOW}Recent logs:${NC}"
    docker-compose logs --tail=20 gps-monitor
    exit 1
fi

# Get service status
echo ""
echo -e "${BLUE}=> GPS Production Monitoring System is Ready!${NC}"
echo -e "${BLUE}================================================${NC}"

# Display system information
echo ""
echo -e "${GREEN}=> System Information:${NC}"
echo -e "   • Service: GPS Production Monitor v${VERSION}"
echo -e "   • Mode: Remote monitoring (read-only)"
echo -e "   • Target: ${RABBITMQ_HOST}:${RABBITMQ_PORT}"
echo -e "   • Health Check: http://localhost:${HEALTH_CHECK_PORT}/health"
echo -e "   • Ready Check: http://localhost:${HEALTH_CHECK_PORT}/ready"

echo ""
echo -e "${GREEN}=> Monitoring Targets:${NC}"
echo -e "   • Target RabbitMQ: http://${RABBITMQ_HOST}:${RABBITMQ_PORT}"
echo -e "   • Collection Interval: ${COLLECTION_INTERVAL} seconds"
echo -e "   • Target System: ${TARGET_SYSTEM_NAME}"

echo ""
echo -e "${GREEN}=> Alerts & Notifications:${NC}"
echo -e "   • Discord alerts configured and tested"
echo -e "   • 14 alert types active"
echo -e "   • Recovery alerts enabled"
echo -e "   • Real-time configuration reload via file watching"

# Show running containers
echo ""
echo -e "${BLUE}=> Running Services:${NC}"
docker-compose ps

# Display logs preview
echo ""
echo -e "${CYAN}=> Recent Monitor Logs:${NC}"
echo -e "${CYAN}========================${NC}"
timeout 5 docker-compose logs --tail=10 gps-monitor || true

echo ""
echo -e "${YELLOW}=> Management Commands:${NC}"
echo -e "   • View logs:      ${NC}docker-compose logs -f gps-monitor"
echo -e "   • Stop system:    ${NC}docker-compose down"
echo -e "   • Restart:        ${NC}docker-compose restart gps-monitor"
echo -e "   • Check health:   ${NC}curl http://localhost:${HEALTH_CHECK_PORT}/health"
echo -e "   • Check ready:    ${NC}curl http://localhost:${HEALTH_CHECK_PORT}/ready"

echo ""
echo -e "${PURPLE}=> Configuration Management:${NC}"
echo -e "   • Edit queues:    ${NC}nano ${QUEUE_CONFIG_FILE}"
echo -e "   • Edit env:       ${NC}nano .env"
echo -e "   • Config reload:  ${NC}Automatic via file watching"
echo -e "   • Test Discord:   ${NC}python3 scripts/discord_sender.py"

echo ""
echo -e "${GREEN}=> GPS Production Monitoring is now active!${NC}"
echo -e "${GREEN}   => Monitoring GPS queues on ${RABBITMQ_HOST}${NC}"
echo -e "${GREEN}   => Check Discord for real-time alerts and notifications.${NC}"

# Optional: Follow logs
echo ""
read -p "$(echo -e ${CYAN}Follow monitor logs? [y/N]: ${NC})" -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${BLUE}Following GPS monitor logs (Ctrl+C to exit):${NC}"
    echo -e "${BLUE}================================================${NC}"
    docker-compose logs -f gps-monitor
fi