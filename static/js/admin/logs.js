document.addEventListener('DOMContentLoaded', function() {
    // Initialize variables
    let currentPage = 1;
    const logsPerPage = 50;
    let currentFilters = {
        type: 'all',
        startDate: moment().subtract(7, 'days').startOf('day'),
        endDate: moment().endOf('day'),
        user: '',
        search: ''
    };

    // Initialize date range picker
    $('#dateRange').daterangepicker({
        startDate: currentFilters.startDate,
        endDate: currentFilters.endDate,
        ranges: {
           'Today': [moment().startOf('day'), moment().endOf('day')],
           'Yesterday': [moment().subtract(1, 'days').startOf('day'), moment().subtract(1, 'days').endOf('day')],
           'Last 7 Days': [moment().subtract(6, 'days').startOf('day'), moment().endOf('day')],
           'Last 30 Days': [moment().subtract(29, 'days').startOf('day'), moment().endOf('day')],
           'This Month': [moment().startOf('month'), moment().endOf('month')],
           'Last Month': [moment().subtract(1, 'month').startOf('month'), moment().subtract(1, 'month').endOf('month')]
        }
    }, function(start, end) {
        currentFilters.startDate = start;
        currentFilters.endDate = end;
        loadLogs();
    });

    // Event listeners for filters
    document.getElementById('logType').addEventListener('change', function(e) {
        currentFilters.type = e.target.value;
        currentPage = 1;
        loadLogs();
    });

    document.getElementById('userFilter').addEventListener('change', function(e) {
        currentFilters.user = e.target.value;
        currentPage = 1;
        loadLogs();
    });

    document.getElementById('search').addEventListener('input', debounce(function(e) {
        currentFilters.search = e.target.value;
        currentPage = 1;
        loadLogs();
    }, 300));

    // Pagination handlers
    document.getElementById('prevPage').addEventListener('click', function() {
        if (currentPage > 1) {
            currentPage--;
            loadLogs();
        }
    });

    document.getElementById('nextPage').addEventListener('click', function() {
        currentPage++;
        loadLogs();
    });

    // Refresh button handler
    document.getElementById('refreshLogsBtn').addEventListener('click', function() {
        loadLogs();
    });

    // Export PDF handler
    document.getElementById('exportPdfBtn')?.addEventListener('click', function() {
        exportLogs();
    });

    // Function to load logs from the server
    function loadLogs() {
        const params = new URLSearchParams({
            page: currentPage,
            per_page: logsPerPage,
            type: currentFilters.type,
            start_date: currentFilters.startDate.toISOString(),
            end_date: currentFilters.endDate.toISOString(),
            user: currentFilters.user,
            search: currentFilters.search
        });

        fetch(`/admin/api/admin/logs?${params}`)
            .then(response => response.json())
            .then(data => {
                updateLogsTable(data.logs);
                updatePagination(data.total, data.page, data.per_page);
            })
            .catch(error => {
                console.error('Error loading logs:', error);
                showAlert('error', 'Error loading logs. Please try again.');
            });
    }

    // Function to update the logs table
    function updateLogsTable(logs) {
        const tbody = document.getElementById('logsTableBody');
        tbody.innerHTML = '';

        logs.forEach(log => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${moment(log.timestamp).format('YYYY-MM-DD HH:mm:ss')}</td>
                <td><span class="badge bg-${getLevelBadgeClass(log.level)}">${log.level}</span></td>
                <td>${log.user || '-'}</td>
                <td>${log.message}</td>
                <td>
                    <button class="btn btn-sm btn-outline-primary" onclick="showLogDetails(${JSON.stringify(log)})">
                        <i class="fas fa-info-circle"></i>
                    </button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    }

    // Function to update pagination
    function updatePagination(total, page, perPage) {
        const start = (page - 1) * perPage + 1;
        const end = Math.min(start + perPage - 1, total);
        
        document.getElementById('currentRange').textContent = `${start}-${end}`;
        document.getElementById('totalLogs').textContent = total;
        
        const prevBtn = document.getElementById('prevPage');
        const nextBtn = document.getElementById('nextPage');
        
        prevBtn.parentElement.classList.toggle('disabled', page === 1);
        nextBtn.parentElement.classList.toggle('disabled', end >= total);
    }

    // Function to show log details in modal
    window.showLogDetails = function(log) {
        document.getElementById('modalTimestamp').textContent = moment(log.timestamp).format('YYYY-MM-DD HH:mm:ss');
        document.getElementById('modalLevel').textContent = log.level;
        document.getElementById('modalUser').textContent = log.user || '-';
        document.getElementById('modalMessage').textContent = log.message;
        document.getElementById('modalStackTrace').textContent = log.stack_trace || 'No stack trace available';
        document.getElementById('modalData').textContent = JSON.stringify(log.data || {}, null, 2);
        
        new bootstrap.Modal(document.getElementById('logDetailsModal')).show();
    };

    // Function to export logs as PDF
    function exportLogs() {
        const params = new URLSearchParams({
            type: currentFilters.type,
            start_date: currentFilters.startDate.toISOString(),
            end_date: currentFilters.endDate.toISOString(),
            user: currentFilters.user,
            search: currentFilters.search
        });

        window.location.href = `/admin/api/admin/logs/export?${params}`;
    }

    // Utility function to get badge class based on log level
    function getLevelBadgeClass(level) {
        const classes = {
            'ERROR': 'danger',
            'WARNING': 'warning',
            'INFO': 'info',
            'DEBUG': 'secondary'
        };
        return classes[level.toUpperCase()] || 'secondary';
    }

    // Utility function to debounce input
    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    // Load initial logs
    loadLogs();
});
