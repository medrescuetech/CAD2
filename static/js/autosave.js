class AutoSaveManager {
    constructor(options = {}) {
        this.interval = options.interval || 30000; // Default 30 seconds
        this.onSave = options.onSave || (() => {});
        this.onError = options.onError || (() => {});
        this.enabled = true;
        this.pendingChanges = false;
        this.lastSaveTime = new Date();
        this.maxRetries = options.maxRetries || 3;
        this.timeout = options.timeout || 10000; // 10 second timeout
        this.retryDelay = options.retryDelay || 5000; // 5 second delay between retries
        this.currentRetry = 0;
        this.setupAutoSave();
    }

    setupAutoSave() {
        // Regular interval save
        setInterval(() => this.checkAndSave(), this.interval);

        // Save before page unload if there are pending changes
        window.addEventListener('beforeunload', (e) => {
            if (this.pendingChanges) {
                this.save();
                e.preventDefault();
                e.returnValue = '';
            }
        });

        // Save when tab becomes inactive
        document.addEventListener('visibilitychange', () => {
            if (document.hidden && this.pendingChanges) {
                this.save();
            }
        });
    }

    async save() {
        if (!this.enabled || !this.pendingChanges) return;

        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), this.timeout);

            await Promise.race([
                this.onSave(),
                new Promise((_, reject) => {
                    setTimeout(() => reject(new Error('Save operation timed out')), this.timeout);
                })
            ]);

            clearTimeout(timeoutId);
            this.currentRetry = 0;
            this.markSaved();
            // Logger.info('Auto-save successful'); // Commented out as Logger is not defined
        } catch (error) {
            // Logger.error('Auto-save failed', { error: error.message, retry: this.currentRetry }); // Commented out as Logger is not defined
            
            if (this.currentRetry < this.maxRetries) {
                this.currentRetry++;
                setTimeout(() => this.save(), this.retryDelay);
                this.updateSaveIndicator(true);
            } else {
                this.currentRetry = 0;
                this.onError(error);
                this.updateSaveIndicator(false);
            }
        }
    }

    checkAndSave() {
        if (this.pendingChanges) {
            this.save();
        }
    }

    markUnsaved() {
        this.pendingChanges = true;
        this.updateSaveIndicator();
    }

    markSaved() {
        this.pendingChanges = false;
        this.lastSaveTime = new Date();
        this.updateSaveIndicator();
    }

    updateSaveIndicator(isRetrying = false) {
        const indicator = document.getElementById('saveIndicator');
        if (indicator) {
            if (this.pendingChanges) {
                if (isRetrying) {
                    indicator.textContent = `Retrying save... (Attempt ${this.currentRetry}/${this.maxRetries})`;
                    indicator.className = 'badge bg-warning';
                } else {
                    indicator.textContent = 'Unsaved changes';
                    indicator.className = 'badge bg-warning';
                }
            } else {
                indicator.textContent = `Last saved: ${this.lastSaveTime.toLocaleTimeString()}`;
                indicator.className = 'badge bg-success';
            }
        }
    }

    enable() {
        this.enabled = true;
    }

    disable() {
        this.enabled = false;
    }

    createSaveIndicator() {
        const indicator = document.createElement('div');
        indicator.id = 'saveIndicator';
        indicator.className = 'badge bg-success';
        indicator.style.position = 'fixed';
        indicator.style.bottom = '20px';
        indicator.style.right = '20px';
        indicator.style.zIndex = '1000';
        document.body.appendChild(indicator);
        this.updateSaveIndicator();
        return indicator;
    }
}
