# Incident Template Reference

## Template Structure
- Extends: base.html
- Title: "Edit Incident" or "New Incident" - CAD System

## External Dependencies
- Leaflet CSS: `https://unpkg.com/leaflet@1.9.4/dist/leaflet.css`
- Font Awesome (via base.html)
- Bootstrap (via base.html)

## Form Components

### Main Form
```html
<form id="incidentForm" data-custom-submit="true">
```

### Left Column Fields
1. **Case Number**
   ```html
   <input type="text" 
          class="form-control" 
          id="caseNumber" 
          name="case_number" 
          readonly 
          data-label="Case Number">
   ```

2. **Created At**
   ```html
   <input type="text" 
          class="form-control" 
          id="createdAt" 
          name="created_at" 
          readonly 
          data-label="Created At">
   ```

3. **Incident Type**
   ```html
   <select class="form-select" 
           id="incidentType" 
           name="type" 
           data-label="Incident Type">
       <option value="">Select Type</option>
       <option value="MEDICAL_EMERGENCY">Medical Emergency</option>
       <option value="FIRE">Fire</option>
       <option value="TRAFFIC_ACCIDENT">Traffic Accident</option>
       <option value="PUBLIC_DISTURBANCE">Public Disturbance</option>
       <option value="CRIME_IN_PROGRESS">Crime in Progress</option>
       <option value="NATURAL_DISASTER">Natural Disaster</option>
       <option value="HAZMAT">Hazardous Materials</option>
       <option value="RESCUE">Rescue</option>
       <option value="OTHER">Other</option>
   </select>
   ```

4. **Priority**
   ```html
   <select class="form-select" 
           id="priority" 
           name="priority" 
           data-label="Priority">
       <option value="HIGH">High</option>
       <option value="MEDIUM">Medium</option>
       <option value="LOW">Low</option>
   </select>
   ```

### Right Column Fields
5. **Caller Name**
   ```html
   <input type="text" 
          class="form-control" 
          id="callerName" 
          name="caller" 
          data-label="Caller Name">
   ```

6. **Callback Number**
   ```html
   <input type="text" 
          class="form-control" 
          id="callbackNumber" 
          name="callback_number" 
          data-label="Callback Number">
   ```

7. **Location**
   ```html
   <div class="input-group">
       <input type="text" 
              class="form-control" 
              id="location" 
              name="location" 
              placeholder="Search or enter new location"
              data-label="Location">
       <button class="btn btn-outline-secondary" 
               type="button" 
               onclick="IncidentManager._handleNewLocation(document.getElementById('location').value)">
           <i class="fas fa-plus"></i> Add New
       </button>
   </div>
   ```

8. **Problem Description**
   ```html
   <textarea class="form-control" 
             id="problem" 
             name="problem_description" 
             rows="3" 
             data-label="Problem Description">
   </textarea>
   ```

9. **Pickup Point**
   ```html
   <select class="form-select" 
           id="pickupPoint" 
           name="pickup_point" 
           data-label="Pickup Point">
       <!-- Populated dynamically -->
   </select>
   ```

### Bottom Field
10. **Description**
    ```html
    <textarea class="form-control" 
              id="description" 
              name="description" 
              rows="3" 
              data-label="Description">
    </textarea>
    ```

## Status Colors
```css
.status-ACTIVE { background-color: #dc3545 }
.status-PENDING { background-color: #ffc107 }
.status-CLOSED { background-color: #6c757d }
.status-DISPATCHED { background-color: #0dcaf0 }
.status-ENROUTE { background-color: #fd7e14 }
.status-ON_SCENE { background-color: #198754 }
.status-RETURNING { background-color: #6610f2 }
.status-OUT_OF_SERVICE { background-color: #343a40 }
.status-MEAL_BREAK { background-color: #20c997 }
.status-AT_MEDICAL_CENTRE { background-color: #0d6efd }
.status-PATROL { background-color: #6f42c1 }
```

## Priority Colors
```css
.priority-HIGH { color: #dc3545 }
.priority-MEDIUM { color: #ffc107 }
.priority-LOW { color: #198754 }
```

## Live Log Styles
```css
.live-log {
    height: 400px;
    overflow-y: auto;
    padding: 10px;
    background-color: #f8f9fa;
    border-radius: 4px;
}

.log-entry {
    padding: 5px 0;
    border-bottom: 1px solid #dee2e6;
}

.log-timestamp {
    font-size: 0.85em;
    color: #6c757d;
    margin-right: 10px;
}

.log-message { color: #212529 }
.log-note { color: #0d6efd }
.log-status { color: #198754 }
.log-warning { color: #ffc107 }
.log-error { color: #dc3545 }
```

## JavaScript Functions

### IncidentManager Methods
1. `saveIncident(exitAfterSave)`
   - Saves the current incident
   - Redirects if exitAfterSave is true

2. `_handleNewLocation(locationText)`
   - Handles adding a new location to the system

3. `_handleFieldChange(event)`
   - Logs field changes to the live log
   - Updates old values

4. `updateUnitStatus(unitId, newStatus, note)`
   - Updates a unit's status
   - Logs the change

### Auto-generated Values
1. **Case Number Format**:  
   `INC-YYYYMMDD-RANDOM`
   - Example: INC-20250112-X7Y9Z2

2. **Created At Format**:  
   Local date/time string using browser's locale

## Event Listeners
1. Form fields:
   - SELECT elements: 'change' event
   - Other inputs: 'blur' event
   - All track old values with data-old-value attribute

2. Form submission:
   - Prevented default
   - Handled by IncidentManager.saveIncident()

## Live Log Features
- Scrollable container
- Timestamp for each entry
- Different styles for:
  - Field changes
  - Status updates
  - Notes
  - Warnings
  - Errors

## Location Search
- Dropdown suggestions
- Add new location button
- Search existing or add new

## Quick Notes
- Preset buttons
- Custom note input
- Note type selection
