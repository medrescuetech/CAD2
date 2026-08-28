import secrets
import hashlib
from time import time
from functools import wraps
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from flask import current_app, request, jsonify
from models import BlacklistedToken

def generate_reset_token(user_id):
    """
    Generate a secure token for password reset
    
    Args:
        user_id (int): The ID of the user requesting password reset
        
    Returns:
        str: A secure URL-safe token
    """
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    return serializer.dumps(user_id, salt=current_app.config.get('SECURITY_PASSWORD_SALT', 'password-reset-salt'))

def verify_reset_token(token, expiration=3600):
    """
    Verify a password reset token
    
    Args:
        token (str): The token to verify
        expiration (int): The token expiration time in seconds (default: 1 hour)
        
    Returns:
        int or None: The user ID if token is valid, None otherwise
    """
    # First check if the token is blacklisted
    if BlacklistedToken.check_blacklist(token):
        return None
        
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        user_id = serializer.loads(
            token,
            salt=current_app.config.get('SECURITY_PASSWORD_SALT', 'password-reset-salt'),
            max_age=expiration
        )
        return user_id
    except (SignatureExpired, BadSignature):
        return None

def generate_api_key():
    """
    Generate a secure API key
    
    Returns:
        str: A secure API key
    """
    # Generate a random token
    token = secrets.token_hex(32)
    
    # Add a timestamp component for uniqueness
    timestamp = int(time())
    
    # Combine and hash for the final key
    combined = f"{token}-{timestamp}"
    hashed = hashlib.sha256(combined.encode()).hexdigest()
    
    return hashed

def token_required(f):
    """
    Decorator for routes that require a valid token
    Used for API routes that should verify a token
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Check if token is in the headers
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]
        
        # Check if token is in the URL parameters
        if not token:
            token = request.args.get('token')
            
        # Check if token is in the form data
        if not token and request.form:
            token = request.form.get('token')
            
        # Check if token is in the JSON data
        if not token and request.is_json:
            token = request.json.get('token')
            
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
            
        # Verify token here and get the user
        user_id = verify_reset_token(token)
        if not user_id:
            return jsonify({'error': 'Token is invalid or expired'}), 401
            
        # Add user_id to kwargs
        kwargs['user_id'] = user_id
        
        return f(*args, **kwargs)
    
    return decorated
