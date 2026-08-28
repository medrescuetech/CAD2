# CAD System User Manual for Operators

## Introduction

Welcome to the Computer-Aided Dispatch (CAD) System User Manual. This document serves as a comprehensive guide for operators who manage emergency incidents, dispatch resources, and coordinate response efforts. This manual covers all aspects of the system's functionality from login to advanced features.

## Table of Contents

1. [System Access and Login](#system-access-and-login)
2. [Dashboard Overview](#dashboard-overview)
3. [Managing Incidents](#managing-incidents)
4. [Resource Management](#resource-management)
5. [Communication Tools](#communication-tools)
6. [Maps and Location Services](#maps-and-location-services)
7. [AMPDS Integration](#ampds-integration)
8. [Reporting and Analytics](#reporting-and-analytics)
9. [System Administration](#system-administration)
10. [Troubleshooting](#troubleshooting)
11. [Keyboard Shortcuts](#keyboard-shortcuts)
12. [Glossary](#glossary)

## System Access and Login

### System Requirements

- Modern web browser (Chrome, Firefox, Edge, or Safari)
- Minimum screen resolution: 1280 x 800
- Stable internet connection

### Login Procedure

1. Open your web browser and navigate to the CAD System URL provided by your administrator.
2. Enter your username and password in the login form.
3. If two-factor authentication is enabled, you will be prompted to enter a verification code sent to your registered device.
4. Upon successful authentication, you will be directed to the main dashboard.

### Password Policies

- Passwords must be at least 12 characters long
- Must include at least one uppercase letter, one lowercase letter, one number, and one special character
- Passwords expire every 90 days
- New passwords cannot match any of your last 5 passwords

### Session Management

- Your session will automatically time out after 60 minutes of inactivity
- To manually log out, click your username in the top-right corner and select "Logout"
- For security reasons, only one active session per user is allowed

## Dashboard Overview

### Main Components

![Dashboard Overview](../static/images/manual/dashboard_overview.png)

1. **Navigation Bar**: Access different modules of the system
2. **Status Panel**: Shows system status and important alerts
3. **Active Incidents Panel**: Displays currently active incidents
4. **Resource Status Panel**: Shows the status of all resources
5. **Map View**: Geographic display of incidents and resources
6. **Recent Activity Feed**: Real-time log of system activities
7. **Quick Action Buttons**: Common tasks like creating a new incident

### Customizing Your Dashboard

1. Click the "Customize" button in the top-right corner of the dashboard
2. Drag and drop panels to rearrange them
3. Use the visibility toggles to show or hide specific panels
4. Adjust the refresh rate for real-time data
5. Click "Save Layout" to preserve your customizations

## Managing Incidents

### Creating a New Incident

1. Click the "New Incident" button on the dashboard or press `Ctrl+N`
2. Enter the incident details in the form:
   - Location (address or coordinates)
   - Incident type
   - Priority level
   - Description
3. If available, enter caller information
4. Click "Create Incident" to save

### Viewing Incident Details

1. From the Active Incidents panel, click on an incident to view its details
2. The Incident Details view includes:
   - Case number and timestamps
   - Location and map view
   - Priority and status
   - Timeline of actions taken
   - Assigned resources
   - Notes and updates

### Updating an Incident

1. From the Incident Details view, click "Edit" to modify incident information
2. Update the necessary fields
3. Add notes to document changes or new information
4. Click "Save Changes"

### Managing Incident Priority

Incidents are classified by priority levels that determine response protocols:

- **Critical**: Immediate life threat, highest priority response
- **High**: Serious situation requiring rapid response
- **Medium**: Requires attention but not immediately life-threatening
- **Low**: Routine incident, standard response protocols

To change an incident's priority:
1. Open the Incident Details view
2. Click "Change Priority"
3. Select the new priority level
4. Add a note explaining the reason for the change
5. Click "Update Priority"

### Incident Statuses

Incidents progress through various statuses:
- **New**: Just created, not yet dispatched
- **Dispatched**: Resources assigned and notified
- **En Route**: Resources traveling to the scene
- **On Scene**: Resources arrived at the incident location
- **In Progress**: Actively working the incident
- **Resolved**: Primary response completed
- **Closed**: Incident fully documented and completed

### Closing an Incident

1. Ensure all required fields are completed
2. Verify that all resources have been released
3. Add a resolution summary
4. Click "Close Incident"
5. Complete the incident review form if prompted

## Resource Management

### Resource Types

The system tracks various resource types:
- Emergency vehicles (ambulance, fire truck, police car)
- Personnel (paramedics, firefighters, police officers)
- Specialized equipment
- Facilities (hospitals, command posts)

### Resource Statuses

Resources can have the following statuses:
- **Available**: Ready for assignment
- **Assigned**: Allocated to an incident but not yet en route
- **En Route**: Traveling to an incident
- **On Scene**: At the incident location
- **Returning**: Heading back to base
- **Out of Service**: Temporarily unavailable
- **Off Duty**: Not currently working

### Assigning Resources to an Incident

1. From the Incident Details view, click "Assign Resources"
2. Use the filters to find appropriate resources:
   - Resource type
   - Current location
   - Special capabilities
   - Status
3. Select the resources to assign
4. Specify any special instructions
5. Click "Dispatch Selected Resources"

### Tracking Resource Movements

1. From the Resource Management module, select a resource
2. View the resource's current location and status on the map
3. Review the activity timeline showing status changes and assignments
4. For resources with GPS tracking, enable "Live Tracking" to see real-time updates

### Managing Resource Availability

1. From the Resource Management module, select a resource
2. Click "Change Status"
3. Select the new status and provide a reason
4. If setting to "Out of Service," specify an estimated return time
5. Click "Update Status"

## Communication Tools

### Internal Messaging

1. Click the "Messages" icon in the navigation bar
2. Select "New Message"
3. Choose recipients from the user directory
4. Enter a subject and message
5. Add attachments if needed
6. Click "Send"

### Real-time Chat

The system provides real-time chat for immediate communication:
1. Click the "Chat" icon in the navigation bar
2. Select an existing conversation or start a new one
3. Enter your message and press Enter to send
4. Use the formatting tools for emphasis and clarity
5. Share images or files by clicking the attachment icon

### Email Notifications

Configure which events trigger email notifications:
1. Go to your user settings
2. Select the "Notifications" tab
3. Choose which events should generate emails:
   - New incidents
   - High-priority incidents
   - Status changes
   - Resource assignments
   - System alerts
4. Specify delivery options (immediate or digest)
5. Click "Save Preferences"

### Broadcast Alerts

For urgent communications to all users:
1. Click "Broadcast" in the communication panel
2. Enter your message
3. Select the urgency level
4. Choose delivery methods (system message, email, SMS)
5. Click "Send Broadcast"

## Maps and Location Services

### Map Navigation

1. Pan the map by clicking and dragging
2. Zoom in or out using the scroll wheel or zoom controls
3. Switch between map layers using the layer selector
4. Toggle resource and incident visibility using the display filters

### Finding Locations

1. Click the "Search" button on the map
2. Enter an address, landmark, or coordinates
3. Select from the suggested results
4. The map will center on the selected location

### Measuring Distances

1. Click the "Measure" tool on the map
2. Click on the starting point
3. Click on subsequent points to measure segments
4. Double-click to complete the measurement
5. The total distance will be displayed

### Geofencing

Create geographic boundaries for alerts:
1. Click "Geofence" on the map toolbar
2. Draw a polygon by clicking points on the map
3. Double-click to complete the polygon
4. Enter a name and description for the geofence
5. Specify alert conditions (resources entering/leaving, incidents)
6. Click "Save Geofence"

### Route Planning

1. Select a resource on the map
2. Click "Plan Route"
3. Enter or select the destination
4. Choose routing options (fastest, shortest, avoid areas)
5. Click "Calculate Route"
6. Review the suggested route and ETA
7. Click "Dispatch" to send the route to the resource

## AMPDS Integration

### Processing AMPDS Calls

1. AMPDS data will automatically populate when integrated with the phone system
2. Review the call information and dispatch details
3. Verify the determinant code and assigned priority
4. Adjust incident details if necessary
5. Confirm the recommended resource assignments
6. Click "Accept and Create Incident"

### AMPDS Codes and Protocols

Access the AMPDS reference guide:
1. Click "AMPDS Protocols" in the Resources menu
2. Search by protocol number, keyword, or chief complaint
3. View the detailed protocol information
4. Use the suggested questions and post-dispatch instructions

### Determinant Code Mapping

Understanding how AMPDS codes map to system priorities and resource assignments:
1. Chief complaints are categorized into Protocol sections (1-33)
2. Each complaint is assigned a code (A/B/C/D/E) indicating severity
3. The system automatically maps these codes to incident types and priorities
4. Protocol changes are indicated in the AMPDS Version field

## Reporting and Analytics

### Standard Reports

Access pre-configured reports:
1. Go to the Reporting module
2. Select a report category:
   - Incident Statistics
   - Resource Utilization
   - Response Times
   - Call Volume
   - Operator Performance
3. Choose a report from the list
4. Set the date range and filters
5. Click "Generate Report"

### Custom Reports

Create your own reports:
1. Go to the Reporting module
2. Click "Custom Report"
3. Select data fields to include
4. Define filters and sorting options
5. Choose visualization options (tables, charts, maps)
6. Save the report configuration for future use

### Exporting Data

1. Generate the desired report
2. Click the "Export" button
3. Choose the export format:
   - PDF
   - Excel
   - CSV
   - JSON
4. Select export options (include charts, raw data)
5. Click "Download"

### Scheduled Reports

Set up automatic report generation:
1. Configure a report as desired
2. Click "Schedule"
3. Select frequency (daily, weekly, monthly)
4. Choose delivery method (email, system notification)
5. Specify recipients
6. Click "Save Schedule"

## System Administration

### User Management

For users with administrative privileges:
1. Go to the Admin module
2. Select "User Management"
3. View existing users or create new ones
4. Manage user roles and permissions
5. Reset passwords if needed
6. Enable/disable two-factor authentication

### Audit Logs

Review system activity logs:
1. Go to the Admin module
2. Select "Audit Logs"
3. Filter by date, user, action type, or module
4. View detailed information about each action
5. Export logs for record-keeping

### System Settings

Configure system-wide settings:
1. Go to the Admin module
2. Select "System Settings"
3. Adjust parameters for:
   - Session timeouts
   - Password policies
   - Map defaults
   - Incident numbering
   - Integration endpoints
4. Click "Save Changes"

### Backup and Restore

Manage system data:
1. Go to the Admin module
2. Select "Backup & Restore"
3. Create a manual backup or view scheduled backups
4. Configure backup settings (frequency, retention)
5. Restore from a previous backup if needed

## Troubleshooting

### Common Issues and Solutions

**Issue**: Slow system performance
**Solution**: 
- Clear your browser cache
- Check your internet connection
- Reduce the number of open panels
- Contact IT if problem persists

**Issue**: Unable to log in
**Solution**:
- Verify credentials are correct
- Check CAPS LOCK is not enabled
- Reset password if necessary
- Contact administrator if account is locked

**Issue**: Map not displaying
**Solution**:
- Check internet connection
- Ensure location services are enabled
- Try refreshing the page
- Clear browser cache

**Issue**: Resource status not updating
**Solution**:
- Check if WebSocket connection is active
- Refresh the resource panel
- Verify the resource has proper connectivity
- Manually update if automatic updates fail

### Contacting Support

For issues not covered in this manual:
1. Click the "Help" icon in the navigation bar
2. Select "Contact Support"
3. Choose the issue category
4. Provide a detailed description
5. Attach screenshots if relevant
6. Submit the support request

### System Status Page

Check the health of system components:
1. Click the "System Status" link in the footer
2. View the status of:
   - Web Application
   - Database
   - WebSocket Server
   - Map Services
   - AMPDS Integration
   - External APIs

## Keyboard Shortcuts

Increase your efficiency with these keyboard shortcuts:

| Action | Shortcut |
|--------|----------|
| Create New Incident | Ctrl+N |
| Save Changes | Ctrl+S |
| Print Current View | Ctrl+P |
| Search | Ctrl+F |
| Refresh Data | F5 |
| Navigate to Dashboard | Alt+H |
| Navigate to Incidents | Alt+I |
| Navigate to Resources | Alt+R |
| Navigate to Map | Alt+M |
| Navigate to Reports | Alt+T |
| Open Help | F1 |
| Log Out | Alt+Q |

## Glossary

**AMPDS** - Advanced Medical Priority Dispatch System: A systematic protocol for emergency medical dispatch.

**CAD** - Computer-Aided Dispatch: The software system used to dispatch and coordinate emergency services.

**Determinant Code** - A code assigned by the AMPDS that indicates the nature and severity of a medical emergency.

**Dispatch** - The process of assigning and sending resources to an incident.

**ETA** - Estimated Time of Arrival: Projected time when a resource will arrive at a location.

**Geofence** - A virtual geographic boundary that can trigger alerts when resources enter or exit.

**Incident** - An event requiring emergency service response and management.

**MDT** - Mobile Data Terminal: A device in emergency vehicles that displays dispatch information.

**Resource** - Any asset that can be dispatched to an incident (vehicle, personnel, equipment).

**WebSocket** - Technology that enables real-time data updates without refreshing the page.
