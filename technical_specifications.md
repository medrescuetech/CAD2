# CAD System Technical Specifications

## Table of Contents
1. [System Overview](#system-overview)
2. [User Interface](#user-interface)
3. [Incident Management](#incident-management)
4. [Authentication and Authorization](#authentication-and-authorization)
5. [Database Schema](#database-schema)
6. [non-API Endpoints](#non-api-endpoints)

## System Overview

The Computer-Aided Dispatch (CAD) system is a web-based application designed to manage emergency response operations. It provides real-time incident tracking, unit management, and dispatch coordination capabilities.

### Technology Stack
- **Backend**: Python with Flask framework
- **Database**: SQLite with direct SQL queries
- **Frontend**: HTML5, CSS3, JavaScript
- **Authentication**: Flask-Login with role-based access control
- **Maps Integration**: Leaflet.js for map visualization

## User Interface

### Global UI Components

#### Navigation Bar
- Quick access to main functions: Incidents, Units, Map, Reports
- User profile and settings dropdown
- Real-time notifications indicator
- Active incidents counter

#### Status Bar
- System status indicator
- Connected users count
- Last sync timestamp
- Active units counter

### Theme Support
- Light and dark mode support
- High contrast mode for accessibility
- Customizable color schemes per user preference

## Incident Management

### Incident Dashboard

#### Layout
```
+------------------------+------------------+
|     Incident List     |  Incident Map   |
|                       |                 |
+------------------------+                 |
|    Incident Details   |                 |
|                       |                 |
+------------------------+-----------------+
|        Unit Status Bar                  |
+----------------------------------------+
```

#### Incident List Panel
- Real-time updating incident list
- Color-coded priority levels
- Quick filters:
  - Status (Active, Pending, Closed)
  - Priority (High, Medium, Low)
  - Type (Medical, Fire, Police)
  - Time Range
- Sorting options:
  - Creation Time
  - Priority
  - Status
  - Location
- Column customization
- Row highlighting for new/updated incidents

#### Incident Creation Form
- **Required Fields**:
  - Incident Type (dropdown)
  - Priority Level (radio buttons)
  - Location (map picker or address input)
  - Description (text area)
- **Optional Fields**:
  - Caller Information
  - Additional Resources Required
  - Special Instructions
  - Hazard Warnings
- **Validation**:
  - Real-time field validation
  - Address verification
  - Duplicate incident detection

#### Incident Details View
- **Header Section**:
  - Incident ID
  - Status Badge
  - Priority Level
  - Creation Time
  - Last Update Time
- **Location Section**:
  - Address
  - GPS Coordinates
  - Map Preview
  - Nearest Landmarks
- **Resources Section**:
  - Assigned Units
  - Available Units
  - Required Resources
  - Equipment Status
- **Timeline Section**:
  - Chronological event log
  - Status changes
  - Unit assignments
  - Notes and updates
- **Communication Log**:
  - Radio transmissions
  - Phone calls
  - Text messages
  - Email correspondence

### Real-time Updates

#### WebSocket Events
```javascript
// Event Types
const INCIDENT_EVENTS = {
    CREATED: 'incident.created',
    UPDATED: 'incident.updated',
    DELETED: 'incident.deleted',
    STATUS_CHANGED: 'incident.status_changed',
    UNIT_ASSIGNED: 'incident.unit_assigned',
    UNIT_CLEARED: 'incident.unit_cleared'
};

// Event Handlers
socket.on(INCIDENT_EVENTS.CREATED, (data) => {
    updateIncidentList(data);
    showNotification(data);
});
```

#### Update Throttling
- List updates: 1 second minimum interval
- Map updates: 2 seconds minimum interval
- Status updates: Real-time
- Batch updates for multiple changes

## Database Schema

### Incidents Table
```sql
CREATE TABLE incidents (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    priority INTEGER NOT NULL,
    status TEXT NOT NULL,
    description TEXT,
    location_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_at TEXT,
    created_by TEXT,
    FOREIGN KEY (location_id) REFERENCES locations(id),
    FOREIGN KEY (created_by) REFERENCES users(id)
);
```

### Incident Units Table
```sql
CREATE TABLE incident_units (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    unit_id TEXT NOT NULL,
    status TEXT NOT NULL,
    assigned_at TEXT NOT NULL,
    cleared_at TEXT,
    FOREIGN KEY (incident_id) REFERENCES incidents(id),
    FOREIGN KEY (unit_id) REFERENCES units(id)
);
```

### Incident Logs Table
```sql
CREATE TABLE incident_logs (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    type TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT,
    FOREIGN KEY (incident_id) REFERENCES incidents(id),
    FOREIGN KEY (created_by) REFERENCES users(id)
);
```

## Performance Considerations

### Client-Side Optimizations
1. **Data Caching**
   - Browser cache for static assets
   - LocalStorage for user preferences
   - IndexedDB for offline incident data

2. **Resource Loading**
   - Lazy loading of map tiles
   - Dynamic import of non-critical components
   - Image optimization and lazy loading

3. **State Management**
   - Optimistic UI updates
   - Debounced search inputs
   - Throttled WebSocket updates

### Server-Side Optimizations
1. **Database**
   - Indexed fields for frequent queries
   - Prepared statements
   - Connection pooling

2. **Caching**
   - In-memory cache for active incidents
   - Query result caching
   - Session data caching

3. **API**
   - Pagination for large result sets
   - Compression for response data
   - Rate limiting for API endpoints
