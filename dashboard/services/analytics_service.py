#!/usr/bin/env python3
"""
Analytics Service for GPS Dashboard
Handles storage analytics, growth projections, and system insights
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import asyncio

from influxdb_client import InfluxDBClient
from influxdb_client.client.query_api import QueryApi

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Service for handling analytics and storage insights"""
    
    def __init__(self):
        # InfluxDB connection settings
        self.url = os.getenv('INFLUXDB_URL', 'http://localhost:8086')
        self.token = os.getenv('INFLUXDB_TOKEN', 'gps-monitoring-token')
        self.org = os.getenv('INFLUXDB_ORG', 'gps-monitoring')
        self.bucket = os.getenv('INFLUXDB_BUCKET', 'gps-metrics')
        
        # Client instances
        self.client = None
        self.query_api = None
        
        # Analytics cache
        self.cache = {}
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
            
            logger.info(f"AnalyticsService initialized successfully: {self.url}")
            
        except Exception as e:
            logger.error(f"Failed to initialize AnalyticsService: {e}")
            raise
    
    async def get_storage_analytics(self) -> Dict[str, Any]:
        """Get comprehensive storage analytics"""
        try:
            # Get basic metrics
            current_size = await self.get_database_size()
            data_points = await self.get_total_data_points()
            daily_growth = await self.calculate_daily_growth()
            queue_stats = await self.get_queue_statistics()
            
            # Calculate projections
            projections = await self.calculate_storage_projections(daily_growth)
            
            return {
                "current_usage": {
                    "total_size_mb": current_size,
                    "data_points": data_points,
                    "active_queues": queue_stats["active_queues"],
                    "collection_rate": queue_stats["collections_per_minute"],
                    "retention_days": 30
                },
                "growth": {
                    "daily_mb": daily_growth,
                    "weekly_mb": daily_growth * 7,
                    "monthly_mb": daily_growth * 30
                },
                "projections": projections,
                "breakdown": await self.get_storage_breakdown(),
                "last_updated": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting storage analytics: {e}")
            return {
                "error": str(e),
                "current_usage": {
                    "total_size_mb": 0,
                    "data_points": 0,
                    "active_queues": 0,
                    "collection_rate": 0,
                    "retention_days": 30
                }
            }
    
    async def get_database_size(self) -> float:
        """Get InfluxDB storage size in MB"""
        try:
            # Method 1: Try InfluxDB system monitoring
            query = f'''
            import "influxdata/influxdb/monitor"
            
            monitor.from(start: -5m)
                |> filter(fn: (r) => r._measurement == "influxdb_database")
                |> filter(fn: (r) => r._field == "numBytes")
                |> filter(fn: (r) => r.bucket == "{self.bucket}")
                |> last()
            '''
            
            result = self.query_api.query(query)
            
            for table in result:
                for record in table.records:
                    bytes_size = record.get_value()
                    return bytes_size / (1024 * 1024)  # Convert to MB
            
            # Method 2: Estimate based on data points
            data_points = await self.get_total_data_points()
            estimated_mb = (data_points * 25) / (1024 * 1024)  # ~25 bytes per point
            
            return estimated_mb
            
        except Exception as e:
            logger.error(f"Error getting database size: {e}")
            return 0.0
    
    async def get_total_data_points(self) -> int:
        """Get total number of data points stored"""
        try:
            query = f'''
            from(bucket: "{self.bucket}")
                |> range(start: -30d)
                |> filter(fn: (r) => r._measurement == "queue_metrics")
                |> count()
                |> sum()
            '''
            
            result = self.query_api.query(query)
            
            total_points = 0
            for table in result:
                for record in table.records:
                    total_points += record.get_value()
            
            return total_points
            
        except Exception as e:
            logger.error(f"Error getting total data points: {e}")
            return 0
    
    async def calculate_daily_growth(self) -> float:
        """Calculate average daily storage growth in MB"""
        try:
            # Get data points for last 7 days
            query = f'''
            from(bucket: "{self.bucket}")
                |> range(start: -7d)
                |> filter(fn: (r) => r._measurement == "queue_metrics")
                |> aggregateWindow(every: 1d, fn: count)
                |> sum()
                |> mean()
            '''
            
            result = self.query_api.query(query)
            
            daily_points = 0
            for table in result:
                for record in table.records:
                    daily_points = record.get_value()
                    break
            
            # Convert to MB (assuming ~25 bytes per point)
            daily_mb = (daily_points * 25) / (1024 * 1024)
            
            return daily_mb
            
        except Exception as e:
            logger.error(f"Error calculating daily growth: {e}")
            # Fallback calculation
            current_points = await self.get_current_daily_points()
            estimated_mb_per_point = 0.000025  # ~25 bytes per point
            return current_points * estimated_mb_per_point
    
    async def get_current_daily_points(self) -> int:
        """Get current daily data point collection rate"""
        try:
            query = f'''
            from(bucket: "{self.bucket}")
                |> range(start: -24h)
                |> filter(fn: (r) => r._measurement == "queue_metrics")
                |> count()
                |> sum()
            '''
            
            result = self.query_api.query(query)
            
            for table in result:
                for record in table.records:
                    return record.get_value()
            
            return 0
            
        except Exception as e:
            logger.error(f"Error getting current daily points: {e}")
            return 0
    
    async def get_queue_statistics(self) -> Dict[str, Any]:
        """Get queue-related statistics"""
        try:
            # Get unique queues in last 24 hours
            queue_query = f'''
            import "influxdata/influxdb/schema"
            
            schema.tagValues(
                bucket: "{self.bucket}",
                tag: "queue_name",
                predicate: (r) => r._measurement == "queue_metrics" and r._time >= -24h
            )
            '''
            
            queue_result = self.query_api.query(queue_query)
            
            queue_count = 0
            for table in queue_result:
                for record in table.records:
                    queue_count += 1
            
            # Calculate collection rate
            daily_points = await self.get_current_daily_points()
            collections_per_minute = daily_points / (24 * 60) if daily_points > 0 else 0
            
            return {
                "active_queues": queue_count,
                "collections_per_minute": round(collections_per_minute, 2),
                "estimated_interval_seconds": 60 / collections_per_minute if collections_per_minute > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Error getting queue statistics: {e}")
            return {
                "active_queues": 0,
                "collections_per_minute": 0,
                "estimated_interval_seconds": 0
            }
    
    async def calculate_storage_projections(self, daily_growth_mb: float) -> Dict[str, Any]:
        """Calculate storage growth projections"""
        try:
            current_size = await self.get_database_size()
            
            return {
                "1_month": {
                    "size_mb": round(current_size + (daily_growth_mb * 30), 2),
                    "size_gb": round((current_size + (daily_growth_mb * 30)) / 1024, 3),
                    "additional_mb": round(daily_growth_mb * 30, 2)
                },
                "6_months": {
                    "size_mb": round(current_size + (daily_growth_mb * 180), 2),
                    "size_gb": round((current_size + (daily_growth_mb * 180)) / 1024, 3),
                    "additional_mb": round(daily_growth_mb * 180, 2)
                },
                "1_year": {
                    "size_mb": round(current_size + (daily_growth_mb * 365), 2),
                    "size_gb": round((current_size + (daily_growth_mb * 365)) / 1024, 3),
                    "additional_mb": round(daily_growth_mb * 365, 2)
                }
            }
            
        except Exception as e:
            logger.error(f"Error calculating projections: {e}")
            return {}
    
    async def get_storage_breakdown(self) -> Dict[str, Any]:
        """Get storage component breakdown"""
        try:
            total_size = await self.get_database_size()
            
            # Estimate breakdown (InfluxDB typical ratios)
            metrics_data = total_size * 0.75  # 75% actual data
            indexes = total_size * 0.15       # 15% indexes
            metadata = total_size * 0.10      # 10% metadata/overhead
            
            return {
                "metrics_data": {
                    "size_mb": round(metrics_data, 2),
                    "percentage": 75
                },
                "indexes": {
                    "size_mb": round(indexes, 2),
                    "percentage": 15
                },
                "metadata": {
                    "size_mb": round(metadata, 2),
                    "percentage": 10
                },
                "total_mb": round(total_size, 2)
            }
            
        except Exception as e:
            logger.error(f"Error getting storage breakdown: {e}")
            return {}
    
    async def get_queue_storage_breakdown(self) -> List[Dict[str, Any]]:
        """Get per-queue storage breakdown"""
        try:
            # Get all queues and their data point counts
            queues_data = []
            
            # Get unique queues
            queue_query = f'''
            import "influxdata/influxdb/schema"
            
            schema.tagValues(
                bucket: "{self.bucket}",
                tag: "queue_name",
                predicate: (r) => r._measurement == "queue_metrics" and r._time >= -30d
            )
            '''
            
            queue_result = self.query_api.query(queue_query)
            queue_names = []
            
            for table in queue_result:
                for record in table.records:
                    queue_names.append(record.get_value())
            
            # Get data points per queue
            for queue_name in queue_names:
                try:
                    point_query = f'''
                    from(bucket: "{self.bucket}")
                        |> range(start: -30d)
                        |> filter(fn: (r) => r._measurement == "queue_metrics")
                        |> filter(fn: (r) => r.queue_name == "{queue_name}")
                        |> count()
                        |> sum()
                    '''
                    
                    point_result = self.query_api.query(point_query)
                    data_points = 0
                    
                    for table in point_result:
                        for record in table.records:
                            data_points = record.get_value()
                            break
                    
                    # Get queue category and last activity
                    category = await self.get_queue_category(queue_name)
                    last_activity = await self.get_queue_last_activity(queue_name)
                    
                    # Estimate storage (~25 bytes per point)
                    estimated_mb = (data_points * 25) / (1024 * 1024)
                    
                    queues_data.append({
                        "name": queue_name,
                        "category": category,
                        "data_points": data_points,
                        "estimated_size_mb": round(estimated_mb, 2),
                        "last_activity": last_activity
                    })
                    
                except Exception as e:
                    logger.error(f"Error processing queue {queue_name}: {e}")
                    continue
            
            # Calculate percentages
            total_size = sum(q["estimated_size_mb"] for q in queues_data)
            for queue in queues_data:
                queue["percentage"] = round((queue["estimated_size_mb"] / total_size) * 100, 1) if total_size > 0 else 0
            
            # Sort by size (descending)
            return sorted(queues_data, key=lambda x: x["estimated_size_mb"], reverse=True)
            
        except Exception as e:
            logger.error(f"Error getting queue storage breakdown: {e}")
            return []
    
    async def get_queue_category(self, queue_name: str) -> str:
        """Get queue category"""
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
            
            return 'SUPPORT'
            
        except Exception as e:
            logger.debug(f"Could not get category for {queue_name}: {e}")
            return 'SUPPORT'
    
    async def get_queue_last_activity(self, queue_name: str) -> Optional[str]:
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
                    return record.get_time().isoformat()
            
            return None
            
        except Exception as e:
            logger.debug(f"Could not get last activity for {queue_name}: {e}")
            return None
    
    async def get_growth_projections(self) -> List[Dict[str, Any]]:
        """Get growth projections as list"""
        daily_growth = await self.calculate_daily_growth()
        projections = await self.calculate_storage_projections(daily_growth)
        
        return [
            {
                "period": "1 Month",
                "size_mb": projections["1_month"]["size_mb"],
                "size_gb": projections["1_month"]["size_gb"],
                "additional_mb": projections["1_month"]["additional_mb"]
            },
            {
                "period": "6 Months", 
                "size_mb": projections["6_months"]["size_mb"],
                "size_gb": projections["6_months"]["size_gb"],
                "additional_mb": projections["6_months"]["additional_mb"]
            },
            {
                "period": "1 Year",
                "size_mb": projections["1_year"]["size_mb"],
                "size_gb": projections["1_year"]["size_gb"],
                "additional_mb": projections["1_year"]["additional_mb"]
            }
        ]
    
    async def get_usage_trends(self, days: int = 30) -> Dict[str, Any]:
        """Get usage trends over specified period"""
        try:
            query = f'''
            from(bucket: "{self.bucket}")
                |> range(start: -{days}d)
                |> filter(fn: (r) => r._measurement == "queue_metrics")
                |> aggregateWindow(every: 1d, fn: count)
                |> sum()
                |> map(fn: (r) => ({{ r with _value: float(v: r._value) * 25.0 / 1024.0 / 1024.0 }}))
            '''
            
            result = self.query_api.query(query)
            
            trend_data = []
            for table in result:
                for record in table.records:
                    trend_data.append({
                        "date": record.get_time().date().isoformat(),
                        "size_mb": round(record.get_value(), 2)
                    })
            
            return {
                "period_days": days,
                "data_points": len(trend_data),
                "trends": sorted(trend_data, key=lambda x: x["date"])
            }
            
        except Exception as e:
            logger.error(f"Error getting usage trends: {e}")
            return {"period_days": days, "data_points": 0, "trends": []}
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Get analytics system health status"""
        try:
            # Test InfluxDB connection
            health = self.client.health()
            influx_healthy = health.status == "pass"
            
            # Get basic stats
            total_size = await self.get_database_size()
            data_points = await self.get_total_data_points()
            
            return {
                "status": "healthy" if influx_healthy else "degraded",
                "influxdb_connection": influx_healthy,
                "database_size_mb": total_size,
                "total_data_points": data_points,
                "last_check": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Analytics health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "last_check": datetime.utcnow().isoformat()
            }
    
    async def refresh_cache(self):
        """Refresh analytics cache"""
        try:
            # Clear existing cache
            self.cache.clear()
            self.last_cache_update.clear()
            
            # Trigger cache refresh by calling main analytics
            await self.get_storage_analytics()
            
            logger.info("Analytics cache refreshed successfully")
            
        except Exception as e:
            logger.error(f"Error refreshing analytics cache: {e}")
            raise
    
    async def close(self):
        """Close InfluxDB client connections"""
        if self.client:
            self.client.close()
            logger.info("AnalyticsService client closed")