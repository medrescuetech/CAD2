"""
Static Asset Optimization Module

This module provides functionality for optimizing static assets including:
- CSS and JS minification
- Static asset caching
- Automatic versioning
- Conditional serving based on ETags
"""

import os
import re
import hashlib
import gzip
import time
from datetime import datetime, timedelta
from flask import request, current_app, send_file, make_response, Response
from functools import wraps
from webassets import Bundle

# Cache for minified files to avoid repetitive processing
# Format: {'file_path': {'content': bytes, 'timestamp': datetime, 'etag': str}}
_asset_cache = {}

# File extensions that can be minimized
# Disabled: the regex-based minifier corrupts JS (`//` inside strings/regexes).
# Gzip compression below still applies and is safe.
MINIFIABLE_EXTENSIONS = ()

# File extensions that can be gzipped
GZIPPABLE_EXTENSIONS = ('.js', '.css', '.html', '.txt', '.json', '.svg')

def init_asset_optimization(app):
    """Initialize asset optimization for the Flask app."""
    # Set up before_request handler for asset optimization
    @app.before_request
    def optimize_assets():
        # Skip non-static requests
        if not request.path.startswith('/static/'):
            return None
            
        # Check if the file exists and is minifiable
        file_path = os.path.join(app.static_folder, request.path[8:])
        if not os.path.isfile(file_path):
            return None
            
        _, ext = os.path.splitext(file_path)
        if ext not in MINIFIABLE_EXTENSIONS and ext not in GZIPPABLE_EXTENSIONS:
            return None
            
        # Check if the client has a valid cached version
        if_none_match = request.headers.get('If-None-Match')
        etag = generate_etag(file_path)
        
        if if_none_match and if_none_match == etag:
            return Response(status=304)  # Not Modified
            
        # Get optimized asset (cached uncompressed; gzip per request)
        content, content_type = get_optimized_asset(file_path)
        if should_use_gzip(file_path) and accepts_gzip():
            content = gzip.compress(content)
        
        # Prepare response
        response = make_response(content)
        response.headers['Content-Type'] = content_type
        response.headers['ETag'] = etag
        
        # Set cache control headers
        cache_duration = app.config.get('STATIC_ASSET_CACHE_SECONDS', 86400)  # Default 24 hours
        response.headers['Cache-Control'] = f'public, max-age={cache_duration}'
        response.headers['Expires'] = (datetime.utcnow() + timedelta(seconds=cache_duration)).strftime(
            '%a, %d %b %Y %H:%M:%S GMT')
            
        # Set content encoding if gzipped
        if should_use_gzip(file_path) and accepts_gzip():
            response.headers['Content-Encoding'] = 'gzip'
            
        return response
        
    # Return the app for chaining
    return app

def generate_etag(file_path):
    """Generate an ETag for a file based on its path and last modified time."""
    stat = os.stat(file_path)
    etag_data = f"{file_path}:{stat.st_mtime}:{stat.st_size}"
    return hashlib.md5(etag_data.encode()).hexdigest()

def get_optimized_asset(file_path):
    """Get optimized (minified/gzipped) version of an asset."""
    # Check if we have a cached version
    stat = os.stat(file_path)
    cached = _asset_cache.get(file_path)
    
    if cached and cached['timestamp'] >= stat.st_mtime:
        return cached['content'], cached['content_type']
        
    # Read the file
    with open(file_path, 'rb') as f:
        content = f.read()
        
    # Determine content type
    content_type = get_content_type(file_path)
    
    # Minify if applicable
    _, ext = os.path.splitext(file_path)
    if ext in MINIFIABLE_EXTENSIONS:
        content = minify_content(content, ext)
        
    # Cache the result (uncompressed — gzip is negotiated per request)
    _asset_cache[file_path] = {
        'content': content,
        'timestamp': stat.st_mtime,
        'content_type': content_type
    }
    
    return content, content_type

def get_content_type(file_path):
    """Determine the content type based on file extension."""
    _, ext = os.path.splitext(file_path)
    content_types = {
        '.js': 'application/javascript',
        '.css': 'text/css',
        '.html': 'text/html',
        '.txt': 'text/plain',
        '.json': 'application/json',
        '.svg': 'image/svg+xml',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.ico': 'image/x-icon'
    }
    return content_types.get(ext.lower(), 'application/octet-stream')

def minify_content(content, extension):
    """Minify content based on file type."""
    if extension == '.js':
        # Basic JS minification (removing comments and unnecessary whitespace)
        content_str = content.decode('utf-8')
        # Remove multi-line comments
        content_str = re.sub(r'/\*[\s\S]*?\*/', '', content_str)
        # Remove single-line comments
        content_str = re.sub(r'//.*$', '', content_str, flags=re.MULTILINE)
        # Remove leading/trailing whitespace
        content_str = re.sub(r'^\s+', '', content_str, flags=re.MULTILINE)
        content_str = re.sub(r'\s+$', '', content_str, flags=re.MULTILINE)
        # Reduce multiple spaces to single space
        content_str = re.sub(r'\s{2,}', ' ', content_str)
        return content_str.encode('utf-8')
        
    elif extension == '.css':
        # Basic CSS minification
        content_str = content.decode('utf-8')
        # Remove comments
        content_str = re.sub(r'/\*[\s\S]*?\*/', '', content_str)
        # Remove whitespace
        content_str = re.sub(r'\s+', ' ', content_str)
        content_str = re.sub(r';\s', ';', content_str)
        content_str = re.sub(r':\s', ':', content_str)
        content_str = re.sub(r',\s', ',', content_str)
        content_str = re.sub(r'{\s', '{', content_str)
        content_str = re.sub(r'}\s', '}', content_str)
        return content_str.encode('utf-8')
        
    elif extension == '.html':
        # Basic HTML minification
        content_str = content.decode('utf-8')
        # Remove comments (except conditional comments)
        content_str = re.sub(r'<!--(?!<!)[^\[>][\s\S]*?-->', '', content_str)
        # Remove whitespace between tags
        content_str = re.sub(r'>\s+<', '><', content_str)
        # Remove leading/trailing whitespace
        content_str = re.sub(r'^\s+', '', content_str, flags=re.MULTILINE)
        content_str = re.sub(r'\s+$', '', content_str, flags=re.MULTILINE)
        return content_str.encode('utf-8')
        
    # If no minification is applicable, return the original content
    return content

def should_use_gzip(file_path):
    """Determine if a file should be gzipped based on extension and size."""
    _, ext = os.path.splitext(file_path)
    # Only gzip certain file types
    if ext not in GZIPPABLE_EXTENSIONS:
        return False
        
    # Only gzip files over a certain size
    min_size = current_app.config.get('GZIP_MIN_SIZE', 1024)  # Default 1KB
    return os.path.getsize(file_path) >= min_size

def accepts_gzip():
    """Check if the client accepts gzip encoding."""
    accept_encoding = request.headers.get('Accept-Encoding', '')
    return 'gzip' in accept_encoding

def versioned_static_url(filename):
    """Generate a versioned URL for a static file."""
    # In production, this would append a version hash or timestamp
    # For development, just return the regular URL
    return f"/static/{filename}"

def configure_assets(assets):
    """Configure Flask-Assets bundles.
    
    Args:
        assets: The Flask-Assets Environment instance
    """
    # Only register bundles if they haven't been registered yet
    if 'css_all' not in assets:
        # CSS Bundle - include only local stylesheet; Bootstrap is loaded via CDN in templates
        css_bundle = Bundle(
            'css/style.css',
            filters='cssmin',
            output='gen/packed.css'
        )
        assets.register('css_all', css_bundle)
    
    if 'js_all' not in assets:
        # JavaScript Bundle - only include local main.js; jQuery/Bootstrap are loaded via CDN in templates
        js_bundle = Bundle(
            'js/main.js',
            filters='jsmin',
            output='gen/packed.js'
        )
        assets.register('js_all', js_bundle)
