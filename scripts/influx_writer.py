#!/usr/bin/env python3
"""
InfluxDB Writer for GPS Queue Monitoring
Handles time-series data storage and management
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
import re

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

logger = logging.getLogger(__name__)


class InfluxDBWriter:
    """Handles writing queue metrics to InfluxDB"""
    
    def __init__(self):
        # InfluxDB connection settings
        self.url = os.getenv('INFLUXDB_URL', 'http://localhost:8086')
        self.token = os.getenv('INFLUXDB_TOKEN', 'gps-monitoring-token')
        self.org = os.getenv('INFLUXDB_ORG', 'gps-monitoring')
        self.bucket = os.getenv('INFLUXDB_BUCKET', 'gps-metrics')
        
        # Initialize client
        self.client = None
        self.write_api = None
        self.query_api = None
        
        # Queue configuration cache
        self.queue_categories = {}
        
        self.initialize_client()
    
    def initialize_client(self):
        """Initialize InfluxDB client and APIs"""
        try:
            self.client = InfluxDBClient(
                url=self.url,
                token=self.token,
                org=self.org,
                timeout=30000  # 30 second timeout
            )
            
            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
            self.query_api = self.client.query_api()
            
            # Test connection
            health = self.client.health()
            if health.status == "pass":
                logger.info(f"InfluxDB connection successful: {self.url}")
            else:
                logger.error(f"InfluxDB health check failed: {health.status}")
                
        except Exception as e:
            logger.error(f"Failed to initialize InfluxDB client: {e}")
            raise
    
    def write_queue_metrics(self, queue_data: Dict[str, Dict]):
        """Write queue metrics to InfluxDB"""
        if not queue_data:
            logger.warning("No queue data to write")
            return
        
        points = []
        timestamp = datetime.now(timezone.utc)
        
        for queue_name, metrics in queue_data.items():
            try:
                # Determine queue category
                category = self.get_queue_category(queue_name)
                
                # Extract metrics with safe defaults
                messages_ready = metrics.get('messages_ready', 0)
                messages_unacked = metrics.get('messages_unacknowledged', 0)
                consumers = metrics.get('consumers', 0)
                
                # Extract rate information
                message_stats = metrics.get('message_stats', {})
                publish_rate = message_stats.get('publish_details', {}).get('rate', 0.0)
                deliver_rate = message_stats.get('deliver_get_details', {}).get('rate', 0.0)
                ack_rate = message_stats.get('ack_details', {}).get('rate', 0.0)
                
                # Create InfluxDB point
                point = Point("queue_metrics") \
                    .tag("queue_name", queue_name) \
                    .tag("category", category) \
                    .tag("environment", os.getenv("DEPLOYMENT_ENVIRONMENT", "production")) \
                    .field("messages_ready", int(messages_ready)) \
                    .field("messages_unacked", int(messages_unacked)) \
                    .field("consumer_count", int(consumers)) \
                    .field("incoming_rate", float(publish_rate)) \
                    .field("consume_rate", float(deliver_rate)) \
                    .field("ack_rate", float(ack_rate)) \
                    .time(timestamp, WritePrecision.S)
                
                # Add derived metrics
                total_messages = messages_ready + messages_unacked
                net_rate = deliver_rate - publish_rate
                processing_lag = messages_ready / deliver_rate if deliver_rate > 0 else 0
                
                point = point \
                    .field("total_messages", int(total_messages)) \
                    .field("net_rate", float(net_rate)) \
                    .field("processing_lag_seconds", float(processing_lag))
                
                points.append(point)
                
                logger.debug(f"Prepared metrics point for {queue_name}: "
                           f"ready={messages_ready}, consumers={consumers}, "
                           f"rates=in:{publish_rate:.1f}/out:{deliver_rate:.1f}")
                
            except Exception as e:
                logger.error(f"Error preparing metrics for queue {queue_name}: {e}")
                continue
        
        # Batch write to InfluxDB
        if points:
            try:
                self.write_api.write(bucket=self.bucket, record=points)
                logger.info(f"Successfully wrote {len(points)} metric points to InfluxDB")
                
            except Exception as e:
                logger.error(f"Failed to write metrics to InfluxDB: {e}")
                raise
        else:
            logger.warning("No valid metrics points to write")
    
    def get_queue_category(self, queue_name: str) -> str:
        """Determine queue category (CORE/SUPPORT)"""
        
        # Check cache first
        if queue_name in self.queue_categories:
            return self.queue_categories[queue_name]
        
        # Load from config if available
        category = self.get_category_from_config(queue_name)
        
        if not category:
            # Pattern-based categorization
            category = self.categorize_by_pattern(queue_name)
        
        # Cache the result
        self.queue_categories[queue_name] = category
        return category
    
    def get_category_from_config(self, queue_name: str) -> str:
        """Get category from configuration file"""
        try:
            import json
            config_file = os.getenv('QUEUE_CONFIG_FILE', 'config/queues.json')
            
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    
                queues = config.get('queue_monitoring', {}).get('queues', {})
                if queue_name in queues:
                    return queues[queue_name].get('category', 'SUPPORT')
                    
        except Exception as e:
            logger.debug(f"Could not load category from config: {e}")
        
        return None
    
    def categorize_by_pattern(self, queue_name: str) -> str:
        """Categorize queue based on naming patterns"""
        
        # CORE queue patterns (critical for operations)
        core_patterns = [
            r'^gps_queue(?!_history).*',      # GPS queues except history
            r'^current_position_queue.*',      # Real-time positioning
            r'^bus_tracking_queue.*',          # Bus tracking
            r'^pis_queue.*',                   # Passenger information
        ]
        
        for pattern in core_patterns:
            if re.match(pattern, queue_name, re.IGNORECASE):
                return "CORE"
        
        # Everything else is SUPPORT
        return "SUPPORT"
    
    def health_check(self) -> bool:
        """Check InfluxDB connection health"""
        try:
            health = self.client.health()
            return health.status == "pass"
        except Exception as e:
            logger.error(f"InfluxDB health check failed: {e}")
            return False
    
    def get_database_size(self) -> float:
        """Get approximate database size in MB"""
        try:
            query = f'''
            import "influxdata/influxdb/monitor"
            
            monitor.from(start: -5m, host: "", fn: (r) => r._measurement == "influxdb_database")
                |> filter(fn: (r) => r._field == "numBytes")
                |> filter(fn: (r) => r.bucket == "{self.bucket}")
                |> last()
            '''
            
            result = self.query_api.query(query)
            
            for table in result:
                for record in table.records:
                    bytes_size = record.get_value()
                    return bytes_size / (1024 * 1024)  # Convert to MB
            
            return 0.0
            
        except Exception as e:
            logger.error(f"Error getting database size: {e}")
            return 0.0
    
    def cleanup_old_data(self, retention_days: int = 30):
        """Clean up data older than retention period"""
        try:
            cutoff_time = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            cutoff_time = cutoff_time - timedelta(days=retention_days)
            
            delete_api = self.client.delete_api()
            delete_api.delete(
                start=datetime(1970, 1, 1, tzinfo=timezone.utc),
                stop=cutoff_time,
                predicate='_measurement="queue_metrics"',
                bucket=self.bucket,
                org=self.org
            )
            
            logger.info(f"Cleaned up data older than {retention_days} days")
            
        except Exception as e:
            logger.error(f"Error cleaning up old data: {e}")
    
    def close(self):
        """Close InfluxDB client connections"""
        if self.client:
            self.client.close()
            logger.info("InfluxDB client closed")


def main():
    """Test InfluxDB writer standalone"""
    import time
    
    # Setup logging
    logging.basicConfig(level=logging.DEBUG)
    
    # Test data
    test_queue_data = {
        'gps_queue_18': {
            'messages_ready': 1247,
            'messages_unacknowledged': 23,
            'consumers': 3,
            'message_stats': {
                'publish_details': {'rate': 45.2},
                'deliver_get_details': {'rate': 38.1},
                'ack_details': {'rate': 37.8}
            }
        },
        'bus_tracking_queue': {
            'messages_ready': 856,
            'messages_unacknowledged': 12,
            'consumers': 2,
            'message_stats': {
                'publish_details': {'rate': 32.1},
                'deliver_get_details': {'rate': 29.8},
                'ack_details': {'rate': 29.5}
            }
        }
    }
    
    try:
        # Initialize writer
        writer = InfluxDBWriter()
        
        # Test health check
        if writer.health_check():
            print("✅ InfluxDB connection healthy")
        else:
            print("❌ InfluxDB connection failed")
            return
        
        # Test writing data
        print("Writing test data...")
        writer.write_queue_metrics(test_queue_data)
        print("✅ Test data written successfully")
        
        # Test database size
        size_mb = writer.get_database_size()
        print(f"📊 Database size: {size_mb:.2f} MB")
        
        # Cleanup
        writer.close()
        print("✅ Writer closed")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")


if __name__ == "__main__":
    main()