class UnitManager {
    static state = {
        units: []
    };
    
    static init() {
        this.initializeEventListeners();
        this.loadUnits();
    }
    
    static initializeEventListeners() {
        // Unit form
        const unitForm = document.getElementById('unitForm');
        if (unitForm) {
            unitForm.setAttribute('data-custom-submit', 'true');
            unitForm.addEventListener('submit', (event) => {
                event.preventDefault();
                this.saveUnit();
            });
        }

        // Save unit button
        const saveUnitBtn = document.getElementById('saveUnitBtn');
        if (saveUnitBtn) {
            saveUnitBtn.addEventListener('click', () => this.saveUnit());
        }

        // Save status button
        const saveStatusBtn = document.getElementById('saveStatusBtn');
        if (saveStatusBtn) {
            saveStatusBtn.addEventListener('click', () => this.saveUnitStatus());
        }

        // Confirm delete button
        const confirmDeleteBtn = document.getElementById('confirmDeleteBtn');
        if (confirmDeleteBtn) {
            confirmDeleteBtn.addEventListener('click', () => {
                if (this.state.deleteUnitId) {
                    const modal = bootstrap.Modal.getInstance(document.getElementById('confirmDeleteModal'));
                    modal.hide();
                    this.deleteUnit(this.state.deleteUnitId);
                }
            });
        }
    }
    
    static async loadUnits() {
        try {
            const response = await fetch('/api/units');
            if (!response.ok) throw new Error('Failed to load units');
            
            const data = await response.json();
            this.state.units = data.units;
            this.refreshUnitsTable();
            
        } catch (error) {
            console.error('Error loading units:', error);
            this._showAlert('error', 'Failed to load units');
        }
    }
    
    static async saveUnit() {
        if (!validateForm()) return;

        const form = document.getElementById('unitForm');
        if (!form || !form.checkValidity()) {
            form.reportValidity();
            return;
        }
        
        try {
            setLoading(true);
            const formData = new FormData(form);
            const unitData = {
                unit_number: formData.get('unit_number'),
                unit_type: formData.get('unit_type'),
                icon: formData.get('icon'),
                status: formData.get('status'),
                location: formData.get('location'),
                crew: formData.get('crew')
            };

            const unitId = form.getAttribute('data-unit-id');
            const url = unitId ? `/api/units/${unitId}` : '/api/units';
            const method = unitId ? 'PUT' : 'POST';

            const response = await fetch(url, {
                method: method,
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(unitData)
            });

            if (!response.ok) throw new Error('Failed to save unit');
            
            const modal = bootstrap.Modal.getInstance(document.getElementById('addUnitModal'));
            modal.hide();
            
            this._showAlert('success', 'Unit saved successfully');
            this.loadUnits();
            
        } catch (error) {
            handleError(error);
        } finally {
            setLoading(false);
        }
    }
    
    static async saveUnitStatus() {
        const form = document.getElementById('statusForm');
        if (!form || !form.checkValidity()) {
            form.reportValidity();
            return;
        }

        try {
            setLoading(true);
            const unitId = form.getAttribute('data-unit-id');
            const status = document.getElementById('unitStatus').value;
            const note = document.getElementById('statusNote').value;

            const response = await fetch(`/api/units/${unitId}/status`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ status, note })
            });

            if (!response.ok) throw new Error('Failed to update status');

            const modal = bootstrap.Modal.getInstance(document.getElementById('unitStatusModal'));
            modal.hide();

            this._showAlert('success', 'Unit status updated successfully');
            this.loadUnits();

        } catch (error) {
            handleError(error);
        } finally {
            setLoading(false);
        }
    }
    
    static async deleteUnit(unitId) {
        try {
            setLoading(true);
            const response = await fetch(`/api/units/${unitId}`, {
                method: 'DELETE'
            });
            
            if (!response.ok) throw new Error('Failed to delete unit');
            
            this._showAlert('success', 'Unit deleted successfully');
            this.loadUnits();
            
        } catch (error) {
            handleError(error);
        } finally {
            setLoading(false);
        }
    }
    
    static refreshUnitsTable() {
        const tbody = document.querySelector('table tbody');
        if (!tbody) return;
        
        tbody.innerHTML = '';
        
        this.state.units.forEach(unit => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>
                    ${this._getUnitIcon(unit.icon)}
                </td>
                <td>${unit.unit_number}</td>
                <td>${unit.unit_type}</td>
                <td>
                    <span class="badge bg-${this._getStatusClass(unit.status)}">
                        ${unit.status}
                    </span>
                </td>
                <td>${unit.location || '-'}</td>
                <td>${unit.crew || '-'}</td>
                <td class="timestamp" data-utc="${unit.last_updated}">
                    ${unit.last_updated}
                </td>
                <td>
                    <div class="btn-group">
                        <button class="btn btn-sm btn-info" onclick="UnitManager.editUnit('${unit.id}')" title="Edit Unit">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn btn-sm btn-warning" onclick="UnitManager.updateUnitStatus('${unit.id}')" title="Update Status">
                            <i class="fas fa-sync-alt"></i>
                        </button>
                        <button class="btn btn-sm btn-danger" onclick="UnitManager.confirmDeleteUnit('${unit.id}')" title="Delete Unit">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </td>
            `;
            tbody.appendChild(row);
        });
    }
    
    static editUnit(unitId) {
        const unit = this.state.units.find(u => u.id === unitId);
        if (!unit) return;
        
        const form = document.getElementById('unitForm');
        if (!form) return;
        
        form.setAttribute('data-unit-id', unit.id);
        document.querySelector('#addUnitModal .modal-title').textContent = 'Edit Unit';
        
        // Populate form fields
        form.elements['unit_number'].value = unit.unit_number;
        form.elements['unit_type'].value = unit.unit_type;
        form.elements['icon'].value = unit.icon;
        form.elements['status'].value = unit.status;
        form.elements['location'].value = unit.location || '';
        form.elements['crew'].value = unit.crew || '';
        
        const modal = new bootstrap.Modal(document.getElementById('addUnitModal'));
        modal.show();
    }
    
    static updateUnitStatus(unitId) {
        const unit = this.state.units.find(u => u.id === unitId);
        if (!unit) return;
        
        const form = document.getElementById('statusForm');
        if (!form) return;
        
        form.setAttribute('data-unit-id', unit.id);
        document.getElementById('unitStatus').value = unit.status;
        document.getElementById('statusNote').value = '';
        
        const modal = new bootstrap.Modal(document.getElementById('unitStatusModal'));
        modal.show();
    }
    
    static confirmDeleteUnit(unitId) {
        this.state.deleteUnitId = unitId;
        confirmAction('Are you sure you want to delete this unit?').then((confirmed) => {
            if (confirmed) {
                this.deleteUnit(unitId);
            }
        });
    }
    
    static _getUnitIcon(icon) {
        switch (icon) {
            case 'ambulance': return '🚑';
            case 'fire-engine': return '🚒';
            case 'police-car': return '🚓';
            case 'rescue': return '🚨';
            default: return '🚗';
        }
    }
    
    static _getStatusClass(status) {
        switch (status) {
            case 'AVAILABLE': return 'success';
            case 'ASSIGNED': return 'primary';
            case 'ENROUTE': return 'warning';
            case 'ON_SCENE': return 'danger';
            case 'RETURNING': return 'info';
            case 'OUT_OF_SERVICE': return 'secondary';
            case 'MEAL_BREAK': return 'dark';
            case 'AT_MEDICAL_CENTRE': return 'purple';
            case 'PATROL': return 'blue';
            default: return 'light';
        }
    }
    
    static _showAlert(type, message) {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        const container = document.querySelector('.container-fluid');
        if (container) {
            container.insertBefore(alertDiv, container.firstChild);
            
            // Auto-dismiss after 5 seconds
            setTimeout(() => {
                alertDiv.remove();
            }, 5000);
        }
    }
}

// WebSocket integration
const socket = io();

socket.on('unit_update', (data) => {
    if (data.unitId) {
        UnitManager.refreshUnitsTable();
    }
});

// Error handling
const handleError = (error) => {
    console.error(error);
    UnitManager._showAlert('danger', error.message || 'An error occurred');
    throw error;
};

// Loading states
const setLoading = (isLoading) => {
    document.body.classList.toggle('loading', isLoading);
};

// Form validation
const validateForm = () => {
    const requiredFields = ['unit_number', 'unit_type', 'status'];
    let isValid = true;

    requiredFields.forEach(field => {
        const input = document.getElementById(field);
        if (!input || !input.value) {
            isValid = false;
            input.classList.add('is-invalid');
        } else {
            input.classList.remove('is-invalid');
        }
    });

    return isValid;
};

// Confirmation dialogs
const confirmAction = (message) => {
    return new Promise((resolve) => {
        const modal = new bootstrap.Modal(document.getElementById('confirmationModal'));
        const messageElem = document.getElementById('confirmationMessage');
        const confirmBtn = document.getElementById('confirmActionBtn');

        messageElem.textContent = message;
        confirmBtn.onclick = () => {
            modal.hide();
            resolve(true);
        };

        modal.show();
    });
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    UnitManager.init();
});
