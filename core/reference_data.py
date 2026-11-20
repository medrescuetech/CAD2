"""Seed controlled dictionaries for the CAD ecosystem core (Appendix A-C)."""
import json
from datetime import datetime

from extensions import db
from core.models import CodeSet, CodeSetEntry


REFERENCE_DATA = {
    'incident_status': {
        'name': 'Incident statuses',
        'entries': [
            ('NEW', 'New', 0), ('PENDING', 'Pending', 10),
            ('HELD', 'Held', 20), ('ASSIGNED', 'Assigned', 30),
            ('ACTIVE', 'Active', 40), ('AWAITING_CLOSURE', 'Awaiting closure', 50),
            ('CLOSED', 'Closed', 60), ('CANCELLED', 'Cancelled', 70),
            ('DUPLICATE_CANCELLED', 'Cancelled as duplicate', 80),
            ('SCHEDULED', 'Scheduled', 90),
        ],
    },
    'response_status': {
        'name': 'Response statuses',
        'entries': [
            ('ASSIGNED', 'Assigned', 0), ('DISPATCHED', 'Dispatched', 10),
            ('ACKNOWLEDGED', 'Acknowledged', 20), ('EN_ROUTE', 'En route', 30),
            ('ARRIVED_SCENE', 'Arrived scene', 40),
            ('DEPARTED_SCENE', 'Departed scene', 50),
            ('ARRIVED_DESTINATION', 'Arrived destination', 60),
            ('CLEAR', 'Clear', 70), ('CANCELLED', 'Cancelled', 80),
            ('DEALLOCATED', 'Deallocated', 90),
        ],
    },
    'unit_status': {
        'name': 'Unit statuses',
        'entries': [
            ('available', 'Available / in service', 0),
            ('meal_break', 'Meal break / rest', 10),
            ('patrol', 'Patrol / standby / staging', 20),
            ('out_of_service', 'Out of service', 30),
            ('assigned', 'Assigned / alerted', 40),
            ('acknowledged', 'Acknowledged', 50),
            ('en_route', 'En route', 60),
            ('on_scene', 'Arrived / on scene', 70),
            ('on_scene_available', 'On scene but available', 80),
            ('departed_scene', 'Loaded / departed scene', 90),
            ('at_destination', 'At destination', 100),
            ('returning', 'Returning / return to station', 110),
            ('clear', 'Clear / in station', 120),
        ],
    },
    'priority': {
        'name': 'Operational priorities',
        'entries': [
            ('P1', 'Immediate', 10),
            ('P2', 'Urgent', 20),
            ('P3', 'Standard', 30),
            ('P4', 'Low', 40),
        ],
    },
    'outcome': {
        'name': 'Closure outcomes',
        'entries': [
            ('transported', 'Transported', 0),
            ('treated_not_transported', 'Treated, not transported', 10),
            ('not_required_before_arrival', 'Service not required before arrival', 20),
            ('not_required_after_arrival', 'Response not required after arrival', 30),
            ('not_found', 'Patient/person not found', 40),
            ('referred', 'Referred', 50),
            ('resolved_on_scene', 'Resolved on scene', 60),
            ('handed_to_agency', 'Handed to another agency', 70),
            ('false_alarm', 'False alarm', 80),
            ('cancelled', 'Cancelled', 90),
            ('duplicate', 'Duplicate', 100),
            ('information_only', 'Information only', 110),
            ('other', 'Other', 120),
        ],
    },
    'alert_category': {
        'name': 'Alert categories',
        'entries': [
            ('scene_safety', 'Violence/aggression or scene safety', 0),
            ('access_hazard', 'Access hazard', 10),
            ('clinical_requirement', 'Clinical special requirement', 20),
            ('infection', 'Infection/contamination', 30),
            ('manual_handling', 'Manual handling/complex patient', 40),
            ('dangerous_animal', 'Dangerous animal', 50),
            ('site_hazard', 'Environmental or site hazard', 60),
            ('security_restriction', 'Security restriction', 70),
            ('event_instruction', 'Event-specific instruction', 80),
            ('information_only', 'Information only', 90),
        ],
    },
    'response_role': {
        'name': 'Response roles',
        'entries': [
            ('primary', 'Primary response', 0),
            ('backup', 'Backup/support', 10),
            ('transport_leg', 'Later transport leg', 20),
            ('command', 'Command/supervision', 30),
            ('staging', 'Staging', 40),
            ('third_party', 'Third-party provider', 50),
            ('liaison', 'Agency liaison', 60),
            ('post_coverage', 'Event post coverage', 70),
        ],
    },
    'intake_source': {
        'name': 'Intake sources',
        'entries': [
            ('telephone', 'Telephone', 0), ('radio', 'Radio', 10),
            ('walkup', 'Walk-up', 20), ('electronic', 'Electronic message', 30),
            ('scheduled', 'Scheduled request', 40), ('agency', 'Other agency', 50),
        ],
    },
    'service_domain': {
        'name': 'Service domains',
        'entries': [
            ('medical', 'Medical', 0), ('fire', 'Fire', 10),
            ('rescue', 'Rescue', 20), ('security', 'Security', 30),
            ('welfare', 'Welfare', 40), ('logistics', 'Logistics', 50),
            ('other', 'Other', 60),
        ],
    },
}


def insert_defaults(session=None):
    """Create or update the controlled dictionaries. Idempotent."""
    sess = session or db.session
    for key, spec in REFERENCE_DATA.items():
        code_set = CodeSet.query.filter_by(key=key).first()
        if code_set is None:
            code_set = CodeSet(key=key, name=spec['name'])
            sess.add(code_set)
            sess.flush()
        for code, label, rank in spec['entries']:
            entry = CodeSetEntry.query.filter_by(
                code_set_id=code_set.id, code=code).first()
            if entry is None:
                entry = CodeSetEntry(code_set_id=code_set.id, code=code)
                sess.add(entry)
            entry.label = label
            entry.rank_order = rank
            entry.active = True
    sess.commit()
