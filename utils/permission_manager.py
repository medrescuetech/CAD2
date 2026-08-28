from models import User, Role, Permission
from extensions import db

class PermissionManager:
    """Manages user and role permissions in the system."""

    @staticmethod
    def update_user_permissions(user_id, permissions):
        """Update a user's permissions.
        
        Args:
            user_id: The ID of the user to update
            permissions: List of Permission flags to assign
        """
        user = User.query.get_or_404(user_id)
        
        # Calculate the total permission value
        permission_value = 0
        for perm in permissions:
            permission_value |= perm
        
        # Create or update custom role for the user
        role_name = f"Custom_{user.username}"
        role = Role.query.filter_by(name=role_name).first()
        
        if role is None:
            role = Role(name=role_name, permissions=permission_value)
        else:
            role.permissions = permission_value
        
        db.session.add(role)
        user.role_id = role.id
        db.session.commit()

    @staticmethod
    def get_user_permissions(user_id):
        """Get a user's current permissions.
        
        Args:
            user_id: The ID of the user
            
        Returns:
            List of Permission flags that the user has
        """
        user = User.query.get_or_404(user_id)
        if not user.role_info:
            return []
        
        permissions = []
        for perm in Permission.__members__.values():
            if user.can(perm):
                permissions.append(perm)
        
        return permissions

    @staticmethod
    def check_permission(user_id, permission):
        """Check if a user has a specific permission.
        
        Args:
            user_id: The ID of the user
            permission: The Permission flag to check
            
        Returns:
            bool: True if the user has the permission, False otherwise
        """
        user = User.query.get_or_404(user_id)
        return user.can(permission)
