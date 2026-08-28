"""
API Keys Management Blueprint

This module provides endpoints to manage API keys for external service integration.
Only users with the MANAGE_API_KEYS permission can access these endpoints.
"""

from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from models import db, User, Permission, APIKey
from blueprints.admin import permission_required
from datetime import datetime, timedelta
from utils.security import secure_endpoint, ajax_csrf_protect
from utils.validation import validate_json_payload, validate_pattern, validate_length

# Create blueprint
bp = Blueprint('api_keys', __name__)

# Validators for API key creation and updates
api_key_schema = {
    'name': [
        lambda v: validate_pattern(v, pattern=r'^[a-zA-Z0-9_\-\s]{3,64}$', required=True),
        lambda v: validate_length(v, min_length=3, max_length=64, required=True)
    ],
    'description': lambda v: validate_length(v, max_length=500, required=False),
    'expires_in_days': lambda v: (
        isinstance(v, (int, float)) and v > 0, 
        "Expiration must be a positive number of days" if v is not None else ""
    ),
    'permissions': lambda v: (
        isinstance(v, int) and v >= 0,
        "Permissions must be a non-negative integer"
    )
}

@bp.route('/', methods=['GET'])
@login_required
@permission_required(Permission.MANAGE_API_KEYS)
@ajax_csrf_protect
def list_api_keys():
    """List all API keys."""
    try:
        api_keys = APIKey.query.all()
        return jsonify({
            'success': True,
            'api_keys': [key.to_dict() for key in api_keys]
        })
    except Exception as e:
        current_app.logger.error(f"Error listing API keys: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error retrieving API keys: {str(e)}"
        }), 500

@bp.route('/<int:key_id>', methods=['GET'])
@login_required
@permission_required(Permission.MANAGE_API_KEYS)
@ajax_csrf_protect
def get_api_key(key_id):
    """Get a specific API key by ID."""
    try:
        api_key = APIKey.query.get_or_404(key_id)
        return jsonify({
            'success': True,
            'api_key': api_key.to_dict()
        })
    except Exception as e:
        current_app.logger.error(f"Error retrieving API key {key_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error retrieving API key: {str(e)}"
        }), 500

@bp.route('/', methods=['POST'])
@login_required
@permission_required(Permission.MANAGE_API_KEYS)
@secure_endpoint(limit="5/minute")
@validate_json_payload(api_key_schema)
def create_api_key():
    """Create a new API key."""
    try:
        data = request.get_json()
        name = data.get('name')
        description = data.get('description')
        permissions = data.get('permissions', Permission.API_ACCESS)
        
        # Calculate expiration date if provided
        expires_at = None
        if 'expires_in_days' in data and data['expires_in_days']:
            expires_at = datetime.utcnow() + timedelta(days=float(data['expires_in_days']))
        
        # Create the API key
        api_key, raw_key = APIKey.create_key(
            name=name,
            description=description,
            permissions=permissions,
            created_by=current_user,
            expires_at=expires_at
        )
        
        # Log the API key creation
        current_app.logger.info(f"API key created: {api_key.id} by user {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': 'API key created successfully',
            'api_key': api_key.to_dict(),
            'raw_key': raw_key  # This is the only time the raw key will be available
        })
    except Exception as e:
        current_app.logger.error(f"Error creating API key: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error creating API key: {str(e)}"
        }), 500

@bp.route('/<int:key_id>', methods=['PUT'])
@login_required
@permission_required(Permission.MANAGE_API_KEYS)
@secure_endpoint(limit="10/minute")
@validate_json_payload({
    'name': lambda v: validate_pattern(v, pattern=r'^[a-zA-Z0-9_\-\s]{3,64}$', required=False),
    'description': lambda v: validate_length(v, max_length=500, required=False),
    'permissions': lambda v: (
        isinstance(v, int) and v >= 0,
        "Permissions must be a non-negative integer"
    ),
    'active': lambda v: (isinstance(v, bool), "Active must be a boolean")
})
def update_api_key(key_id):
    """Update an existing API key."""
    try:
        api_key = APIKey.query.get_or_404(key_id)
        data = request.get_json()
        
        # Update fields if provided
        if 'name' in data:
            api_key.name = data['name']
        if 'description' in data:
            api_key.description = data['description']
        if 'permissions' in data:
            api_key.permissions = data['permissions']
        if 'active' in data:
            api_key.active = data['active']
        if 'expires_in_days' in data and data['expires_in_days']:
            api_key.expires_at = datetime.utcnow() + timedelta(days=float(data['expires_in_days']))
        
        db.session.commit()
        
        # Log the API key update
        current_app.logger.info(f"API key updated: {api_key.id} by user {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': 'API key updated successfully',
            'api_key': api_key.to_dict()
        })
    except Exception as e:
        current_app.logger.error(f"Error updating API key {key_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error updating API key: {str(e)}"
        }), 500

@bp.route('/<int:key_id>', methods=['DELETE'])
@login_required
@permission_required(Permission.MANAGE_API_KEYS)
@secure_endpoint(limit="5/minute")
def delete_api_key(key_id):
    """Delete (deactivate) an API key."""
    try:
        api_key = APIKey.query.get_or_404(key_id)
        
        # Soft delete by setting inactive
        api_key.active = False
        db.session.commit()
        
        # Log the API key deletion
        current_app.logger.info(f"API key deactivated: {api_key.id} by user {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': 'API key deactivated successfully'
        })
    except Exception as e:
        current_app.logger.error(f"Error deactivating API key {key_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error deactivating API key: {str(e)}"
        }), 500

@bp.route('/<int:key_id>/revoke', methods=['POST'])
@login_required
@permission_required(Permission.MANAGE_API_KEYS)
@secure_endpoint(limit="5/minute")
def revoke_api_key(key_id):
    """Revoke an API key (set it as inactive)."""
    try:
        api_key = APIKey.query.get_or_404(key_id)
        
        # Revoke by setting inactive
        api_key.active = False
        db.session.commit()
        
        # Log the API key revocation
        current_app.logger.info(f"API key revoked: {api_key.id} by user {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': 'API key revoked successfully'
        })
    except Exception as e:
        current_app.logger.error(f"Error revoking API key {key_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error revoking API key: {str(e)}"
        }), 500

@bp.route('/<int:key_id>/regenerate', methods=['POST'])
@login_required
@permission_required(Permission.MANAGE_API_KEYS)
@secure_endpoint(limit="2/minute")
def regenerate_api_key(key_id):
    """Regenerate an API key while keeping its metadata."""
    try:
        old_key = APIKey.query.get_or_404(key_id)
        
        # Create a new key with the same metadata
        new_key, raw_key = APIKey.create_key(
            name=old_key.name,
            description=old_key.description,
            permissions=old_key.permissions,
            created_by=current_user,
            expires_at=old_key.expires_at
        )
        
        # Deactivate the old key
        old_key.active = False
        db.session.commit()
        
        # Log the API key regeneration
        current_app.logger.info(f"API key regenerated: old={old_key.id}, new={new_key.id} by user {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': 'API key regenerated successfully',
            'api_key': new_key.to_dict(),
            'raw_key': raw_key  # This is the only time the raw key will be available
        })
    except Exception as e:
        current_app.logger.error(f"Error regenerating API key {key_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error regenerating API key: {str(e)}"
        }), 500
