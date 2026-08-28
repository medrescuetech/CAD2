# CAD System Database Schema

## Overview
This document describes the database schema for the CAD (Computer-Aided Dispatch) System. The system uses SQLAlchemy ORM with SQLite as the database backend.

## Core Tables

### Users and Authentication

#### users
- `id`: Primary key
- `username`: Unique username
- `email`: Unique email address
- `password_hash`: Hashed password
- `first_name`: User's first name
- `last_name`: User's last name
- `role_id`: Foreign key to roles.id
- `active`: Boolean indicating if the account is active
- `last_login`: Timestamp of last login
- `last_seen`: Timestamp when user was last active
- `created_at`: Account creation timestamp
- `updated_at`: Last update timestamp
- `session_id`: WebSocket session ID

#### roles
- `id`: Primary key
- `name`: Role name (e.g., Administrator, Dispatcher)
- `permissions`: Bitmask of permissions

#### password_history
- `id`: Primary key
- `user_id`: Foreign key to users.id
- `password_hash`: Hashed password
- `created_at`: Timestamp when password was set

### Units and Locations

#### unit_type
- `id`: Primary key
- `name`: Type name (e.g., Ambulance, Fire Engine, Police)
- `description`: Description of the unit type
- `created_at`: Creation timestamp
- `updated_at`: Last update timestamp

#### location
- `id`: Primary key
- `name`: Location name
- `address`: Full address
- `latitude`: GPS latitude
- `longitude`: GPS longitude
- `city`: City name
- `state`: State/Province code
- `postal_code`: Postal/ZIP code
- `active`: Boolean indicating if location is active

#### unit
- `id`: Primary key
- `name`: Unit identifier (e.g., AMB-101)
- `type_id`: Foreign key to unit_type.id
- `active`: Boolean indicating if unit is active
- `location_id`: Foreign key to location.id
- `status`: Current status (e.g., available, assigned)
- `created_at`: Creation timestamp
- `updated_at`: Last update timestamp

### Incidents and Dispatch

#### incident_types
- `id`: Primary key
- `name`: Incident type name (e.g., Medical Emergency)
- `description`: Description of incident type
- `default_priority`: Default priority level
- `color`: Color code for UI
- `requires_location`: Boolean
- `requires_caller`: Boolean
- `active`: Boolean

#### incidents
- `id`: Primary key
- `incident_number`: Unique incident identifier (e.g., INC-1001)
- `incident_type_id`: Foreign key to incident_types.id
- `priority`: Priority level (1-4)
- `status`: Current status (pending, open, closed)
- `location`: Text description of location
- `location_id`: External location identifier
- `latitude`: GPS latitude
- `longitude`: GPS longitude
- `caller`: Caller's name
- `callback_number`: Callback phone number
- `description`: Incident details
- `ampds_code`: AMPDS code (if applicable)
- `ampds_data`: JSON-encoded AMPDS data
- `resolution`: Resolution notes
- `created_at`: Creation timestamp
- `updated_at`: Last update timestamp
- `created_by_id`: Foreign key to users.id
- `updated_by_id`: Foreign key to users.id

#### unit_assignment
- `id`: Primary key
- `unit_id`: Foreign key to unit.id
- `incident_id`: Foreign key to incidents.id
- `status`: Assignment status (assigned, enroute, on_scene, etc.)
- `dispatched_by_id`: Foreign key to users.id
- `dispatched_at`: Dispatch timestamp
- `arrived_at`: Arrival timestamp
- `cleared_at`: Clearance timestamp
- `notes`: Additional notes
- `created_at`: Creation timestamp
- `updated_at`: Last update timestamp

#### incident_log
- `id`: Primary key
- `incident_id`: Foreign key to incidents.id
- `user_id`: Foreign key to users.id
- `message`: Log message
- `type`: Log type (info, warning, error, etc.)
- `timestamp`: Log timestamp

### Additional Features

#### pickup_point
- `id`: Primary key
- `name`: Point name
- `location`: Address
- `latitude`: GPS latitude
- `longitude`: GPS longitude
- `description`: Additional details
- `active`: Boolean
- `created_at`: Creation timestamp
- `updated_at`: Last update timestamp

#### daily_log
- `id`: Primary key
- `date`: Log date
- `shift`: Shift identifier
- `user_id`: Foreign key to users.id
- `notes`: Log notes
- `created_at`: Creation timestamp
- `updated_at`: Last update timestamp
- `is_archived`: Boolean
- `archived_at`: Archival timestamp

## Relationships

### User Relationships
- A user belongs to one role (many-to-one)
- A user can create multiple incidents (one-to-many)
- A user can update multiple incidents (one-to-many)
- A user can dispatch multiple unit assignments (one-to-many)
- A user can have multiple log entries (one-to-many)

### Unit Relationships
- A unit has one type (many-to-one)
- A unit has one current location (many-to-one)
- A unit can have multiple assignments (one-to-many)

### Incident Relationships
- An incident has one type (many-to-one)
- An incident can have multiple unit assignments (one-to-many)
- An incident can have multiple log entries (one-to-many)
- An incident is created by one user (many-to-one)
- An incident can be updated by one user (many-to-one)

## Initial Data

The database is pre-populated with the following data:

### Roles
1. Administrator (full permissions)
2. Dispatcher (incident management and unit dispatch permissions)

### Users
1. admin (admin@localhost) - Administrator role
2. dispatcher (dispatcher@localhost) - Dispatcher role

### Unit Types
1. Ambulance
2. Fire Engine
3. Police

### Locations
1. Central Station (Chicago, IL)
2. North Station (New York, NY)
3. South Station (Houston, TX)

### Units
1. AMB-101 (Ambulance at Central Station)
2. ENG-201 (Fire Engine at North Station)
3. POL-301 (Police at South Station)
