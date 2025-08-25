/**
 * WebSocket Manager for GPS Dashboard
 * Handles real-time data streaming and connection management
 */

class WebSocketManager {
    constructor() {
        this.ws = null;

        // connection state
        this.connected = false;            // <— was isConnected (boolean). Renamed to avoid clashing with method name.
        this.lastError = null;

        // reconnect/backoff
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectInterval = 1000;     // start 1s
        this.maxReconnectInterval = 30000; // cap 30s

        // heartbeat
        this.pingInterval = null;

        // UI
        this.connectionStatusEl = document.getElementById('connection-status');

        // event hooks
        this.onMessage = null;
        this.onConnectionChange = null;
    }

    /**
     * Connect to WebSocket server
     */
    async connect() {
        try {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/metrics`;

            this.updateConnectionStatus('connecting', 'Connecting...');
            this.ws = new WebSocket(wsUrl);

            // bind handlers
            this.ws.onopen = this.handleOpen.bind(this);
            this.ws.onmessage = this.handleMessage.bind(this);
            this.ws.onclose = this.handleClose.bind(this);
            this.ws.onerror = this.handleError.bind(this);

            console.log('WebSocket connection initiated');
        } catch (error) {
            console.error('WebSocket connection failed:', error);
            this.handleConnectionFailure(error);
        }
    }

    /** onopen */
    handleOpen() {
        console.log('WebSocket connected successfully');

        this.connected = true;
        this.reconnectAttempts = 0;
        this.reconnectInterval = 1000;

        this.updateConnectionStatus('connected', 'Connected');
        this.startPing();

        if (this.onConnectionChange) this.onConnectionChange(true);
        if (typeof showNotification === 'function') {
            showNotification('Real-time connection established', 'success');
        }
    }

    /** onmessage */
    handleMessage(event) {
        try {
            const data = JSON.parse(event.data);

            switch (data.type) {
                case 'metrics_update':
                    this.handleMetricsUpdate(data.payload);
                    break;

                case 'queue_discovered':
                    this.handleQueueDiscovered(data.payload);
                    break;

                case 'system_alert':
                    this.handleSystemAlert(data.payload);
                    break;

                case 'pong':
                    // ok: keep-alive response
                    break;

                case 'ping':
                    // server ping — reply pong (idempotent)
                    this.send({ type: 'pong' });
                    break;

                case 'system_heartbeat':
                    // optional: you could update a heartbeat UI here
                    // console.debug('Heartbeat:', data.payload);
                    break;

                default:
                    console.log('Unknown WebSocket message type:', data.type);
            }
        } catch (error) {
            console.error('Error parsing WebSocket message:', error);
        }
    }

    /** onclose */
    handleClose(event) {
        console.log('WebSocket connection closed:', event.code, event.reason || '');
        this.connected = false;
        this.stopPing();
        this.updateConnectionStatus('disconnected', 'Disconnected');

        if (this.onConnectionChange) this.onConnectionChange(false);

        // Attempt reconnection (non-normal close)
        if (event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
            this.scheduleReconnect();
        } else if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            if (typeof showNotification === 'function') {
                showNotification('Connection lost - switching to polling mode', 'warning');
            }
        }
    }

    /** onerror */
    handleError(error) {
        console.error('WebSocket error:', error);
        this.lastError = error;
        this.handleConnectionFailure(error);
    }

    handleConnectionFailure() {
        this.connected = false;
        this.updateConnectionStatus('disconnected', 'Connection Failed');
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.scheduleReconnect();
        }
    }

    /** reconnection with backoff */
    scheduleReconnect() {
        this.reconnectAttempts++;

        const delay = Math.min(
            this.reconnectInterval * Math.pow(2, this.reconnectAttempts - 1),
            this.maxReconnectInterval
        );

        this.updateConnectionStatus(
            'connecting',
            `Reconnecting in ${Math.round(delay / 1000)}s... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`
        );

        setTimeout(() => {
            if (!this.connected) {
                console.log(`Reconnection attempt ${this.reconnectAttempts}`);
                this.connect();
            }
        }, delay);
    }

    /** keep-alive ping */
    startPing() {
        this.stopPing(); // ensure single interval
        this.pingInterval = setInterval(() => {
            if (this.connected && this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.send({ type: 'ping', timestamp: new Date().toISOString() });
            }
        }, 30000);
    }

    stopPing() {
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
            this.pingInterval = null;
        }
    }

    /** send JSON message */
    send(message) {
        if (this.connected && this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(message));
        } else {
            console.warn('Cannot send message - WebSocket not connected');
        }
    }

    /** message helpers */
    handleMetricsUpdate(metrics) {
        if (window.currentView === 'timeseries' && typeof updateChartsWithRealTimeData === 'function') {
            updateChartsWithRealTimeData(metrics);
        }
        if (typeof updateSystemInfo === 'function') updateSystemInfo();
        if (this.onMessage) this.onMessage('metrics_update', metrics);
    }

    handleQueueDiscovered(queueInfo) {
        console.log('New queue discovered:', queueInfo);
        if (typeof showNotification === 'function') {
            showNotification(`New queue discovered: ${queueInfo.name}`, 'info');
        }
        if (typeof loadInitialData === 'function') {
            setTimeout(() => loadInitialData(), 2000);
        }
        if (this.onMessage) this.onMessage('queue_discovered', queueInfo);
    }

    handleSystemAlert(alert) {
        console.log('System alert received:', alert);
        const type = alert.severity === 'critical' ? 'error'
                   : alert.severity === 'warning' ? 'warning'
                   : 'info';
        if (typeof showNotification === 'function') {
            showNotification(`Alert: ${alert.message}`, type);
        }
        if (this.onMessage) this.onMessage('system_alert', alert);
    }

    /** status UI */
    updateConnectionStatus(status, message) {
        if (!this.connectionStatusEl) return;

        const indicator = this.connectionStatusEl.querySelector('.status-indicator');
        const text = this.connectionStatusEl.querySelector('span:last-child') || this.connectionStatusEl;

        if (indicator) indicator.className = `status-indicator ${status}`;
        if (text) text.textContent = message;
    }

    /** public: is connected? (kept for compatibility) */
    isConnectedNow() {
        return this.connected && this.ws && this.ws.readyState === WebSocket.OPEN;
    }

    /** public: state label */
    getConnectionState() {
        if (!this.ws) return 'not_initialized';
        switch (this.ws.readyState) {
            case WebSocket.CONNECTING: return 'connecting';
            case WebSocket.OPEN:       return 'connected';
            case WebSocket.CLOSING:    return 'closing';
            case WebSocket.CLOSED:     return 'closed';
            default:                   return 'unknown';
        }
    }

    /** subscriptions */
    subscribeToQueue(queueName) {
        this.send({ type: 'subscribe', queue: queueName });
    }
    unsubscribeFromQueue(queueName) {
        this.send({ type: 'unsubscribe', queue: queueName });
    }
    requestMetricsUpdate() {
        this.send({ type: 'request_update' });
    }

    /** hooks */
    setMessageHandler(handler) {
        this.onMessage = handler;
    }
    setConnectionChangeHandler(handler) {
        this.onConnectionChange = handler;
    }

    /** manual disconnect */
    disconnect() {
        if (this.ws) {
            this.stopPing();
            try { this.ws.close(1000, 'Manual disconnect'); } catch (_) {}
            this.ws = null;
        }
        this.connected = false;
        this.updateConnectionStatus('disconnected', 'Disconnected');
    }

    /** diagnostics */
    getConnectionStats() {
        return {
            connected: this.connected,
            reconnectAttempts: this.reconnectAttempts,
            connectionState: this.getConnectionState(),
            lastError: this.lastError || null
        };
    }
}

/**
 * Fallback polling mechanism when WebSocket is not available
 */
class PollingManager {
    constructor(interval = 15000) {
        this.interval = interval;
        this.pollingTimer = null;
        this.isPolling = false;
    }

    start() {
        if (this.isPolling) return;
        this.isPolling = true;
        console.log('Starting polling mode with interval:', this.interval);
        this.poll();
        this.pollingTimer = setInterval(() => this.poll(), this.interval);
    }

    stop() {
        if (this.pollingTimer) {
            clearInterval(this.pollingTimer);
            this.pollingTimer = null;
        }
        this.isPolling = false;
        console.log('Polling stopped');
    }

    async poll() {
        try {
            if (window.currentView === 'timeseries') {
                const response = await fetch('/api/queues/current');
                if (response.ok) {
                    const metrics = await response.json();
                    if (typeof updateChartsWithRealTimeData === 'function') {
                        updateChartsWithRealTimeData(metrics);
                    }
                }
            }
        } catch (error) {
            console.error('Polling error:', error);
        }
    }

    isActive() {
        return this.isPolling;
    }
}

// Global instances
let websocketManager = null;
let pollingManager = null;

/** Initialize real-time data connection (optional helper) */
function initializeRealTimeConnection() {
    websocketManager = new WebSocketManager();
    pollingManager = new PollingManager(30000);

    websocketManager.setConnectionChangeHandler((connected) => {
        if (connected) {
            if (pollingManager.isActive()) pollingManager.stop();
        } else {
            setTimeout(() => {
                if (!websocketManager.isConnected()) {
                    pollingManager.start();
                }
            }, 5000);
        }
    });

    websocketManager.connect();
}

// Export for global access
window.WebSocketManager = WebSocketManager;
window.PollingManager = PollingManager;
window.initializeRealTimeConnection = initializeRealTimeConnection;
window.websocketManager = websocketManager; // optional exposure
