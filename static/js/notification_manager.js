/**
 * Notification Manager
 * Handles notification functionality across the application
 */

class NotificationManager {
    constructor() {
        this.unreadCount = 0;
        this.notifications = [];
        this.page = 1;
        this.perPage = 10;
        this.hasMore = false;
        this.currentFilter = '';
        
        this.initialize();
    }

    /**
     * Initialize the notification manager
     */
    initialize() {
        // Update notification badge count on page load
        this.getUnreadCount();

        // Set up WebSocket listener for real-time notifications
        if (typeof socket !== 'undefined') {
            // Listen for new notifications
            socket.on('new_notification', (data) => {
                this.handleNewNotification(data);
            });
            
            // Listen for notification list updates
            socket.on('notifications_list', (data) => {
                this.handleNotificationsList(data);
            });
            
            // Listen for status updates
            socket.on('notification_status_updated', (data) => {
                this.handleNotificationStatusUpdate(data);
            });
            
            // Listen for preference updates
            socket.on('notification_settings', (data) => {
                this.handleNotificationSettings(data);
            });
        }

        // Initialize sound manager for notification sounds
        this.initializeSoundManager();
        
        // Initialize UI event handlers
        this.initializeUIHandlers();
    }
    
    /**
     * Initialize UI event handlers for notification elements
     */
    initializeUIHandlers() {
        // Mark all as read button
        $(document).on('click', '#mark-all-read', (e) => {
            e.preventDefault();
            this.markAllAsRead();
        });
        
        // Notification preference button
        $(document).on('click', '#notification-preferences', (e) => {
            e.preventDefault();
            this.loadNotificationPreferences();
        });
        
        // Individual notification actions
        $(document).on('click', '.notification-mark-read', (e) => {
            e.preventDefault();
            const id = $(e.currentTarget).closest('.notification-item').data('id');
            this.markAsRead(id);
        });
        
        $(document).on('click', '.notification-archive', (e) => {
            e.preventDefault();
            const id = $(e.currentTarget).closest('.notification-item').data('id');
            this.archiveNotification(id);
        });
        
        $(document).on('click', '.notification-delete', (e) => {
            e.preventDefault();
            const id = $(e.currentTarget).closest('.notification-item').data('id');
            this.deleteNotification(id);
        });
        
        // Load more buttons
        $(document).on('click', '.load-more-btn', (e) => {
            e.preventDefault();
            const listType = $(e.currentTarget).data('list');
            this.loadMoreNotifications(listType);
        });
        
        // Tab change event
        $(document).on('shown.bs.tab', 'a[data-toggle="tab"]', (e) => {
            const target = $(e.target).attr("href");
            if (target === '#all') {
                this.loadNotifications('all');
            } else if (target === '#unread') {
                this.loadNotifications('unread');
            } else if (target === '#archived') {
                this.loadNotifications('archived');
            }
        });
        
        // Save notification preferences
        $(document).on('submit', '#notification-preferences-form', (e) => {
            e.preventDefault();
            this.saveNotificationPreferences();
        });
    }

    /**
     * Get unread notification count from the server
     */
    getUnreadCount() {
        if (typeof socket !== 'undefined') {
            socket.emit('get_unread_notification_count', {}, (response) => {
                if (response.success) {
                    this.unreadCount = response.count;
                    this.updateNotificationBadge();
                }
            });
        }
    }
    
    /**
     * Load notifications from the server
     * @param {string} filter - Filter type (all, unread, archived)
     * @param {number} page - Page number to load
     */
    loadNotifications(filter = 'all', page = 1) {
        this.currentFilter = filter;
        this.page = page;
        
        if (typeof socket !== 'undefined') {
            socket.emit('get_notifications', {
                page: page,
                per_page: this.perPage,
                status: filter === 'unread' ? 'unread' : (filter === 'archived' ? 'archived' : null)
            });
        }
    }
    
    /**
     * Load more notifications (next page)
     * @param {string} listType - List type (all, unread, archived)
     */
    loadMoreNotifications(listType) {
        this.loadNotifications(listType, this.page + 1);
    }
    
    /**
     * Handle notifications list data from WebSocket
     * @param {Object} data - Notifications list data
     */
    handleNotificationsList(data) {
        if (data.success) {
            // If first page, clear the list
            if (data.page === 1) {
                this.notifications = data.notifications;
                $(`#${this.currentFilter}-notifications .notification-items`).empty();
            } else {
                // Append to existing list
                this.notifications = [...this.notifications, ...data.notifications];
            }
            
            // Update UI
            this.renderNotifications(data.notifications, this.currentFilter, data.page === 1);
            
            // Update pagination
            this.hasMore = data.has_more;
            $(`#${this.currentFilter}-load-more`).toggleClass('d-none', !this.hasMore);
            
            // Update empty state
            const isEmpty = data.notifications.length === 0 && data.page === 1;
            $(`#${this.currentFilter}-notifications .empty-state`).toggleClass('d-none', !isEmpty);
            
            // Update counts
            if (data.counts) {
                $('#all-count').text(data.counts.all || 0);
                $('#unread-count').text(data.counts.unread || 0);
            }
            
            // Update page number
            this.page = data.page;
        }
    }

    /**
     * Render notifications in the UI
     * @param {Array} notifications - Array of notification objects
     * @param {string} listType - List type to render in (all, unread, archived)
     * @param {boolean} clearList - Whether to clear the list before rendering
     */
    renderNotifications(notifications, listType = 'all', clearList = false) {
        const container = $(`#${listType}-notifications .notification-items`);
        
        // Clear list if requested
        if (clearList) {
            container.empty();
        }
        
        // Render each notification
        notifications.forEach(notification => {
            const template = $('#notification-template').html();
            const element = $(template);
            
            // Set notification data
            element.attr('data-id', notification.id);
            element.find('.notification-title').text(notification.title);
            element.find('.notification-message').text(notification.message);
            element.find('.notification-time').text(this.formatTime(notification.created_at));
            
            // Add type class
            element.addClass(`notification-type-${notification.notification_type.toLowerCase()}`);
            
            // Set status class
            if (notification.status === 'unread') {
                element.addClass('notification-unread');
            }
            
            // Handle reference links
            if (notification.reference_id && notification.reference_type) {
                const link = element.find('.notification-link');
                if (notification.reference_type.includes('incident')) {
                    link.attr('href', `/incident/${notification.reference_id}`);
                    link.show();
                } else if (notification.reference_type.includes('unit')) {
                    link.attr('href', `/unit/${notification.reference_id}`);
                    link.show();
                } else {
                    link.hide();
                }
            } else {
                element.find('.notification-link').hide();
            }
            
            // Append to container
            container.append(element);
        });
    }

    /**
     * Format timestamp for display
     * @param {string} timestamp - ISO timestamp
     * @return {string} Formatted time string
     */
    formatTime(timestamp) {
        const date = new Date(timestamp);
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.round(diffMs / 60000);
        const diffHours = Math.round(diffMs / 3600000);
        const diffDays = Math.round(diffMs / 86400000);
        
        if (diffMins < 1) {
            return 'Just now';
        } else if (diffMins < 60) {
            return `${diffMins} min${diffMins !== 1 ? 's' : ''} ago`;
        } else if (diffHours < 24) {
            return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;
        } else if (diffDays < 7) {
            return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;
        } else {
            return date.toLocaleDateString();
        }
    }

    /**
     * Update the notification badge in the navbar
     */
    updateNotificationBadge() {
        const count = this.unreadCount;
        
        // Update notification badge
        $('.notification-badge').text(count > 0 ? count : '');
        $('.notification-badge').toggle(count > 0);
        
        // Update page title if there are unread notifications
        if (count > 0) {
            const originalTitle = document.title.replace(/^\(\d+\) /, '');
            document.title = `(${count}) ${originalTitle}`;
        } else {
            document.title = document.title.replace(/^\(\d+\) /, '');
        }
        
        // Update favicon if supported
        this.updateFavicon(count);
    }
    
    /**
     * Update the favicon to show notification count
     * @param {number} count - Number of unread notifications
     */
    updateFavicon(count) {
        if (count <= 0) {
            // Reset to original favicon
            $('link[rel="icon"]').attr('href', '/static/img/favicon.ico');
            return;
        }
        
        // Only proceed if canvas is supported
        if (!document.createElement('canvas').getContext) {
            return;
        }
        
        try {
            const canvas = document.createElement('canvas');
            canvas.width = 16;
            canvas.height = 16;
            const ctx = canvas.getContext('2d');
            
            // Draw original favicon
            const img = new Image();
            img.onload = function() {
                // Draw original favicon
                ctx.drawImage(img, 0, 0, 16, 16);
                
                // Draw notification count
                if (count > 0) {
                    ctx.fillStyle = '#FF0000';
                    ctx.beginPath();
                    ctx.arc(12, 4, 4, 0, 2 * Math.PI);
                    ctx.fill();
                    
                    // Add number if less than 10
                    if (count < 10) {
                        ctx.fillStyle = '#FFFFFF';
                        ctx.font = 'bold 8px Arial';
                        ctx.textAlign = 'center';
                        ctx.textBaseline = 'middle';
                        ctx.fillText(count.toString(), 12, 4);
                    }
                }
                
                // Set as favicon
                $('link[rel="icon"]').attr('href', canvas.toDataURL('image/png'));
            };
            
            img.src = '/static/img/favicon.ico';
        } catch (e) {
            console.error('Error updating favicon:', e);
        }
    }

    /**
     * Handle a new notification from WebSocket
     * @param {Object} notification - The notification data
     */
    handleNewNotification(notification) {
        // Update the badge count
        this.unreadCount++;
        this.updateNotificationBadge();

        // Play sound notification if enabled
        this.playNotificationSound(notification.notification_type);

        // Show desktop notification if enabled and supported
        this.showDesktopNotification(notification);
        
        // If we're on the notifications page, update the lists
        if ($('#notification-tabs').length) {
            // Prepend to appropriate lists
            if (this.currentFilter === 'all' || this.currentFilter === 'unread') {
                this.prependNotification(notification, this.currentFilter);
            }
            
            // Update counts
            $('#all-count').text(parseInt($('#all-count').text() || 0) + 1);
            $('#unread-count').text(parseInt($('#unread-count').text() || 0) + 1);
        }
    }
    
    /**
     * Prepend a notification to a list
     * @param {Object} notification - Notification data
     * @param {string} listType - List type (all, unread)
     */
    prependNotification(notification, listType) {
        const template = $('#notification-template').html();
        const element = $(template);
        
        // Set notification data
        element.attr('data-id', notification.id);
        element.find('.notification-title').text(notification.title);
        element.find('.notification-message').text(notification.message);
        element.find('.notification-time').text('Just now');
        
        // Add type class
        element.addClass(`notification-type-${notification.notification_type.toLowerCase()}`);
        
        // Set status class
        element.addClass('notification-unread');
        
        // Handle reference links
        if (notification.reference_id && notification.reference_type) {
            const link = element.find('.notification-link');
            if (notification.reference_type.includes('incident')) {
                link.attr('href', `/incident/${notification.reference_id}`);
                link.show();
            } else if (notification.reference_type.includes('unit')) {
                link.attr('href', `/unit/${notification.reference_id}`);
                link.show();
            } else {
                link.hide();
            }
        } else {
            element.find('.notification-link').hide();
        }
        
        // Prepend to container
        $(`#${listType}-notifications .notification-items`).prepend(element);
        
        // Hide empty state
        $(`#${listType}-notifications .empty-state`).addClass('d-none');
    }
    
    /**
     * Mark a notification as read
     * @param {number} id - Notification ID
     */
    markAsRead(id) {
        if (typeof socket !== 'undefined') {
            socket.emit('update_notification_status', {
                id: id,
                status: 'read'
            }, (response) => {
                if (response.success) {
                    // Update UI
                    $(`.notification-item[data-id="${id}"]`).removeClass('notification-unread');
                    
                    // Update count
                    this.unreadCount--;
                    if (this.unreadCount < 0) this.unreadCount = 0;
                    this.updateNotificationBadge();
                    
                    // Update count badges
                    const unreadCount = parseInt($('#unread-count').text() || 0) - 1;
                    $('#unread-count').text(unreadCount > 0 ? unreadCount : 0);
                }
            });
        }
    }
    
    /**
     * Mark all notifications as read
     */
    markAllAsRead() {
        if (typeof socket !== 'undefined') {
            socket.emit('mark_all_notifications_read', {}, (response) => {
                if (response.success) {
                    // Update UI
                    $('.notification-item.notification-unread').removeClass('notification-unread');
                    
                    // Update count
                    this.unreadCount = 0;
                    this.updateNotificationBadge();
                    
                    // Update count badges
                    $('#unread-count').text('0');
                    
                    // Show empty state for unread tab
                    $('#unread-notifications .empty-state').removeClass('d-none');
                    $('#unread-notifications .notification-items').empty();
                }
            });
        }
    }
    
    /**
     * Archive a notification
     * @param {number} id - Notification ID
     */
    archiveNotification(id) {
        if (typeof socket !== 'undefined') {
            socket.emit('update_notification_status', {
                id: id,
                status: 'archived'
            }, (response) => {
                if (response.success) {
                    // Remove from current lists
                    $(`.notification-item[data-id="${id}"]`).slideUp(300, function() {
                        $(this).remove();
                    });
                    
                    // Update count if it was unread
                    if ($(`.notification-item[data-id="${id}"]`).hasClass('notification-unread')) {
                        this.unreadCount--;
                        if (this.unreadCount < 0) this.unreadCount = 0;
                        this.updateNotificationBadge();
                        
                        // Update count badges
                        const unreadCount = parseInt($('#unread-count').text() || 0) - 1;
                        $('#unread-count').text(unreadCount > 0 ? unreadCount : 0);
                    }
                    
                    // Update all count
                    const allCount = parseInt($('#all-count').text() || 0) - 1;
                    $('#all-count').text(allCount > 0 ? allCount : 0);
                }
            });
        }
    }
    
    /**
     * Delete a notification
     * @param {number} id - Notification ID
     */
    deleteNotification(id) {
        if (typeof socket !== 'undefined') {
            socket.emit('delete_notification', {
                id: id
            }, (response) => {
                if (response.success) {
                    // Remove from all lists
                    $(`.notification-item[data-id="${id}"]`).slideUp(300, function() {
                        $(this).remove();
                    });
                    
                    // Update count if it was unread
                    if ($(`.notification-item[data-id="${id}"]`).hasClass('notification-unread')) {
                        this.unreadCount--;
                        if (this.unreadCount < 0) this.unreadCount = 0;
                        this.updateNotificationBadge();
                        
                        // Update count badges
                        const unreadCount = parseInt($('#unread-count').text() || 0) - 1;
                        $('#unread-count').text(unreadCount > 0 ? unreadCount : 0);
                    }
                    
                    // Update all count
                    const allCount = parseInt($('#all-count').text() || 0) - 1;
                    $('#all-count').text(allCount > 0 ? allCount : 0);
                }
            });
        }
    }

    /**
     * Initialize sound manager for notification sounds
     */
    initializeSoundManager() {
        // Create audio elements
        this.sounds = {
            incident: new Audio('/static/sounds/incident_notification.mp3'),
            unit: new Audio('/static/sounds/unit_notification.mp3'),
            system: new Audio('/static/sounds/system_notification.mp3'),
            default: new Audio('/static/sounds/notification.mp3')
        };

        // Preload sounds
        for (const sound in this.sounds) {
            this.sounds[sound].load();
        }
    }

    /**
     * Play notification sound based on type
     * @param {string} type - Notification type
     */
    playNotificationSound(type) {
        // Check user sound preferences before playing
        const soundPreferencesEnabled = localStorage.getItem('sound_notifications_enabled') !== 'false';
        
        if (!soundPreferencesEnabled) {
            return;
        }

        // Determine which sound to play
        let sound;
        switch (type) {
            case 'INCIDENT':
                sound = this.sounds.incident;
                break;
            case 'UNIT':
                sound = this.sounds.unit;
                break;
            case 'SYSTEM':
                sound = this.sounds.system;
                break;
            default:
                sound = this.sounds.default;
        }

        // Play the sound
        if (sound) {
            sound.play().catch(error => {
                console.error('Error playing notification sound:', error);
            });
        }
    }

    /**
     * Show desktop notification if supported
     * @param {Object} notification - Notification data
     */
    showDesktopNotification(notification) {
        // Check if desktop notifications are supported and enabled
        if (!("Notification" in window)) {
            return;
        }

        // Check user preferences
        const desktopNotificationsEnabled = localStorage.getItem('desktop_notifications_enabled') !== 'false';
        if (!desktopNotificationsEnabled) {
            return;
        }

        // Check permission
        if (Notification.permission === "granted") {
            this.createDesktopNotification(notification);
        } else if (Notification.permission !== "denied") {
            Notification.requestPermission().then(permission => {
                if (permission === "granted") {
                    this.createDesktopNotification(notification);
                }
            });
        }
    }

    /**
     * Create a desktop notification
     * @param {Object} notification - Notification data
     */
    createDesktopNotification(notification) {
        // Determine icon based on notification type
        let icon = '/static/img/logo-icon.png';
        
        if (notification.notification_type === 'INCIDENT') {
            icon = '/static/img/incident-icon.png';
        } else if (notification.notification_type === 'UNIT') {
            icon = '/static/img/unit-icon.png';
        }
        
        // Create notification
        const n = new Notification(notification.title, {
            body: notification.message,
            icon: icon
        });
        
        // Auto close after 5 seconds
        setTimeout(() => {
            n.close();
        }, 5000);
        
        // Click event to go to notification target
        n.onclick = () => {
            window.focus();
            if (notification.reference_id && notification.reference_type) {
                if (notification.reference_type.includes('incident')) {
                    window.location.href = `/incident/${notification.reference_id}`;
                } else if (notification.reference_type.includes('unit')) {
                    window.location.href = `/unit/${notification.reference_id}`;
                } else {
                    window.location.href = '/notifications';
                }
            } else {
                window.location.href = '/notifications';
            }
        };
    }
    
    /**
     * Load notification preferences from the server
     */
    loadNotificationPreferences() {
        if (typeof socket !== 'undefined') {
            socket.emit('get_notification_settings', {}, (response) => {
                if (response) {
                    this.updatePreferencesForm(response);
                    $('#preferencesModal').modal('show');
                }
            });
        } else {
            $('#preferencesModal').modal('show');
        }
    }
    
    /**
     * Update preferences form with server data
     * @param {Object} prefs - Notification preferences
     */
    updatePreferencesForm(prefs) {
        // App notifications
        $('#app_notifications_enabled').prop('checked', prefs.app_enabled || false);
        $('#system_notifications').prop('checked', prefs.app_notify_system_events || false);
        $('#incident_created').prop('checked', prefs.app_notify_incident_created || false);
        $('#incident_updated').prop('checked', prefs.app_notify_incident_updated || false);
        $('#incident_closed').prop('checked', prefs.app_notify_incident_closed || false);
        $('#unit_assigned').prop('checked', prefs.app_notify_unit_assigned || false);
        $('#unit_status_change').prop('checked', prefs.app_notify_unit_status_changed || false);
        
        // Email notifications
        $('#email_enabled').prop('checked', prefs.email_enabled || false);
        $('#email_system_notifications').prop('checked', prefs.email_notify_system_events || false);
        $('#email_incident_created').prop('checked', prefs.email_notify_incident_created || false);
        $('#email_incident_updated').prop('checked', prefs.email_notify_incident_updated || false);
        $('#email_incident_closed').prop('checked', prefs.email_notify_incident_closed || false);
        $('#email_unit_assigned').prop('checked', prefs.email_notify_unit_assigned || false);
        $('#email_unit_status_change').prop('checked', prefs.email_notify_unit_status_changed || false);
        
        // Sound notifications
        $('#sound_notifications').prop('checked', localStorage.getItem('sound_notifications_enabled') !== 'false');
        
        // Desktop notifications
        $('#desktop_notifications').prop('checked', localStorage.getItem('desktop_notifications_enabled') !== 'false');
    }
    
    /**
     * Save notification preferences to the server
     */
    saveNotificationPreferences() {
        const prefs = {
            app_enabled: $('#app_notifications_enabled').is(':checked'),
            app_notify_system_events: $('#system_notifications').is(':checked'),
            app_notify_incident_created: $('#incident_created').is(':checked'),
            app_notify_incident_updated: $('#incident_updated').is(':checked'),
            app_notify_incident_closed: $('#incident_closed').is(':checked'),
            app_notify_unit_assigned: $('#unit_assigned').is(':checked'),
            app_notify_unit_status_changed: $('#unit_status_change').is(':checked'),
            
            email_enabled: $('#email_enabled').is(':checked'),
            email_notify_system_events: $('#email_system_notifications').is(':checked'),
            email_notify_incident_created: $('#email_incident_created').is(':checked'),
            email_notify_incident_updated: $('#email_incident_updated').is(':checked'),
            email_notify_incident_closed: $('#email_incident_closed').is(':checked'),
            email_notify_unit_assigned: $('#email_unit_assigned').is(':checked'),
            email_notify_unit_status_changed: $('#email_unit_status_change').is(':checked')
        };
        
        // Save sound and desktop preferences to localStorage
        localStorage.setItem('sound_notifications_enabled', $('#sound_notifications').is(':checked'));
        localStorage.setItem('desktop_notifications_enabled', $('#desktop_notifications').is(':checked'));
        
        // Save to server
        if (typeof socket !== 'undefined') {
            socket.emit('update_notification_settings', prefs, (response) => {
                if (response.success) {
                    // Show success message
                    showToast('success', 'Notification preferences saved successfully');
                    
                    // Close modal
                    $('#preferencesModal').modal('hide');
                } else {
                    showToast('error', 'Failed to save notification preferences');
                }
            });
        } else {
            // Show error message
            showToast('error', 'Unable to save notification preferences - WebSocket not available');
        }
    }
    
    /**
     * Handle notification settings update from WebSocket
     * @param {Object} settings - Notification settings
     */
    handleNotificationSettings(settings) {
        // Update the form if it's open
        if ($('#preferencesModal').hasClass('show')) {
            this.updatePreferencesForm(settings);
        }
    }
    
    /**
     * Handle notification status update from WebSocket
     * @param {Object} data - Status update data
     */
    handleNotificationStatusUpdate(data) {
        if (data.success && data.notification) {
            const notification = data.notification;
            
            // Handle status change
            if (notification.status === 'read') {
                $(`.notification-item[data-id="${notification.id}"]`).removeClass('notification-unread');
                
                // Update unread count
                this.unreadCount--;
                if (this.unreadCount < 0) this.unreadCount = 0;
                this.updateNotificationBadge();
                
                // Update count badges
                const unreadCount = parseInt($('#unread-count').text() || 0) - 1;
                $('#unread-count').text(unreadCount > 0 ? unreadCount : 0);
                
                // Remove from unread list if in that tab
                if (this.currentFilter === 'unread') {
                    $(`.notification-item[data-id="${notification.id}"]`).slideUp(300, function() {
                        $(this).remove();
                    });
                    
                    // Show empty state if needed
                    if ($('#unread-notifications .notification-items').children().length === 0) {
                        $('#unread-notifications .empty-state').removeClass('d-none');
                    }
                }
            } else if (notification.status === 'archived') {
                // Remove from current lists except archived
                if (this.currentFilter !== 'archived') {
                    $(`.notification-item[data-id="${notification.id}"]`).slideUp(300, function() {
                        $(this).remove();
                    });
                }
                
                // Update count if it was unread
                if ($(`.notification-item[data-id="${notification.id}"]`).hasClass('notification-unread')) {
                    this.unreadCount--;
                    if (this.unreadCount < 0) this.unreadCount = 0;
                    this.updateNotificationBadge();
                    
                    // Update count badges
                    const unreadCount = parseInt($('#unread-count').text() || 0) - 1;
                    $('#unread-count').text(unreadCount > 0 ? unreadCount : 0);
                }
            }
        }
    }
}

// Initialize the notification manager
const notificationManager = new NotificationManager();

// Make it available globally
window.notificationManager = notificationManager;
