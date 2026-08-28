// Handle permission updates
class PermissionHandler {
    static init() {
        // Wait for socket to be initialized
        if (typeof socket !== 'undefined') {
            this.initializeSocketListeners();
        } else {
            // If socket is not yet initialized, wait for it
            window.addEventListener('socket_initialized', () => {
                this.initializeSocketListeners();
            });
        }
    }

    static initializeSocketListeners() {
        if (!socket) {
            console.warn('Socket not initialized');
            return;
        }

        // Listen for permission refresh events
        socket.on('refresh_permissions', (data) => {
            // Check if current user is affected
            const currentUserId = document.body.getAttribute('data-user-id');
            const affectedUserIds = data.user_ids || [data.user_id];
            
            if (affectedUserIds.includes(currentUserId)) {
                // Refresh the page to get updated permissions
                window.location.reload();
            }
        });
    }
}

// Initialize permission handler when document is ready
document.addEventListener('DOMContentLoaded', () => {
    PermissionHandler.init();
});
