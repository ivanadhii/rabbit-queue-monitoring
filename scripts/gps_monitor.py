#!/usr/bin/env python3
"""
Production Queue Monitoring System (Discord Only)
Remote monitoring of RabbitMQ queues for RMQ-Queue system
"""

import os
import json
import time
import requests
import logging
import threading
from datetime import datetime
from typing import Dict, Any, Tuple
from pathlib import Path

# File watching
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Import Discord sender and Health server
from discord_sender import DiscordAlertSender
from health_server import HealthServer

# Setup logging
logger = logging.getLogger(__name__)


class QueueConfigHandler(FileSystemEventHandler):
    """File system event handler for configuration changes"""
    
    def __init__(self, monitor_instance):
        self.monitor = monitor_instance
        
    def on_modified(self, event):
        if event.src_path.endswith('queues.json'):
            logger.info(f"Configuration file changed: {event.src_path}")
            time.sleep(0.5)  # Brief delay to ensure file write is complete
            self.monitor.reload_configuration()


class AlertRecoveryTracker:
    """Track alert states and detect recoveries"""
    
    def __init__(self):
        self.active_alerts = {}
        self.lock = threading.Lock()
    
    def track_alert(self, queue_name: str, alert_type: str):
        """Track when alert is sent"""
        with self.lock:
            self.active_alerts[queue_name] = {
                'type': alert_type,
                'timestamp': time.time(),
                'resolved': False
            }
    
    def check_recovery(self, queue_name: str, queue_data: Dict, monitor) -> bool:
        """Check if queue has recovered from previous alerts"""
        with self.lock:
            if queue_name not in self.active_alerts:
                return False
            
            alert_info = self.active_alerts[queue_name]
            if alert_info['resolved']:
                return False
            
            # Check recovery conditions
            messages_ready = queue_data.get('messages_ready', 0)
            consumers = queue_data.get('consumers', 0)
            threshold = monitor.get_queue_threshold(queue_name, 'high_backlog', 1000)
            
            is_recovered = (
                messages_ready < (threshold * 0.3) and  # Below 30% of alert threshold
                consumers > 0 and                       # Has active consumers
                messages_ready < 50                     # Reasonable queue size
            )
            
            if is_recovered:
                recovery_time = time.time() - alert_info['timestamp']
                monitor.send_recovery_alert(queue_name, recovery_time, alert_info['type'])
                alert_info['resolved'] = True
                return True
            
            return False


class ProductionGPSMonitor:
    """Production Queue Monitor with Discord-only alerting"""
    
    def __init__(self):
        # Configuration
        self.config_file = os.getenv('QUEUE_CONFIG_FILE', 'config/queues.json')
        self.config = {}
        self.target_queues = []
        self.core_queues = []
        self.support_queues = []
        self.queue_thresholds = {}
        
        # RabbitMQ connection settings
        self.rabbitmq_host = os.getenv('RABBITMQ_HOST', 'localhost')
        self.rabbitmq_port = int(os.getenv('RABBITMQ_PORT', 15672))
        self.rabbitmq_user = os.getenv('RABBITMQ_USERNAME', 'admin')
        self.rabbitmq_pass = os.getenv('RABBITMQ_PASSWORD', 'password')
        self.rabbitmq_url = f"http://{self.rabbitmq_host}:{self.rabbitmq_port}"
        self.auth = (self.rabbitmq_user, self.rabbitmq_pass)
        
        # Monitoring settings
        self.collection_interval = int(os.getenv('COLLECTION_INTERVAL', 15))
        self.alert_cooldown = int(os.getenv('ALERT_COOLDOWN_MINUTES', 5)) * 60
        
        # Alert management (Discord only)
        self.discord_webhook = os.getenv('DISCORD_WEBHOOK_URL')
        if not self.discord_webhook:
            raise ValueError("DISCORD_WEBHOOK_URL is required")
        
        self.discord_sender = DiscordAlertSender(self.discord_webhook)
        self.last_alert_time = {}
        self.recovery_tracker = AlertRecoveryTracker()
        
        # Production settings
        self.monitoring_mode = os.getenv('MONITORING_MODE', 'remote')
        self.read_only_mode = os.getenv('READ_ONLY_MODE', 'true').lower() == 'true'
        self.target_system_name = os.getenv('TARGET_SYSTEM_NAME', 'Remote-RabbitMQ')
        self.shutdown_notification_sent = False
        
        # Initialize components
        self.load_configuration()
        self.setup_file_watcher()
        self.setup_health_server()
        
        logger.info(f"Queue Monitor initialized - Mode: {self.monitoring_mode}")
        logger.info(f"Target: {self.rabbitmq_host}:{self.rabbitmq_port}")
        logger.info(f"Queues: {len(self.target_queues)} total ({len(self.core_queues)} CORE)")
        logger.info("Alert system: Discord only")
    
    def load_configuration(self):
        """Load queue configuration from JSON file"""
        if not os.path.exists(self.config_file):
            raise FileNotFoundError(f"Configuration file not found: {self.config_file}")
        
        try:
            with open(self.config_file, 'r') as f:
                self.config = json.load(f)
            
            self.parse_queue_configuration()
            self.validate_configuration()
            
            logger.info(f"Configuration loaded: {len(self.target_queues)} queues")
            logger.info(f"CORE queues: {self.core_queues}")
            logger.info(f"SUPPORT queues: {self.support_queues}")
            
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            raise
    
    def parse_queue_configuration(self):
        """Parse loaded configuration into working variables"""
        queues_config = self.config.get('queue_monitoring', {}).get('queues', {})
        
        self.target_queues = list(queues_config.keys())
        self.core_queues = []
        self.support_queues = []
        self.queue_thresholds = {}
        
        for queue_name, queue_config in queues_config.items():
            category = queue_config.get('category', 'SUPPORT')
            
            if category == 'CORE':
                self.core_queues.append(queue_name)
            else:
                self.support_queues.append(queue_name)
            
            # Store thresholds per queue
            self.queue_thresholds[queue_name] = queue_config.get('thresholds', {})
    
    def validate_configuration(self):
        """Basic validation of configuration"""
        errors = []
        
        # Check required structure
        if 'queue_monitoring' not in self.config:
            errors.append("Missing 'queue_monitoring' section")
            
        if 'queues' not in self.config.get('queue_monitoring', {}):
            errors.append("Missing 'queues' section")
        
        # Validate each queue
        for queue_name, config in self.config['queue_monitoring']['queues'].items():
            if 'category' not in config:
                errors.append(f"Queue '{queue_name}' missing 'category'")
            
            if config.get('category') not in ['CORE', 'SUPPORT']:
                errors.append(f"Queue '{queue_name}' invalid category: {config.get('category')}")
            
            if 'thresholds' not in config:
                errors.append(f"Queue '{queue_name}' missing 'thresholds'")
                continue
            
            # Check required thresholds
            thresholds = config['thresholds']
            required = ['high_backlog', 'critical_lag_seconds', 'no_consumers_alert']
            
            for threshold in required:
                if threshold not in thresholds:
                    errors.append(f"Queue '{queue_name}' missing threshold: {threshold}")
        
        if errors:
            raise ValueError(f"Configuration validation failed: {'; '.join(errors)}")
    
    def setup_file_watcher(self):
        """Setup file system watcher for configuration changes"""
        try:
            config_dir = os.path.dirname(os.path.abspath(self.config_file))
            
            self.config_handler = QueueConfigHandler(self)
            self.observer = Observer()
            self.observer.schedule(self.config_handler, config_dir, recursive=False)
            self.observer.start()
            
            logger.info(f"File watcher started for: {config_dir}")
            
        except Exception as e:
            logger.warning(f"File watcher setup failed: {e}")
    
    def setup_health_server(self):
        """Setup health check server"""
        try:
            self.health_server = HealthServer(self)
            self.health_server.start()
        except Exception as e:
            logger.error(f"Failed to start health server: {e}")
            raise RuntimeError(f"Cannot start health server: {e}")
    
    def get_queue_threshold(self, queue_name: str, threshold_type: str, default_value: int) -> int:
        """Get specific threshold for a queue"""
        return self.queue_thresholds.get(queue_name, {}).get(threshold_type, default_value)
    
    def is_core_queue(self, queue_name: str) -> bool:
        """Check if queue is CORE priority"""
        return queue_name in self.core_queues
    
    def should_alert_no_consumers(self, queue_name: str) -> bool:
        """Check if should alert when no consumers"""
        return self.queue_thresholds.get(queue_name, {}).get('no_consumers_alert', False)
    
    def get_queue_details(self) -> Dict[str, Dict]:
        """Get queue details from RabbitMQ Management API"""
        try:
            response = requests.get(
                f"{self.rabbitmq_url}/api/queues",
                auth=self.auth,
                timeout=10
            )
            response.raise_for_status()
            
            # Filter only target queues
            all_queues = response.json()
            target_queue_data = {}
            
            for queue in all_queues:
                queue_name = queue.get('name', '')
                if queue_name in self.target_queues:
                    target_queue_data[queue_name] = queue
            
            return target_queue_data
            
        except Exception as e:
            logger.error(f"Error fetching queue details: {e}")
            return {}
    
    def categorize_queue_status(self, queue_data: Dict) -> Tuple[str, float, str]:
        """Categorize queue processing status"""
        messages_ready = queue_data.get('messages_ready', 0)
        message_stats = queue_data.get('message_stats', {})
        
        publish_rate = message_stats.get('publish_details', {}).get('rate', 0)
        deliver_rate = message_stats.get('deliver_get_details', {}).get('rate', 0)
        net_rate = deliver_rate - publish_rate
        
        if net_rate > 0.1:  # Queue draining
            lag = messages_ready / net_rate if net_rate > 0 else 0
            return "DRAINING", lag, f"Queue clearing in {lag:.1f}s"
        
        elif abs(net_rate) <= 0.1:  # Stable
            if deliver_rate > 0:
                stable_lag = messages_ready / deliver_rate
                return "STABLE", stable_lag, f"Stable {stable_lag:.1f}s lag"
            else:
                return "STALLED", 999, "No processing activity"
        
        else:  # Growing queue
            growth_rate = abs(net_rate)
            return "GROWING", 9999, f"Growing at {growth_rate:.1f} msg/sec"
    
    def get_queue_status_icon(self, queue_data: Dict, queue_name: str) -> str:
        """Get simple status icon based on queue condition"""
        messages_ready = queue_data.get('messages_ready', 0)
        consumers = queue_data.get('consumers', 0)
        high_backlog_threshold = self.get_queue_threshold(queue_name, 'high_backlog', 1000)
        
        # Simple, clear status based on real conditions
        if consumers == 0 and messages_ready > 0:
            return "CRITICAL"    # No processing
        elif messages_ready > high_backlog_threshold:
            return "WARNING"     # High backlog
        else:
            return "HEALTHY"     # Normal operation
    
    def should_send_alert(self, alert_key: str) -> bool:
        """Check if enough time has passed for alert cooldown"""
        now = time.time()
        if alert_key not in self.last_alert_time:
            self.last_alert_time[alert_key] = now
            return True
        
        if now - self.last_alert_time[alert_key] > self.alert_cooldown:
            self.last_alert_time[alert_key] = now
            return True
        
        return False
    
    def send_discord_alert(self, alert_data: Dict[str, Any]) -> bool:
        """Send alert to Discord"""
        try:
            return self.discord_sender.send_alert(alert_data)
        except Exception as e:
            logger.error(f"Discord alert failed: {e}")
            return False
    
    def send_recovery_alert(self, queue_name: str, recovery_time: float, original_alert_type: str):
        """Send recovery alert for a queue"""
        alert_data = {
            "alert_name": "Queue Recovery",
            "description": f"QUEUE RECOVERED\n\n{'CORE' if self.is_core_queue(queue_name) else 'SUPPORT'} queue **{queue_name}** has recovered!\n\nMessages processing normally\nConsumers active\nBacklog cleared\n\nRecovery time: {recovery_time/60:.1f} minutes",
            "severity": "info",
            "alert_type": "recovery",
            "status": "resolved",
            "queue": queue_name,
            "value": f"Recovered in {recovery_time/60:.1f} min",
            "queue_category": "CORE" if self.is_core_queue(queue_name) else "SUPPORT",
            "original_alert": original_alert_type,
            "system": "RMQ-Queue"
        }
        self.send_discord_alert(alert_data)
    
    def check_queue_alerts(self, queue_name: str, queue_data: Dict):
        """Check for alert conditions and send notifications"""
        messages_ready = queue_data.get('messages_ready', 0)
        consumers = queue_data.get('consumers', 0)
        
        # Get queue-specific thresholds
        high_backlog_threshold = self.get_queue_threshold(queue_name, 'high_backlog', 1000)
        should_alert_consumers = self.should_alert_no_consumers(queue_name)
        
        # Determine severity based on category
        is_core = self.is_core_queue(queue_name)
        base_severity = "critical" if is_core else "warning"
        category_name = "CORE" if is_core else "SUPPORT"
        
        # Check for recovery first
        self.recovery_tracker.check_recovery(queue_name, queue_data, self)
        
        # High backlog alert
        if messages_ready > high_backlog_threshold:
            alert_key = f"backlog_{queue_name}"
            if self.should_send_alert(alert_key):
                status, lag, description = self.categorize_queue_status(queue_data)
                
                trend_description = ""
                if status == "GROWING":
                    trend_description = " (GROWING - getting worse!)"
                elif status == "STABLE":
                    trend_description = " (stable backlog)"
                elif status == "DRAINING":
                    trend_description = " (draining - improving)"
                
                alert_data = {
                    "alert_name": f"{category_name} Queue Backlog",
                    "description": f"CRITICAL BACKLOG{trend_description}\n\n{category_name} queue **{queue_name}** has **{messages_ready:,}** messages pending!\n\nThreshold: {high_backlog_threshold:,} messages\nStatus: {description}",
                    "severity": base_severity,
                    "alert_type": "queue_backlog",
                    "status": "firing",
                    "queue": queue_name,
                    "value": f"{messages_ready:,} messages",
                    "queue_category": category_name,
                    "threshold": high_backlog_threshold,
                    "system": "RMQ-Queue"
                }
                self.send_discord_alert(alert_data)
                self.recovery_tracker.track_alert(queue_name, "queue_backlog")
        
        # No consumers alert
        if should_alert_consumers and consumers == 0 and messages_ready > 0:
            alert_key = f"no_consumers_{queue_name}"
            if self.should_send_alert(alert_key):
                alert_data = {
                    "alert_name": f"{category_name} No Consumers",
                    "description": f"NO CONSUMERS\n\n{category_name} queue **{queue_name}** has **{messages_ready}** messages but **NO CONSUMERS**!\n\nProcessing completely stopped.",
                    "severity": "critical",
                    "alert_type": "no_consumers", 
                    "status": "firing",
                    "queue": queue_name,
                    "value": f"0 consumers, {messages_ready} messages",
                    "queue_category": category_name,
                    "system": "RMQ-Queue"
                }
                self.send_discord_alert(alert_data)
                self.recovery_tracker.track_alert(queue_name, "no_consumers")
        
        # Stalled queue alert (no messages and no consumers)
        if messages_ready == 0 and consumers == 0:
            alert_key = f"stalled_{queue_name}"
            if self.should_send_alert(alert_key):
                alert_data = {
                    "alert_name": f"{category_name} Queue Stalled",
                    "description": f"QUEUE STALLED\n\nQueue **{queue_name}** has **NO MESSAGES** and **NO CONSUMERS**!\n\nNo activity detected - system may be down.",
                    "severity": "critical",
                    "alert_type": "stalled_queue",
                    "status": "firing", 
                    "queue": queue_name,
                    "value": "0 messages, 0 consumers",
                    "queue_category": category_name,
                    "system": "RMQ-Queue"
                }
                self.send_discord_alert(alert_data)
                self.recovery_tracker.track_alert(queue_name, "stalled_queue")
    
    def collect_metrics(self):
        """Main metrics collection and alerting logic"""
        queue_data = self.get_queue_details()
        
        if not queue_data:
            logger.warning("No queue data received from RabbitMQ")
            return
        
        total_backlog = 0
        core_healthy = 0
        total_core = len(self.core_queues)
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logger.info(f"Queue Status - {timestamp}")
        logger.info("=" * 90)
        
        for queue_name in self.target_queues:
            if queue_name not in queue_data:
                logger.warning(f"Queue '{queue_name}' not found on target server")
                continue
            
            queue = queue_data[queue_name]
            category = "CORE" if self.is_core_queue(queue_name) else "SUPPORT"
            
            # Extract metrics
            messages_ready = queue.get('messages_ready', 0)
            messages_unacked = queue.get('messages_unacknowledged', 0)
            consumers = queue.get('consumers', 0)
            
            message_stats = queue.get('message_stats', {})
            publish_rate = message_stats.get('publish_details', {}).get('rate', 0)
            deliver_rate = message_stats.get('deliver_get_details', {}).get('rate', 0)
            
            # Get simple status
            status_icon = self.get_queue_status_icon(queue, queue_name)
            status, lag, status_desc = self.categorize_queue_status(queue)
            
            # Track healthy CORE queues (simple logic)
            if category == "CORE" and status_icon == "HEALTHY":
                core_healthy += 1
            
            total_backlog += messages_ready
            
            # Enhanced console output with rate information
            logger.info(f"{status_icon:<12} {queue_name:<25} | "
                       f"Ready: {messages_ready:>6} | "
                       f"Consumers: {consumers:>2} | "
                       f"Rate: {publish_rate:>5.1f}/s | "
                       f"Status: {status}")
            
            # Check for alerts
            self.check_queue_alerts(queue_name, queue)
        
        logger.info("=" * 90)
        logger.info(f"Total Backlog: {total_backlog:,} messages")
        logger.info(f"CORE Queues Healthy: {core_healthy}/{total_core}")
        
        # System-wide alerts
        self.check_system_alerts(total_backlog, core_healthy, total_core)
    
    def check_system_alerts(self, total_backlog: int, core_healthy: int, total_core: int):
        """Check for system-wide alert conditions"""
        
        # System-wide high backlog
        if total_backlog > 10000:
            alert_key = "system_backlog"
            if self.should_send_alert(alert_key):
                alert_data = {
                    "alert_name": "System-Wide High Backlog",
                    "description": f"SYSTEM BACKLOG HIGH\n\nTotal Queue system has **{total_backlog:,}** messages pending!\n\nMultiple queues experiencing backlogs.\n\nSuggestion: Scale consumers or optimize processing.",
                    "severity": "warning",
                    "alert_type": "system_backlog",
                    "status": "firing",
                    "value": f"{total_backlog:,} messages",
                    "affected_queues": f"{len([q for q in self.target_queues if q in self.get_queue_details()])}",
                    "system": "RMQ-Queue"
                }
                self.send_discord_alert(alert_data)
        
        # Critical system failure
        if total_core > 0:
            core_health_ratio = core_healthy / total_core
            if core_health_ratio < 0.5:
                alert_key = "critical_system_failure"
                if self.should_send_alert(alert_key):
                    alert_data = {
                        "alert_name": "Critical System Failure",
                        "description": f"SYSTEM FAILURE\n\nOnly **{core_healthy}/{total_core}** CORE Queue queues are healthy!\n\nImmediate attention required.\n\nImpact: Severe service degradation",
                        "severity": "critical",
                        "alert_type": "system_failure",
                        "status": "firing",
                        "value": f"{core_healthy}/{total_core} healthy",
                        "system_health": f"{core_health_ratio*100:.0f}%",
                        "system": "RMQ-Queue"
                    }
                    self.send_discord_alert(alert_data)
    
    def send_startup_notification(self):
        """Send startup notification to Discord"""
        alert_data = {
            "alert_name": "Queue Monitoring Started",
            "description": f"QUEUE MONITORING ONLINE\n\nMonitoring {len(self.target_queues)} queues\nConnected to {self.target_system_name}\nDiscord alerts active\n\nCORE Queues: {len(self.core_queues)}\nSUPPORT Queues: {len(self.support_queues)}\nTarget: {self.rabbitmq_host}:{self.rabbitmq_port}\n\nAlert System: Discord Only",
            "severity": "info",
            "alert_type": "system_startup",
            "status": "firing",
            "system": "RMQ-Queue",
            "target_system": self.target_system_name,
            "monitoring_mode": self.monitoring_mode
        }
        self.send_discord_alert(alert_data)
    
    def send_shutdown_notification(self):
        """Send shutdown notification to Discord"""
        if self.shutdown_notification_sent:
            return                           
    
        self.shutdown_notification_sent = True

        alert_data = {
            "alert_name": "Queue Monitoring Stopped",
            "description": f"QUEUE MONITORING OFFLINE\n\nMonitoring shutdown detected\nNo more alerts will be sent until restart.\n\nTarget: {self.target_system_name}\nMode: {self.monitoring_mode}",
            "severity": "warning",
            "alert_type": "system_shutdown",
            "status": "firing",
            "system": "RMQ-Queue"
        }
        self.send_discord_alert(alert_data)
    
    def reload_configuration(self):
        """Reload configuration from file"""
        try:
            logger.info("Reloading queue configuration...")
            
            # Store old configuration for comparison
            old_core = set(self.core_queues)
            old_support = set(self.support_queues)
            old_targets = set(self.target_queues)
            
            # Load new configuration
            self.load_configuration()
            
            # Compare changes
            new_core = set(self.core_queues)
            new_support = set(self.support_queues)
            new_targets = set(self.target_queues)
            
            # Report changes
            added_queues = new_targets - old_targets
            removed_queues = old_targets - new_targets
            category_changes = []
            
            # Check for category changes
            for queue in old_targets & new_targets:
                old_cat = "CORE" if queue in old_core else "SUPPORT"
                new_cat = "CORE" if queue in new_core else "SUPPORT"
                if old_cat != new_cat:
                    category_changes.append(f"{queue}: {old_cat}→{new_cat}")
            
            changes = []
            if added_queues:
                changes.append(f"Added: {', '.join(added_queues)}")
            if removed_queues:
                changes.append(f"Removed: {', '.join(removed_queues)}")
            if category_changes:
                changes.append(f"Category changed: {'; '.join(category_changes)}")
            
            if changes:
                change_summary = "; ".join(changes)
                logger.info(f"Configuration changes: {change_summary}")
                
                # Send Discord notification about config change
                alert_data = {
                    "alert_name": "Configuration Changed",
                    "description": f"QUEUE MONITORING CONFIG UPDATED\n\nConfiguration reloaded successfully:\n\n{change_summary}\n\nMonitoring automatically adjusted to new configuration.",
                    "severity": "info",
                    "alert_type": "configuration_change",
                    "status": "firing",
                    "value": change_summary,
                    "system": "Queue Monitoring"
                }
                self.send_discord_alert(alert_data)
            else:
                logger.info("Configuration reloaded - no changes detected")
                
        except Exception as e:
            logger.error(f"Error reloading configuration: {e}")
    
    def run(self):
        """Main monitoring loop"""
        logger.info("Starting Queue Queue Monitoring")
        logger.info(f"Target: {self.rabbitmq_host}:{self.rabbitmq_port}")
        logger.info(f"Mode: {self.monitoring_mode} (read-only: {self.read_only_mode})")
        logger.info(f"Queues: {len(self.target_queues)} total ({len(self.core_queues)} CORE)")
        logger.info("Alert system: Discord only")
        
        # Test connectivity
        try:
            response = requests.get(f"{self.rabbitmq_url}/api/overview", auth=self.auth, timeout=10)
            response.raise_for_status()
            logger.info("Successfully connected to target RabbitMQ")
        except Exception as e:
            logger.error(f"Failed to connect to target RabbitMQ: {e}")
            raise
        
        # Send startup notification
        self.send_startup_notification()
        
        logger.info(f"Starting monitoring loop (interval: {self.collection_interval}s)")
        logger.info("Press Ctrl+C to stop...")
        
        try:
            while True:
                start_time = time.time()
                
                try:
                    self.collect_metrics()
                except Exception as e:
                    logger.error(f"Error in metrics collection: {e}")
                
                # Calculate sleep time to maintain interval
                elapsed = time.time() - start_time
                sleep_time = max(0, self.collection_interval - elapsed)
                
                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    logger.warning(f"Metrics collection took {elapsed:.1f}s (longer than {self.collection_interval}s interval)")
                
        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}")
            raise
        finally:
            # Cleanup
            if hasattr(self, 'observer'):
                self.observer.stop()
                self.observer.join()
            
            if hasattr(self, 'health_server'):
                self.health_server.stop()
            
            # Send shutdown notification
            self.send_shutdown_notification()


if __name__ == "__main__":
    monitor = ProductionGPSMonitor()
    monitor.run()