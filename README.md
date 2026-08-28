# CAD System (Computer-Aided Dispatch)

A comprehensive Computer-Aided Dispatch (CAD) system designed for emergency services, events, and medical priority dispatch operations. Built with Flask, SQLAlchemy, Socket.IO, and modern web interfaces.

---

## 🌟 Architecture Overview

The system is designed around a three-application ecosystem operating over a shared, transactional core:

1. **CAD - Call Taker**: High-speed intake, caller/contact validation, duplicate detection, hazard/alert notifications, and routing.
2. **CAD - Event**: Venue/site-based dispatch with versioned location packs (levels, aisles, stands, grid maps), primary/secondary response rules, and lossless escalation to CAD Main.
3. **CAD Main**: Central operational dispatch console with queue management, persistent unit status monitoring, major-incident command mode, reporting, and administration.

---

## 🚀 Key Features

- **Real-Time Communication**: WebSocket-driven instant status updates for incidents and units.
- **Append-Only Chronology & Audit**: Immutable action logging for operational transparency.
- **Incident & Resource Separation**: 1:N relationship between incidents and unit responses with independent lifecycles.
- **Geospatial & Location Services**: Fixed incident/location GPS coordinate capture, pickup points, and map displays.
- **AMPDS Code Integration**: Emergency dispatch protocol lookup, search, and protocol suggestions.
- **Daily Operations Log**: Shift-wide operational logging with categorization and export.
- **Comprehensive Reporting**: PDF and CSV export for incident summaries, response times, and daily logs.
- **Role-Based Access Control (RBAC)**: Granular permission flags, API key management, and session controls.

---

## 📦 Setup & Installation

### 1. Prerequisites
- Python 3.10+
- pip

### 2. Environment Setup
Clone the repository and install dependencies:
```bash
git clone https://github.com/agillam69/CAD2.git
cd CAD2
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Configuration
Copy the example configuration:
```bash
cp .env.example .env
```
Edit `.env` as needed for your environment.

### 4. Initialize Database
```bash
python init_db.py
```

### 5. Run the Application
```bash
python run.py
```
Access the application at `http://localhost:5000`.

---

## 🧪 Testing

Run unit and integration tests:
```bash
pytest
```
For UI testing instructions, see `TESTING-UI.md`.

---

## 📚 Documentation

Detailed documentation is available in the [`docs/`](docs/) directory:
- [System Architecture](docs/system_architecture.md)
- [API Documentation](docs/api_documentation.md)
- [Database Schema](docs/DATABASE_SCHEMA.md)
- [Security Features](docs/security_features.md)
- [Permissions Reference](docs/permissions.md)
- [User Manual](docs/user_manual.md)
- [CAD Ecosystem Master Design](CAD_Ecosystem_Master_Design_and_External_Agency_Reference.md)
