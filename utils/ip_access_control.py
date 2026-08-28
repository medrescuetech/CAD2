"""
IP Access Control

This module provides functions for controlling access to the CAD system
based on IP address restrictions and allowlists.
"""

from flask import request, current_app
from functools import wraps
from models import IPAllowList, IPRestriction, db
from datetime import datetime
import ipaddress
from utils.audit_log import log_audit_event, AuditCategory, AuditSeverity

def is_ip_allowed(ip_address):
    """
    Check if an IP address is allowed to access the system.
    
    Args:
        ip_address (str): IP address to check
        
    Returns:
        bool: True if IP is allowed, False if restricted
    """
    # If IP restrictions are disabled in config, allow all
    if not current_app.config.get('ENABLE_IP_RESTRICTIONS', False):
        return True
    
    # Check if IP is in active restrictions (blacklist)
    restriction = IPRestriction.query.filter_by(
        ip_address=ip_address, 
        is_active=True
    ).first()
    
    if restriction:
        # IP is explicitly restricted
        return False
    
    # Check if allowlist mode is enabled (default is False - blacklist only mode)
    if current_app.config.get('IP_ALLOWLIST_ONLY', False):
        # In allowlist-only mode, check if IP is in allowlist
        allowlist_entry = IPAllowList.query.filter_by(
            ip_address=ip_address,
            is_active=True
        ).first()
        
        # Only allow if explicitly in allowlist
        return allowlist_entry is not None
    
    # By default, allow all IPs that aren't explicitly blacklisted
    return True

def is_ip_in_cidr_list(ip_address, cidr_list):
    """
    Check if an IP address is within any of the CIDR blocks.
    
    Args:
        ip_address (str): IP address to check
        cidr_list (list): List of CIDR blocks to check against
        
    Returns:
        bool: True if IP is in any CIDR block, False otherwise
    """
    try:
        ip_obj = ipaddress.ip_address(ip_address)
        
        for cidr in cidr_list:
            network = ipaddress.ip_network(cidr, strict=False)
            if ip_obj in network:
                return True
        
        return False
    except ValueError:
        # If we can't parse the IP or CIDR, assume not in list
        return False

def ip_access_required(f):
    """
    Decorator to restrict access based on IP address.
    
    Usage:
        @app.route('/protected')
        @ip_access_required
        def protected_route():
            # Only accessible from allowed IPs
            return 'Protected content'
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import jsonify, abort
        
        # Get client IP address
        ip_address = request.remote_addr
        
        if not is_ip_allowed(ip_address):
            # Log the access attempt
            log_audit_event(
                category=AuditCategory.SECURITY,
                action="IP access denied",
                severity=AuditSeverity.WARNING,
                details={
                    'ip_address': ip_address,
                    'path': request.path,
                    'method': request.method
                }
            )
            
            # Return 403 Forbidden
            return jsonify({
                'success': False,
                'message': 'Access denied: Your IP address is restricted'
            }), 403
        
        return f(*args, **kwargs)
    
    return decorated_function

def add_ip_restriction(ip_address, reason=None, added_by_user_id=None):
    """
    Add an IP address to the restriction list.
    
    Args:
        ip_address (str): IP address to restrict
        reason (str, optional): Reason for restriction
        added_by_user_id (int, optional): User ID who added the restriction
        
    Returns:
        tuple: (success, message)
    """
    try:
        # Validate IP address
        ipaddress.ip_address(ip_address)
        
        # Check if already restricted
        existing = IPRestriction.query.filter_by(ip_address=ip_address).first()
        
        if existing:
            if existing.is_active:
                return False, "IP address is already restricted"
            
            # Reactivate if inactive
            existing.is_active = True
            existing.updated_at = datetime.utcnow()
            existing.reason = reason or existing.reason
            existing.added_by_user_id = added_by_user_id or existing.added_by_user_id
            db.session.commit()
            
            log_audit_event(
                category=AuditCategory.SECURITY,
                action="IP restriction reactivated",
                severity=AuditSeverity.INFO,
                user_id=added_by_user_id,
                details={
                    'ip_address': ip_address,
                    'reason': reason
                }
            )
            
            return True, "IP restriction reactivated"
        
        # Create new restriction
        restriction = IPRestriction(
            ip_address=ip_address,
            reason=reason,
            added_by_user_id=added_by_user_id
        )
        
        db.session.add(restriction)
        db.session.commit()
        
        log_audit_event(
            category=AuditCategory.SECURITY,
            action="IP restriction added",
            severity=AuditSeverity.INFO,
            user_id=added_by_user_id,
            details={
                'ip_address': ip_address,
                'reason': reason
            }
        )
        
        return True, "IP restriction added successfully"
    except ValueError:
        return False, "Invalid IP address format"
    except Exception as e:
        db.session.rollback()
        return False, f"Error adding IP restriction: {str(e)}"

def remove_ip_restriction(ip_address, removed_by_user_id=None):
    """
    Remove an IP address from the restriction list.
    
    Args:
        ip_address (str): IP address to unrestrict
        removed_by_user_id (int, optional): User ID who removed the restriction
        
    Returns:
        tuple: (success, message)
    """
    try:
        # Find the restriction
        restriction = IPRestriction.query.filter_by(
            ip_address=ip_address,
            is_active=True
        ).first()
        
        if not restriction:
            return False, "IP address is not currently restricted"
        
        # Deactivate the restriction
        restriction.is_active = False
        restriction.updated_at = datetime.utcnow()
        restriction.removed_by_user_id = removed_by_user_id
        restriction.removed_at = datetime.utcnow()
        
        db.session.commit()
        
        log_audit_event(
            category=AuditCategory.SECURITY,
            action="IP restriction removed",
            severity=AuditSeverity.INFO,
            user_id=removed_by_user_id,
            details={
                'ip_address': ip_address
            }
        )
        
        return True, "IP restriction removed successfully"
    except Exception as e:
        db.session.rollback()
        return False, f"Error removing IP restriction: {str(e)}"

def add_to_ip_allowlist(ip_address, description=None, added_by_user_id=None):
    """
    Add an IP address to the allowlist.
    
    Args:
        ip_address (str): IP address to allow
        description (str, optional): Description/reason
        added_by_user_id (int, optional): User ID who added the address
        
    Returns:
        tuple: (success, message)
    """
    try:
        # Validate IP address
        ipaddress.ip_address(ip_address)
        
        # Check if already in allowlist
        existing = IPAllowList.query.filter_by(ip_address=ip_address).first()
        
        if existing:
            if existing.is_active:
                return False, "IP address is already in allowlist"
            
            # Reactivate if inactive
            existing.is_active = True
            existing.updated_at = datetime.utcnow()
            existing.description = description or existing.description
            existing.added_by_user_id = added_by_user_id or existing.added_by_user_id
            db.session.commit()
            
            log_audit_event(
                category=AuditCategory.SECURITY,
                action="IP allowlist entry reactivated",
                severity=AuditSeverity.INFO,
                user_id=added_by_user_id,
                details={
                    'ip_address': ip_address,
                    'description': description
                }
            )
            
            return True, "IP allowlist entry reactivated"
        
        # Create new allowlist entry
        allowlist_entry = IPAllowList(
            ip_address=ip_address,
            description=description,
            added_by_user_id=added_by_user_id
        )
        
        db.session.add(allowlist_entry)
        db.session.commit()
        
        log_audit_event(
            category=AuditCategory.SECURITY,
            action="IP added to allowlist",
            severity=AuditSeverity.INFO,
            user_id=added_by_user_id,
            details={
                'ip_address': ip_address,
                'description': description
            }
        )
        
        return True, "IP address added to allowlist successfully"
    except ValueError:
        return False, "Invalid IP address format"
    except Exception as e:
        db.session.rollback()
        return False, f"Error adding IP to allowlist: {str(e)}"

def remove_from_ip_allowlist(ip_address, removed_by_user_id=None):
    """
    Remove an IP address from the allowlist.
    
    Args:
        ip_address (str): IP address to remove
        removed_by_user_id (int, optional): User ID who removed the address
        
    Returns:
        tuple: (success, message)
    """
    try:
        # Find the allowlist entry
        allowlist_entry = IPAllowList.query.filter_by(
            ip_address=ip_address,
            is_active=True
        ).first()
        
        if not allowlist_entry:
            return False, "IP address is not in the allowlist"
        
        # Deactivate the allowlist entry
        allowlist_entry.is_active = False
        allowlist_entry.updated_at = datetime.utcnow()
        allowlist_entry.removed_by_user_id = removed_by_user_id
        allowlist_entry.removed_at = datetime.utcnow()
        
        db.session.commit()
        
        log_audit_event(
            category=AuditCategory.SECURITY,
            action="IP removed from allowlist",
            severity=AuditSeverity.INFO,
            user_id=removed_by_user_id,
            details={
                'ip_address': ip_address
            }
        )
        
        return True, "IP address removed from allowlist successfully"
    except Exception as e:
        db.session.rollback()
        return False, f"Error removing IP from allowlist: {str(e)}"

def initialize_ip_access_settings():
    """
    Initialize IP access control settings.
    This creates default settings in the database.
    """
    from flask import current_app
    from models import db, IPRestriction, IPAllowList
    
    # Default to blacklist mode (IP_ALLOWLIST_ONLY = False)
    mode = False
    
    # Add localhost to allowlist for safety
    localhost = IPAllowList.query.filter_by(ip_address='127.0.0.1').first()
    if not localhost:
        localhost = IPAllowList(
            ip_address='127.0.0.1',
            description='Localhost - Added by system initialization',
            is_active=True
        )
        db.session.add(localhost)
    
    # Also add ::1 (IPv6 localhost)
    localhost_ipv6 = IPAllowList.query.filter_by(ip_address='::1').first()
    if not localhost_ipv6:
        localhost_ipv6 = IPAllowList(
            ip_address='::1',
            description='Localhost IPv6 - Added by system initialization',
            is_active=True
        )
        db.session.add(localhost_ipv6)
    
    # Commit the changes
    db.session.commit()
    
    return True
