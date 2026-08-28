/**
 * CAD System Data Visualization Module
 * Uses Chart.js to create visualizations of CAD system data
 */

class DataVisualization {
    constructor() {
        // Track chart instances for cleanup
        this.charts = {};
        
        // Color schemes for different chart types
        this.colorSchemes = {
            type: [
                'rgba(54, 162, 235, 0.8)',  // Blue
                'rgba(255, 99, 132, 0.8)',  // Red
                'rgba(75, 192, 192, 0.8)',  // Teal
                'rgba(255, 206, 86, 0.8)',  // Yellow
                'rgba(153, 102, 255, 0.8)', // Purple
                'rgba(255, 159, 64, 0.8)',  // Orange
                'rgba(199, 199, 199, 0.8)'  // Gray
            ],
            priority: {
                1: 'rgba(255, 99, 132, 0.8)',  // Red - Emergency
                2: 'rgba(255, 206, 86, 0.8)',  // Yellow - Urgent
                3: 'rgba(75, 192, 192, 0.8)',  // Teal - Non-urgent
            },
            status: {
                'PENDING': 'rgba(255, 206, 86, 0.8)',    // Yellow
                'ACTIVE': 'rgba(54, 162, 235, 0.8)',     // Blue
                'CLOSED': 'rgba(75, 192, 192, 0.8)',     // Teal
                'CANCELED': 'rgba(199, 199, 199, 0.8)'   // Gray
            }
        };
    }
    
    /**
     * Initialize visualizations on a page
     */
    init() {
        // Get any chart containers on the page
        const chartContainers = document.querySelectorAll('[data-chart-type]');
        
        // Initialize each chart
        chartContainers.forEach(container => {
            const chartType = container.getAttribute('data-chart-type');
            const dataUrl = container.getAttribute('data-url');
            const refreshInterval = parseInt(container.getAttribute('data-refresh-interval') || '0');
            
            if (chartType && dataUrl) {
                this.loadChart(container.id, chartType, dataUrl);
                
                // Set up auto-refresh if specified
                if (refreshInterval && refreshInterval > 0) {
                    setInterval(() => {
                        this.loadChart(container.id, chartType, dataUrl);
                    }, refreshInterval * 1000);
                }
            }
        });
    }
    
    /**
     * Load data and create a chart
     * @param {string} containerId - The ID of the container element
     * @param {string} chartType - The type of chart to create (pie, bar, line, etc.)
     * @param {string} dataUrl - The URL to fetch data from
     */
    async loadChart(containerId, chartType, dataUrl) {
        try {
            // Add query parameters if they exist in the form
            const form = document.querySelector(`#${containerId}`).closest('form');
            let url = dataUrl;
            
            if (form) {
                const formData = new FormData(form);
                const params = new URLSearchParams();
                
                for (const [key, value] of formData.entries()) {
                    if (value) {
                        params.append(key, value);
                    }
                }
                
                if (params.toString()) {
                    url = `${dataUrl}?${params.toString()}`;
                }
            }
            
            // Fetch the data
            const response = await fetch(url);
            
            if (!response.ok) {
                throw new Error(`Error fetching data: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (!data.success) {
                throw new Error(data.message || 'Error loading chart data');
            }
            
            // Create or update the chart
            this.createChart(containerId, chartType, data);
            
            // Update timestamp if it exists
            const timestampElement = document.querySelector(`#${containerId}-timestamp`);
            if (timestampElement) {
                timestampElement.textContent = new Date().toLocaleString();
            }
            
        } catch (error) {
            console.error(`Error loading chart ${containerId}:`, error);
            document.getElementById(containerId).innerHTML = `
                <div class="alert alert-danger">
                    Error loading chart: ${error.message}
                </div>
            `;
        }
    }
    
    /**
     * Create or update a chart
     * @param {string} containerId - The ID of the container element
     * @param {string} chartType - The type of chart to create
     * @param {object} data - The data object returned from the API
     */
    createChart(containerId, chartType, data) {
        // Get the canvas element
        const container = document.getElementById(containerId);
        let canvas = container.querySelector('canvas');
        
        // Create canvas if it doesn't exist
        if (!canvas) {
            canvas = document.createElement('canvas');
            container.innerHTML = '';
            container.appendChild(canvas);
        }
        
        // Destroy existing chart if it exists
        if (this.charts[containerId]) {
            this.charts[containerId].destroy();
        }
        
        // Create new chart based on type
        switch (chartType) {
            case 'incident-by-type':
                this.createIncidentByTypeChart(containerId, canvas, data);
                break;
            case 'incident-by-priority':
                this.createIncidentByPriorityChart(containerId, canvas, data);
                break;
            case 'incident-by-status':
                this.createIncidentByStatusChart(containerId, canvas, data);
                break;
            case 'incident-activity':
                this.createIncidentActivityChart(containerId, canvas, data);
                break;
            default:
                container.innerHTML = `<div class="alert alert-warning">Unknown chart type: ${chartType}</div>`;
        }
    }
    
    /**
     * Create a pie chart showing incidents by type
     * @param {string} containerId - The ID of the container element
     * @param {HTMLCanvasElement} canvas - The canvas element
     * @param {object} data - The data object returned from the API
     */
    createIncidentByTypeChart(containerId, canvas, data) {
        const chartData = data.data;
        
        // Extract labels and values
        const labels = chartData.map(item => item.type_name);
        const values = chartData.map(item => item.count);
        
        // Use colors from the scheme
        const colors = this.colorSchemes.type.slice(0, chartData.length);
        
        // Create the chart
        this.charts[containerId] = new Chart(canvas, {
            type: 'pie',
            data: {
                labels: labels,
                datasets: [{
                    data: values,
                    backgroundColor: colors
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const label = context.label || '';
                                const value = context.raw || 0;
                                const total = values.reduce((a, b) => a + b, 0);
                                const percentage = Math.round((value / total) * 100);
                                return `${label}: ${value} (${percentage}%)`;
                            }
                        }
                    }
                }
            }
        });
    }
    
    /**
     * Create a pie chart showing incidents by priority
     * @param {string} containerId - The ID of the container element
     * @param {HTMLCanvasElement} canvas - The canvas element
     * @param {object} data - The data object returned from the API
     */
    createIncidentByPriorityChart(containerId, canvas, data) {
        const chartData = data.data;
        
        // Extract labels and values
        const labels = chartData.map(item => item.priority_label);
        const values = chartData.map(item => item.count);
        
        // Use priority-specific colors
        const colors = chartData.map(item => this.colorSchemes.priority[item.priority_value] || 'rgba(199, 199, 199, 0.8)');
        
        // Create the chart
        this.charts[containerId] = new Chart(canvas, {
            type: 'pie',
            data: {
                labels: labels,
                datasets: [{
                    data: values,
                    backgroundColor: colors
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const label = context.label || '';
                                const value = context.raw || 0;
                                const total = values.reduce((a, b) => a + b, 0);
                                const percentage = Math.round((value / total) * 100);
                                return `${label}: ${value} (${percentage}%)`;
                            }
                        }
                    }
                }
            }
        });
    }
    
    /**
     * Create a pie chart showing incidents by status
     * @param {string} containerId - The ID of the container element
     * @param {HTMLCanvasElement} canvas - The canvas element
     * @param {object} data - The data object returned from the API
     */
    createIncidentByStatusChart(containerId, canvas, data) {
        const chartData = data.data;
        
        // Extract labels and values
        const labels = chartData.map(item => item.status);
        const values = chartData.map(item => item.count);
        
        // Use status-specific colors
        const colors = chartData.map(item => this.colorSchemes.status[item.status] || 'rgba(199, 199, 199, 0.8)');
        
        // Create the chart
        this.charts[containerId] = new Chart(canvas, {
            type: 'pie',
            data: {
                labels: labels,
                datasets: [{
                    data: values,
                    backgroundColor: colors
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const label = context.label || '';
                                const value = context.raw || 0;
                                const total = values.reduce((a, b) => a + b, 0);
                                const percentage = Math.round((value / total) * 100);
                                return `${label}: ${value} (${percentage}%)`;
                            }
                        }
                    }
                }
            }
        });
    }
    
    /**
     * Create a line chart showing incident activity over time
     * @param {string} containerId - The ID of the container element
     * @param {HTMLCanvasElement} canvas - The canvas element
     * @param {object} data - The data object returned from the API
     */
    createIncidentActivityChart(containerId, canvas, data) {
        const chartData = data.data;
        
        // Extract dates and counts
        const dates = chartData.map(item => item.date);
        const counts = chartData.map(item => item.count);
        
        // Create the chart
        this.charts[containerId] = new Chart(canvas, {
            type: 'line',
            data: {
                labels: dates,
                datasets: [{
                    label: 'Incident Count',
                    data: counts,
                    borderColor: 'rgba(54, 162, 235, 1)',
                    backgroundColor: 'rgba(54, 162, 235, 0.2)',
                    tension: 0.1,
                    fill: true
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            precision: 0
                        }
                    }
                },
                plugins: {
                    tooltip: {
                        callbacks: {
                            title: function(context) {
                                // Format the date for display
                                const date = new Date(context[0].label);
                                return date.toLocaleDateString();
                            }
                        }
                    }
                }
            }
        });
    }
}

// Create a global instance
window.visualization = new DataVisualization();

// Initialize visualizations when the document is ready
document.addEventListener('DOMContentLoaded', function() {
    window.visualization.init();
});
