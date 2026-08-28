/**
 * Asset Optimizer Module
 * Handles minification, bundling and caching for static assets
 */

const AssetOptimizer = {
    /**
     * CSS and JS cache that stores minified/bundled content
     * Format: { 'asset_path': { content: '...', timestamp: Date, etag: '...' } }
     */
    cache: {},
    
    /**
     * Settings for the optimizer
     */
    settings: {
        cacheEnabled: true,
        minifyEnabled: true,
        bundleEnabled: true,
        cacheMaxAge: 3600 * 24, // 24 hours in seconds
        etagEnabled: true
    },
    
    /**
     * Initialize the optimizer
     * @param {Object} options - Optimizer settings
     */
    init(options = {}) {
        // Apply custom settings
        this.settings = { ...this.settings, ...options };
        
        // Apply cache headers to static assets
        this.applyCacheHeaders();
        
        // Handle resource hints (preload, prefetch, etc.)
        this.setupResourceHints();
        
        console.log('Asset optimizer initialized with settings:', this.settings);
    },
    
    /**
     * Apply cache headers to static assets
     */
    applyCacheHeaders() {
        // Cache control implementation
        if (this.settings.cacheEnabled) {
            document.addEventListener('DOMContentLoaded', () => {
                // Add timestamp to static assets to enable long-term caching
                const timestamp = new Date().getTime();
                
                // Apply to stylesheets
                document.querySelectorAll('link[rel="stylesheet"]').forEach(link => {
                    if (!link.href.includes('?')) {
                        link.href = `${link.href}?v=${timestamp}`;
                    }
                });
                
                // Apply to scripts
                document.querySelectorAll('script[src]').forEach(script => {
                    if (!script.src.includes('?')) {
                        script.src = `${script.src}?v=${timestamp}`;
                    }
                });
            });
        }
    },
    
    /**
     * Set up resource hints for performance
     */
    setupResourceHints() {
        const criticalResources = [
            '/static/css/main.css',
            '/static/js/utils.js',
            '/static/js/websocket.js'
        ];
        
        document.addEventListener('DOMContentLoaded', () => {
            // Add preload for critical resources
            criticalResources.forEach(resource => {
                const hint = document.createElement('link');
                hint.rel = resource.endsWith('.css') ? 'preload' : 'prefetch';
                hint.href = resource;
                hint.as = resource.endsWith('.css') ? 'style' : 'script';
                hint.crossOrigin = 'anonymous';
                document.head.appendChild(hint);
            });
        });
    },
    
    /**
     * Lazy load non-critical resources
     * @param {Array} resources - Array of resource URLs to lazy load
     */
    lazyLoadResources(resources) {
        if (!resources || !resources.length) return;
        
        // Setup intersection observer for lazy loading
        const observer = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const placeholder = entry.target;
                    const resourceType = placeholder.dataset.resourceType;
                    const resourceUrl = placeholder.dataset.resourceUrl;
                    
                    if (resourceType === 'image') {
                        // Handle image lazy loading
                        const img = new Image();
                        img.src = resourceUrl;
                        img.onload = () => {
                            placeholder.src = resourceUrl;
                            placeholder.classList.add('loaded');
                        };
                    } else if (resourceType === 'script') {
                        // Handle script lazy loading
                        const script = document.createElement('script');
                        script.src = resourceUrl;
                        script.async = true;
                        document.body.appendChild(script);
                    } else if (resourceType === 'style') {
                        // Handle stylesheet lazy loading
                        const link = document.createElement('link');
                        link.rel = 'stylesheet';
                        link.href = resourceUrl;
                        document.head.appendChild(link);
                    }
                    
                    // Stop observing once loaded
                    observer.unobserve(entry.target);
                }
            });
        }, {
            rootMargin: '100px 0px',
            threshold: 0.01
        });
        
        // Create placeholders for lazy loaded resources
        resources.forEach(resource => {
            if (typeof resource === 'string') {
                resource = { url: resource, type: resource.split('.').pop() };
            }
            
            // Create appropriate placeholder based on resource type
            let placeholder;
            if (resource.type === 'image' || resource.type === 'jpg' || resource.type === 'png' || resource.type === 'gif') {
                placeholder = document.createElement('img');
                placeholder.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"%3E%3C/svg%3E';
                placeholder.dataset.resourceType = 'image';
                document.querySelector(resource.container || 'body').appendChild(placeholder);
            } else {
                placeholder = document.createElement('div');
                placeholder.style.display = 'none';
                placeholder.dataset.resourceType = resource.type === 'css' ? 'style' : 'script';
                document.body.appendChild(placeholder);
            }
            
            placeholder.dataset.resourceUrl = resource.url;
            observer.observe(placeholder);
        });
    }
};

// Auto-initialize on load
document.addEventListener('DOMContentLoaded', () => {
    AssetOptimizer.init();
});

// Expose globally
window.AssetOptimizer = AssetOptimizer;
