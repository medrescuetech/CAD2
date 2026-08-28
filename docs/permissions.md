# CAD System Permissions Documentation

This document outlines all available permissions in the CAD system and what they allow users to do.

## Permission Overview

### Incident Management

- `VIEW_INCIDENTS`: View incident list and details
  - Access to incident list page
  - View individual incident details
  - View incident history and status
  - Access to incident reports and summaries

- `MANAGE_INCIDENTS`: Full incident management capabilities
  - Create new incidents
  - Edit incident details and status
  - Delete or archive incidents
  - Manage incident assignments
  - Configure incident settings
  - All incident-related operations

### Unit Management

- `VIEW_UNITS`: View unit list and details
  - Access to unit list page
  - View unit status and details
  - View unit assignments and history
  - Monitor unit locations

- `MANAGE_UNITS`: Full unit management capabilities
  - Create and edit units
  - Update unit status
  - Assign units to incidents
  - Configure unit settings
  - Manage unit availability
  - All unit-related operations

### Daily Log Management

- `VIEW_DAILY_LOG`: Access daily logs
  - View daily log entries
  - Search and filter logs
  - Export daily log reports
  - Access historical logs

- `MANAGE_DAILY_LOG`: Full daily log management
  - Create new log entries
  - Edit existing entries
  - Delete log entries
  - Configure log settings
  - Manage log categories
  - All daily log operations

### Pickup Point Management

- `VIEW_PICKUP_POINTS`: View pickup points
  - Access pickup point list
  - View point details and status
  - View location information
  - Access point history

- `MANAGE_PICKUP_POINTS`: Full pickup point management
  - Create new pickup points
  - Edit point details
  - Delete pickup points
  - Configure point settings
  - Manage point categories
  - All pickup point operations

### Report Management

- `VIEW_REPORTS`: Access system reports
  - View generated reports
  - Access report templates
  - View report history
  - Export report data

- `MANAGE_REPORTS`: Full report management
  - Create custom reports
  - Edit report templates
  - Delete reports
  - Configure report settings
  - Schedule automated reports
  - All report-related operations

### User Management

- `MANAGE_USERS`: User administration
  - Create new user accounts
  - Edit user details
  - Deactivate users
  - Reset user passwords
  - Manage user settings
  - All user-related operations

- `MANAGE_ROLES`: Role administration
  - Create new roles
  - Edit role permissions
  - Delete custom roles
  - Assign roles to users
  - All role-related operations

### System Logs

- `VIEW_SYSTEM_LOGS`: Access system logs
  - View system activity logs
  - Search and filter logs
  - View error logs
  - Access audit trails

- `EXPORT_SYSTEM_LOGS`: Export system logs
  - Export logs to various formats
  - Generate log reports
  - Schedule automated exports
  - Configure export settings

### Administrator

- `ADMIN`: Full system access
  - All permissions combined
  - System configuration access
  - Advanced settings management
  - Complete system control

## Default User Permissions

New users are automatically granted these basic permissions:
- `VIEW_INCIDENTS`
- `VIEW_UNITS`
- `VIEW_DAILY_LOG`
- `VIEW_PICKUP_POINTS`

## Permission Notes

1. Permissions are independent and do not automatically inherit.
2. The `ADMIN` permission grants all available permissions.
3. `MANAGE` permissions include the ability to perform all operations within their scope.
4. `VIEW` permissions are typically required for basic access to features.
5. Some features may require multiple permissions to access all functionality.

## Security Best Practices

1. Follow the principle of least privilege - only grant permissions that are necessary.
2. Regularly review user permissions and roles.
3. Use roles to manage groups of permissions instead of individual permissions.
4. Monitor and audit permission changes through system logs.
5. Remove unnecessary permissions when user roles change.

For questions about permissions or to request changes, contact your system administrator.
