// Keyboard Shortcuts Manager
class ShortcutManager {
    constructor() {
        this.shortcuts = new Map();
        this.touchStartX = 0;
        this.touchStartY = 0;
        this.touchEndX = 0;
        this.touchEndY = 0;
        this.isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
        
        // Initialize event listeners
        this.initializeEventListeners();
        
        // Log initialization
        Logger.info('ShortcutManager initialized', { isMobile: this.isMobile });
    }

    initializeEventListeners() {
        try {
            // Keyboard events for desktop
            document.addEventListener('keydown', this.handleKeyPress.bind(this));
            
            // Touch events for mobile
            if (this.isMobile) {
                document.addEventListener('touchstart', this.handleTouchStart.bind(this));
                document.addEventListener('touchend', this.handleTouchEnd.bind(this));
                document.addEventListener('touchmove', this.handleTouchMove.bind(this));
            }
            
            // Cleanup on page unload
            window.addEventListener('unload', () => {
                this.cleanup();
            });
        } catch (error) {
            Logger.error('Failed to initialize event listeners', { error: error.message });
        }
    }

    handleTouchStart(event) {
        try {
            this.touchStartX = event.touches[0].clientX;
            this.touchStartY = event.touches[0].clientY;
        } catch (error) {
            Logger.error('Error in handleTouchStart', { error: error.message });
        }
    }

    handleTouchMove(event) {
        try {
            this.touchEndX = event.touches[0].clientX;
            this.touchEndY = event.touches[0].clientY;
        } catch (error) {
            Logger.error('Error in handleTouchMove', { error: error.message });
        }
    }

    handleTouchEnd() {
        try {
            const deltaX = this.touchEndX - this.touchStartX;
            const deltaY = this.touchEndY - this.touchStartY;
            
            // Minimum distance for swipe
            const minDistance = 50;
            
            if (Math.abs(deltaX) > minDistance || Math.abs(deltaY) > minDistance) {
                const direction = Math.abs(deltaX) > Math.abs(deltaY)
                    ? (deltaX > 0 ? 'right' : 'left')
                    : (deltaY > 0 ? 'down' : 'up');
                
                this.handleGesture(direction);
            }
        } catch (error) {
            Logger.error('Error in handleTouchEnd', { error: error.message });
        }
    }

    handleGesture(direction) {
        try {
            // Map gestures to keyboard shortcuts
            const gestureMap = {
                'left': 'ArrowLeft',
                'right': 'ArrowRight',
                'up': 'ArrowUp',
                'down': 'ArrowDown'
            };
            
            const mappedKey = gestureMap[direction];
            if (mappedKey) {
                const shortcut = Array.from(this.shortcuts.entries())
                    .find(([key]) => key.includes(mappedKey));
                
                if (shortcut) {
                    shortcut[1]();
                    Logger.info('Gesture executed', { direction, mappedKey });
                }
            }
        } catch (error) {
            Logger.error('Error in handleGesture', { error: error.message });
        }
    }

    handleKeyPress(event) {
        try {
            // Don't trigger shortcuts when typing in input fields
            if (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA') {
                return;
            }
            
            const key = this.getKeyCombo(event);
            if (this.shortcuts.has(key)) {
                event.preventDefault();
                this.shortcuts.get(key)();
                Logger.info('Shortcut executed', { key });
            }
        } catch (error) {
            Logger.error('Error in handleKeyPress', { error: error.message });
        }
    }

    getKeyCombo(event) {
        try {
            const combo = [];
            if (event.ctrlKey) combo.push('Ctrl');
            if (event.altKey) combo.push('Alt');
            if (event.shiftKey) combo.push('Shift');
            if (event.key !== 'Control' && event.key !== 'Alt' && event.key !== 'Shift') {
                combo.push(event.key);
            }
            return combo.join('+');
        } catch (error) {
            Logger.error('Error in getKeyCombo', { error: error.message });
            return '';
        }
    }

    register(shortcut, callback) {
        try {
            if (typeof shortcut !== 'string' || typeof callback !== 'function') {
                throw new Error('Invalid shortcut registration parameters');
            }
            
            this.shortcuts.set(shortcut, callback);
            Logger.info('Shortcut registered', { shortcut });
            
            // Return unregister function
            return () => this.unregister(shortcut);
        } catch (error) {
            Logger.error('Failed to register shortcut', { 
                error: error.message,
                shortcut 
            });
        }
    }

    unregister(shortcut) {
        try {
            const success = this.shortcuts.delete(shortcut);
            if (success) {
                Logger.info('Shortcut unregistered', { shortcut });
            } else {
                Logger.warn('Shortcut not found for unregister', { shortcut });
            }
            return success;
        } catch (error) {
            Logger.error('Failed to unregister shortcut', {
                error: error.message,
                shortcut
            });
            return false;
        }
    }

    cleanup() {
        try {
            this.shortcuts.clear();
            Logger.info('ShortcutManager cleaned up');
        } catch (error) {
            Logger.error('Error during cleanup', { error: error.message });
        }
    }
}

// Initialize shortcut manager
const shortcutManager = new ShortcutManager();

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = shortcutManager;
}

// Help dialog for keyboard shortcuts
function showShortcutsHelp() {
    try {
        const shortcuts = Array.from(shortcutManager.shortcuts.entries()).map(([key, _]) => key);
        const helpContent = `
            <h5>General Shortcuts</h5>
            <ul>
                <li><kbd>?</kbd> - Show this help dialog</li>
                <li><kbd>Esc</kbd> - Close dialogs/menus</li>
                <li><kbd>Ctrl+S</kbd> - Save current form</li>
                <li><kbd>Ctrl+N</kbd> - New incident</li>
                <li><kbd>Ctrl+P</kbd> - Generate PDF</li>
            </ul>
            
            <h5>Navigation</h5>
            <ul>
                <li><kbd>Ctrl+1</kbd> - Go to Incidents</li>
                <li><kbd>Ctrl+2</kbd> - Go to Unit Manager</li>
                <li><kbd>Ctrl+3</kbd> - Go to Admin Panel</li>
                <li><kbd>Tab</kbd> - Navigate form fields</li>
            </ul>
            
            <h5>Incident Management</h5>
            <ul>
                <li><kbd>Alt+C</kbd> - Close incident</li>
                <li><kbd>Alt+U</kbd> - Focus unit search</li>
                <li><kbd>Alt+L</kbd> - Focus location field</li>
                <li><kbd>Alt+P</kbd> - Focus problem field</li>
            </ul>
            
            <h5>Mouse Actions</h5>
            <ul>
                <li><strong>Double-click unit</strong> - Quick assign/unassign</li>
                <li><strong>Right-click unit</strong> - Change unit status</li>
                <li><strong>Drag unit</strong> - Assign/unassign to incident</li>
                <li><strong>Double-click incident row</strong> - Open incident</li>
            </ul>
        `;

        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.id = 'shortcutsHelpModal';
        modal.innerHTML = `
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Keyboard Shortcuts & Mouse Actions</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        ${helpContent}
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();

        modal.addEventListener('hidden.bs.modal', () => {
            modal.remove();
        });
    } catch (error) {
        Logger.error('Failed to show shortcuts help', { error: error.message });
        alert('Error showing keyboard shortcuts. Please try again.');
    }
}

// Register global shortcuts
shortcutManager.register('?', showShortcutsHelp);
shortcutManager.register('Escape', () => {
    // Close any open modals or context menus
    const openModals = document.querySelectorAll('.modal.show');
    openModals.forEach(modal => {
        const bsModal = bootstrap.Modal.getInstance(modal);
        if (bsModal) bsModal.hide();
    });
    
    const openMenus = document.querySelectorAll('.dropdown-menu.show');
    openMenus.forEach(menu => menu.style.display = 'none');
});
