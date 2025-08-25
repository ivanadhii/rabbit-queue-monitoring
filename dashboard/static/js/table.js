/**
 * Table View Management for GPS Dashboard
 * Handles tabular data display with filtering and sorting
 */

let tableData = [];
let sortColumn = 'timestamp';
let sortDirection = 'desc';
let currentFilter = '';

/**
 * Load and render table view
 */
async function loadTableView(customFromTime = null, customToTime = null) {
    try {
        hideLoading();
        
        // Clear existing content and show table container
        document.getElementById('table-container').innerHTML = '';
        document.getElementById('table-container').style.display = 'block';
        
        // Create table layout
        createTableLayout();
        
        // Load table data
        await loadTableData(customFromTime, customToTime);
        
    } catch (error) {
        console.error('Error loading table view:', error);
        showError('Failed to load table data');
    }
}

/**
 * Create table HTML layout
 */
function createTableLayout() {
    const container = document.getElementById('table-container');
    
    const tableHtml = `
        <div class="table-header">
            <div class="table-title">
                <h2>Queue Metrics Data</h2>
                <div class="table-info">
                    <span id="table-row-count">0 records</span>
                    <span class="separator">•</span>
                    <span id="table-time-range">Loading...</span>
                </div>
            </div>
            <div class="table-controls">
                <div class="search-box">
                    <input type="text" id="table-search" placeholder="Search queues..." 
                           onkeyup="filterTable()" />
                    <span class="search-icon">🔍</span>
                </div>
                <div class="table-actions">
                    <button class="btn-secondary" onclick="refreshTableData()">
                        🔄 Refresh
                    </button>
                    <button class="btn-secondary" onclick="exportTableData('csv')">
                        📄 Export CSV
                    </button>
                </div>
            </div>
        </div>
        
        <div class="table-content">
            <div class="table-wrapper">
                <table class="data-table" id="metrics-table">
                    <thead>
                        <tr>
                            <th class="sortable" onclick="sortTable('timestamp')">
                                Timestamp
                                <span class="sort-indicator" id="sort-timestamp">▼</span>
                            </th>
                            <th class="sortable" onclick="sortTable('queue_name')">
                                Queue Name
                                <span class="sort-indicator" id="sort-queue_name"></span>
                            </th>
                            <th class="sortable" onclick="sortTable('category')">
                                Category
                                <span class="sort-indicator" id="sort-category"></span>
                            </th>
                            <th class="sortable" onclick="sortTable('messages_ready')">
                                Ready Messages
                                <span class="sort-indicator" id="sort-messages_ready"></span>
                            </th>
                            <th class="sortable" onclick="sortTable('incoming_rate')">
                                Incoming Rate
                                <span class="sort-indicator" id="sort-incoming_rate"></span>
                            </th>
                            <th class="sortable" onclick="sortTable('consume_rate')">
                                Consume Rate
                                <span class="sort-indicator" id="sort-consume_rate"></span>
                            </th>
                            <th class="sortable" onclick="sortTable('consumer_count')">
                                Consumers
                                <span class="sort-indicator" id="sort-consumer_count"></span>
                            </th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody id="metrics-table-body">
                        <tr>
                            <td colspan="8" class="loading-cell">Loading table data...</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            
            <!-- Pagination -->
            <div class="table-pagination" id="table-pagination" style="display: none;">
                <div class="pagination-info">
                    Showing <span id="pagination-start">0</span> to <span id="pagination-end">0</span> 
                    of <span id="pagination-total">0</span> records
                </div>
                <div class="pagination-controls">
                    <button class="btn-secondary" id="prev-page" onclick="changePage(-1)" disabled>
                        ← Previous
                    </button>
                    <span class="page-info">
                        Page <span id="current-page">1</span> of <span id="total-pages">1</span>
                    </span>
                    <button class="btn-secondary" id="next-page" onclick="changePage(1)" disabled>
                        Next →
                    </button>
                </div>
            </div>
        </div>
        
        <!-- Loading overlay -->
        <div class="table-loading-overlay" id="table-loading" style="display: none;">
            <div class="loading-spinner"></div>
            <p>Loading data...</p>
        </div>
    `;
    
    container.innerHTML = tableHtml;
}

/**
 * Load table data from API
 */
async function loadTableData(customFromTime = null, customToTime = null) {
    try {
        showTableLoading();
        
        // Build query parameters
        const params = new URLSearchParams();
        
        if (customFromTime && customToTime) {
            params.set('from_time', customFromTime);
            params.set('to_time', customToTime);
        }
        
        params.set('limit', '1000'); // Limit for performance
        
        // Fetch data
        const response = await fetch(`/api/metrics/table?${params.toString()}`);
        if (!response.ok) throw new Error('Failed to fetch table data');
        
        const data = await response.json();
        
        // Store data
        tableData = data.records || [];
        
        // Update UI
        renderTableData();
        updateTableInfo(data);
        hideTableLoading();
        
    } catch (error) {
        console.error('Error loading table data:', error);
        hideTableLoading();
        showTableError('Failed to load table data: ' + error.message);
    }
}

/**
 * Render table data
 */
function renderTableData() {
    const tbody = document.getElementById('metrics-table-body');
    if (!tbody) return;
    
    // Apply current filter
    let filteredData = tableData;
    if (currentFilter) {
        filteredData = tableData.filter(row => 
            row.queue_name?.toLowerCase().includes(currentFilter.toLowerCase()) ||
            row.category?.toLowerCase().includes(currentFilter.toLowerCase())
        );
    }
    
    // Apply current sort
    filteredData.sort((a, b) => {
        const aVal = a[sortColumn];
        const bVal = b[sortColumn];
        
        let comparison = 0;
        if (aVal < bVal) comparison = -1;
        if (aVal > bVal) comparison = 1;
        
        return sortDirection === 'desc' ? -comparison : comparison;
    });
    
    // Render rows
    if (filteredData.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="no-data">No data available</td></tr>';
        return;
    }
    
    tbody.innerHTML = filteredData.map(row => `
        <tr>
            <td class="timestamp-cell">
                <div class="timestamp-primary">${formatDate(row.timestamp)}</div>
                <div class="timestamp-secondary">${formatTime(row.timestamp)}</div>
            </td>
            <td>
                <strong class="queue-name">${row.queue_name || '-'}</strong>
            </td>
            <td>
                <span class="queue-category ${(row.category || 'support').toLowerCase()}">
                    ${row.category || 'SUPPORT'}
                </span>
            </td>
            <td class="numeric-cell">
                <span class="metric-value">${formatNumber(row.messages_ready || 0)}</span>
            </td>
            <td class="numeric-cell">
                <span class="rate-value">${formatRate(row.incoming_rate || 0)}</span>
            </td>
            <td class="numeric-cell">
                <span class="rate-value">${formatRate(row.consume_rate || 0)}</span>
            </td>
            <td class="numeric-cell">
                <span class="consumer-count">${row.consumer_count || 0}</span>
            </td>
            <td>
                <span class="status-badge ${getStatusClass(row)}">
                    ${getStatusText(row)}
                </span>
            </td>
        </tr>
    `).join('');
    
    // Update row count
    document.getElementById('table-row-count').textContent = 
        `${filteredData.length.toLocaleString()} record${filteredData.length !== 1 ? 's' : ''}`;
}

/**
 * Update table information
 */
function updateTableInfo(data) {
    const timeRangeEl = document.getElementById('table-time-range');
    
    if (data.time_range) {
        timeRangeEl.textContent = `${data.time_range.from} to ${data.time_range.to}`;
    } else {
        // Default time range display
        const now = new Date();
        const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000);
        timeRangeEl.textContent = `${formatDate(yesterday)} to ${formatDate(now)}`;
    }
}

/**
 * Sort table by column
 */
function sortTable(column) {
    // Toggle sort direction if same column
    if (sortColumn === column) {
        sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        sortColumn = column;
        sortDirection = 'desc'; // Default to descending
    }
    
    // Update sort indicators
    updateSortIndicators();
    
    // Re-render table
    renderTableData();
}

/**
 * Update sort indicators
 */
function updateSortIndicators() {
    // Clear all indicators
    document.querySelectorAll('.sort-indicator').forEach(indicator => {
        indicator.textContent = '';
    });
    
    // Set current column indicator
    const indicator = document.getElementById(`sort-${sortColumn}`);
    if (indicator) {
        indicator.textContent = sortDirection === 'asc' ? '▲' : '▼';
    }
}

/**
 * Filter table data
 */
function filterTable() {
    const searchInput = document.getElementById('table-search');
    currentFilter = searchInput.value;
    renderTableData();
}

/**
 * Refresh table data
 */
async function refreshTableData() {
    const customFrom = document.getElementById('time-from')?.value;
    const customTo = document.getElementById('time-to')?.value;
    
    let fromTime = null;
    let toTime = null;
    
    if (customFrom && customTo) {
        fromTime = new Date(customFrom).toISOString();
        toTime = new Date(customTo).toISOString();
    }
    
    await loadTableData(fromTime, toTime);
    showNotification('Table data refreshed', 'success');
}

/**
 * Export table data
 */
async function exportTableData(format = 'csv') {
    try {
        const params = new URLSearchParams();
        const customFrom = document.getElementById('time-from')?.value;
        const customTo = document.getElementById('time-to')?.value;
        
        if (customFrom && customTo) {
            params.set('from_time', new Date(customFrom).toISOString());
            params.set('to_time', new Date(customTo).toISOString());
        }
        
        const url = `/api/metrics/export/${format}?${params.toString()}`;
        const response = await fetch(url);
        
        if (!response.ok) throw new Error('Export failed');
        
        // Trigger download
        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = `queue-metrics-table-${new Date().toISOString().split('T')[0]}.${format}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(downloadUrl);
        
        showNotification(`Table data exported as ${format.toUpperCase()}`, 'success');
        
    } catch (error) {
        console.error('Export error:', error);
        showNotification('Export failed', 'error');
    }
}

/**
 * Show table loading overlay
 */
function showTableLoading() {
    const overlay = document.getElementById('table-loading');
    if (overlay) overlay.style.display = 'flex';
}

/**
 * Hide table loading overlay
 */
function hideTableLoading() {
    const overlay = document.getElementById('table-loading');
    if (overlay) overlay.style.display = 'none';
}

/**
 * Show table error
 */
function showTableError(message) {
    const tbody = document.getElementById('metrics-table-body');
    if (tbody) {
        tbody.innerHTML = `
            <tr>
                <td colspan="8" class="error-cell">
                    <div class="table-error">
                        <span class="error-icon">⚠️</span>
                        <span class="error-message">${message}</span>
                        <button class="btn-secondary" onclick="refreshTableData()">Retry</button>
                    </div>
                </td>
            </tr>
        `;
    }
}

/**
 * Utility functions for formatting
 */
function formatDate(timestamp) {
    if (!timestamp) return '-';
    const date = new Date(timestamp);
    return date.toLocaleDateString();
}

function formatTime(timestamp) {
    if (!timestamp) return '-';
    const date = new Date(timestamp);
    return date.toLocaleTimeString();
}

function formatNumber(value) {
    if (value === null || value === undefined) return '-';
    return Number(value).toLocaleString();
}

function formatRate(value) {
    if (value === null || value === undefined) return '-';
    return `${Number(value).toFixed(1)}/s`;
}

function getStatusClass(row) {
    const ready = row.messages_ready || 0;
    const consumers = row.consumer_count || 0;
    
    if (consumers === 0 && ready > 0) return 'critical';
    if (ready > 1000) return 'warning';
    return 'healthy';
}

function getStatusText(row) {
    const ready = row.messages_ready || 0;
    const consumers = row.consumer_count || 0;
    
    if (consumers === 0 && ready > 0) return 'NO CONSUMERS';
    if (ready > 1000) return 'HIGH BACKLOG';
    return 'HEALTHY';
}

// Add CSS for table-specific elements
const tableCSS = `
.table-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 20px;
    gap: 20px;
}

.table-title h2 {
    color: var(--text-primary);
    font-size: 20px;
    font-weight: 600;
    margin: 0 0 8px 0;
}

.table-info {
    color: var(--text-muted);
    font-size: 12px;
}

.separator {
    margin: 0 8px;
}

.table-controls {
    display: flex;
    align-items: flex-start;
    gap: 12px;
}

.search-box {
    position: relative;
}

.search-box input {
    padding: 8px 36px 8px 12px;
    background-color: var(--primary-bg);
    border: 1px solid var(--border-color);
    border-radius: var(--border-radius);
    color: var(--text-primary);
    font-size: 13px;
    width: 200px;
}

.search-box input:focus {
    outline: none;
    border-color: var(--status-info);
}

.search-icon {
    position: absolute;
    right: 12px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--text-muted);
    font-size: 12px;
}

.table-actions {
    display: flex;
    gap: 8px;
}

.table-content {
    position: relative;
}

.table-wrapper {
    overflow-x: auto;
    background-color: var(--secondary-bg);
    border: 1px solid var(--border-color);
    border-radius: var(--border-radius);
}

.data-table th.sortable {
    cursor: pointer;
    user-select: none;
    position: relative;
}

.data-table th.sortable:hover {
    background-color: var(--tertiary-bg);
}

.sort-indicator {
    font-size: 10px;
    margin-left: 4px;
    opacity: 0.7;
}

.timestamp-cell {
    min-width: 120px;
}

.timestamp-primary {
    font-weight: 600;
    color: var(--text-primary);
}

.timestamp-secondary {
    font-size: 11px;
    color: var(--text-muted);
}

.queue-name {
    color: var(--text-primary);
}

.numeric-cell {
    text-align: right;
    font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', monospace;
}

.metric-value, .rate-value, .consumer-count {
    font-weight: 500;
}

.status-badge {
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
}

.status-badge.healthy {
    background-color: rgba(16, 185, 129, 0.1);
    color: var(--status-healthy);
}

.status-badge.warning {
    background-color: rgba(245, 158, 11, 0.1);
    color: var(--status-warning);
}

.status-badge.critical {
    background-color: rgba(239, 68, 68, 0.1);
    color: var(--status-critical);
}

.table-loading-overlay {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(15, 23, 42, 0.8);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    color: var(--text-muted);
    z-index: 10;
}

.loading-cell, .no-data, .error-cell {
    text-align: center;
    color: var(--text-muted);
    font-style: italic;
    padding: 40px 20px;
}

.table-error {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
}

.error-icon {
    font-size: 16px;
}

.table-pagination {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 20px;
    padding: 16px;
    background-color: var(--secondary-bg);
    border: 1px solid var(--border-color);
    border-radius: var(--border-radius);
}

.pagination-info {
    color: var(--text-muted);
    font-size: 12px;
}

.pagination-controls {
    display: flex;
    align-items: center;
    gap: 16px;
}

.page-info {
    color: var(--text-secondary);
    font-size: 12px;
}

@media (max-width: 768px) {
    .table-header {
        flex-direction: column;
        align-items: stretch;
    }
    
    .table-controls {
        flex-direction: column;
    }
    
    .search-box input {
        width: 100%;
    }
    
    .table-actions {
        justify-content: center;
    }
}
`;

// Inject table CSS
if (!document.getElementById('table-styles')) {
    const styleEl = document.createElement('style');
    styleEl.id = 'table-styles';
    styleEl.textContent = tableCSS;
    document.head.appendChild(styleEl);
}