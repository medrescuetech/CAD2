"""
User and Role Management API

This module provides endpoints for managing users and roles in the CAD system.
Only users with appropriate permissions can access these endpoints.
"""

from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from models import db, User, Role, Permission
from blueprints.admin import permission_required
from utils.security import secure_endpoint, ajax_csrf_protect
from utils.audit_log import log_audit_event, AuditCategory, AuditSeverity, audit_role_change
from utils.validation import validate_json_payload, validate_pattern, validate_length
from werkzeug.security import generate_password_hash
from datetime import datetime
import re

# Create blueprint
bp = Blueprint('user_management', __name__)

# Validators for user creation and updates
user_schema = {
    'username': [
        lambda v: validate_pattern(v, pattern=r'^[a-zA-Z0-9_\-\.]{3,64}$', required=True),
        lambda v: validate_length(v, min_length=3, max_length=64, required=True)
    ],
    'email': lambda v: validate_pattern(v, pattern=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', required=True),
    'first_name': lambda v: validate_length(v, min_length=1, max_length=64, required=True),
    'last_name': lambda v: validate_length(v, min_length=1, max_length=64, required=True),
    'role_id': lambda v: (isinstance(v, int) and v > 0, "Role ID must be a positive integer"),
    'is_active': lambda v: (isinstance(v, bool), "Active status must be a boolean")
}

@bp.route('/users', methods=['GET'])
@login_required
@permission_required(Permission.MANAGE_USERS)
@secure_endpoint(limit="60/minute")
def list_users():
    """List all users."""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        
        # Get query parameters for filtering
        username = request.args.get('username')
        email = request.args.get('email')
        role_id = request.args.get('role_id', type=int)
        is_active = request.args.get('is_active')
        
        query = User.query
        
        # Apply filters if provided
        if username:
            query = query.filter(User.username.ilike(f'%{username}%'))
        if email:
            query = query.filter(User.email.ilike(f'%{email}%'))
        if role_id is not None:
            query = query.filter(User.role_id == role_id)
        if is_active is not None:
            is_active_bool = is_active.lower() == 'true'
            query = query.filter(User.is_active == is_active_bool)
        
        # Paginate the results
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        users = pagination.items
        
        # Log the access
        log_audit_event(
            category=AuditCategory.DATA_ACCESS,
            action="Listed users",
            severity=AuditSeverity.INFO,
            user_id=current_user.id
        )
        
        return jsonify({
            'success': True,
            'users': [user.to_dict() for user in users],
            'total': pagination.total,
            'pages': pagination.pages,
            'current_page': page
        })
    except Exception as e:
        current_app.logger.error(f"Error listing users: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error retrieving users: {str(e)}"
        }), 500

@bp.route('/users/<int:user_id>', methods=['GET'])
@login_required
@permission_required(Permission.MANAGE_USERS)
@ajax_csrf_protect
def get_user(user_id):
    """Get a specific user by ID."""
    try:
        user = User.query.get_or_404(user_id)
        
        # Log the access
        log_audit_event(
            category=AuditCategory.DATA_ACCESS,
            action="Viewed user details",
            severity=AuditSeverity.INFO,
            user_id=current_user.id,
            resource_id=str(user_id),
            resource_type='user'
        )
        
        return jsonify({
            'success': True,
            'user': user.to_dict()
        })
    except Exception as e:
        current_app.logger.error(f"Error retrieving user {user_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error retrieving user: {str(e)}"
        }), 500

@bp.route('/users', methods=['POST'])
@login_required
@permission_required(Permission.MANAGE_USERS)
@secure_endpoint(limit="10/minute")
@validate_json_payload(user_schema)
def create_user():
    """Create a new user."""
    try:
        data = request.get_json()
        
        # Check if username already exists
        existing_username = User.query.filter_by(username=data['username']).first()
        if existing_username:
            return jsonify({
                'success': False,
                'message': 'Username already exists'
            }), 400
        
        # Check if email already exists
        existing_email = User.query.filter_by(email=data['email']).first()
        if existing_email:
            return jsonify({
                'success': False,
                'message': 'Email already exists'
            }), 400
        
        # Validate role
        role = Role.query.get(data.get('role_id'))
        if not role:
            return jsonify({
                'success': False,
                'message': 'Invalid role ID'
            }), 400
        
        # Generate a random password
        import secrets
        import string
        temp_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
        
        # Create the user
        new_user = User(
            username=data['username'],
            email=data['email'],
            password=temp_password,  # This will be hashed by the User model
            first_name=data.get('first_name', ''),
            last_name=data.get('last_name', ''),
            role_id=data.get('role_id'),
            is_active=data.get('is_active', True)
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        # Log the user creation
        log_audit_event(
            category=AuditCategory.DATA_MODIFICATION,
            action="Created user",
            severity=AuditSeverity.INFO,
            user_id=current_user.id,
            resource_id=str(new_user.id),
            resource_type='user'
        )
        
        return jsonify({
            'success': True,
            'message': 'User created successfully',
            'user': new_user.to_dict(),
            'temp_password': temp_password  # Include temporary password in response
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating user: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error creating user: {str(e)}"
        }), 500

@bp.route('/users/<int:user_id>', methods=['PUT'])
@login_required
@permission_required(Permission.MANAGE_USERS)
@secure_endpoint(limit="20/minute")
@validate_json_payload({
    'username': lambda v: validate_pattern(v, pattern=r'^[a-zA-Z0-9_\-\.]{3,64}$', required=False),
    'email': lambda v: validate_pattern(v, pattern=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', required=False),
    'first_name': lambda v: validate_length(v, min_length=1, max_length=64, required=False),
    'last_name': lambda v: validate_length(v, min_length=1, max_length=64, required=False),
    'role_id': lambda v: (isinstance(v, int) and v > 0, "Role ID must be a positive integer"),
    'is_active': lambda v: (isinstance(v, bool), "Active status must be a boolean")
})
def update_user(user_id):
    """Update an existing user."""
    try:
        user = User.query.get_or_404(user_id)
        data = request.get_json()
        
        # Collect old values for audit log
        old_values = {
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'role_id': user.role_id,
            'is_active': user.is_active
        }
        
        # Check if username is changed and already exists
        if 'username' in data and data['username'] != user.username:
            existing_username = User.query.filter_by(username=data['username']).first()
            if existing_username:
                return jsonify({
                    'success': False,
                    'message': 'Username already exists'
                }), 400
        
        # Check if email is changed and already exists
        if 'email' in data and data['email'] != user.email:
            existing_email = User.query.filter_by(email=data['email']).first()
            if existing_email:
                return jsonify({
                    'success': False,
                    'message': 'Email already exists'
                }), 400
        
        # Validate role if provided
        if 'role_id' in data:
            role = Role.query.get(data['role_id'])
            if not role:
                return jsonify({
                    'success': False,
                    'message': 'Invalid role ID'
                }), 400
            
            # If role is changed, log it specially
            if data['role_id'] != user.role_id:
                old_role = Role.query.get(user.role_id)
                new_role = role
                audit_role_change(
                    current_user.id, 
                    user_id, 
                    old_role.name if old_role else None, 
                    new_role.name
                )
        
        # Update fields if provided
        if 'username' in data:
            user.username = data['username']
        if 'email' in data:
            user.email = data['email']
        if 'first_name' in data:
            user.first_name = data['first_name']
        if 'last_name' in data:
            user.last_name = data['last_name']
        if 'role_id' in data:
            user.role_id = data['role_id']
        if 'is_active' in data:
            user.is_active = data['is_active']
        
        # Update timestamp
        user.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        # Log the user update
        log_audit_event(
            category=AuditCategory.DATA_MODIFICATION,
            action="Updated user",
            severity=AuditSeverity.INFO,
            user_id=current_user.id,
            resource_id=str(user_id),
            resource_type='user',
            details={
                'changes': {k: data[k] for k in data if k in old_values and data[k] != old_values[k]}
            }
        )
        
        return jsonify({
            'success': True,
            'message': 'User updated successfully',
            'user': user.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating user {user_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error updating user: {str(e)}"
        }), 500

@bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@permission_required(Permission.MANAGE_USERS)
@secure_endpoint(limit="10/minute")
def reset_user_password(user_id):
    """Reset a user's password."""
    try:
        user = User.query.get_or_404(user_id)
        
        # Generate a new random password
        import secrets
        import string
        new_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
        
        # Update the password
        user.password = new_password  # This will be hashed by the User model
        db.session.commit()
        
        # Log the password reset
        log_audit_event(
            category=AuditCategory.AUTHENTICATION,
            action="Password reset by administrator",
            severity=AuditSeverity.INFO,
            user_id=current_user.id,
            resource_id=str(user_id),
            resource_type='user'
        )
        
        return jsonify({
            'success': True,
            'message': 'Password reset successfully',
            'new_password': new_password  # Include the new password in the response
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error resetting password for user {user_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error resetting password: {str(e)}"
        }), 500

@bp.route('/users/<int:user_id>', methods=['DELETE'])
@login_required
@permission_required(Permission.MANAGE_USERS)
@secure_endpoint(limit="5/minute")
def delete_user(user_id):
    """Delete (deactivate) a user."""
    try:
        # Protect against self-deletion
        if user_id == current_user.id:
            return jsonify({
                'success': False,
                'message': 'Cannot delete your own account'
            }), 403
        
        user = User.query.get_or_404(user_id)
        
        # Soft delete by setting inactive
        user.is_active = False
        db.session.commit()
        
        # Log the user deletion
        log_audit_event(
            category=AuditCategory.DATA_MODIFICATION,
            action="Deactivated user",
            severity=AuditSeverity.INFO,
            user_id=current_user.id,
            resource_id=str(user_id),
            resource_type='user'
        )
        
        return jsonify({
            'success': True,
            'message': 'User deactivated successfully'
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deactivating user {user_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error deactivating user: {str(e)}"
        }), 500

# Role Management Endpoints

# Validators for role creation and updates
role_schema = {
    'name': lambda v: validate_length(v, min_length=3, max_length=64, required=True),
    'permissions': lambda v: (isinstance(v, int), "Permissions must be an integer"),
    'description': lambda v: validate_length(v, max_length=255),
    'default': lambda v: (isinstance(v, bool), "Default flag must be a boolean"),
    'template_key': lambda v: validate_length(v, max_length=64)
}

@bp.route('/roles', methods=['GET'])
@login_required
@permission_required(Permission.MANAGE_ROLES)
@secure_endpoint(limit="60/minute")
def list_roles():
    """List all roles."""
    try:
        roles = Role.query.all()
        
        # Log the access
        log_audit_event(
            category=AuditCategory.DATA_ACCESS,
            action="Listed roles",
            severity=AuditSeverity.INFO,
            user_id=current_user.id
        )
        
        return jsonify({
            'success': True,
            'roles': [role.to_dict() for role in roles]
        })
    except Exception as e:
        current_app.logger.error(f"Error listing roles: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error retrieving roles: {str(e)}"
        }), 500

@bp.route('/roles/<int:role_id>', methods=['GET'])
@login_required
@permission_required(Permission.MANAGE_ROLES)
@ajax_csrf_protect
def get_role(role_id):
    """Get a specific role by ID."""
    try:
        role = Role.query.get_or_404(role_id)
        
        # Log the access
        log_audit_event(
            category=AuditCategory.DATA_ACCESS,
            action="Viewed role details",
            severity=AuditSeverity.INFO,
            user_id=current_user.id,
            resource_id=str(role_id),
            resource_type='role'
        )
        
        return jsonify({
            'success': True,
            'role': role.to_dict()
        })
    except Exception as e:
        current_app.logger.error(f"Error retrieving role {role_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error retrieving role: {str(e)}"
        }), 500

@bp.route('/roles/templates', methods=['GET'])
@login_required
@permission_required(Permission.MANAGE_ROLES)
@secure_endpoint(limit="30/minute")
def get_role_templates():
    """Get available role templates."""
    try:
        # Import role templates - avoid circular imports
        from utils.role_templates import RoleTemplate
        
        # Get all templates
        templates = RoleTemplate.get_all_templates()
        
        # Log the access
        log_audit_event(
            category=AuditCategory.DATA_ACCESS,
            action="Viewed role templates",
            severity=AuditSeverity.INFO,
            user_id=current_user.id
        )
        
        return jsonify({
            'success': True,
            'templates': templates
        })
    except Exception as e:
        current_app.logger.error(f"Error retrieving role templates: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error retrieving role templates: {str(e)}"
        }), 500

@bp.route('/roles/templates/<string:template_key>', methods=['GET'])
@login_required
@permission_required(Permission.MANAGE_ROLES)
@secure_endpoint(limit="30/minute")
def get_role_template(template_key):
    """Get a specific role template by key."""
    try:
        # Import role templates - avoid circular imports
        from utils.role_templates import RoleTemplate
        
        # Get the template
        template = RoleTemplate.get_template(template_key)
        if not template:
            return jsonify({
                'success': False,
                'message': f"Template '{template_key}' not found"
            }), 404
        
        # Log the access
        log_audit_event(
            category=AuditCategory.DATA_ACCESS,
            action=f"Viewed role template: {template_key}",
            severity=AuditSeverity.INFO,
            user_id=current_user.id
        )
        
        return jsonify({
            'success': True,
            'template': template
        })
    except Exception as e:
        current_app.logger.error(f"Error retrieving role template {template_key}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error retrieving role template: {str(e)}"
        }), 500

@bp.route('/roles/templates/<string:template_key>/apply', methods=['POST'])
@login_required
@permission_required(Permission.MANAGE_ROLES)
@secure_endpoint(limit="10/minute")
def apply_role_template(template_key):
    """Apply a role template to create a new role."""
    try:
        # Import role templates - avoid circular imports
        from utils.role_templates import RoleTemplate
        
        # Get the template
        template = RoleTemplate.get_template(template_key)
        if not template:
            return jsonify({
                'success': False,
                'message': f"Template '{template_key}' not found"
            }), 404
        
        # Get custom data from request
        data = request.get_json() or {}
        
        # Create name with suffix if custom name not provided
        name = data.get('name', template['name'])
        
        # Check if role already exists
        existing_role = Role.query.filter_by(name=name).first()
        if existing_role:
            return jsonify({
                'success': False,
                'message': f"Role with name '{name}' already exists"
            }), 400
        
        # Create the role using template values, overridden by any provided values
        new_role = Role(
            name=name,
            permissions=data.get('permissions', template['permissions']),
            description=data.get('description', template['description']),
            default=data.get('default', template['default'])
        )
        
        db.session.add(new_role)
        db.session.commit()
        
        # Log the creation from template
        log_audit_event(
            category=AuditCategory.DATA_MODIFICATION,
            action=f"Created role from template: {template_key}",
            severity=AuditSeverity.INFO,
            user_id=current_user.id,
            resource_id=str(new_role.id),
            resource_type='role'
        )
        
        return jsonify({
            'success': True,
            'message': 'Role created successfully from template',
            'role': {
                'id': new_role.id,
                'name': new_role.name,
                'permissions': new_role.permissions,
                'description': new_role.description,
                'default': new_role.default,
                'from_template': template_key
            }
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating role from template {template_key}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error creating role from template: {str(e)}"
        }), 500

@bp.route('/roles', methods=['POST'])
@login_required
@permission_required(Permission.MANAGE_ROLES)
@secure_endpoint(limit="10/minute")
@validate_json_payload(role_schema)
def create_role():
    """Create a new role."""
    try:
        data = request.get_json()
        
        # Check if name already exists
        existing_role = Role.query.filter_by(name=data['name']).first()
        if existing_role:
            return jsonify({
                'success': False,
                'message': 'Role name already exists'
            }), 400
        
        # If a template is specified, use it as a base
        if 'template_key' in data and data['template_key']:
            from utils.role_templates import RoleTemplate
            template = RoleTemplate.get_template(data['template_key'])
            
            if template:
                # Use template values but allow explicit overrides
                if 'permissions' not in data:
                    data['permissions'] = template['permissions']
                if 'description' not in data:
                    data['description'] = template['description']
                if 'default' not in data:
                    data['default'] = template['default']
        
        # Create the role
        new_role = Role(
            name=data['name'],
            permissions=data.get('permissions', 0),
            description=data.get('description', ''),
            default=data.get('default', False)
        )
        
        # If this is set as default, unset any other default roles
        if data.get('default', False):
            existing_default = Role.query.filter_by(default=True).all()
            for role in existing_default:
                role.default = False
        
        db.session.add(new_role)
        db.session.commit()
        
        # Construct the permission names list for logging
        permission_names = new_role.get_permissions()
        
        # Log the role creation
        log_audit_event(
            category=AuditCategory.DATA_MODIFICATION,
            action=f"Created role: {data['name']} with permissions: {', '.join(permission_names)}",
            severity=AuditSeverity.INFO,
            user_id=current_user.id,
            resource_id=str(new_role.id),
            resource_type='role'
        )
        
        return jsonify({
            'success': True,
            'message': 'Role created successfully',
            'role': {
                'id': new_role.id,
                'name': new_role.name,
                'permissions': new_role.permissions,
                'description': new_role.description,
                'default': new_role.default
            }
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating role: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error creating role: {str(e)}"
        }), 500

@bp.route('/roles/<int:role_id>', methods=['PUT'])
@login_required
@permission_required(Permission.MANAGE_ROLES)
@secure_endpoint(limit="20/minute")
@validate_json_payload(role_schema)
def update_role(role_id):
    """Update an existing role."""
    try:
        role = Role.query.get_or_404(role_id)
        
        # Prevent administrators from removing their own administrator role
        if (role.name == 'Administrator' and 
            role.has_permission(Permission.ADMIN) and 
            current_user.role_id == role_id):
            return jsonify({
                'success': False,
                'message': 'Cannot modify your own Administrator role'
            }), 403
        
        data = request.get_json()
        
        # Check if name change would conflict with existing role
        if 'name' in data and data['name'] != role.name:
            existing_role = Role.query.filter_by(name=data['name']).first()
            if existing_role and existing_role.id != role_id:
                return jsonify({
                    'success': False,
                    'message': 'Role name already exists'
                }), 400
                
        # If applying a template
        if 'template_key' in data and data['template_key']:
            from utils.role_templates import RoleTemplate
            template = RoleTemplate.get_template(data['template_key'])
            
            if template:
                # Use template values but allow explicit overrides
                if 'permissions' not in data:
                    data['permissions'] = template['permissions']
                if 'description' not in data:
                    data['description'] = template['description']
                if 'default' not in data:
                    data['default'] = template['default']
        
        # Store original values for audit log
        original_name = role.name
        original_permissions = role.get_permissions()
        
        # Update role attributes if provided
        if 'name' in data:
            role.name = data['name']
        if 'permissions' in data:
            role.permissions = data['permissions']
        if 'description' in data:
            role.description = data['description']
        if 'default' in data:
            # If setting this role as default, unset any other default roles
            if data['default'] and not role.default:
                existing_default = Role.query.filter_by(default=True).all()
                for other_role in existing_default:
                    other_role.default = False
            role.default = data['default']
        
        db.session.commit()
        
        # Get updated permission names for logging
        updated_permissions = role.get_permissions()
        
        # Prepare audit message
        if original_name != role.name:
            change_desc = f"Renamed role from '{original_name}' to '{role.name}'"
        else:
            change_desc = f"Updated role: {role.name}"
        
        if set(original_permissions) != set(updated_permissions):
            removed = set(original_permissions) - set(updated_permissions)
            added = set(updated_permissions) - set(original_permissions)
            
            if removed:
                change_desc += f", removed permissions: {', '.join(removed)}"
            if added:
                change_desc += f", added permissions: {', '.join(added)}"
        
        # Log the role update
        log_audit_event(
            category=AuditCategory.DATA_MODIFICATION,
            action=change_desc,
            severity=AuditSeverity.INFO,
            user_id=current_user.id,
            resource_id=str(role_id),
            resource_type='role'
        )
        
        return jsonify({
            'success': True,
            'message': 'Role updated successfully',
            'role': {
                'id': role.id,
                'name': role.name,
                'permissions': role.permissions,
                'description': role.description,
                'default': role.default
            }
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating role {role_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error updating role: {str(e)}"
        }), 500

@bp.route('/roles/<int:role_id>', methods=['DELETE'])
@login_required
@permission_required(Permission.MANAGE_ROLES)
@secure_endpoint(limit="5/minute")
def delete_role(role_id):
    """Delete a role."""
    try:
        role = Role.query.get_or_404(role_id)
        
        # Prevent deleting default roles
        if role.is_default:
            return jsonify({
                'success': False,
                'message': 'Cannot delete default roles'
            }), 403
        
        # Check if role is assigned to users
        users_with_role = User.query.filter_by(role_id=role_id).count()
        if users_with_role > 0:
            return jsonify({
                'success': False,
                'message': f'Cannot delete role assigned to {users_with_role} users'
            }), 400
        
        # Delete the role
        db.session.delete(role)
        db.session.commit()
        
        # Log the role deletion
        log_audit_event(
            category=AuditCategory.DATA_MODIFICATION,
            action="Deleted role",
            severity=AuditSeverity.INFO,
            user_id=current_user.id,
            resource_id=str(role_id),
            resource_type='role',
            details={
                'name': role.name
            }
        )
        
        return jsonify({
            'success': True,
            'message': 'Role deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting role {role_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error deleting role: {str(e)}"
        }), 500

@bp.route('/permissions', methods=['GET'])
@login_required
@permission_required(Permission.MANAGE_ROLES)
@ajax_csrf_protect
def get_permissions():
    """Get all available permissions."""
    try:
        # Get all permission names and values
        permissions = {name: value for name, value in vars(Permission).items() 
                      if not name.startswith('__') and isinstance(value, int)}
        
        # Log the access
        log_audit_event(
            category=AuditCategory.DATA_ACCESS,
            action="Viewed permissions list",
            severity=AuditSeverity.INFO,
            user_id=current_user.id
        )
        
        return jsonify({
            'success': True,
            'permissions': permissions
        })
    except Exception as e:
        current_app.logger.error(f"Error retrieving permissions: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error retrieving permissions: {str(e)}"
        }), 500

@bp.route('/users/bulk-import', methods=['POST'])
@login_required
@permission_required(Permission.MANAGE_USERS)
@secure_endpoint(limit="2/minute")
def bulk_import_users():
    """Bulk import users from JSON data."""
    try:
        if not request.is_json:
            return jsonify({
                'success': False,
                'message': 'Request must be JSON'
            }), 400
            
        data = request.get_json()
        users_data = data.get('users', [])
        
        if not users_data:
            return jsonify({
                'success': False,
                'message': 'No users data provided'
            }), 400
            
        results = {
            'success': [],
            'failed': []
        }
        
        for user_data in users_data:
            try:
                # Validate required fields
                if not all(k in user_data for k in ['username', 'email', 'first_name', 'last_name']):
                    results['failed'].append({
                        'data': user_data,
                        'reason': 'Missing required fields'
                    })
                    continue
                
                # Check if username already exists
                if User.query.filter_by(username=user_data['username']).first():
                    results['failed'].append({
                        'data': user_data,
                        'reason': 'Username already exists'
                    })
                    continue
                
                # Check if email already exists
                if User.query.filter_by(email=user_data['email']).first():
                    results['failed'].append({
                        'data': user_data,
                        'reason': 'Email already exists'
                    })
                    continue
                
                # Validate role if provided
                role_id = user_data.get('role_id')
                if role_id and not Role.query.get(role_id):
                    results['failed'].append({
                        'data': user_data,
                        'reason': 'Invalid role ID'
                    })
                    continue
                
                # Generate a random password
                import secrets
                import string
                temp_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
                
                # Create the user
                new_user = User(
                    username=user_data['username'],
                    email=user_data['email'],
                    password=temp_password,
                    first_name=user_data.get('first_name', ''),
                    last_name=user_data.get('last_name', ''),
                    role_id=role_id or Role.query.filter_by(name='User').first().id,
                    is_active=user_data.get('is_active', True)
                )
                
                db.session.add(new_user)
                db.session.flush()  # Get ID without committing
                
                # Add to success results
                results['success'].append({
                    'user_id': new_user.id,
                    'username': new_user.username,
                    'email': new_user.email,
                    'temp_password': temp_password
                })
                
            except Exception as e:
                results['failed'].append({
                    'data': user_data,
                    'reason': str(e)
                })
        
        # Commit all successful users at once
        if results['success']:
            db.session.commit()
            
            # Log the bulk import
            log_audit_event(
                category=AuditCategory.DATA_MODIFICATION,
                action="Bulk imported users",
                severity=AuditSeverity.INFO,
                user_id=current_user.id,
                details={
                    'success_count': len(results['success']),
                    'failed_count': len(results['failed'])
                }
            )
        else:
            db.session.rollback()
        
        return jsonify({
            'success': True,
            'message': f"Imported {len(results['success'])} users, {len(results['failed'])} failed",
            'results': results
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in bulk user import: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error importing users: {str(e)}"
        }), 500

# User Association Management Endpoints

class UserAssociationType:
    """Types of associations between users"""
    SUPERVISOR = 'supervisor'  # User is a supervisor of target
    DIRECT_REPORT = 'direct_report'  # User is a direct report of target
    PARTNER = 'partner'  # User is a partner/associate of target
    SUBSTITUTE = 'substitute'  # User can substitute for target

    @classmethod
    def all_types(cls):
        """Return all association types"""
        return [cls.SUPERVISOR, cls.DIRECT_REPORT, cls.PARTNER, cls.SUBSTITUTE]

@bp.route('/users/<int:user_id>/associations', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_USERS)
@secure_endpoint(limit="30/minute")
def list_user_associations(user_id):
    """List all associations for a user."""
    try:
        user = User.query.get_or_404(user_id)
        
        # Get associations where the user is the source
        source_assocs = UserAssociation.query.filter_by(user_id=user_id).all()
        
        # Get associations where the user is the target
        target_assocs = UserAssociation.query.filter_by(target_user_id=user_id).all()
        
        # Log the access
        log_audit_event(
            category=AuditCategory.DATA_ACCESS,
            action="Listed user associations",
            severity=AuditSeverity.INFO,
            user_id=current_user.id,
            resource_id=str(user_id),
            resource_type='user'
        )
        
        return jsonify({
            'success': True,
            'user_id': user_id,
            'username': user.username,
            'outgoing_associations': [assoc.to_dict() for assoc in source_assocs],
            'incoming_associations': [assoc.to_dict() for assoc in target_assocs]
        })
    except Exception as e:
        current_app.logger.error(f"Error listing user associations for user {user_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error retrieving user associations: {str(e)}"
        }), 500

@bp.route('/users/<int:user_id>/associations', methods=['POST'])
@login_required
@permission_required(Permission.MANAGE_USERS)
@secure_endpoint(limit="10/minute")
@validate_json_payload({
    'target_user_id': lambda v: (isinstance(v, int) and v > 0, "Target user ID must be a positive integer"),
    'association_type': lambda v: (v in UserAssociationType.all_types(), f"Association type must be one of: {', '.join(UserAssociationType.all_types())}"),
    'notes': lambda v: validate_length(v, max_length=255, required=False)
})
def create_user_association(user_id):
    """Create a new association between users."""
    try:
        data = request.get_json()
        
        # Validate users exist
        user = User.query.get_or_404(user_id)
        target_user = User.query.get_or_404(data['target_user_id'])
        
        # Prevent self-association
        if user_id == data['target_user_id']:
            return jsonify({
                'success': False,
                'message': 'Cannot create an association with yourself'
            }), 400
        
        # Check if association already exists
        existing = UserAssociation.query.filter_by(
            user_id=user_id,
            target_user_id=data['target_user_id'],
            association_type=data['association_type']
        ).first()
        
        if existing:
            return jsonify({
                'success': False,
                'message': 'Association already exists'
            }), 400
        
        # Create the association
        new_association = UserAssociation(
            user_id=user_id,
            target_user_id=data['target_user_id'],
            association_type=data['association_type'],
            notes=data.get('notes', '')
        )
        
        db.session.add(new_association)
        db.session.commit()
        
        # If creating a supervisor relationship, create the reverse direct_report relationship
        if data['association_type'] == UserAssociationType.SUPERVISOR:
            # Check if the reverse relationship already exists
            existing_reverse = UserAssociation.query.filter_by(
                user_id=data['target_user_id'],
                target_user_id=user_id,
                association_type=UserAssociationType.DIRECT_REPORT
            ).first()
            
            if not existing_reverse:
                reverse_association = UserAssociation(
                    user_id=data['target_user_id'],
                    target_user_id=user_id,
                    association_type=UserAssociationType.DIRECT_REPORT,
                    notes=f"Auto-created reverse relationship for supervisor association"
                )
                db.session.add(reverse_association)
                db.session.commit()
        
        # Similarly for direct_report, create the reverse supervisor relationship
        elif data['association_type'] == UserAssociationType.DIRECT_REPORT:
            existing_reverse = UserAssociation.query.filter_by(
                user_id=data['target_user_id'],
                target_user_id=user_id,
                association_type=UserAssociationType.SUPERVISOR
            ).first()
            
            if not existing_reverse:
                reverse_association = UserAssociation(
                    user_id=data['target_user_id'],
                    target_user_id=user_id,
                    association_type=UserAssociationType.SUPERVISOR,
                    notes=f"Auto-created reverse relationship for direct report association"
                )
                db.session.add(reverse_association)
                db.session.commit()
        
        # Log the creation
        log_audit_event(
            category=AuditCategory.DATA_MODIFICATION,
            action="Created user association",
            severity=AuditSeverity.INFO,
            user_id=current_user.id,
            resource_id=str(user_id),
            resource_type='user_association',
            details={
                'association_id': new_association.id,
                'source_user': user_id,
                'target_user': data['target_user_id'],
                'type': data['association_type']
            }
        )
        
        return jsonify({
            'success': True,
            'message': 'User association created successfully',
            'association': new_association.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating user association: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error creating user association: {str(e)}"
        }), 500

@bp.route('/users/associations/<int:association_id>', methods=['PUT'])
@login_required
@permission_required(Permission.MANAGE_USERS)
@secure_endpoint(limit="20/minute")
@validate_json_payload({
    'notes': lambda v: validate_length(v, max_length=255, required=False)
})
def update_user_association(association_id):
    """Update a user association."""
    try:
        association = UserAssociation.query.get_or_404(association_id)
        data = request.get_json()
        
        # Only notes can be updated
        if 'notes' in data:
            association.notes = data['notes']
        
        db.session.commit()
        
        # Log the update
        log_audit_event(
            category=AuditCategory.DATA_MODIFICATION,
            action="Updated user association",
            severity=AuditSeverity.INFO,
            user_id=current_user.id,
            resource_id=str(association_id),
            resource_type='user_association'
        )
        
        return jsonify({
            'success': True,
            'message': 'User association updated successfully',
            'association': association.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating user association {association_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error updating user association: {str(e)}"
        }), 500

@bp.route('/users/associations/<int:association_id>', methods=['DELETE'])
@login_required
@permission_required(Permission.MANAGE_USERS)
@secure_endpoint(limit="10/minute")
def delete_user_association(association_id):
    """Delete a user association."""
    try:
        association = UserAssociation.query.get_or_404(association_id)
        
        # Store association details for later use
        user_id = association.user_id
        target_user_id = association.target_user_id
        assoc_type = association.association_type
        
        # Delete the association
        db.session.delete(association)
        
        # If deleting a supervisor or direct_report relationship, 
        # also delete the corresponding reverse relationship
        if assoc_type in [UserAssociationType.SUPERVISOR, UserAssociationType.DIRECT_REPORT]:
            reverse_type = UserAssociationType.DIRECT_REPORT if assoc_type == UserAssociationType.SUPERVISOR else UserAssociationType.SUPERVISOR
            
            reverse_association = UserAssociation.query.filter_by(
                user_id=target_user_id,
                target_user_id=user_id,
                association_type=reverse_type
            ).first()
            
            if reverse_association:
                db.session.delete(reverse_association)
        
        db.session.commit()
        
        # Log the deletion
        log_audit_event(
            category=AuditCategory.DATA_MODIFICATION,
            action="Deleted user association",
            severity=AuditSeverity.INFO,
            user_id=current_user.id,
            resource_id=str(association_id),
            resource_type='user_association',
            details={
                'source_user': user_id,
                'target_user': target_user_id,
                'type': assoc_type
            }
        )
        
        return jsonify({
            'success': True,
            'message': 'User association deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting user association {association_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error deleting user association: {str(e)}"
        }), 500

@bp.route('/users/associations/types', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_USERS)
@ajax_csrf_protect
def get_association_types():
    """Get all available user association types."""
    try:
        types = [
            {
                'id': t, 
                'name': t.replace('_', ' ').title(),
                'description': get_association_type_description(t)
            } 
            for t in UserAssociationType.all_types()
        ]
        
        return jsonify({
            'success': True,
            'association_types': types
        })
    except Exception as e:
        current_app.logger.error(f"Error retrieving association types: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error retrieving association types: {str(e)}"
        }), 500

def get_association_type_description(assoc_type):
    """Get a description for an association type."""
    descriptions = {
        UserAssociationType.SUPERVISOR: "Indicates a supervisory relationship where the source user supervises the target user",
        UserAssociationType.DIRECT_REPORT: "Indicates that the source user reports directly to the target user",
        UserAssociationType.PARTNER: "Indicates that users work together as partners or associates",
        UserAssociationType.SUBSTITUTE: "Indicates that the source user can substitute for the target user"
    }
    return descriptions.get(assoc_type, "")

# Permission checking endpoints

@bp.route('/permissions/check', methods=['POST'])
@login_required
@secure_endpoint(limit="60/minute")
@validate_json_payload({
    'permissions': lambda v: (
        isinstance(v, list) and all(isinstance(p, int) for p in v), 
        "Permissions must be a list of integers"
    )
})
def check_permissions():
    """Check if the current user has the specified permissions."""
    try:
        data = request.get_json()
        permissions = data.get('permissions', [])
        
        if not permissions:
            return jsonify({
                'success': False,
                'message': 'No permissions specified'
            }), 400
            
        results = {}
        for permission in permissions:
            results[str(permission)] = current_user.can(permission)
            
        return jsonify({
            'success': True,
            'user_id': current_user.id,
            'username': current_user.username,
            'permissions': results
        })
    except Exception as e:
        current_app.logger.error(f"Error checking permissions: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error checking permissions: {str(e)}"
        }), 500

@bp.route('/permissions/me', methods=['GET'])
@login_required
@secure_endpoint(limit="60/minute")
def get_my_permissions():
    """Get the permissions of the current user."""
    try:
        # Get all permission constants
        all_permissions = {name: value for name, value in vars(Permission).items() 
                         if not name.startswith('__') and isinstance(value, int)}
        
        # Check which permissions the user has
        user_permissions = {}
        for name, value in all_permissions.items():
            user_permissions[name] = current_user.can(value)
            
        return jsonify({
            'success': True,
            'user_id': current_user.id,
            'username': current_user.username,
            'role': current_user.role.name if current_user.role else None,
            'permissions': user_permissions
        })
    except Exception as e:
        current_app.logger.error(f"Error getting user permissions: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error getting user permissions: {str(e)}"
        }), 500

@bp.route('/users/me', methods=['GET'])
@login_required
@secure_endpoint(limit="60/minute")
def get_current_user():
    """Get the current user's details."""
    try:
        user_data = current_user.to_dict()
        
        # Add role information
        if current_user.role:
            user_data['role'] = current_user.role.to_dict()
            
        return jsonify({
            'success': True,
            'user': user_data
        })
    except Exception as e:
        current_app.logger.error(f"Error getting current user details: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error getting user details: {str(e)}"
        }), 500
