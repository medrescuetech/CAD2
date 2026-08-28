"""
Role Templates Module

This module provides predefined role templates with appropriate permissions for the CAD system.
These templates can be used to initialize standard roles or as a starting point for custom roles.
"""

from models import Permission

class RoleTemplate:
    """Role template class for creating predefined roles."""
    
    @classmethod
    def get_administrator_permissions(cls):
        """Get permissions for the administrator role."""
        return Permission.ADMIN

    @classmethod
    def get_dispatcher_permissions(cls):
        """Get permissions for the dispatcher role."""
        return (
            Permission.VIEW_DASHBOARD |
            Permission.CREATE_INCIDENT |
            Permission.EDIT_INCIDENT |
            Permission.VIEW_INCIDENTS |
            Permission.CLOSE_INCIDENT |
            Permission.EXPORT_INCIDENTS |
            Permission.ADD_INCIDENT_LOGS |
            Permission.VIEW_UNITS |
            Permission.ASSIGN_UNITS |
            Permission.TRACK_UNITS |
            Permission.VIEW_UNIT_LOCATIONS |
            Permission.VIEW_LOCATIONS |
            Permission.VIEW_MAP |
            Permission.ACCESS_ROUTING |
            Permission.VIEW_PICKUP_POINTS |
            Permission.VIEW_AMPDS |
            Permission.VIEW_REPORTS
        )

    @classmethod
    def get_supervisor_permissions(cls):
        """Get permissions for the supervisor role."""
        return (
            cls.get_dispatcher_permissions() |
            Permission.MANAGE_UNITS |
            Permission.MANAGE_USERS |
            Permission.VIEW_ROLES |
            Permission.EXPORT_DATA |
            Permission.IMPORT_DATA |
            Permission.MANAGE_AMPDS |
            Permission.MANAGE_REPORTS |
            Permission.API_ACCESS
        )

    @classmethod
    def get_readonly_permissions(cls):
        """Get permissions for the read-only role."""
        return (
            Permission.VIEW_DASHBOARD |
            Permission.VIEW_INCIDENTS |
            Permission.VIEW_UNITS |
            Permission.VIEW_UNIT_LOCATIONS |
            Permission.VIEW_LOCATIONS |
            Permission.VIEW_MAP |
            Permission.VIEW_PICKUP_POINTS |
            Permission.VIEW_AMPDS |
            Permission.VIEW_REPORTS
        )
        
    @classmethod
    def get_api_user_permissions(cls):
        """Get permissions for the API user role."""
        return (
            Permission.ACCESS_API |
            Permission.API_ACCESS |
            Permission.VIEW_INCIDENTS |
            Permission.VIEW_UNITS
        )

    @classmethod
    def get_analytics_permissions(cls):
        """Get permissions for the analytics role."""
        return (
            Permission.VIEW_DASHBOARD |
            Permission.VIEW_INCIDENTS |
            Permission.VIEW_UNITS |
            Permission.VIEW_REPORTS |
            Permission.EXPORT_DATA |
            Permission.MANAGE_REPORTS
        )

    @classmethod
    def get_template_dict(cls):
        """Get a dictionary of all available role templates."""
        return {
            'administrator': {
                'name': 'Administrator',
                'permissions': cls.get_administrator_permissions(),
                'description': 'Full administrative access to all system features',
                'default': False
            },
            'supervisor': {
                'name': 'Supervisor',
                'permissions': cls.get_supervisor_permissions(),
                'description': 'Manages dispatchers and has access to most system features',
                'default': False
            },
            'dispatcher': {
                'name': 'Dispatcher',
                'permissions': cls.get_dispatcher_permissions(),
                'description': 'Creates and manages incidents and unit assignments',
                'default': True
            },
            'readonly': {
                'name': 'Read Only',
                'permissions': cls.get_readonly_permissions(),
                'description': 'View-only access to system data',
                'default': False
            },
            'api_user': {
                'name': 'API User',
                'permissions': cls.get_api_user_permissions(),
                'description': 'Limited access for external API integrations',
                'default': False
            },
            'analytics': {
                'name': 'Analytics',
                'permissions': cls.get_analytics_permissions(),
                'description': 'Access to reporting and data analysis features',
                'default': False
            }
        }

    @classmethod
    def get_all_templates(cls):
        """Get a list of all available role templates."""
        templates = cls.get_template_dict()
        return [
            {
                'key': key,
                'name': value['name'],
                'permissions': value['permissions'],
                'description': value['description'],
                'default': value['default']
            }
            for key, value in templates.items()
        ]

    @classmethod
    def get_template(cls, template_name):
        """Get a specific role template by name."""
        templates = cls.get_template_dict()
        template = templates.get(template_name.lower())
        if not template:
            return None
        
        return {
            'name': template['name'],
            'permissions': template['permissions'],
            'description': template['description'],
            'default': template['default']
        }
