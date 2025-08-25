#!/usr/bin/env python3
"""
Health Server for GPS Queue Monitoring
Provides health check endpoints for production monitoring
"""

import os
import json
import requests
import threading
import logging
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

logger = logging.getLogger(__name__)


class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP request handler for health check endpoints"""
    
    def __init__(self, monitor_instance, *args, **kwargs):
        self.monitor = monitor_instance
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """Handle GET requests for health endpoints"""
        if self.path == "/health":
            self._handle_health_check()
        elif self.path == "/ready":
            self._handle_readiness_check()
        else:
            self._handle_not_found()
    
    def _handle_health_check(self):
        """Handle /health endpoint"""
        try:
            health_data = {
                "status": "healthy",
                "service": "gps-production-monitor",
                "timestamp": datetime.utcnow().isoformat(),
                "version": "2.0",
                "mode": "discord_only",
                "target": f"{self.monitor.rabbitmq_host}:{self.monitor.rabbitmq_port}",
                "monitoring": {
                    "total_queues": len(self.monitor.target_queues),
                    "core_queues": len(self.monitor.core_queues),
                    "support_queues": len(self.monitor.support_queues),
                    "interval_seconds": self.monitor.collection_interval,
                    "alert_system": "discord"
                }
            }
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(health_data, indent=2).encode())
            
        except Exception as e:
            logger.error(f"Health check error: {e}")
            self._send_error_response(500, "Health check failed")
    
    def _handle_readiness_check(self):
        """Handle /ready endpoint"""
        try:
            # Test RabbitMQ connectivity
            response = requests.get(
                f"{self.monitor.rabbitmq_url}/api/overview",
                auth=self.monitor.auth,
                timeout=5
            )
            response.raise_for_status()
            
            # Success - ready
            status_data = {
                "status": "ready",
                "target_reachable": True,
                "timestamp": datetime.utcnow().isoformat(),
                "target": f"{self.monitor.rabbitmq_host}:{self.monitor.rabbitmq_port}",
                "last_check": datetime.utcnow().isoformat()
            }
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(status_data, indent=2).encode())
            
        except Exception as e:
            # Failed - not ready
            logger.warning(f"Readiness check failed: {e}")
            
            status_data = {
                "status": "not_ready",
                "target_reachable": False,
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e),
                "target": f"{self.monitor.rabbitmq_host}:{self.monitor.rabbitmq_port}"
            }
            
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(status_data, indent=2).encode())
    
    def _handle_not_found(self):
        """Handle 404 responses"""
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        
        error_data = {
            "error": "Not Found",
            "message": "Available endpoints: /health, /ready",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.wfile.write(json.dumps(error_data, indent=2).encode())
    
    def _send_error_response(self, status_code: int, message: str):
        """Send error response"""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        
        error_data = {
            "error": message,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.wfile.write(json.dumps(error_data, indent=2).encode())
    
    def log_message(self, format, *args):
        """Suppress HTTP server access logs"""
        pass


class HealthServer:
    """Health check server for GPS monitoring"""
    
    def __init__(self, monitor_instance):
        self.monitor = monitor_instance
        self.port = int(os.getenv('HEALTH_CHECK_PORT', 8080))
        self.server = None
        self.server_thread = None
    
    def create_handler(self):
        """Create request handler with monitor instance"""
        def handler(*args, **kwargs):
            return HealthCheckHandler(self.monitor, *args, **kwargs)
        return handler
    
    def start(self):
        """Start health check server in background thread"""
        try:
            handler_class = self.create_handler()
            self.server = HTTPServer(("", self.port), handler_class)
            
            self.server_thread = threading.Thread(
                target=self.server.serve_forever,
                daemon=True,
                name="HealthServer"
            )
            self.server_thread.start()
            
            logger.info(f"Health server started on port {self.port}")
            logger.info(f"Health endpoints: http://localhost:{self.port}/health, http://localhost:{self.port}/ready")
            
        except Exception as e:
            logger.error(f"Failed to start health server: {e}")
            raise
    
    def stop(self):
        """Stop health check server"""
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
                logger.info("Health server stopped")
            except Exception as e:
                logger.error(f"Error stopping health server: {e}")


def main():
    """Test health server standalone"""
    # Mock monitor for testing
    class MockMonitor:
        def __init__(self):
            self.rabbitmq_host = "localhost"
            self.rabbitmq_port = 15672
            self.rabbitmq_url = f"http://{self.rabbitmq_host}:{self.rabbitmq_port}"
            self.auth = ("guest", "guest")
            self.target_queues = ["test_queue"]
            self.core_queues = ["test_queue"]
            self.support_queues = []
            self.collection_interval = 15
    
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    # Start health server
    monitor = MockMonitor()
    health_server = HealthServer(monitor)
    health_server.start()
    
    print("Health server running on http://localhost:8080")
    print("Test endpoints:")
    print("  curl http://localhost:8080/health")
    print("  curl http://localhost:8080/ready")
    print("Press Ctrl+C to stop...")
    
    try:
        # Keep main thread alive
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        health_server.stop()
        print("Health server stopped")


if __name__ == "__main__":
    main()