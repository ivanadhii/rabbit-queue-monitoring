#!/usr/bin/env python3
"""
WebSocket Manager for GPS Dashboard
Handles real-time data streaming and connection management
"""

import asyncio
import logging
from typing import List, Dict, Any
from fastapi import WebSocket, WebSocketDisconnect
import json
from datetime import datetime

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages WebSocket connections and real-time data broadcasting"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.broadcasting = False
        self.broadcast_task = None
    
    async def connect(self, websocket: WebSocket):
        """Accept new WebSocket connection"""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
    
    async def disconnect_all(self):
        """Disconnect all WebSocket connections"""
        connections = self.active_connections.copy()
        for websocket in connections:
            try:
                await websocket.close()
            except Exception as e:
                logger.error(f"Error closing WebSocket: {e}")
        
        self.active_connections.clear()
        self.broadcasting = False
        
        if self.broadcast_task:
            self.broadcast_task.cancel()
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        """Send message to specific WebSocket"""
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
            self.disconnect(websocket)
    
    async def broadcast_message(self, message: Dict[str, Any]):
        """Broadcast message to all connected WebSockets"""
        if not self.active_connections:
            return
        
        message_str = json.dumps(message)
        disconnected = []
        
        for websocket in self.active_connections:
            try:
                await websocket.send_text(message_str)
            except Exception as e:
                logger.error(f"Error broadcasting message: {e}")
                disconnected.append(websocket)
        
        # Remove disconnected websockets
        for websocket in disconnected:
            self.disconnect(websocket)
    
    async def send_metrics_update(self, websocket: WebSocket):
        """Send metrics update to specific WebSocket"""
        try:
            # This would normally fetch current metrics
            # For now, send a keep-alive message
            message = {
                "type": "ping",
                "timestamp": datetime.utcnow().isoformat()
            }
            await websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.error(f"Error sending metrics update: {e}")
            self.disconnect(websocket)
    
    async def start_broadcasting(self):
        """Start background broadcasting task"""
        if self.broadcasting:
            return
        
        self.broadcasting = True
        self.broadcast_task = asyncio.create_task(self._broadcast_loop())
        logger.info("WebSocket broadcasting started")
    
    async def _broadcast_loop(self):
        """Background task for periodic broadcasting"""
        try:
            while self.broadcasting:
                if self.active_connections:
                    # Send periodic updates to all connections
                    message = {
                        "type": "system_heartbeat",
                        "timestamp": datetime.utcnow().isoformat(),
                        "active_connections": len(self.active_connections)
                    }
                    await self.broadcast_message(message)
                
                await asyncio.sleep(30)  # Broadcast every 30 seconds
                
        except asyncio.CancelledError:
            logger.info("Broadcasting task cancelled")
        except Exception as e:
            logger.error(f"Error in broadcast loop: {e}")
    
    async def send_queue_discovery(self, queue_info: Dict[str, Any]):
        """Send queue discovery notification"""
        message = {
            "type": "queue_discovered",
            "payload": queue_info,
            "timestamp": datetime.utcnow().isoformat()
        }
        await self.broadcast_message(message)
    
    async def send_system_alert(self, alert: Dict[str, Any]):
        """Send system alert notification"""
        message = {
            "type": "system_alert",
            "payload": alert,
            "timestamp": datetime.utcnow().isoformat()
        }
        await self.broadcast_message(message)
    
    def get_connection_count(self) -> int:
        """Get number of active connections"""
        return len(self.active_connections)