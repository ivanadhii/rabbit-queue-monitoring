## Features

- Zero-Impact Monitoring - Read-only operations with no modifications to target system
- Remote Deployment - Monitor from any server with network access to target RabbitMQ
- Real-Time Discord Alerts - 14 types of notifications with recovery detection
- Dynamic Configuration - Hot-reload queue settings without service restart
- Health Endpoints - Built-in health checks and readiness monitoring
- Queue Categorization - CORE vs SUPPORT queue classification with different thresholds
- Recovery Tracking - Automatic detection and notification when issues are resolved
- File Watching - Configuration changes trigger automatic reload and notifications

## Architecture

```
GPS Monitor (Any Server) → HTTP API → Target RabbitMQ (172.20.36.171)
                        ↓
                   Discord Alerts
                        ↓
                 Health Endpoints (:8080)
```

## Queue Categories

CORE Queues: Critical
SUPPORT Queues: Background

## Alert Types

CRITICAL: Queue backlog, no consumers, system failure, connection lost
WARNING: SUPPORT queue issues, system degradation
INFO: Recovery notifications, startup/shutdown, configuration changes

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Network access to target RabbitMQ (port 15672)
- Discord webhook URL

### 1. Setup Target RabbitMQ

Edit `.env` with required settings:

```bash
RABBITMQ_HOST= 
RABBITMQ_USERNAME=
RABBITMQ_PASSWORD=
DISCORD_WEBHOOK_URL=
```

### 2. Configure Queues

Edit `config/queues.json`:

```json
{
  "queue_monitoring": {
    "queues": {
      "gps_queue_18": {
        "category": "CORE",
        "thresholds": {
          "high_backlog": 500,
          "critical_lag_seconds": 10,
          "no_consumers_alert": true
        },
        "description": "GPS QUEUE 18"
      },
      "gps_queue_11": {
        "category": "CORE",
        "thresholds": {
          "high_backlog": 1000,
          "critical_lag_seconds": 30,
          "no_consumers_alert": true
        },
        "description": "GPS QUEUE 11"
      }
    }
  }
}
```

### 3. Start Monitoring

```bash
chmod +x start-production-monitor.sh
./start-production-monitor.sh
```

```
docker compose up -d
```

### Configuration Updates

Edit `config/queues.json` 

### Health Endpoints

- `GET /health` - Service health status and configuration summary
- `GET /ready` - Target RabbitMQ connectivity status


### Queue Configuration

```json
{
  "queue_monitoring": {
    "queues": {
      "queue_name": {
        "category": "CORE|SUPPORT",
        "thresholds": {
          "high_backlog": 1000,
          "critical_lag_seconds": 60,
          "no_consumers_alert": true
        },
        "description": "Queue description"
      }
    }
  }
}
```

## Troubleshooting

**Cannot connect to RabbitMQ**:
```bash
curl -u username:password <TARGET RABBIT DESTINATION>:<PORT>/api/overview
```

**Discord alerts not working**:
```bash
python3 scripts/discord_sender.py
```

**Configuration not reloading**:
```bash
docker-compose logs gps-monitor | grep "Configuration"
cat config/queues.json | jq .
```

## Security

- All operations are read-only
- No modifications to target RabbitMQ
- No message content accessed
- Minimal network requirements (HTTP only)# rabbit-queue-monitoring
