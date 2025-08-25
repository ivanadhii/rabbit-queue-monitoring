#!/usr/bin/env python3
"""
Metrics Service for GPS Dashboard
Handles InfluxDB queries and data processing
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import csv
import json
from io import StringIO

from influxdb_client import InfluxDBClient
from influxdb_client.client.query_api import QueryApi

logger = logging.getLogger(__name__)


class MetricsService:
    """Service for handling metrics data operations"""
    
    def __init__(self):
        # InfluxDB connection settings
        self.url = os.getenv('INFLUXDB_URL', 'http://localhost:8086')
        self.token = os.getenv('INFLUXDB_TOKEN', 'gps-monitoring-token')
        self.org = os.getenv('INFLUXDB_ORG', 'gps-monitoring')
        self.bucket = os.getenv('INFLUXDB_BUCKET', 'gps-metrics')
        
        # Client instances
        self.client = None
        self.query_api = None
        
        # Cache for performance
        self.queue_cache = {}
        self.cache_ttl = 300  # 5 minutes
        self.last_cache_update = {}
    
    async def initialize(self):
        """Initialize InfluxDB client"""
        try:
            self.client = InfluxDBClient(
                url=self.url,
                token=self.token,
                org=self.org,
                timeout=30000
            )
            
            self.query_api = self.client.query_api()
            
            # Test connection
            health = self.client.health()
            if health.status != "pass":
                raise Exception(f"InfluxDB health check failed: {health.status}")
            
            logger.info(f"MetricsService initialized successfully: {self.url}")
            
        except Exception as e:
            logger.error(f"Failed to initialize MetricsService: {e}")
            raise
    
    async def health_check(self) -> bool:
        """Check InfluxDB connection health"""
        try:
            if not self.client:
                return False
            
            health = self.client.health()
            return health.status == "pass"
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    async def get_all_queues(self) -> List[Dict[str, Any]]:
        """Get list of all monitored queues"""
        try:
            query = f'''
            import "influxdata/influxdb/schema"
            
            schema.tagValues(
                bucket: "{self.bucket}",
                tag: "queue_name",
                predicate: (r) => r._measurement == "queue_metrics" and r._time >= -24h
            )
            '''
            
            result = self.query_api.query(query)
            
            queues = []
            for table in result:
                for record in table.records:
                    queue_name = record.get_value()
                    
                    # Get additional queue info
                    category = await self.get_queue_category(queue_name)
                    last_seen = await self.get_queue_last_activity(queue_name)
                    
                    queues.append({
                        "name": queue_name,
                        "category": category,
                        "last_seen": last_seen,
                        "status": "active" if last_seen else "inactive"
                    })
            
            # Sort: CORE first, then alphabetically
            return sorted(queues, key=lambda q: (0 if q['category'] == 'CORE' else 1, q['name']))
            
        except Exception as e:
            logger.error(f"Error getting queues: {e}")
            return []
    
    async def get_queue_timeseries(
        self, 
        queue_name: str, 
        time_range: str, 
        resolution: str = "5m"
    ) -> Dict[str, Any]:
        """Get time series data for specific queue"""
        try:
            # Map time ranges
            range_map = {"1h": "1h", "8h": "8h", "1d": "24h"}
            influx_range = range_map.get(time_range, "8h")
            
            # Base query for all metrics
            base_query = f'''
            from(bucket: "{self.bucket}")
                |> range(start: -{influx_range})
                |> filter(fn: (r) => r._measurement == "queue_metrics")
                |> filter(fn: (r) => r.queue_name == "{queue_name}")
                |> aggregateWindow(every: {resolution}, fn: mean, createEmpty: false)
                |> fill(column: "_value", usePrevious: true)
            '''
            
            # Get ready messages
            ready_query = base_query + '|> filter(fn: (r) => r._field == "messages_ready")'
            ready_result = self.query_api.query(ready_query)
            
            # Get rates
            incoming_query = base_query + '|> filter(fn: (r) => r._field == "incoming_rate")'
            incoming_result = self.query_api.query(incoming_query)
            
            consume_query = base_query + '|> filter(fn: (r) => r._field == "consume_rate")'
            consume_result = self.query_api.query(consume_query)
            
            # Get consumer count (use last value, not mean)
            consumer_query = f'''
            from(bucket: "{self.bucket}")
                |> range(start: -{influx_range})
                |> filter(fn: (r) => r._measurement == "queue_metrics")
                |> filter(fn: (r) => r.queue_name == "{queue_name}")
                |> filter(fn: (r) => r._field == "consumer_count")
                |> aggregateWindow(every: {resolution}, fn: last, createEmpty: false)
                |> fill(column: "_value", usePrevious: true)
            '''
            consumer_result = self.query_api.query(consumer_query)
            
            # Process results
            ready_data = self._process_timeseries_result(ready_result)
            incoming_data = self._process_timeseries_result(incoming_result)
            consume_data = self._process_timeseries_result(consume_result)
            consumer_data = self._process_timeseries_result(consumer_result)
            
            return {
                "queue_name": queue_name,
                "category": await self.get_queue_category(queue_name),
                "time_range": time_range,
                "resolution": resolution,
                "data": {
                    "ready_messages": ready_data,
                    "rates": self._combine_rate_data(incoming_data, consume_data),
                    "consumers": consumer_data
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting timeseries for {queue_name}: {e}")
            return {
                "queue_name": queue_name,
                "error": str(e),
                "data": {"ready_messages": [], "rates": [], "consumers": []}
            }
    
    def _process_timeseries_result(self, result) -> List[Dict[str, Any]]:
        """Process InfluxDB query result into time series data"""
        data = []
        for table in result:
            for record in table.records:
                data.append({
                    "timestamp": record.get_time().isoformat(),
                    "value": record.get_value()
                })
        return data
    
    def _combine_rate_data(self, incoming_data: List, consume_data: List) -> List[Dict[str, Any]]:
        """Combine incoming and consume rate data"""
        # Create timestamp-indexed dictionaries
        incoming_dict = {item["timestamp"]: item["value"] for item in incoming_data}
        consume_dict = {item["timestamp"]: item["value"] for item in consume_data}
        
        # Get all unique timestamps
        all_timestamps = sorted(set(incoming_dict.keys()) | set(consume_dict.keys()))
        
        combined = []
        for timestamp in all_timestamps:
            combined.append({
                "timestamp": timestamp,
                "incoming_rate": incoming_dict.get(timestamp, 0.0),
                "consume_rate": consume_dict.get(timestamp, 0.0)
            })
        
        return combined
    
    async def get_current_metrics(self) -> List[Dict[str, Any]]:
        """Get current metrics for all queues"""
        try:
            query = f'''
            from(bucket: "{self.bucket}")
                |> range(start: -1h)
                |> filter(fn: (r) => r._measurement == "queue_metrics")
                |> group(columns: ["queue_name", "category"])
                |> last()
                |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
            '''
            
            result = self.query_api.query(query)
            
            current_metrics = []
            for table in result:
                for record in table.records:
                    metrics = {
                        "queue_name": record.values.get("queue_name", "unknown"),
                        "category": record.values.get("category", "SUPPORT"),
                        "timestamp": record.get_time(),
                        "messages_ready": int(record.values.get("messages_ready", 0)),
                        "consumer_count": int(record.values.get("consumer_count", 0)),
                        "incoming_rate": float(record.values.get("incoming_rate", 0.0)),
                        "consume_rate": float(record.values.get("consume_rate", 0.0))
                    }
                    current_metrics.append(metrics)
            
            return current_metrics
            
        except Exception as e:
            logger.error(f"Error getting current metrics: {e}")
            return []
    
    async def get_queue_category(self, queue_name: str) -> str:
        """Get queue category from latest data"""
        try:
            query = f'''
            from(bucket: "{self.bucket}")
                |> range(start: -24h)
                |> filter(fn: (r) => r._measurement == "queue_metrics")
                |> filter(fn: (r) => r.queue_name == "{queue_name}")
                |> keep(columns: ["category"])
                |> last()
            '''
            
            result = self.query_api.query(query)
            
            for table in result:
                for record in table.records:
                    return record.values.get('category', 'SUPPORT')
            
            return 'SUPPORT'  # Default
            
        except Exception as e:
            logger.debug(f"Could not get category for {queue_name}: {e}")
            return 'SUPPORT'
    
    async def get_queue_last_activity(self, queue_name: str) -> Optional[datetime]:
        """Get last activity timestamp for queue"""
        try:
            query = f'''
            from(bucket: "{self.bucket}")
                |> range(start: -7d)
                |> filter(fn: (r) => r._measurement == "queue_metrics")
                |> filter(fn: (r) => r.queue_name == "{queue_name}")
                |> last()
                |> keep(columns: ["_time"])
            '''
            
            result = self.query_api.query(query)
            
            for table in result:
                for record in table.records:
                    return record.get_time()
            
            return None
            
        except Exception as e:
            logger.debug(f"Could not get last activity for {queue_name}: {e}")
            return None
    
    async def close(self):
        """Close InfluxDB client connections"""
        if self.client:
            self.client.close()
            logger.info("MetricsService client closed")