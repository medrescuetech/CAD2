class ThemeManager {
    constructor() {
        this.init();
    }

    init() {
        // Get theme from localStorage or system settings
        const savedTheme = localStorage.getItem('theme');
        const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        const theme = savedTheme || systemTheme;

        // Apply theme
        this.setTheme(theme);

        // Listen for theme changes
        document.querySelectorAll('input[name="theme"]').forEach(input => {
            input.addEventListener('change', (e) => {
                this.setTheme(e.target.value);
                this.saveTheme(e.target.value);
            });
        });

        // Listen for system theme changes
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
            if (!localStorage.getItem('theme')) {
                this.setTheme(e.matches ? 'dark' : 'light');
            }
        });
    }

    setTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        const themeInput = document.querySelector(`input[name="theme"][value="${theme}"]`);
        if (themeInput) {
            themeInput.checked = true;
        }
    }

    saveTheme(theme) {
        localStorage.setItem('theme', theme);
        // Save to server
        fetch('/api/settings/theme', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ theme })
        }).catch(error => console.error('Error saving theme:', error));
    }
}

// Initialize theme manager
document.addEventListener('DOMContentLoaded', () => {
    window.themeManager = new ThemeManager();
});
