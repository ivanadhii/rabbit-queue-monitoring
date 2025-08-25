/**
 * Charts Management for GPS Dashboard
 * Handles Chart.js implementation and queue visualization
 */

// Chart instances store
const chartInstances = new Map();

// Chart color configuration
const chartColors = {
    ready: '#3b82f6',          // Blue
    incoming: '#10b981',       // Green  
    consume: '#f59e0b',        // Amber
    consumers: '#8b5cf6',      // Purple
    background: {
        ready: 'rgba(59, 130, 246, 0.1)',
        incoming: 'rgba(16, 185, 129, 0.1)',
        consume: 'rgba(245, 158, 11, 0.1)',
        consumers: 'rgba(139, 92, 246, 0.1)'
    }
};

// Time range configurations
const timeRangeConfig = {
    '1h': {
        hours: 1,
        timeUnit: 'minute',
        stepSize: 5,
        maxDataPoints: 240
    },
    '8h': {
        hours: 8,
        timeUnit: 'hour',
        stepSize: 30,
        maxDataPoints: 1920
    },
    '1d': {
        hours: 24,
        timeUnit: 'hour',
        stepSize: 120,
        maxDataPoints: 5760
    }
};

/**
 * Load and render time series view
 */
async function loadTimeSeriesView() {
    try {
        hideLoading();
        
        // Clear existing content
        const container = document.getElementById('queue-container');
        container.innerHTML = '';
        container.style.display = 'block';
        
        // Destroy existing chart instances
        destroyAllCharts();
        
        if (!queueData || queueData.length === 0) {
            container.innerHTML = '<div class="no-data">No queues available</div>';
            return;
        }
        
        // Create queue cards
        for (const queue of queueData) {
            await createQueueCard(queue, container);
        }
        
        // Load metrics for all queues
        await loadAllQueueMetrics();
        
    } catch (error) {
        console.error('Error loading time series view:', error);
        showError('Failed to load time series data');
    }
}

/**
 * Create queue card HTML structure
 */
async function createQueueCard(queue, container) {
    const cardId = `queue-card-${queue.name}`;
    
    const cardHtml = `
        <div class="queue-card" id="${cardId}" data-queue-name="${queue.name}">
            <div class="queue-header">
                <div class="queue-name">${queue.name}</div>
                <div class="queue-meta">
                    <span class="queue-category ${queue.category.toLowerCase()}">${queue.category}</span>
                    <span class="queue-status healthy">HEALTHY</span>
                    <span class="last-seen">Last: ${formatTimeAgo(queue.last_seen)}</span>
                </div>
            </div>
            <div class="queue-body">
                <div class="metric-panel">
                    <h4>Ready Messages</h4>
                    <div class="chart-container">
                        <canvas id="ready-chart-${queue.name}"></canvas>
                    </div>
                </div>
                <div class="metric-panel">
                    <h4>Throughput Rate</h4>
                    <div class="chart-container">
                        <canvas id="speed-chart-${queue.name}"></canvas>
                    </div>
                </div>
                <div class="metric-panel">
                    <h4>Active Consumers</h4>
                    <div class="chart-container">
                        <canvas id="consumer-chart-${queue.name}"></canvas>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    container.insertAdjacentHTML('beforeend', cardHtml);
}

/**
 * Load metrics for all queues
 */
async function loadAllQueueMetrics() {
    const promises = queueData.map(queue => loadQueueMetrics(queue.name));
    await Promise.all(promises);
}

/**
 * Load metrics for specific queue
 */
async function loadQueueMetrics(queueName) {
    try {
        const response = await fetch(`/api/queues/${queueName}/metrics?time_range=${currentTimeRange}`);
        if (!response.ok) throw new Error(`Failed to fetch metrics for ${queueName}`);
        
        const metricsData = await response.json();
        
        // Create charts for this queue
        createReadyMessagesChart(queueName, metricsData.data.ready_messages);
        createThroughputChart(queueName, metricsData.data.rates);
        createConsumerChart(queueName, metricsData.data.consumers);
        
        // Update queue status
        updateQueueStatus(queueName, metricsData);
        
    } catch (error) {
        console.error(`Error loading metrics for ${queueName}:`, error);
        
        // Show error in queue card
        const card = document.querySelector(`[data-queue-name="${queueName}"]`);
        if (card) {
            const statusEl = card.querySelector('.queue-status');
            if (statusEl) {
                statusEl.className = 'queue-status critical';
                statusEl.textContent = 'ERROR';
            }
        }
    }
}

/**
 * Create ready messages chart
 */
function createReadyMessagesChart(queueName, data) {
    const ctx = document.getElementById(`ready-chart-${queueName}`);
    if (!ctx) return;
    
    const config = timeRangeConfig[currentTimeRange];
    
    const chart = new Chart(ctx, {
        type: 'line',
        data: {
            datasets: [{
                label: 'Ready Messages',
                data: data.map(item => ({
                    x: new Date(item.timestamp),
                    y: item.value
                })),
                borderColor: chartColors.ready,
                backgroundColor: chartColors.background.ready,
                tension: 0.1,
                fill: true,
                pointRadius: 0,
                pointHoverRadius: 4,
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            scales: {
                x: {
                    type: 'time',
                    time: {
                        unit: config.timeUnit,
                        displayFormats: {
                            minute: 'HH:mm',
                            hour: 'HH:mm'
                        }
                    },
                    grid: {
                        color: 'rgba(71, 85, 105, 0.3)'
                    },
                    ticks: {
                        color: '#94a3b8',
                        maxTicksLimit: 6
                    }
                },
                y: {
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(71, 85, 105, 0.3)'
                    },
                    ticks: {
                        color: '#94a3b8',
                        callback: function(value) {
                            return value >= 1000 ? (value/1000).toFixed(1) + 'K' : value;
                        }
                    },
                    title: {
                        display: false
                    }
                }
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: '#1e293b',
                    titleColor: '#f1f5f9',
                    bodyColor: '#cbd5e1',
                    borderColor: '#475569',
                    borderWidth: 1,
                    callbacks: {
                        title: function(context) {
                            return formatDateTime(context[0].parsed.x);
                        },
                        label: function(context) {
                            return `${context.parsed.y.toLocaleString()} messages`;
                        }
                    }
                }
            },
            animation: {
                duration: 0
            }
        }
    });
    
    chartInstances.set(`ready-${queueName}`, chart);
}

/**
 * Create throughput rate chart (dual line)
 */
function createThroughputChart(queueName, data) {
    const ctx = document.getElementById(`speed-chart-${queueName}`);
    if (!ctx) return;
    
    const config = timeRangeConfig[currentTimeRange];
    
    const chart = new Chart(ctx, {
        type: 'line',
        data: {
            datasets: [
                {
                    label: 'Incoming',
                    data: data.map(item => ({
                        x: new Date(item.timestamp),
                        y: item.incoming_rate
                    })),
                    borderColor: chartColors.incoming,
                    backgroundColor: 'transparent',
                    tension: 0.1,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    borderWidth: 2
                },
                {
                    label: 'Consuming',
                    data: data.map(item => ({
                        x: new Date(item.timestamp),
                        y: item.consume_rate
                    })),
                    borderColor: chartColors.consume,
                    backgroundColor: 'transparent',
                    tension: 0.1,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    borderWidth: 2
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            scales: {
                x: {
                    type: 'time',
                    time: {
                        unit: config.timeUnit,
                        displayFormats: {
                            minute: 'HH:mm',
                            hour: 'HH:mm'
                        }
                    },
                    grid: {
                        color: 'rgba(71, 85, 105, 0.3)'
                    },
                    ticks: {
                        color: '#94a3b8',
                        maxTicksLimit: 6
                    }
                },
                y: {
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(71, 85, 105, 0.3)'
                    },
                    ticks: {
                        color: '#94a3b8',
                        callback: function(value) {
                            return value.toFixed(1) + '/s';
                        }
                    },
                    title: {
                        display: false
                    }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    align: 'end',
                    labels: {
                        color: '#cbd5e1',
                        font: {
                            size: 11
                        },
                        boxWidth: 12,
                        boxHeight: 12,
                        padding: 15
                    }
                },
                tooltip: {
                    backgroundColor: '#1e293b',
                    titleColor: '#f1f5f9',
                    bodyColor: '#cbd5e1',
                    borderColor: '#475569',
                    borderWidth: 1,
                    callbacks: {
                        title: function(context) {
                            return formatDateTime(context[0].parsed.x);
                        },
                        label: function(context) {
                            return `${context.dataset.label}: ${context.parsed.y.toFixed(1)} msg/s`;
                        }
                    }
                }
            },
            animation: {
                duration: 0
            }
        }
    });
    
    chartInstances.set(`speed-${queueName}`, chart);
}

/**
 * Create consumer count chart
 */
function createConsumerChart(queueName, data) {
    const ctx = document.getElementById(`consumer-chart-${queueName}`);
    if (!ctx) return;
    
    const config = timeRangeConfig[currentTimeRange];
    
    // Get max consumers for better Y-axis scaling
    const maxConsumers = Math.max(...data.map(item => item.value), 5);
    
    const chart = new Chart(ctx, {
        type: 'line',
        data: {
            datasets: [{
                label: 'Consumers',
                data: data.map(item => ({
                    x: new Date(item.timestamp),
                    y: item.value
                })),
                borderColor: chartColors.consumers,
                backgroundColor: chartColors.background.consumers,
                tension: 0,
                fill: true,
                stepped: true,
                pointRadius: 2,
                pointHoverRadius: 5,
                pointBackgroundColor: chartColors.consumers,
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            scales: {
                x: {
                    type: 'time',
                    time: {
                        unit: config.timeUnit,
                        displayFormats: {
                            minute: 'HH:mm',
                            hour: 'HH:mm'
                        }
                    },
                    grid: {
                        color: 'rgba(71, 85, 105, 0.3)'
                    },
                    ticks: {
                        color: '#94a3b8',
                        maxTicksLimit: 6
                    }
                },
                y: {
                    beginAtZero: true,
                    max: maxConsumers + 1,
                    grid: {
                        color: 'rgba(71, 85, 105, 0.3)'
                    },
                    ticks: {
                        color: '#94a3b8',
                        stepSize: 1,
                        callback: function(value) {
                            return Number.isInteger(value) ? value : '';
                        }
                    },
                    title: {
                        display: false
                    }
                }
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: '#1e293b',
                    titleColor: '#f1f5f9',
                    bodyColor: '#cbd5e1',
                    borderColor: '#475569',
                    borderWidth: 1,
                    callbacks: {
                        title: function(context) {
                            return formatDateTime(context[0].parsed.x);
                        },
                        label: function(context) {
                            const count = context.parsed.y;
                            return `${count} consumer${count !== 1 ? 's' : ''} active`;
                        }
                    }
                }
            },
            animation: {
                duration: 0
            }
        }
    });
    
    chartInstances.set(`consumer-${queueName}`, chart);
}

/**
 * Update queue status based on metrics
 */
function updateQueueStatus(queueName, metricsData) {
    const card = document.querySelector(`[data-queue-name="${queueName}"]`);
    if (!card) return;
    
    const statusEl = card.querySelector('.queue-status');
    if (!statusEl) return;
    
    // Determine status based on latest metrics
    const readyData = metricsData.data.ready_messages;
    const consumerData = metricsData.data.consumers;
    
    if (readyData.length === 0 && consumerData.length === 0) {
        statusEl.className = 'queue-status critical';
        statusEl.textContent = 'NO DATA';
        return;
    }
    
    const latestReady = readyData[readyData.length - 1]?.value || 0;
    const latestConsumers = consumerData[consumerData.length - 1]?.value || 0;
    
    // Simple status logic
    if (latestConsumers === 0 && latestReady > 0) {
        statusEl.className = 'queue-status critical';
        statusEl.textContent = 'NO CONSUMERS';
    } else if (latestReady > 1000) {
        statusEl.className = 'queue-status warning';
        statusEl.textContent = 'HIGH BACKLOG';
    } else {
        statusEl.className = 'queue-status healthy';
        statusEl.textContent = 'HEALTHY';
    }
}

/**
 * Update charts with real-time data
 */
function updateChartsWithRealTimeData(queueMetrics) {
    queueMetrics.forEach(queue => {
        const timestamp = new Date(queue.timestamp);
        
        // Update ready messages chart
        const readyChart = chartInstances.get(`ready-${queue.queue_name}`);
        if (readyChart) {
            const dataset = readyChart.data.datasets[0];
            dataset.data.push({
                x: timestamp,
                y: queue.messages_ready
            });
            
            // Maintain data window
            const maxPoints = timeRangeConfig[currentTimeRange].maxDataPoints;
            if (dataset.data.length > maxPoints) {
                dataset.data.shift();
            }
            
            readyChart.update('none');
        }
        
        // Update speed chart
        const speedChart = chartInstances.get(`speed-${queue.queue_name}`);
        if (speedChart) {
            const dataPoint = { x: timestamp };
            
            speedChart.data.datasets[0].data.push({
                ...dataPoint,
                y: queue.incoming_rate
            });
            
            speedChart.data.datasets[1].data.push({
                ...dataPoint,
                y: queue.consume_rate
            });
            
            // Maintain data window for both datasets
            const maxPoints = timeRangeConfig[currentTimeRange].maxDataPoints;
            speedChart.data.datasets.forEach(dataset => {
                if (dataset.data.length > maxPoints) {
                    dataset.data.shift();
                }
            });
            
            speedChart.update('none');
        }
        
        // Update consumer chart
        const consumerChart = chartInstances.get(`consumer-${queue.queue_name}`);
        if (consumerChart) {
            const dataset = consumerChart.data.datasets[0];
            dataset.data.push({
                x: timestamp,
                y: queue.consumer_count
            });
            
            // Maintain data window
            const maxPoints = timeRangeConfig[currentTimeRange].maxDataPoints;
            if (dataset.data.length > maxPoints) {
                dataset.data.shift();
            }
            
            consumerChart.update('none');
        }
        
        // Update queue status
        updateQueueStatus(queue.queue_name, {
            data: {
                ready_messages: [{value: queue.messages_ready}],
                consumers: [{value: queue.consumer_count}]
            }
        });
    });
}

/**
 * Destroy all chart instances
 */
function destroyAllCharts() {
    chartInstances.forEach((chart, key) => {
        try {
            chart.destroy();
        } catch (error) {
            console.warn(`Error destroying chart ${key}:`, error);
        }
    });
    chartInstances.clear();
}

/**
 * Utility functions
 */
function formatDateTime(timestamp) {
    return new Date(timestamp).toLocaleString();
}

function formatTimeAgo(timestamp) {
    if (!timestamp) return 'Never';
    
    const now = new Date();
    const time = new Date(timestamp);
    const diffMs = now - time;
    const diffMins = Math.floor(diffMs / 60000);
    
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffMins < 1440) return `${Math.floor(diffMins / 60)}h ago`;
    return `${Math.floor(diffMins / 1440)}d ago`;
}