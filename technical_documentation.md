# CAD System Technical Documentation

## System Overview
The CAD (Computer-Aided Dispatch) system is a Flask-based web application designed for managing dispatch operations, incident tracking, and administrative tasks.

## System Architecture

### Core Components
1. **Application Core**
   - `app.py`: Main application entry point
   - `config.py`: Configuration management
   - `models.py`: Database models
   - `wsgi.py`: WSGI application entry point

2. **Modules**
   - `admin/`: Administrative functionality
   - `routes/`: URL routing and request handling
   - `store.py`: Data storage operations

3. **Frontend**
   - `templates/`: Jinja2 HTML templates
   - `static/`: Static assets (CSS, JS, images)

4. **Data Management**
   - `data/`: Application data storage
   - `migrations/`: Database migration scripts
   - `init_db.py`: Database initialization
   - `migrate_to_sqlite.py`: Database migration utility

### Key Features
1. **Incident Management**
   - Incident creation and tracking
   - Real-time monitoring
   - Daily logging system

2. **Location Services**
   - Map integration
   - Pickup points management
   - Unit tracking

3. **Administrative Tools**
   - User management
   - Role-based access control
   - System settings
   - System logs
   - Report generation

4. **Monitoring and Reporting**
   - Real-time monitoring dashboard
   - Custom report generation
   - System health monitoring

## Technical Stack

### Backend
- **Framework**: Flask (Python)
- **Database**: SQLite
- **Session Management**: Flask-Session
- **Authentication**: Custom implementation

### Frontend
- **Template Engine**: Jinja2
- **CSS Framework**: Bootstrap
- **JavaScript**: Vanilla JS with modern ES6+ features

### Development Tools
- **Testing**: pytest
- **Task Runner**: nox
- **Code Coverage**: coverage.py

## Directory Structure
```
cad_system/
├── app.py                 # Main application file
├── config/               # Configuration files
├── modules/              # Core application modules
│   ├── admin/           # Admin module
│   ├── routes/          # Route handlers
│   └── store.py         # Data storage operations
├── templates/            # HTML templates
├── static/              # Static files
├── data/                # Application data
├── docs/                # Documentation
├── tests/               # Test suite
└── tools/               # Utility scripts
```

## Configuration
The system uses a layered configuration approach:
- `config.ini`: Main configuration file
- `.env`: Environment-specific settings
- `config.py`: Configuration loading and management

## Security Features
1. Role-based access control
2. Session management
3. Secure password handling
4. Input validation


## Testing
- Comprehensive test suite using pytest
- UI validation tests
- Page rendering tests
- non-API endpoint tests

## Deployment
The application can be deployed using:
1. WSGI server (Gunicorn/uWSGI)
2. Docker container
3. Direct Python execution (development only)

## Maintenance
Regular maintenance tasks include:
1. Database cleanup (`cleanup_locks.py`)
2. Log rotation
3. Backup management
4. System monitoring

## Backup and Recovery
- Regular automated backups
- Template versioning
- Data export capabilities
- Recovery procedures

## Error Handling
- Custom error pages
- Detailed logging
- Error reporting system
- Incident tracking

## Performance Considerations
1. Database optimization
2. Caching strategies
3. Asset optimization
4. Query optimization

## Future Improvements
1. Real-time notifications
2. Enhanced reporting
3. Mobile application integration
4. non-API expansion

## Support and Contact
For technical support and system maintenance, contact the system administrator.
