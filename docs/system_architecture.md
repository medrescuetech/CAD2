# CAD System Architecture Documentation

## Table of Contents
1. [System Overview](#system-overview)
2. [Architecture](#architecture)
   - [Backend](#backend)
   - [Frontend](#frontend)
   - [Data Layer](#data-layer)
3. [Core Components](#core-components)
4. [Security Model](#security-model)
5. [Deployment](#deployment)
6. [Development Setup](#development-setup)
7. [API Documentation](#api-documentation)
8. [Testing Strategy](#testing-strategy)
9. [Monitoring & Logging](#monitoring--logging)
10. [Future Improvements](#future-improvements)

## System Overview

The Computer-Aided Dispatch (CAD) system is a comprehensive web application designed for emergency service dispatch operations. It provides real-time incident management, resource allocation, and communication capabilities for emergency responders and dispatchers.

## Architecture

### Backend

#### Framework & Dependencies
- **Core**: Python 3.11+, Flask 2.3.3
- **Database**: SQLAlchemy 2.0.21 with PostgreSQL/MySQL/SQLite
- **Authentication**: Flask-Login, Flask-JWT-Extended
- **Real-time**: Flask-SocketIO 5.3.4
- **Background Tasks**: Celery with Redis/RabbitMQ
- **API**: RESTful endpoints with JSON:API specification

#### Key Components
1. **Application Factory** (`app.py`)
   - Central configuration management
   - Extension initialization
   - Blueprint registration
   - Error handling setup

2. **Models** (`models.py`)
   - User management (Users, Roles, Permissions)
   - Incident management (Incidents, Logs, Types)
   - Resource management (Units, Locations, Assignments)
   - Operational (Daily Logs, Audit Trails)

3. **Blueprints**
   - `auth/`: Authentication and user management
   - `api/`: REST API endpoints
   - `admin/`: Administrative functions
   - `incidents/`: Incident management
   - `units/`: Unit/resource management

### Frontend

#### Technologies
- **Templating**: Jinja2
- **Styling**: CSS3 with responsive design
- **JavaScript**: Vanilla JS with modular architecture
- **Maps**: Integration with mapping service (e.g., Mapbox/Google Maps)
- **Real-time**: Socket.IO client

#### Key Features
- Interactive incident map
- Real-time status updates
- Role-based dashboards
- Responsive design for mobile/desktop
- Form validation and submission

### Data Layer

#### Database Schema
- **Users & Authentication**
  - Users, Roles, Permissions
  - Session management
  - Audit logs

- **Incident Management**
  - Incidents with status tracking
  - Incident types and priorities
  - Logs and updates

- **Resource Management**
  - Units and equipment
  - Locations and geofencing
  - Assignments and status tracking

#### Data Flow
1. Client makes HTTP/WebSocket request
2. Request passes through middleware (auth, rate limiting)
3. Route handler processes request
4. Business logic in service layer
5. Data access via repository pattern
6. Response returned to client

## Security Model

### Authentication
- Session-based auth for web interface
- JWT for API access
- Password policies and hashing
- Account lockout after failed attempts

### Authorization
- Role-based access control (RBAC)
- Fine-grained permissions
- Data-level security

### Data Protection
- CSRF protection
- Input validation and sanitization
- Rate limiting
- Secure headers (CSP, HSTS, etc.)

## Deployment

### Requirements
- Python 3.11+
- Database (PostgreSQL recommended)
- Redis (for caching and WebSocket)
- Web server (Nginx/Apache)
- WSGI server (Gunicorn/uWSGI)

### Environment Variables
```
FLASK_APP=run.py
FLASK_ENV=production
SECRET_KEY=your-secret-key
DATABASE_URL=postgresql://user:pass@localhost/dbname
REDIS_URL=redis://localhost:6379/0
MAIL_SERVER=smtp.example.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=user@example.com
MAIL_PASSWORD=password
```

## Development Setup

1. Clone the repository
2. Create and activate virtual environment
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: .\venv\Scripts\activate
   ```
3. Install dependencies
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```
4. Set up environment variables (create `.env` file)
5. Initialize database
   ```bash
   flask db upgrade
   flask init-db
   ```
6. Run development server
   ```bash
   flask run
   ```

## API Documentation

### Authentication
```http
POST /api/auth/login
Content-Type: application/json

{
  "username": "user@example.com",
  "password": "securepassword"
}
```

### Incidents
- `GET /api/incidents` - List incidents
- `POST /api/incidents` - Create new incident
- `GET /api/incidents/<id>` - Get incident details
- `PUT /api/incidents/<id>` - Update incident
- `DELETE /api/incidents/<id>` - Delete incident

## Testing Strategy

### Unit Tests
- Test individual components in isolation
- Mock external dependencies
- Focus on business logic

### Integration Tests
- Test component interactions
- Database operations
- API endpoints

### E2E Tests
- User workflows
- Browser automation (Selenium/Playwright)
- Real-world scenarios

## Monitoring & Logging

### Logging
- Structured JSON logging
- Log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Centralized log management (ELK Stack)

### Monitoring
- Application metrics (Prometheus)
- Uptime monitoring
- Performance metrics
- Error tracking (Sentry)

## Future Improvements

### Technical Debt
- [ ] Refactor legacy code
- [ ] Improve test coverage
- [ ] Update dependencies

### Features
- Mobile application
- Advanced reporting
- AI/ML for incident prediction
- Enhanced mapping capabilities

### Performance
- Implement caching
- Database optimization
- Frontend performance improvements

### Security
- Regular security audits
- Dependency updates
- Enhanced authentication (MFA, SSO)
