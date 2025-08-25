#!/usr/bin/env python3
"""
Discord Alert Sender for Production GPS Queue Monitoring
"""

import requests
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class DiscordAlertSender:
    """Handles Discord webhook notifications for GPS monitoring alerts"""
    
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        self.bot_name = "Rabbit Queue Alert"
        self.avatar_url = "https://cdn-icons-png.flaticon.com/128/7441/7441511.png"
        
        if not webhook_url:
            logger.warning("Discord webhook URL not provided - alerts will be disabled")
    
    def get_color_by_severity(self, severity: str) -> int:
        """Get Discord embed color based on severity"""
        colors = {
            "critical": 0xFF0000,  # Red
            "warning": 0xFFA500,   # Orange  
            "info": 0x00FF00,      # Green
            "resolved": 0x00FF00   # Green
        }
        return colors.get(severity.lower(), 0x808080)  # Gray default
    
    def get_alert_icon(self, alert_type: str, severity: str, status: str = "firing") -> str:
        """Get appropriate icon for alert type and severity"""
        # Recovery/resolved alerts use rabbit emoji
        if alert_type in ["recovery", "system_recovery", "connection_recovered"] or status == "resolved":
            return "🐰"
        
        # System startup and config changes use rabbit emoji
        if alert_type in ["system_startup", "configuration_change"]:
            return "🐰"
        
        # All other alerts use rotating light
        return "🚨"
    
    def create_embed(self, alert_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create Discord embed for alert"""
        severity = alert_data.get("severity", "warning")
        alert_type = alert_data.get("alert_type", "unknown")
        status = alert_data.get("status", "firing")
        
        # Get appropriate icon and color
        icon = self.get_alert_icon(alert_type, severity, status)
        color = self.get_color_by_severity(severity)
        
        # Create title based on alert
        alert_name = alert_data.get("alert_name", "GPS System Alert")
        if status == "resolved":
            title = f"{icon} {alert_name} - RESOLVED"
        elif severity == "critical":
            title = f"{icon} CRITICAL: {alert_name}"
        elif severity == "warning":
            title = f"{icon} WARNING: {alert_name}"
        else:
            title = f"{icon} {alert_name}"
        
        # Create embed
        embed = {
            "title": title,
            "description": alert_data.get("description", "GPS system alert"),
            "color": color,
            "fields": [],
            "footer": {
                "text": f"RabbitMQ Queue Watcher • {alert_data.get('system', 'Transportation')}",
                "icon_url": self.avatar_url
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Add context fields
        if "queue" in alert_data:
            embed["fields"].append({
                "name": "Queue",
                "value": f"`{alert_data['queue']}`",
                "inline": True
            })
        
        if "value" in alert_data:
            embed["fields"].append({
                "name": "Value", 
                "value": str(alert_data['value']),
                "inline": True
            })
        
        # Add severity
        severity_labels = {
            "critical": "CRITICAL",
            "warning": "WARNING", 
            "info": "INFO"
        }
        embed["fields"].append({
            "name": "Severity",
            "value": severity_labels.get(severity, severity.upper()),
            "inline": True
        })
        
        # Add queue category if available
        if "queue_category" in alert_data:
            embed["fields"].append({
                "name": "Category",
                "value": alert_data['queue_category'],
                "inline": True
            })
        
        # Add threshold information if available
        if "threshold" in alert_data:
            embed["fields"].append({
                "name": "Threshold",
                "value": str(alert_data['threshold']),
                "inline": True
            })
        
        # Add system health if available
        if "system_health" in alert_data:
            embed["fields"].append({
                "name": "System Health",
                "value": alert_data['system_health'],
                "inline": True
            })
        
        # Add target system info if available
        if "target_system" in alert_data:
            embed["fields"].append({
                "name": "Target System",
                "value": alert_data['target_system'],
                "inline": True
            })
        
        # Add monitoring mode if available
        if "monitoring_mode" in alert_data:
            embed["fields"].append({
                "name": "Mode",
                "value": alert_data['monitoring_mode'].title(),
                "inline": True
            })
        
        return embed
    
    def send_alert(self, alert_data: Dict[str, Any]) -> bool:
        """Send alert to Discord"""
        if not self.webhook_url:
            logger.warning("Discord webhook not configured - skipping alert")
            return False
        
        try:
            embed = self.create_embed(alert_data)
            
            payload = {
                "username": self.bot_name,
                "avatar_url": self.avatar_url,
                "embeds": [embed]
            }
            
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )
            
            if response.status_code == 204:
                logger.info(f"Discord alert sent: {alert_data.get('alert_name', 'Unknown')}")
                return True
            else:
                logger.error(f"Discord alert failed: HTTP {response.status_code}")
                if response.text:
                    logger.error(f"Discord error response: {response.text}")
                return False
                
        except requests.exceptions.Timeout:
            logger.error("Discord alert timeout - webhook unreachable")
            return False
        except requests.exceptions.ConnectionError:
            logger.error("Discord alert connection error - check network")
            return False
        except Exception as e:
            logger.error(f"Discord alert error: {e}")
            return False
    
    def test_webhook(self) -> bool:
        """Test Discord webhook with a simple message"""
        if not self.webhook_url:
            logger.error("No webhook URL configured for testing")
            return False
        
        test_alert = {
            "alert_name": "GPS Monitoring Test",
            "description": "Test Alert\n\nGPS monitoring system is working correctly!\n\nDiscord integration verified.",
            "severity": "info",
            "alert_type": "system_startup",
            "status": "firing",
            "system": "RMQ-Queue Test"
        }
        
        result = self.send_alert(test_alert)
        if result:
            logger.info("Discord webhook test successful")
        else:
            logger.error("Discord webhook test failed")
        
        return result


# Utility functions for testing
def test_discord_webhook():
    """Test Discord webhook with various alert types"""
    #webhook_url = "https://discord.com/api/webhooks/1407547385953124506/ilHPIO811RC9sQW9UBN6M3fG1GA2yOr0IZWVzYgUm6aqDe3Eo9sfH75NtvpjpimdNWXo"
    webhook_url = "https://discord.com/api/webhooks/1407207534313603182/tAwwVwss5Tfyd9Wu8ogn7O4KK4mb4elXg7hmDgTiVrmcyL3Rls770Svm2oDqyQpHkM_H"
    
    discord = DiscordAlertSender(webhook_url)
    
    # Test different alert types
    test_alerts = [
        {
            "alert_name": "GPS System Test",
            "description": "Test Alert\n\nGPS monitoring system test successful!\n\nAll systems operational.",
            "severity": "info",
            "alert_type": "system_startup",
            "status": "firing",
            "system": "RMQ-Queue",
            "target_system": "Test-Server",
            "monitoring_mode": "remote"
        },
        {
            "alert_name": "CORE Queue Backlog",
            "description": "CRITICAL BACKLOG\n\nCORE queue **gps_queue** has **1,247** messages pending!\n\nThreshold: 100 messages\nStatus: Queue growing rapidly",
            "severity": "critical",
            "alert_type": "queue_backlog",
            "status": "firing",
            "queue": "gps_queue",
            "value": "1,247 messages",
            "queue_category": "CORE",
            "threshold": "100",
            "system": "RMQ-Queue"
        },
        {
            "alert_name": "Queue Recovery",
            "description": "QUEUE RECOVERED\n\nCORE queue **gps_queue** has recovered!\n\nMessages processing normally\nConsumers active\nBacklog cleared\n\nRecovery time: 3.2 minutes",
            "severity": "info",
            "alert_type": "recovery",
            "status": "resolved",
            "queue": "gps_queue", 
            "value": "Recovered in 3.2 min",
            "queue_category": "CORE",
            "system": "RMQ-Queue"
        }
    ]
    
    for i, alert in enumerate(test_alerts, 1):
        print(f"Sending test alert {i}/{len(test_alerts)}: {alert['alert_name']}")
        success = discord.send_alert(alert)
        if success:
            print(f"✅ Test {i} sent successfully")
        else:
            print(f"❌ Test {i} failed")
        
        # Small delay between alerts
        if i < len(test_alerts):
            import time
            time.sleep(2)
    
    return True


if __name__ == "__main__":
    # Run webhook test
    test_discord_webhook()