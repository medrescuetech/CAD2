"""
IP Access Control Blueprint

This module provides endpoints for managing IP access restrictions and allowlists,
enabling administrators to control system access based on IP addresses.
"""

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from models import db, IPRestriction, IPAllowList, User, Permission
from utils.decorators import permission_required
from utils.ip_access_control import (
    add_ip_restriction, remove_ip_restriction, 
    add_to_ip_allowlist, remove_from_ip_allowlist
)
from utils.audit_log import log_audit_event, AuditCategory, AuditSeverity
from utils.security import secure_endpoint

bp = Blueprint('ip_access', __name__)

@bp.route('/restrictions', methods=['GET'])
@login_required
@permission_required(Permission.ADMIN)
@secure_endpoint(limit="20/minute")
def get_ip_restrictions():
    """Get all IP restrictions."""
    try:
        # Check for active only filter
        active_only = request.args.get('active', 'true').lower() == 'true'
        
        query = IPRestriction.query
        if active_only:
            query = query.filter_by(is_active=True)
            
        restrictions = query.order_by(IPRestriction.created_at.desc()).all()
        
        return jsonify({
            'success': True,
            'ip_restrictions': [r.to_dict() for r in restrictions],
            'count': len(restrictions)
        })
    except Exception as e:
        current_app.logger.error(f"Error retrieving IP restrictions: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error retrieving IP restrictions: {str(e)}"
        }), 500

@bp.route('/restrictions', methods=['POST'])
@login_required
@permission_required(Permission.ADMIN)
@secure_endpoint(limit="10/minute")
def add_restriction():
    """Add a new IP restriction."""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': "Missing JSON data"
            }), 400
        
        ip_address = data.get('ip_address')
        reason = data.get('reason')
        
        if not ip_address:
            return jsonify({
                'success': False,
                'message': "IP address is required"
            }), 400
        
        success, message = add_ip_restriction(
            ip_address=ip_address,
            reason=reason,
            added_by_user_id=current_user.id
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': message
            }), 201
        else:
            return jsonify({
                'success': False,
                'message': message
            }), 400
    except Exception as e:
        current_app.logger.error(f"Error adding IP restriction: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error adding IP restriction: {str(e)}"
        }), 500

@bp.route('/restrictions/<int:restriction_id>', methods=['DELETE'])
@login_required
@permission_required(Permission.ADMIN)
@secure_endpoint(limit="10/minute")
def remove_restriction(restriction_id):
    """Remove an IP restriction."""
    try:
        restriction = IPRestriction.query.get_or_404(restriction_id)
        
        success, message = remove_ip_restriction(
            ip_address=restriction.ip_address,
            removed_by_user_id=current_user.id
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': message
            })
        else:
            return jsonify({
                'success': False,
                'message': message
            }), 400
    except Exception as e:
        current_app.logger.error(f"Error removing IP restriction: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error removing IP restriction: {str(e)}"
        }), 500

@bp.route('/allowlist', methods=['GET'])
@login_required
@permission_required(Permission.ADMIN)
@secure_endpoint(limit="20/minute")
def get_ip_allowlist():
    """Get all IP allowlist entries."""
    try:
        # Check for active only filter
        active_only = request.args.get('active', 'true').lower() == 'true'
        
        query = IPAllowList.query
        if active_only:
            query = query.filter_by(is_active=True)
            
        allowlist = query.order_by(IPAllowList.created_at.desc()).all()
        
        return jsonify({
            'success': True,
            'ip_allowlist': [a.to_dict() for a in allowlist],
            'count': len(allowlist)
        })
    except Exception as e:
        current_app.logger.error(f"Error retrieving IP allowlist: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error retrieving IP allowlist: {str(e)}"
        }), 500

@bp.route('/allowlist', methods=['POST'])
@login_required
@permission_required(Permission.ADMIN)
@secure_endpoint(limit="10/minute")
def add_allowlist():
    """Add a new IP to the allowlist."""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': "Missing JSON data"
            }), 400
        
        ip_address = data.get('ip_address')
        description = data.get('description')
        
        if not ip_address:
            return jsonify({
                'success': False,
                'message': "IP address is required"
            }), 400
        
        success, message = add_to_ip_allowlist(
            ip_address=ip_address,
            description=description,
            added_by_user_id=current_user.id
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': message
            }), 201
        else:
            return jsonify({
                'success': False,
                'message': message
            }), 400
    except Exception as e:
        current_app.logger.error(f"Error adding IP to allowlist: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error adding IP to allowlist: {str(e)}"
        }), 500

@bp.route('/allowlist/<int:allowlist_id>', methods=['DELETE'])
@login_required
@permission_required(Permission.ADMIN)
@secure_endpoint(limit="10/minute")
def remove_allowlist(allowlist_id):
    """Remove an IP from the allowlist."""
    try:
        allowlist_entry = IPAllowList.query.get_or_404(allowlist_id)
        
        success, message = remove_from_ip_allowlist(
            ip_address=allowlist_entry.ip_address,
            removed_by_user_id=current_user.id
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': message
            })
        else:
            return jsonify({
                'success': False,
                'message': message
            }), 400
    except Exception as e:
        current_app.logger.error(f"Error removing IP from allowlist: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error removing IP from allowlist: {str(e)}"
        }), 500

@bp.route('/settings', methods=['GET'])
@login_required
@permission_required(Permission.ADMIN)
@secure_endpoint(limit="20/minute")
def get_ip_settings():
    """Get current IP access control settings."""
    try:
        settings = {
            'ip_restrictions_enabled': current_app.config.get('ENABLE_IP_RESTRICTIONS', False),
            'ip_allowlist_only': current_app.config.get('IP_ALLOWLIST_ONLY', False),
            'mode': 'blacklist' if not current_app.config.get('IP_ALLOWLIST_ONLY', False) else 'allowlist'
        }
        
        return jsonify({
            'success': True,
            'settings': settings
        })
    except Exception as e:
        current_app.logger.error(f"Error retrieving IP settings: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error retrieving IP settings: {str(e)}"
        }), 500

@bp.route('/settings', methods=['PUT'])
@login_required
@permission_required(Permission.ADMIN)
@secure_endpoint(limit="10/minute")
def update_ip_settings():
    """Update IP access control settings."""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': "Missing JSON data"
            }), 400
        
        # Only superuser can change these settings
        if not current_user.can(Permission.SUPERUSER):
            log_audit_event(
                category=AuditCategory.SECURITY,
                action="Unauthorized IP settings change attempt",
                severity=AuditSeverity.WARNING,
                user_id=current_user.id
            )
            return jsonify({
                'success': False,
                'message': "You do not have permission to change these settings"
            }), 403
        
        # Update settings in config
        ip_restrictions_enabled = data.get('ip_restrictions_enabled')
        ip_allowlist_only = data.get('ip_allowlist_only')
        mode = data.get('mode')
        
        if ip_restrictions_enabled is not None:
            current_app.config['ENABLE_IP_RESTRICTIONS'] = bool(ip_restrictions_enabled)
            
        if ip_allowlist_only is not None:
            current_app.config['IP_ALLOWLIST_ONLY'] = bool(ip_allowlist_only)
        
        # Allow setting mode directly (blacklist or allowlist)
        if mode is not None:
            if mode.lower() == 'blacklist':
                current_app.config['IP_ALLOWLIST_ONLY'] = False
            elif mode.lower() == 'allowlist':
                current_app.config['IP_ALLOWLIST_ONLY'] = True
        
        # Log the change
        log_audit_event(
            category=AuditCategory.SECURITY,
            action="IP access settings updated",
            severity=AuditSeverity.INFO,
            user_id=current_user.id,
            details={
                'enable_ip_restrictions': current_app.config.get('ENABLE_IP_RESTRICTIONS'),
                'ip_allowlist_only': current_app.config.get('IP_ALLOWLIST_ONLY'),
                'mode': 'blacklist' if not current_app.config.get('IP_ALLOWLIST_ONLY', False) else 'allowlist'
            }
        )
        
        return jsonify({
            'success': True,
            'message': "IP access control settings updated",
            'settings': {
                'ip_restrictions_enabled': current_app.config.get('ENABLE_IP_RESTRICTIONS', False),
                'ip_allowlist_only': current_app.config.get('IP_ALLOWLIST_ONLY', False),
                'mode': 'blacklist' if not current_app.config.get('IP_ALLOWLIST_ONLY', False) else 'allowlist'
            }
        })
    except Exception as e:
        current_app.logger.error(f"Error updating IP settings: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error updating IP settings: {str(e)}"
        }), 500
