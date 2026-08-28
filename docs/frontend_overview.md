# CAD System Frontend Overview

## Core Features

### 1. Incident Management
- **New Incident Form**
  - Auto-generated case number format: INC-YYYYMMDD-XXXX
  - Auto-generated timestamp in local time
  - Required fields:
    - Caller name (text input, Alt+C)
    - Location (typeahead search with new location option, Alt+L)
    - Problem (text input)
    - Priority (dropdown: HIGH/MEDIUM/LOW)
    - Pickup point (dropdown from predefined list, Alt+P)
  - Optional fields:
    - Callback number (tel input, Alt+B)
    - Description (textarea, Alt+D)
  - Status tracking:
    - PENDING (default, no units assigned)
    - OPEN (automatically when unit assigned)
    - CLOSED (manually from incidents view/dashboard)
  - Auto-saves:
    - Every 30 seconds
    - On significant changes (status, priority, problem, location, units)
    - When save button clicked
  - Buttons:
    - Save (Ctrl+S)
    - Save & Exit (Ctrl+Enter)
    - Export PDF (Ctrl+P)
  - Cannot edit closed incidents
  - Opens in new window
  - Standardized button naming

- **Unit Management Panel**
  - Table display showing:
    - Unit name
    - Type
    - Current status
    - Action buttons
  - Status options:
    - AVAILABLE
    - MEAL_BREAK
    - OUT_OF_SERVICE
    - EN_ROUTE
    - ARRIVED
    - LOADED
    - AT_MEDICAL_CENTRE
    - PATROL
    - RETURNING
  - Actions:
    - Assign unit
    - Update status (with optional note)
    - Remove unit
  - Status changes automatically logged
  - Real-time updates via WebSocket

- **Quick Notes Section**
  - One-line text input (Alt+N)
  - Add Note button
  - Notes appear in live log
  - Auto-saves on entry

- **Live Log Panel**
  - Real-time updates
  - Chronological display (newest first)
  - Entry types with color coding:
    - Status changes (green)
    - Field updates (blue)
    - Quick notes (blue)
    - Unit assignments (green)
    - Warnings (yellow)
    - Errors (red)
  - Format: "timestamp - type - message"
  - Included in PDF export
  - Auto-scrolls to new entries
  - Preserves scroll position when viewing history

### 2. Daily Log
- **Entry Management**
  - One-line text entry with enter key support
  - User and timestamp tracking
  - Log type selection:
    - General (default)
    - Radio Message
    - Security
    - Emergency
    - Traffic
    - Patrol
    - Medical
    - Administrative
    - Report
    - Incident
  - Format: "timestamp - log type - text entry - user name"
  - Auto-save on new entries
  - Stored as text file
  - Option to continue existing log or start new
  - Auto-reloads in overview tab

### 3. Medical Incidents
- **Medical Protocol Dialog**
  - Built-in AMPDS API key: "YOUR_AMPDS_API_KEY_HERE"
  - AMPDS category selection
  - Sub-category details
  - Card number display
  - Priority assignment
  - Pre-arrival instructions
  - Feeds back to incident log
  - Opens in separate window
  - Auto-populates incident priority

### 4. User Interface Elements

#### Navigation
- Responsive top navigation bar
- Quick access to key functions
- Permission-based menu items

#### Dashboards
- **Monitor View**
  - Active incidents grid
  - Unit status overview
  - Quick action buttons
  - Real-time updates via WebSocket

- **Incident List**
  - Sortable by:
    - Case number
    - Date/time
    - Status
  - Filter options
  - Export capabilities

#### Forms and Modals
- **Common Elements**
  - Consistent styling
  - Validation feedback
  - Required field indicators
  - Save/cancel buttons
  - Auto-save indicators

- **Status Updates**
  - Modal dialogs
  - Optional notes field
  - Confirmation messages

### 5. Real-time Features
- WebSocket connections for live updates
- Automatic refresh of incident lists
- Status change broadcasts
- Unit assignment notifications
- Log entry synchronization

### 6. Data Management
- **Pickup Points**
  - Managed through admin interface
  - Default pickup points:
    1. Pickup Point 1 (STANDARD)
    2. Pickup Point 2 (STANDARD)
    3. Pickup Point 3 (STANDARD)
    4. Pickup Point 4 (STANDARD)
    5. Pickup Point 5 (STANDARD)
    6. Pickup Point 6 (STANDARD)
    7. Pickup Point 7 (STANDARD)
    8. Pickup Point 8 (STANDARD)
    9. Offsite - MOU Support (OFFSITE)
    10. Offsite - ERV (OFFSITE)
    11. Other - See notes (OTHER)
    12. Offsite - FRV (OFFSITE)
    13. Offsite - Fortescue River Road (OFFSITE)
    14. Field Event (OTHER)
    15. Offsite - DFES (OFFSITE)
    16. Pickup Point Not Listed (OTHER)
    17. Offsite - Highway (OFFSITE)
  - Categorized by type:
    - STANDARD: Regular pickup points
    - OFFSITE: External locations
    - OTHER: Special cases
  - Active/inactive status
  - Managed through admin interface
  - Used in incident form dropdown

- **Location Management**
  - Typeahead search
  - New location submission
  - Review system for new locations

### 7. Keyboard Shortcuts
- Alt+C: Focus caller name
- Alt+B: Focus callback number
- Alt+L: Focus location
- Alt+P: Focus pickup point
- Alt+D: Focus description
- Alt+N: Focus quick note
- Ctrl+S: Save
- Ctrl+Enter: Save & Exit
- Ctrl+P: Generate PDF
- Escape: Close modal

### 8. Security Features
- Permission-based access control
- CSRF protection on forms
- Secure WebSocket connections
- Session management
- Input validation and sanitization

### 9. API Integration
- **AMPDS Integration**
  - Built-in API key: "YOUR_AMPDS_API_KEY_HERE"
  - Endpoint: https://api.ampds.com/v1
  - Used for medical protocol lookup
  - Automatic card number generation
  - Priority mapping
  - Pre-arrival instruction fetching

### 10. Data Storage
- **JSON Files**
  - incidents.json
  - units.json
  - users.json
  - pickup_points.json
  - daily_logs.json (text format)
  - ampds_categories.json
  - ampds_subcategories.json
  - medical_assessments.json
  - locations.json

### 11. UI Components
- **Incident Form Layout**
  - Two-column layout for main fields
  - Full-width description field
  - Unit management panel below
  - Quick notes section
  - Live log panel at bottom
  - Sticky header with status and buttons
  - Responsive design (adjusts to screen size)
  - Minimum width: 800px
  - Maximum width: 1200px
  - Font: System default for readability
  - Colors:
    - Primary: Bootstrap primary
    - Success: Bootstrap success
    - Warning: Bootstrap warning
    - Danger: Bootstrap danger
    - Info: Bootstrap info
    - Text: Bootstrap dark
    - Background: Bootstrap light

## Technical Implementation

### Frontend Technologies
- Bootstrap for responsive design
- Custom CSS for specialized components
- JavaScript for dynamic interactions
- WebSocket for real-time updates
- CSRF tokens for security

### Data Flow
1. User actions trigger JavaScript events
2. Events handled by respective managers (IncidentManager, UnitManager)
3. API calls made to backend endpoints
4. WebSocket broadcasts updates to connected clients
5. UI updates reflect changes in real-time

### State Management
- Client-side state tracking
- Dirty form detection
- Auto-save functionality
- WebSocket connection management
- Error handling and retry logic

### Error Handling
- Form validation feedback
- API error messages
- Connection status indicators
- Retry mechanisms for failed operations
- User-friendly error messages

## Best Practices
1. Consistent naming conventions
2. Regular auto-saving
3. Real-time updates
4. Clear user feedback
5. Keyboard accessibility
6. Error prevention
7. Data validation
8. Security measures 