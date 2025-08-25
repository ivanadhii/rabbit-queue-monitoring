#!/usr/bin/env python3
"""
Metrics API endpoints for GPS Dashboard
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.metrics_service import MetricsService


class QueueMetrics(BaseModel):
    """Queue metrics data model"""
    queue_name: str
    category: str
    timestamp: datetime
    messages_ready: int
    consumer_count: int
    incoming_rate: float
    consume_rate: float


class MetricsAPI:
    """Metrics API router"""
    
    def __init__(self, metrics_service: MetricsService):
        self.metrics_service = metrics_service
        self.router = APIRouter()
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup API routes"""
        
        @self.router.get("/queues")
        async def get_queues() -> List[Dict[str, Any]]:
            """Get list of all monitored queues"""
            try:
                queues = await self.metrics_service.get_all_queues()
                return queues
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.router.get("/queues/{queue_name}/metrics")
        async def get_queue_metrics(
            queue_name: str,
            time_range: str = Query("8h", regex="^(1h|8h|1d)$"),
            resolution: Optional[str] = Query(None, regex="^(1m|5m|15m|1h)$")
        ) -> Dict[str, Any]:
            """Get time series metrics for specific queue"""
            try:
                # Auto-select resolution based on time range
                if not resolution:
                    resolution_map = {"1h": "1m", "8h": "5m", "1d": "15m"}
                    resolution = resolution_map.get(time_range, "5m")
                
                metrics = await self.metrics_service.get_queue_timeseries(
                    queue_name, time_range, resolution
                )
                return metrics
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.router.get("/queues/current")
        async def get_current_metrics() -> List[QueueMetrics]:
            """Get current metrics for all queues"""
            try:
                current_metrics = await self.metrics_service.get_current_metrics()
                return current_metrics
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.router.get("/metrics/table")
        async def get_table_data(
            from_time: Optional[str] = None,
            to_time: Optional[str] = None,
            limit: int = Query(1000, ge=1, le=10000)
        ) -> Dict[str, Any]:
            """Get tabular metrics data for specified time range"""
            try:
                # Parse time parameters
                if from_time and to_time:
                    start_time = datetime.fromisoformat(from_time.replace('Z', '+00:00'))
                    end_time = datetime.fromisoformat(to_time.replace('Z', '+00:00'))
                else:
                    # Default to last 24 hours
                    end_time = datetime.utcnow()
                    start_time = end_time - timedelta(hours=24)
                
                table_data = await self.metrics_service.get_table_data(
                    start_time, end_time, limit
                )
                return table_data
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid time format: {e}")
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.router.get("/metrics/export/{format}")
        async def export_metrics(
            format: str,
            from_time: Optional[str] = None,
            to_time: Optional[str] = None
        ):
            """Export metrics data in specified format"""
            try:
                if format not in ["csv", "json"]:
                    raise HTTPException(status_code=400, detail="Format must be 'csv' or 'json'")
                
                # Parse time parameters
                if from_time and to_time:
                    start_time = datetime.fromisoformat(from_time.replace('Z', '+00:00'))
                    end_time = datetime.fromisoformat(to_time.replace('Z', '+00:00'))
                else:
                    # Default to last 7 days
                    end_time = datetime.utcnow()
                    start_time = end_time - timedelta(days=7)
                
                if format == "csv":
                    return await self.metrics_service.export_csv(start_time, end_time)
                else:
                    return await self.metrics_service.export_json(start_time, end_time)
                    
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid time format: {e}")
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.router.get("/system/overview")
        async def get_system_overview() -> Dict[str, Any]:
            """Get system-wide metrics overview"""
            try:
                overview = await self.metrics_service.get_system_overview()
                return overview
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))