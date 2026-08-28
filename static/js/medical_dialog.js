// Medical Dialog Manager
const MedicalDialogManager = {
    // Configuration
    config: {
        csvStructure: {
            category: 'category',
            cardNumber: 'card_number',
            subCategory: 'subcategory',
            priority: 'priority',
            dispatchAdvice: 'dispatch_advice',
            preArrival: 'prearrival'
        },
        keyBindings: {
            'Alt+F': '#protocolSearch',
            'Alt+C': '#categorySelect',
            'Alt+S': '#subCategorySelect',
            'Alt+N': '#cardNumberInput',
            'Ctrl+S': () => this.saveProtocol(),
            'Ctrl+P': () => this.openPreArrivalPDF()
        }
    },

    // State management
    state: {
        medicalData: [],
        currentProtocol: null,
        categories: new Set(),
        favorites: new Set(),
        recentProtocols: [],
        isDirty: false
    },

    // Callback for incident log updates
    onLogEntry: null,

    // Initialize medical dialog
    init() {
        this._initEventListeners();
        this._initKeyBindings();
        this._loadMedicalData();
        this._setupTypeahead();
        return this;
    },

    // Initialize event listeners
    _initEventListeners() {
        // Category selection
        const categorySelect = document.getElementById('categorySelect');
        if (categorySelect) {
            categorySelect.addEventListener('change', (e) => {
                this._updateSubCategories(e.target.value);
                this._logChange('Category', e.target.value);
            });
        }

        // Sub-category selection
        const subCategorySelect = document.getElementById('subCategorySelect');
        if (subCategorySelect) {
            subCategorySelect.addEventListener('change', (e) => {
                this._updateProtocolInfo(e.target.value);
                this._logChange('Sub-category', e.target.value);
            });
        }

        // Card number search
        const cardNumberInput = document.getElementById('cardNumberInput');
        if (cardNumberInput) {
            cardNumberInput.addEventListener('change', (e) => {
                this._searchByCardNumber(e.target.value);
                this._logChange('Card Number', e.target.value);
            });
        }
    },

    // Load medical data from CSV
    async _loadMedicalData() {
        try {
            const response = await fetch('/api/medical/data');
            if (!response.ok) throw new Error('Failed to load medical data');
            
            const data = await response.json();
            this.state.medicalData = data;
            
            // Extract unique categories
            this.state.categories = new Set(
                data.map(row => row[this.config.csvStructure.category])
            );
            
            this._populateCategorySelect();
            
        } catch (error) {
            console.error('Error loading medical data:', error);
            this._showAlert('Failed to load medical data', 'danger');
            this._logError('Failed to load medical data');
        }
    },

    // Update protocol information based on selection
    _updateProtocolInfo(subCategory) {
        const protocol = this.state.medicalData.find(row => 
            row[this.config.csvStructure.subCategory] === subCategory
        );

        if (!protocol) return;

        // Update priority
        const priority = protocol[this.config.csvStructure.priority];
        document.getElementById('priorityDisplay').textContent = priority;

        // Update dispatch advice
        const dispatchAdvice = protocol[this.config.csvStructure.dispatchAdvice];
        document.getElementById('dispatchAdvice').textContent = dispatchAdvice;

        // Update pre-arrival instructions link
        const preArrivalLink = document.getElementById('preArrivalLink');
        if (preArrivalLink) {
            preArrivalLink.href = protocol[this.config.csvStructure.preArrival];
        }

        this.state.currentProtocol = protocol;
        this._addToRecentProtocols(protocol);

        // Log the protocol selection
        this._logProtocolSelection(protocol);
    },

    // Log changes to incident log
    _logChange(field, value) {
        if (this.onLogEntry) {
            this.onLogEntry('AMPDS', `${field} changed to: ${value}`);
        }
    },

    // Log protocol selection
    _logProtocolSelection(protocol) {
        if (this.onLogEntry) {
            const message = `Selected Protocol - ${protocol[this.config.csvStructure.category]}: ` +
                          `${protocol[this.config.csvStructure.subCategory]} ` +
                          `(Priority: ${protocol[this.config.csvStructure.priority]})`;
            this.onLogEntry('AMPDS', message);
        }
    },

    // Log errors
    _logError(error) {
        if (this.onLogEntry) {
            this.onLogEntry('AMPDS_ERROR', error);
        }
    },

    // Show alert message
    _showAlert(message, type = 'info') {
        const toast = document.getElementById('toast');
        if (!toast) return;

        const toastInstance = bootstrap.Toast.getOrCreateInstance(toast);
        toast.className = `toast align-items-center text-white bg-${type} border-0`;
        toast.querySelector('.toast-body').textContent = message;
        toastInstance.show();
    }
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    MedicalDialogManager.init();
}); 