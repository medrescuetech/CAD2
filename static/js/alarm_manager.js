// Alarm Manager
const AlarmManager = {
    alarms: [],
    alarmSound: null,
    alarmModal: null,
    activeAlarms: new Set(),
    checkInterval: null,
    
    init() {
        this.alarmSound = document.getElementById('alarmSound');
        this.alarmModal = new bootstrap.Modal(document.getElementById('alarmModal'));
        
        // Set up recurring checkbox handler
        document.getElementById('alarmRecurring').addEventListener('change', (e) => {
            document.getElementById('daysSelection').style.display = e.checked ? 'block' : 'none';
        });
        
        // Load alarms and start checking
        this.loadAlarms();
        this.startChecking();
    },
    
    async loadAlarms() {
        try {
            const response = await fetch('/api/alarms');
            const data = await response.json();
            
            if (data.success) {
                this.alarms = data.alarms;
                this.renderAlarms();
                this.updateActiveCount();
            }
        } catch (error) {
            console.error('Error loading alarms:', error);
        }
    },
    
    renderAlarms() {
        const container = document.getElementById('alarmsList');
        container.innerHTML = '';
        
        this.alarms.forEach(alarm => {
            const card = document.createElement('div');
            card.className = 'card mb-2';
            card.innerHTML = `
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <h5 class="card-title mb-1">${alarm.name}</h5>
                            <p class="card-text mb-0">
                                <small class="text-muted">
                                    ${alarm.time}
                                    ${alarm.recurring ? ' (Recurring: ' + (alarm.days || []).join(', ') + ')' : ''}
                                </small>
                            </p>
                        </div>
                        <div class="btn-group">
                            <button class="btn btn-sm btn-${alarm.active ? 'success' : 'secondary'}"
                                    onclick="AlarmManager.toggleAlarm('${alarm.id}')">
                                <i class="fas fa-${alarm.active ? 'bell' : 'bell-slash'}"></i>
                            </button>
                            <button class="btn btn-sm btn-danger" onclick="AlarmManager.deleteAlarm('${alarm.id}')">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                </div>
            `;
            container.appendChild(card);
        });
    },
    
    showAlarmModal() {
        this.alarmModal.show();
    },
    
    showNewAlarmForm() {
        document.getElementById('newAlarmForm').style.display = 'block';
        document.getElementById('alarmForm').reset();
    },
    
    hideNewAlarmForm() {
        document.getElementById('newAlarmForm').style.display = 'none';
    },
    
    async createAlarm(event) {
        event.preventDefault();
        
        const form = event.target;
        const formData = new FormData(form);
        
        const data = {
            name: formData.get('name'),
            time: formData.get('time'),
            recurring: formData.get('recurring') === 'on',
            days: formData.get('recurring') === 'on' ? 
                Array.from(formData.getAll('days')) : null
        };
        
        try {
            const response = await fetch('/api/alarms', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(data)
            });
            
            const result = await response.json();
            if (result.success) {
                this.loadAlarms();
                this.hideNewAlarmForm();
            }
        } catch (error) {
            console.error('Error creating alarm:', error);
        }
    },
    
    async toggleAlarm(alarmId) {
        try {
            const response = await fetch(`/api/alarms/${alarmId}/toggle`, {
                method: 'POST'
            });
            
            const result = await response.json();
            if (result.success) {
                this.loadAlarms();
            }
        } catch (error) {
            console.error('Error toggling alarm:', error);
        }
    },
    
    async deleteAlarm(alarmId) {
        if (!confirm('Are you sure you want to delete this alarm?')) {
            return;
        }
        
        try {
            const response = await fetch(`/api/alarms/${alarmId}`, {
                method: 'DELETE'
            });
            
            const result = await response.json();
            if (result.success) {
                this.loadAlarms();
            }
        } catch (error) {
            console.error('Error deleting alarm:', error);
        }
    },
    
    startChecking() {
        // Check every minute
        this.checkInterval = setInterval(() => this.checkAlarms(), 60000);
        // Also check immediately
        this.checkAlarms();
    },
    
    stopChecking() {
        if (this.checkInterval) {
            clearInterval(this.checkInterval);
            this.checkInterval = null;
        }
    },
    
    checkAlarms() {
        const now = new Date();
        const currentTime = now.toTimeString().slice(0, 5); // HH:mm format
        const currentDay = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][now.getDay()];
        
        this.alarms.forEach(alarm => {
            if (!alarm.active) return;
            
            if (alarm.time === currentTime) {
                if (!alarm.recurring || (alarm.days && alarm.days.includes(currentDay))) {
                    if (!this.activeAlarms.has(alarm.id)) {
                        this.triggerAlarm(alarm);
                    }
                }
            } else {
                this.activeAlarms.delete(alarm.id);
            }
        });
        
        this.updateActiveCount();
    },
    
    triggerAlarm(alarm) {
        this.activeAlarms.add(alarm.id);
        
        // Show notification
        if (Notification.permission === 'granted') {
            new Notification('Alarm: ' + alarm.name, {
                body: alarm.time,
                icon: '/static/img/alarm-icon.png'
            });
        }
        
        // Play sound
        if (this.alarmSound) {
            this.alarmSound.play();
        }
        
        // Show toast
        const toast = document.createElement('div');
        toast.className = 'toast';
        toast.setAttribute('role', 'alert');
        toast.innerHTML = `
            <div class="toast-header">
                <strong class="me-auto">Alarm: ${alarm.name}</strong>
                <button type="button" class="btn-close" data-bs-dismiss="toast"></button>
            </div>
            <div class="toast-body">
                Time: ${alarm.time}
                <button class="btn btn-sm btn-primary ms-2" onclick="AlarmManager.dismissAlarm('${alarm.id}')">
                    Dismiss
                </button>
            </div>
        `;
        
        document.querySelector('.toast-container').appendChild(toast);
        new bootstrap.Toast(toast).show();
    },
    
    dismissAlarm(alarmId) {
        this.activeAlarms.delete(alarmId);
        this.updateActiveCount();
        
        if (this.alarmSound) {
            this.alarmSound.pause();
            this.alarmSound.currentTime = 0;
        }
    },
    
    updateActiveCount() {
        const countElement = document.getElementById('activeAlarmsCount');
        const count = this.activeAlarms.size;
        
        countElement.textContent = count;
        countElement.style.display = count > 0 ? 'inline' : 'none';
    }
};

// Initialize when the page loads
document.addEventListener('DOMContentLoaded', () => {
    AlarmManager.init();
}); 