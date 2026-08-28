/**
 * Frontend Link and Button Checker
 * This script checks all links and buttons in the frontend and produces an error report
 */

class LinkChecker {
    constructor() {
        this.errors = [];
        this.warnings = [];
        this.checkedUrls = new Set();
    }

    async checkElement(element, type) {
        const id = element.id || 'unnamed';
        const text = element.textContent.trim() || 'no text';
        let href = element.href || element.action || '';
        
        // Remove host from href to handle relative URLs
        href = href.replace(window.location.origin, '');
        
        try {
            // Skip if already checked this URL
            if (this.checkedUrls.has(href)) {
                return;
            }
            this.checkedUrls.add(href);

            // Basic attribute checks
            if (type === 'link' || type === 'form') {
                if (!href) {
                    this.errors.push(`${type} "${text}" (${id}) has no href/action attribute`);
                    return;
                }
            }

            if (type === 'button') {
                if (!element.type && !element.onclick) {
                    this.warnings.push(`Button "${text}" (${id}) has no type or onclick handler`);
                }
                if (element.type === 'submit' && !element.closest('form')) {
                    this.errors.push(`Submit button "${text}" (${id}) is not inside a form`);
                }
            }

            // Check if URL is valid
            if (href) {
                try {
                    const options = {
                        method: 'HEAD',
                        headers: {
                            'Content-Type': 'application/json'
                        }
                    };
                    const response = await fetch(href, options);
                    if (!response.ok) {
                        this.errors.push(`${type} "${text}" (${id}) returns ${response.status} status`);
                    }
                } catch (error) {
                    this.errors.push(`${type} "${text}" (${id}) is not reachable: ${error.message}`);
                }
            }

            // Check for ARIA attributes
            if (!element.getAttribute('aria-label') && !element.getAttribute('aria-labelledby')) {
                this.warnings.push(`${type} "${text}" (${id}) missing ARIA label`);
            }

        } catch (error) {
            this.errors.push(`Error checking ${type} "${text}" (${id}): ${error.message}`);
        }
    }

    async checkAllElements() {
        // Check all links
        const links = document.querySelectorAll('a');
        for (const link of links) {
            await this.checkElement(link, 'link');
        }

        // Check all buttons
        const buttons = document.querySelectorAll('button');
        for (const button of buttons) {
            await this.checkElement(button, 'button');
        }

        // Check all forms
        const forms = document.querySelectorAll('form');
        for (const form of forms) {
            await this.checkElement(form, 'form');
        }
    }

    generateReport() {
        const timestamp = new Date().toISOString();
        let report = `Frontend Link Check Report (${timestamp})\n`;
        report += '=====================================\n\n';

        if (this.errors.length > 0) {
            report += 'Errors:\n';
            report += '-------\n';
            this.errors.forEach((error, index) => {
                report += `${index + 1}. ${error}\n`;
            });
            report += '\n';
        }

        if (this.warnings.length > 0) {
            report += 'Warnings:\n';
            report += '---------\n';
            this.warnings.forEach((warning, index) => {
                report += `${index + 1}. ${warning}\n`;
            });
            report += '\n';
        }

        if (this.errors.length === 0 && this.warnings.length === 0) {
            report += 'No issues found! All links and buttons appear to be working correctly.\n';
        }

        report += `\nTotal Issues: ${this.errors.length + this.warnings.length}`;
        report += `\n- Errors: ${this.errors.length}`;
        report += `\n- Warnings: ${this.warnings.length}`;

        return report;
    }

    downloadReport() {
        const report = this.generateReport();
        const blob = new Blob([report], { type: 'text/plain' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `link-check-report-${new Date().toISOString().split('T')[0]}.txt`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
    }
}

// Initialize the checker button
function initializeCheckerButton() {
    const button = document.getElementById('check-links-btn');
    if (!button) {
        console.error('Check links button not found in the template');
        return;
    }
    
    button.addEventListener('click', async () => {
        button.disabled = true;
        button.textContent = 'Checking...';
        
        const checker = new LinkChecker();
        await checker.checkAllElements();
        checker.downloadReport();
        
        button.disabled = false;
        button.textContent = 'Check Links & Buttons';
        button.innerHTML = '<i class="fas fa-check-circle"></i> Check Links & Buttons';
    });
}

// Run when the page loads
document.addEventListener('DOMContentLoaded', initializeCheckerButton);
