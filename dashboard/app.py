#!/usr/bin/env python3
"""
GPS Queue Monitoring Dashboard
FastAPI backend serving web interface and APIs
"""

import os
import asyncio  # FIX: Missing import
import logging
from datetime import datetime
from typing import Dict, Any, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Import dashboard services
from api.metrics import MetricsAPI
from api.analytics import AnalyticsAPI
from api.websocket import WebSocketManager
from services.metrics_service import MetricsService
from services.analytics_service import AnalyticsService

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global services
metrics_service = None
analytics_service = None
websocket_manager = None
metrics_api = None
analytics_api = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Modern FastAPI lifespan handler"""
    global metrics_service, analytics_service, websocket_manager, metrics_api, analytics_api
    
    # Startup
    logger.info("Starting GPS Dashboard...")
    
    try:
        # Initialize services
        metrics_service = MetricsService()
        analytics_service = AnalyticsService()
        websocket_manager = WebSocketManager()
        
        await metrics_service.initialize()
        await analytics_service.initialize()
        
        # Initialize API routers
        metrics_api = MetricsAPI(metrics_service)
        analytics_api = AnalyticsAPI(analytics_service)
        
        # Include API routes
        app.include_router(metrics_api.router, prefix="/api", tags=["metrics"])
        app.include_router(analytics_api.router, prefix="/api", tags=["analytics"])
        
        # Start background tasks
        asyncio.create_task(websocket_manager.start_broadcasting())
        
        logger.info("GPS Dashboard startup complete")
        
        yield
        
    except Exception as e:
        logger.error(f"Startup error: {e}")
        raise
    
    # Shutdown
    logger.info("Shutting down GPS Dashboard...")
    
    try:
        # Close services
        if metrics_service:
            await metrics_service.close()
        if analytics_service:
            await analytics_service.close()
        
        # Disconnect all WebSocket connections
        if websocket_manager:
            await websocket_manager.disconnect_all()
        
        logger.info("GPS Dashboard shutdown complete")
        
    except Exception as e:
        logger.error(f"Shutdown error: {e}")


# Initialize FastAPI app with lifespan
app = FastAPI(
    title="GPS Queue Monitoring Dashboard",
    description="Real-time monitoring dashboard for GPS queue systems",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    """Serve main dashboard page"""
    return FileResponse("static/index.html")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check InfluxDB connection
        influx_healthy = False
        if metrics_service:
            influx_healthy = await metrics_service.health_check()
        
        return {
            "status": "healthy" if influx_healthy else "degraded",
            "service": "gps-dashboard",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0",
            "components": {
                "influxdb": "healthy" if influx_healthy else "unhealthy",
                "websocket": "healthy",
                "api": "healthy"
            },
            "target_system": os.getenv("TARGET_SYSTEM_NAME", "GPS-Production-Server"),
            "environment": os.getenv("DEPLOYMENT_ENVIRONMENT", "production")
        }
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {
            "status": "unhealthy",
            "service": "gps-dashboard",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


@app.websocket("/ws/metrics")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time metrics"""
    if not websocket_manager:
        await websocket.close(code=1000, reason="WebSocket manager not initialized")
        return
    
    await websocket_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and send periodic updates
            await websocket_manager.send_metrics_update(websocket)
            await asyncio.sleep(15)  # Match collection interval
            
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        websocket_manager.disconnect(websocket)


if __name__ == "__main__":
    # Configuration
    host = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    port = int(os.getenv("DASHBOARD_PORT", 8000))
    debug = os.getenv("DASHBOARD_DEBUG", "false").lower() == "true"
    
    logger.info(f"Starting GPS Dashboard on {host}:{port}")
    
    # Run server
    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info"
    )