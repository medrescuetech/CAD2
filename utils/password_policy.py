"""
Password Policy Enforcement

This module provides validation and enforcement of password policies
including complexity requirements, history checks, and expiration.
"""

import re
from datetime import datetime, timedelta
from flask import current_app
from models import db, User

class PasswordPolicyError(Exception):
    """Exception raised for password policy violations."""
    pass

def validate_password_complexity(password, username=None, email=None, first_name=None, last_name=None):
    """
    Validate password complexity against policy requirements.
    
    Args:
        password (str): Password to validate
        username (str, optional): User's username to check against
        email (str, optional): User's email to check against
        first_name (str, optional): User's first name to check against
        last_name (str, optional): User's last name to check against
        
    Returns:
        bool: True if password meets complexity requirements
        
    Raises:
        PasswordPolicyError: If password fails to meet requirements
    """
    # Get configuration from app config with defaults
    min_length = current_app.config.get('PASSWORD_MIN_LENGTH', 8)
    require_uppercase = current_app.config.get('PASSWORD_REQUIRE_UPPERCASE', True)
    require_lowercase = current_app.config.get('PASSWORD_REQUIRE_LOWERCASE', True)
    require_numbers = current_app.config.get('PASSWORD_REQUIRE_NUMBERS', True)
    require_special = current_app.config.get('PASSWORD_REQUIRE_SPECIAL', True)
    special_chars = current_app.config.get('PASSWORD_SPECIAL_CHARS', '!@#$%^&*()_-+={}[]|:;<>,.?/~`')
    
    # Check minimum length
    if len(password) < min_length:
        raise PasswordPolicyError(f"Password must be at least {min_length} characters long.")
    
    # Check for required character types
    if require_uppercase and not any(c.isupper() for c in password):
        raise PasswordPolicyError("Password must contain at least one uppercase letter.")
    
    if require_lowercase and not any(c.islower() for c in password):
        raise PasswordPolicyError("Password must contain at least one lowercase letter.")
    
    if require_numbers and not any(c.isdigit() for c in password):
        raise PasswordPolicyError("Password must contain at least one number.")
    
    if require_special and not any(c in special_chars for c in password):
        raise PasswordPolicyError(f"Password must contain at least one special character ({special_chars}).")
    
    # Check for common patterns to avoid
    common_patterns = [
        r'12345',
        r'qwerty',
        r'password',
        r'admin',
        r'welcome'
    ]
    
    for pattern in common_patterns:
        if re.search(pattern, password, re.IGNORECASE):
            raise PasswordPolicyError(f"Password contains a common pattern ({pattern}) that is not allowed.")
    
    # Check for personal information in password
    personal_info = [username, email, first_name, last_name]
    for info in personal_info:
        if info and len(info) > 3 and info.lower() in password.lower():
            raise PasswordPolicyError("Password cannot contain your personal information (username, email, name).")
    
    return True

def check_password_history(user, new_password, password_history_count=None):
    """
    Check if a new password has been used recently based on password history policy.
    
    Args:
        user (User): User object to check history against
        new_password (str): New password to validate
        password_history_count (int, optional): Number of past passwords to check against
        
    Returns:
        bool: True if password is not in history
        
    Raises:
        PasswordPolicyError: If password is found in history
    """
    # Get configuration from app config with defaults
    if password_history_count is None:
        password_history_count = current_app.config.get('PASSWORD_HISTORY_COUNT', 5)
    
    # If history check is disabled, return True
    if password_history_count <= 0:
        return True
    
    # Get the user's password history
    from models import PasswordHistory
    history_entries = PasswordHistory.query.filter_by(user_id=user.id).order_by(
        PasswordHistory.created_at.desc()
    ).limit(password_history_count).all()
    
    # Check new password against current password
    if user.verify_password(new_password):
        raise PasswordPolicyError("New password cannot be the same as your current password.")
    
    # Check against password history
    for entry in history_entries:
        if entry.verify_password(new_password):
            raise PasswordPolicyError(f"Password has been used recently. You must use a password that has not been used in the past {password_history_count} times.")
    
    return True

def is_password_expired(user):
    """
    Check if a user's password has expired based on policy.
    
    Args:
        user (User): User to check password expiration for
        
    Returns:
        bool: True if password is expired, False otherwise
    """
    # Get configuration from app config with defaults
    password_max_age_days = current_app.config.get('PASSWORD_MAX_AGE_DAYS', 90)
    
    # If password expiration is disabled, return False
    if password_max_age_days <= 0:
        return False
    
    # Check if password is older than the max age
    # Get the most recent password change from password_history if available
    from models import PasswordHistory
    last_password_change = PasswordHistory.query.filter_by(user_id=user.id).order_by(PasswordHistory.created_at.desc()).first()
    
    if last_password_change:
        last_change = last_password_change.created_at
    else:
        # If no password history entries, use account creation time
        last_change = user.created_at
    
    password_expires_at = last_change + timedelta(days=password_max_age_days)
    
    return datetime.utcnow() > password_expires_at

def days_until_password_expiration(user):
    """
    Calculate the number of days until a user's password expires.
    
    Args:
        user (User): User to check password expiration for
        
    Returns:
        int: Number of days until password expires, or -1 if already expired or expiration is disabled
    """
    # Get configuration from app config with defaults
    password_max_age_days = current_app.config.get('PASSWORD_MAX_AGE_DAYS', 90)
    
    # If password expiration is disabled, return -1
    if password_max_age_days <= 0:
        return -1
    
    # Check if password is older than the max age
    # Get the most recent password change from password_history if available
    from models import PasswordHistory
    last_password_change = PasswordHistory.query.filter_by(user_id=user.id).order_by(PasswordHistory.created_at.desc()).first()
    
    if last_password_change:
        last_change = last_password_change.created_at
    else:
        # If no password history entries, use account creation time
        last_change = user.created_at
    
    password_expires_at = last_change + timedelta(days=password_max_age_days)
    
    # If password is already expired, return -1
    if datetime.utcnow() > password_expires_at:
        return -1
    
    # Calculate days until expiration
    delta = password_expires_at - datetime.utcnow()
    return delta.days

def add_password_to_history(user, password):
    """
    Add a password to a user's password history.
    
    Args:
        user (User): User to add password history for
        password (str): Password to add to history
        
    Returns:
        PasswordHistory: New password history entry
    """
    # Create a new password history entry
    from models import PasswordHistory
    history_entry = PasswordHistory(
        user_id=user.id,
        password=password
    )
    
    db.session.add(history_entry)
    db.session.commit()
    
    # Get configuration from app config with defaults
    password_history_count = current_app.config.get('PASSWORD_HISTORY_COUNT', 5)
    
    # If history limit is set, trim the history to the limit
    if password_history_count > 0:
        # Get all history entries for the user
        history_entries = PasswordHistory.query.filter_by(user_id=user.id).order_by(
            PasswordHistory.created_at.desc()
        ).all()
        
        # Remove excess entries
        if len(history_entries) > password_history_count:
            for entry in history_entries[password_history_count:]:
                db.session.delete(entry)
            db.session.commit()
    
    return history_entry
