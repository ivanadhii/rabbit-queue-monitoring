/**
 * Analytics View Management for GPS Dashboard
 * Handles analytics data visualization and storage insights
 */

let analyticsCharts = {};

/**
 * Load and render analytics view
 */
async function loadAnalyticsView() {
    try {
        hideLoading();
        
        // Clear existing content and show analytics container
        document.getElementById('analytics-container').innerHTML = '';
        document.getElementById('analytics-container').style.display = 'block';
        
        // Destroy existing charts
        destroyAnalyticsCharts();
        
        // Create analytics layout
        createAnalyticsLayout();
        
        // Load analytics data
        await loadAnalyticsData();
        
    } catch (error) {
        console.error('Error loading analytics view:', error);
        showError('Failed to load analytics data');
    }
}

/**
 * Create analytics HTML layout
 */
function createAnalyticsLayout() {
    const container = document.getElementById('analytics-container');
    
    const analyticsHtml = `
        <div class="analytics-header">
            <h2>System Analytics</h2>
            <div class="last-updated">Last updated: <span id="analytics-last-updated">Loading...</span></div>
        </div>
        
        <!-- Storage Overview Cards -->
        <div class="analytics-cards">
            <div class="analytics-card">
                <h3>Current Database Size</h3>
                <div class="metric-value" id="current-size">-</div>
                <div class="metric-unit">MB</div>
            </div>
            
            <div class="analytics-card">
                <h3>Daily Growth Rate</h3>
                <div class="metric-value" id="daily-growth">-</div>
                <div class="metric-unit">MB/day</div>
            </div>
            
            <div class="analytics-card">
                <h3>Total Data Points</h3>
                <div class="metric-value" id="total-points">-</div>
                <div class="metric-unit">points</div>
            </div>
            
            <div class="analytics-card">
                <h3>Active Queues</h3>
                <div class="metric-value" id="active-queues">-</div>
                <div class="metric-unit">queues</div>
            </div>
        </div>
        
        <!-- Storage Breakdown Chart -->
        <div class="analytics-section">
            <h3>Storage Breakdown</h3>
            <div class="chart-container" style="height: 300px;">
                <canvas id="storage-breakdown-chart"></canvas>
            </div>
        </div>
        
        <!-- Growth Projection Chart -->
        <div class="analytics-section">
            <h3>Storage Growth Projections</h3>
            <div class="chart-container" style="height: 300px;">
                <canvas id="growth-projection-chart"></canvas>
            </div>
            <div class="projection-summary">
                <div class="projection-item">
                    <strong>1 Month:</strong> <span id="proj-1month">-</span>
                </div>
                <div class="projection-item">
                    <strong>6 Months:</strong> <span id="proj-6months">-</span>
                </div>
                <div class="projection-item">
                    <strong>1 Year:</strong> <span id="proj-1year">-</span>
                </div>
            </div>
        </div>
        
        <!-- Queue Storage Table -->
        <div class="analytics-section">
            <h3>Storage Usage by Queue</h3>
            <div class="table-container">
                <table class="data-table" id="queue-storage-table">
                    <thead>
                        <tr>
                            <th>Queue Name</th>
                            <th>Category</th>
                            <th>Data Points</th>
                            <th>Storage Size</th>
                            <th>% of Total</th>
                            <th>Last Activity</th>
                        </tr>
                    </thead>
                    <tbody id="queue-storage-tbody">
                        <tr><td colspan="6" class="loading-cell">Loading analytics data...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
    `;
    
    container.innerHTML = analyticsHtml;
}

/**
 * Load analytics data from API
 */
async function loadAnalyticsData() {
    try {
        // Load storage analytics
        const storageResponse = await fetch('/api/analytics/storage');
        if (!storageResponse.ok) throw new Error('Failed to fetch storage analytics');
        const storageData = await storageResponse.json();
        
        // Load queue breakdown
        const queueResponse = await fetch('/api/analytics/queues');
        if (!queueResponse.ok) throw new Error('Failed to fetch queue analytics');
        const queueData = await queueResponse.json();
        
        // Update UI components
        updateStorageOverview(storageData);
        renderStorageBreakdownChart(storageData.breakdown);
        renderGrowthProjectionChart(storageData);
        updateQueueStorageTable(queueData);
        
        // Update timestamp
        document.getElementById('analytics-last-updated').textContent = 
            new Date().toLocaleString();
        
    } catch (error) {
        console.error('Analytics data loading error:', error);
        showAnalyticsError('Failed to load analytics data: ' + error.message);
    }
}

/**
 * Update storage overview cards
 */
function updateStorageOverview(data) {
    const current = data.current_usage || {};
    const growth = data.growth || {};
    const projections = data.projections || {};
    
    // Update metric cards
    document.getElementById('current-size').textContent = 
        (current.total_size_mb || 0).toFixed(1);
    
    document.getElementById('daily-growth').textContent = 
        (growth.daily_mb || 0).toFixed(2);
    
    document.getElementById('total-points').textContent = 
        (current.data_points || 0).toLocaleString();
    
    document.getElementById('active-queues').textContent = 
        current.active_queues || 0;
    
    // Update projections summary
    if (projections['1_month']) {
        document.getElementById('proj-1month').textContent = 
            `${projections['1_month'].size_gb.toFixed(2)} GB`;
    }
    
    if (projections['6_months']) {
        document.getElementById('proj-6months').textContent = 
            `${projections['6_months'].size_gb.toFixed(2)} GB`;
    }
    
    if (projections['1_year']) {
        document.getElementById('proj-1year').textContent = 
            `${projections['1_year'].size_gb.toFixed(2)} GB`;
    }
}

/**
 * Render storage breakdown pie chart
 */
function renderStorageBreakdownChart(breakdownData) {
    const ctx = document.getElementById('storage-breakdown-chart');
    if (!ctx || !breakdownData) return;
    
    const data = {
        labels: ['Metrics Data', 'Indexes', 'Metadata'],
        datasets: [{
            data: [
                breakdownData.metrics_data?.size_mb || 0,
                breakdownData.indexes?.size_mb || 0,
                breakdownData.metadata?.size_mb || 0
            ],
            backgroundColor: [
                '#3b82f6',  // Blue - Metrics data
                '#10b981',  // Green - Indexes  
                '#f59e0b'   // Amber - Metadata
            ],
            borderColor: '#1e293b',
            borderWidth: 2
        }]
    };
    
    const config = {
        type: 'doughnut',
        data: data,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        color: '#cbd5e1',
                        padding: 20,
                        usePointStyle: true
                    }
                },
                tooltip: {
                    backgroundColor: '#1e293b',
                    titleColor: '#f1f5f9',
                    bodyColor: '#cbd5e1',
                    borderColor: '#475569',
                    borderWidth: 1,
                    callbacks: {
                        label: function(context) {
                            const value = context.parsed;
                            const percentage = breakdownData[context.label.toLowerCase().replace(' ', '_')]?.percentage || 0;
                            return `${context.label}: ${value.toFixed(1)} MB (${percentage}%)`;
                        }
                    }
                }
            },
            cutout: '60%'
        }
    };
    
    analyticsCharts.breakdown = new Chart(ctx, config);
}

/**
 * Render growth projection line chart
 */
function renderGrowthProjectionChart(data) {
    const ctx = document.getElementById('growth-projection-chart');
    if (!ctx || !data.projections) return;
    
    const current = data.current_usage?.total_size_mb || 0;
    const projections = data.projections;
    
    const chartData = {
        labels: ['Current', '1 Month', '6 Months', '1 Year'],
        datasets: [{
            label: 'Storage Size (GB)',
            data: [
                current / 1024,
                projections['1_month']?.size_gb || 0,
                projections['6_months']?.size_gb || 0,
                projections['1_year']?.size_gb || 0
            ],
            borderColor: '#8b5cf6',
            backgroundColor: 'rgba(139, 92, 246, 0.1)',
            tension: 0.1,
            fill: true,
            pointRadius: 5,
            pointHoverRadius: 7,
            pointBackgroundColor: '#8b5cf6',
            borderWidth: 3
        }]
    };
    
    const config = {
        type: 'line',
        data: chartData,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            scales: {
                x: {
                    grid: {
                        color: 'rgba(71, 85, 105, 0.3)'
                    },
                    ticks: {
                        color: '#94a3b8'
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
                            return value.toFixed(2) + ' GB';
                        }
                    },
                    title: {
                        display: true,
                        text: 'Storage Size (GB)',
                        color: '#cbd5e1'
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
                        label: function(context) {
                            return `${context.parsed.y.toFixed(3)} GB`;
                        }
                    }
                }
            }
        }
    };
    
    analyticsCharts.growth = new Chart(ctx, config);
}

/**
 * Update queue storage table
 */
function updateQueueStorageTable(queueData) {
    const tbody = document.getElementById('queue-storage-tbody');
    if (!tbody) return;
    
    if (!queueData || queueData.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="no-data">No queue data available</td></tr>';
        return;
    }
    
    tbody.innerHTML = queueData.map(queue => `
        <tr>
            <td>
                <strong>${queue.name}</strong>
            </td>
            <td>
                <span class="queue-category ${queue.category.toLowerCase()}">${queue.category}</span>
            </td>
            <td>${queue.data_points.toLocaleString()}</td>
            <td>${queue.estimated_size_mb.toFixed(2)} MB</td>
            <td>
                <div class="percentage-bar">
                    <div class="percentage-fill" style="width: ${queue.percentage}%"></div>
                    <span class="percentage-text">${queue.percentage}%</span>
                </div>
            </td>
            <td class="last-activity">
                ${queue.last_activity ? formatTimeAgo(queue.last_activity) : 'Never'}
            </td>
        </tr>
    `).join('');
}

/**
 * Show analytics error message
 */
function showAnalyticsError(message) {
    const container = document.getElementById('analytics-container');
    container.innerHTML = `
        <div class="analytics-error">
            <div class="error-icon">⚠️</div>
            <h3>Analytics Error</h3>
            <p>${message}</p>
            <button class="btn-primary" onclick="loadAnalyticsView()">Retry</button>
        </div>
    `;
}

/**
 * Destroy analytics charts
 */
function destroyAnalyticsCharts() {
    Object.values(analyticsCharts).forEach(chart => {
        try {
            if (chart && typeof chart.destroy === 'function') {
                chart.destroy();
            }
        } catch (error) {
            console.warn('Error destroying analytics chart:', error);
        }
    });
    analyticsCharts = {};
}

/**
 * Export analytics data
 */
async function exportAnalyticsData(format = 'json') {
    try {
        const response = await fetch('/api/analytics/storage');
        if (!response.ok) throw new Error('Failed to fetch analytics data');
        
        const data = await response.json();
        
        if (format === 'csv') {
            // Convert to CSV format
            const csvData = convertAnalyticsToCSV(data);
            downloadFile(csvData, 'analytics-report.csv', 'text/csv');
        } else {
            // JSON format
            const jsonData = JSON.stringify(data, null, 2);
            downloadFile(jsonData, 'analytics-report.json', 'application/json');
        }
        
        showNotification(`Analytics data exported as ${format.toUpperCase()}`, 'success');
        
    } catch (error) {
        console.error('Export error:', error);
        showNotification('Failed to export analytics data', 'error');
    }
}

/**
 * Convert analytics data to CSV format
 */
function convertAnalyticsToCSV(data) {
    const lines = [];
    
    // Header
    lines.push('GPS Queue Analytics Report');
    lines.push(`Generated: ${new Date().toISOString()}`);
    lines.push('');
    
    // Current Usage
    lines.push('Current Usage');
    lines.push('Metric,Value,Unit');
    lines.push(`Database Size,${data.current_usage?.total_size_mb || 0},MB`);
    lines.push(`Data Points,${data.current_usage?.data_points || 0},points`);
    lines.push(`Active Queues,${data.current_usage?.active_queues || 0},queues`);
    lines.push(`Collection Rate,${data.current_usage?.collection_rate || 0},/min`);
    lines.push('');
    
    // Growth Projections
    lines.push('Growth Projections');
    lines.push('Period,Size (MB),Size (GB),Additional (MB)');
    if (data.projections) {
        lines.push(`1 Month,${data.projections['1_month']?.size_mb || 0},${data.projections['1_month']?.size_gb || 0},${data.projections['1_month']?.additional_mb || 0}`);
        lines.push(`6 Months,${data.projections['6_months']?.size_mb || 0},${data.projections['6_months']?.size_gb || 0},${data.projections['6_months']?.additional_mb || 0}`);
        lines.push(`1 Year,${data.projections['1_year']?.size_mb || 0},${data.projections['1_year']?.size_gb || 0},${data.projections['1_year']?.additional_mb || 0}`);
    }
    
    return lines.join('\n');
}

/**
 * Download file helper
 */
function downloadFile(content, filename, contentType) {
    const blob = new Blob([content], { type: contentType });
    const url = window.URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    
    window.URL.revokeObjectURL(url);
}

/**
 * Format time ago utility
 */
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

/**
 * Refresh analytics data
 */
async function refreshAnalyticsData() {
    try {
        // Show loading indicator
        const refreshBtn = document.querySelector('button[onclick="refreshAnalytics()"]');
        if (refreshBtn) {
            const originalText = refreshBtn.textContent;
            refreshBtn.textContent = '🔄 Refreshing...';
            refreshBtn.disabled = true;
        }
        
        // Call refresh API
        const response = await fetch('/api/analytics/refresh', { method: 'POST' });
        if (!response.ok) throw new Error('Failed to refresh analytics');
        
        // Reload analytics data
        await loadAnalyticsData();
        
        showNotification('Analytics data refreshed successfully', 'success');
        
        // Restore button
        if (refreshBtn) {
            refreshBtn.textContent = '🔄 Refresh Data';
            refreshBtn.disabled = false;
        }
        
    } catch (error) {
        console.error('Refresh error:', error);
        showNotification('Failed to refresh analytics data', 'error');
        
        // Restore button on error
        const refreshBtn = document.querySelector('button[onclick="refreshAnalytics()"]');
        if (refreshBtn) {
            refreshBtn.textContent = '🔄 Refresh Data';
            refreshBtn.disabled = false;
        }
    }
}

/**
 * Initialize analytics view
 */
function initializeAnalyticsView() {
    // Set up any initial event handlers or configurations
    console.log('Analytics view initialized');
    
    // Auto-refresh every 5 minutes
    setInterval(() => {
        if (currentView === 'analytics') {
            loadAnalyticsData();
        }
    }, 300000); // 5 minutes
}

// Add CSS for analytics-specific elements
const analyticsCSS = `
.analytics-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 32px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border-color);
}

.analytics-header h2 {
    color: var(--text-primary);
    font-size: 24px;
    font-weight: 600;
    margin: 0;
}

.last-updated {
    color: var(--text-muted);
    font-size: 12px;
}

.analytics-cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
    margin-bottom: 32px;
}

.analytics-card {
    background-color: var(--secondary-bg);
    border: 1px solid var(--border-color);
    border-radius: var(--border-radius);
    padding: var(--card-padding);
    text-align: center;
    transition: var(--transition);
}

.analytics-card:hover {
    border-color: var(--tertiary-bg);
}

.analytics-card h3 {
    color: var(--text-muted);
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin: 0 0 12px 0;
}

.metric-value {
    font-size: 32px;
    font-weight: 700;
    color: var(--status-info);
    line-height: 1;
    margin-bottom: 4px;
}

.metric-unit {
    color: var(--text-muted);
    font-size: 12px;
}

.analytics-section {
    background-color: var(--secondary-bg);
    border: 1px solid var(--border-color);
    border-radius: var(--border-radius);
    padding: 24px;
    margin-bottom: 24px;
}

.analytics-section h3 {
    color: var(--text-primary);
    font-size: 18px;
    font-weight: 600;
    margin: 0 0 20px 0;
}

.projection-summary {
    display: flex;
    justify-content: space-around;
    margin-top: 20px;
    padding-top: 20px;
    border-top: 1px solid var(--border-color);
}

.projection-item {
    text-align: center;
    color: var(--text-secondary);
    font-size: 14px;
}

.projection-item strong {
    color: var(--text-primary);
}

.percentage-bar {
    position: relative;
    background-color: var(--primary-bg);
    border-radius: 4px;
    height: 20px;
    overflow: hidden;
    min-width: 80px;
}

.percentage-fill {
    background-color: var(--status-info);
    height: 100%;
    transition: width 0.3s ease;
}

.percentage-text {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    color: var(--text-primary);
    font-size: 11px;
    font-weight: 600;
}

.analytics-error {
    text-align: center;
    padding: 60px 20px;
    color: var(--text-muted);
}

.analytics-error .error-icon {
    font-size: 48px;
    margin-bottom: 16px;
}

.analytics-error h3 {
    color: var(--status-critical);
    margin-bottom: 16px;
}

.loading-cell, .no-data {
    text-align: center;
    color: var(--text-muted);
    font-style: italic;
    padding: 20px;
}

.last-activity {
    color: var(--text-muted);
    font-size: 12px;
}

/* Responsive adjustments */
@media (max-width: 768px) {
    .analytics-header {
        flex-direction: column;
        align-items: flex-start;
        gap: 12px;
    }
    
    .analytics-cards {
        grid-template-columns: 1fr 1fr;
    }
    
    .projection-summary {
        flex-direction: column;
        gap: 12px;
        text-align: center;
    }
}

@media (max-width: 480px) {
    .analytics-cards {
        grid-template-columns: 1fr;
    }
}
`;

// Inject analytics CSS
if (!document.getElementById('analytics-styles')) {
    const styleEl = document.createElement('style');
    styleEl.id = 'analytics-styles';
    styleEl.textContent = analyticsCSS;
    document.head.appendChild(styleEl);
}

// Initialize analytics view when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    if (typeof initializeAnalyticsView === 'function') {
        initializeAnalyticsView();
    }
});