#!/usr/bin/env python3
"""
Analytics API endpoints for GPS Dashboard
"""

from datetime import datetime
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.analytics_service import AnalyticsService


class StorageAnalytics(BaseModel):
    """Storage analytics data model"""
    total_size_mb: float
    data_points: int
    daily_growth_mb: float
    active_queues: int
    retention_days: int


class GrowthProjection(BaseModel):
    """Growth projection data model"""
    period: str
    size_mb: float
    size_gb: float
    additional_mb: float


class QueueStorageInfo(BaseModel):
    """Per-queue storage information"""
    name: str
    category: str
    data_points: int
    estimated_size_mb: float
    percentage: float
    last_activity: datetime


class AnalyticsAPI:
    """Analytics API router"""
    
    def __init__(self, analytics_service: AnalyticsService):
        self.analytics_service = analytics_service
        self.router = APIRouter()
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup API routes"""
        
        @self.router.get("/analytics/storage")
        async def get_storage_analytics() -> Dict[str, Any]:
            """Get comprehensive storage analytics"""
            try:
                analytics = await self.analytics_service.get_storage_analytics()
                return analytics
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.router.get("/analytics/queues")
        async def get_queue_analytics() -> List[QueueStorageInfo]:
            """Get per-queue storage breakdown"""
            try:
                queue_analytics = await self.analytics_service.get_queue_storage_breakdown()
                return queue_analytics
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.router.get("/analytics/growth")
        async def get_growth_projections() -> List[GrowthProjection]:
            """Get storage growth projections"""
            try:
                projections = await self.analytics_service.get_growth_projections()
                return projections
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.router.get("/analytics/breakdown")
        async def get_storage_breakdown() -> Dict[str, Any]:
            """Get storage component breakdown"""
            try:
                breakdown = await self.analytics_service.get_storage_breakdown()
                return breakdown
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.router.get("/analytics/trends")
        async def get_usage_trends(days: int = 30) -> Dict[str, Any]:
            """Get usage trends over specified period"""
            try:
                if days < 1 or days > 365:
                    raise HTTPException(status_code=400, detail="Days must be between 1 and 365")
                
                trends = await self.analytics_service.get_usage_trends(days)
                return trends
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.router.post("/analytics/refresh")
        async def refresh_analytics() -> Dict[str, str]:
            """Manually refresh analytics cache"""
            try:
                await self.analytics_service.refresh_cache()
                return {
                    "status": "success",
                    "message": "Analytics cache refreshed",
                    "timestamp": datetime.utcnow().isoformat()
                }
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.router.get("/analytics/health")
        async def get_analytics_health() -> Dict[str, Any]:
            """Get analytics system health status"""
            try:
                health = await self.analytics_service.get_health_status()
                return health
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))