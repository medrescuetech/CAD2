"""Canonical data model for the CAD ecosystem shared core.

Implements the entities from the Ecosystem Master Design sections 7-10:
intakes, responses, event workspaces and location packs, alerts, operator
assignments/transfers, agency notifications, versioned code sets, the
append-only chronology spine and the integration outbox.
"""
import json
import uuid
from datetime import datetime

from extensions import db


def _uuid():
    return str(uuid.uuid4())


class Applications:
    """Source-application identifiers used across chronology and routing."""
    CALL_TAKER = 'CALL_TAKER'
    EVENT = 'EVENT'
    MAIN = 'MAIN'
    SYSTEM = 'SYSTEM'
    ALL = (CALL_TAKER, EVENT, MAIN, SYSTEM)


class EventWorkspace(db.Model):
    """An active event/site operating context (design section 5.2)."""
    __tablename__ = 'event_workspace'

    STATUS_DRAFT = 'DRAFT'
    STATUS_ACTIVE = 'ACTIVE'
    STATUS_SUSPENDED = 'SUSPENDED'
    STATUS_CLOSED = 'CLOSED'

    id = db.Column(db.Integer, primary_key=True)
    workspace_uuid = db.Column(db.String(36), unique=True, nullable=False, default=_uuid)
    code = db.Column(db.String(32), unique=True, nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    venue_name = db.Column(db.String(200))
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    timezone = db.Column(db.String(64), default='UTC')
    status = db.Column(db.String(20), default=STATUS_DRAFT, index=True)
    command_location = db.Column(db.String(200))
    responsible_agency = db.Column(db.String(200))
    terminology_json = db.Column(db.Text)
    config_version = db.Column(db.Integer, default=0)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    created_by = db.relationship('User', foreign_keys=[created_by_id])
    packs = db.relationship('EventLocationPack', back_populates='workspace',
                            cascade='all, delete-orphan', lazy='dynamic')
    locations = db.relationship('EventLocation', back_populates='workspace',
                                cascade='all, delete-orphan', lazy='dynamic')
    response_rules = db.relationship('EventResponseRule', back_populates='workspace',
                                     cascade='all, delete-orphan', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'workspace_uuid': self.workspace_uuid,
            'code': self.code,
            'name': self.name,
            'venue_name': self.venue_name,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'timezone': self.timezone,
            'status': self.status,
            'command_location': self.command_location,
            'responsible_agency': self.responsible_agency,
            'config_version': self.config_version,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class EventLocationPack(db.Model):
    """A versioned import of an event location register (design section 10)."""
    __tablename__ = 'event_location_pack'

    STATUS_STAGED = 'STAGED'
    STATUS_ACTIVE = 'ACTIVE'
    STATUS_RETIRED = 'RETIRED'

    id = db.Column(db.Integer, primary_key=True)
    event_workspace_id = db.Column(db.Integer, db.ForeignKey('event_workspace.id'),
                                   nullable=False, index=True)
    version = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(16), default=STATUS_STAGED, index=True)
    source_filename = db.Column(db.String(255))
    preview_stats_json = db.Column(db.Text)
    imported_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    activated_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    workspace = db.relationship('EventWorkspace', back_populates='packs')
    imported_by = db.relationship('User', foreign_keys=[imported_by_id])
    locations = db.relationship('EventLocation', back_populates='pack',
                                cascade='all, delete-orphan', lazy='dynamic')

    __table_args__ = (
        db.UniqueConstraint('event_workspace_id', 'version', name='uq_pack_version'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'event_workspace_id': self.event_workspace_id,
            'version': self.version,
            'status': self.status,
            'source_filename': self.source_filename,
            'preview_stats': json.loads(self.preview_stats_json) if self.preview_stats_json else None,
            'activated_at': self.activated_at.isoformat() if self.activated_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class EventLocation(db.Model):
    """One row of an event location pack (AO2016-derived schema, section 10.1)."""
    __tablename__ = 'event_location'

    PLACEHOLDER_VALUES = {'***', 'unknown', 'confirm location', 'not listed'}

    id = db.Column(db.Integer, primary_key=True)
    pack_id = db.Column(db.Integer, db.ForeignKey('event_location_pack.id'), index=True)
    event_workspace_id = db.Column(db.Integer, db.ForeignKey('event_workspace.id'),
                                   nullable=False, index=True)
    location_name = db.Column(db.String(200), nullable=False, index=True)
    location_key = db.Column(db.String(64), index=True)
    venue_id = db.Column(db.String(64))
    level = db.Column(db.String(64))
    aisle = db.Column(db.String(64))
    stand_or_zone = db.Column(db.String(64))
    map_reference = db.Column(db.String(64))
    alternate_reference = db.Column(db.String(64))
    other_details = db.Column(db.Text)
    response_area = db.Column(db.String(64), index=True)
    primary_responder = db.Column(db.String(128))
    secondary_responder = db.Column(db.String(128))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    active = db.Column(db.Boolean, default=True, index=True)
    needs_confirmation = db.Column(db.Boolean, default=False)
    is_fallback = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    workspace = db.relationship('EventWorkspace', back_populates='locations')
    pack = db.relationship('EventLocationPack', back_populates='locations')

    __table_args__ = (
        db.UniqueConstraint('pack_id', 'location_key', name='uq_pack_location_key'),
    )

    def is_placeholder(self):
        return (self.location_name or '').strip().lower() in self.PLACEHOLDER_VALUES

    def to_dict(self):
        return {
            'id': self.id,
            'pack_id': self.pack_id,
            'event_workspace_id': self.event_workspace_id,
            'location_name': self.location_name,
            'location_key': self.location_key,
            'venue_id': self.venue_id,
            'level': self.level,
            'aisle': self.aisle,
            'stand_or_zone': self.stand_or_zone,
            'map_reference': self.map_reference,
            'alternate_reference': self.alternate_reference,
            'other_details': self.other_details,
            'response_area': self.response_area,
            'primary_responder': self.primary_responder,
            'secondary_responder': self.secondary_responder,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'active': self.active,
            'needs_confirmation': self.needs_confirmation,
            'is_fallback': self.is_fallback,
        }


class EventResponseRule(db.Model):
    """Grid/area to primary/secondary responder mapping (design section 10.1)."""
    __tablename__ = 'event_response_rule'

    id = db.Column(db.Integer, primary_key=True)
    event_workspace_id = db.Column(db.Integer, db.ForeignKey('event_workspace.id'),
                                   nullable=False, index=True)
    pack_id = db.Column(db.Integer, db.ForeignKey('event_location_pack.id'), index=True)
    map_reference = db.Column(db.String(64))
    response_area = db.Column(db.String(64), index=True)
    primary_responder = db.Column(db.String(128))
    secondary_responder = db.Column(db.String(128))
    active = db.Column(db.Boolean, default=True)

    workspace = db.relationship('EventWorkspace', back_populates='response_rules')

    def to_dict(self):
        return {
            'id': self.id,
            'event_workspace_id': self.event_workspace_id,
            'map_reference': self.map_reference,
            'response_area': self.response_area,
            'primary_responder': self.primary_responder,
            'secondary_responder': self.secondary_responder,
            'active': self.active,
        }


class Intake(db.Model):
    """A received call/contact in CAD - Call Taker (design section 5.1)."""
    __tablename__ = 'intake'

    STATE_OPEN = 'OPEN'
    STATE_ROUTED = 'ROUTED'
    STATE_ABANDONED = 'ABANDONED'
    STATE_HOAX = 'HOAX'
    STATE_INFO_ONLY = 'INFO_ONLY'
    STATE_DUPLICATE = 'DUPLICATE'
    STATE_CANCELLED = 'CANCELLED'
    CLOSED_STATES = (STATE_ABANDONED, STATE_HOAX, STATE_INFO_ONLY,
                     STATE_DUPLICATE, STATE_CANCELLED)

    id = db.Column(db.Integer, primary_key=True)
    intake_uuid = db.Column(db.String(36), unique=True, nullable=False, default=_uuid)
    source = db.Column(db.String(32), default='telephone')
    received_at = db.Column(db.DateTime, default=datetime.utcnow)
    answered_at = db.Column(db.DateTime)
    caller_name = db.Column(db.String(200))
    callback_number = db.Column(db.String(32), index=True)
    location_text = db.Column(db.String(255))
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'))
    event_location_id = db.Column(db.Integer, db.ForeignKey('event_location.id'))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    problem_text = db.Column(db.Text)
    operator_summary = db.Column(db.Text)
    person_details_json = db.Column(db.Text)
    hazards = db.Column(db.Text)
    other_agencies = db.Column(db.String(255))
    narrative = db.Column(db.Text)
    event_workspace_id = db.Column(db.Integer, db.ForeignKey('event_workspace.id'))
    priority_code = db.Column(db.String(32))
    priority_rank = db.Column(db.Integer)
    incident_type_id = db.Column(db.Integer, db.ForeignKey('incident_types.id'))
    state = db.Column(db.String(20), default=STATE_OPEN, index=True)
    closure_reason = db.Column(db.String(64))
    routed_application = db.Column(db.String(16))
    routed_at = db.Column(db.DateTime)
    incident_id = db.Column(db.Integer, db.ForeignKey('incidents.id'), index=True)
    operator_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    row_version = db.Column(db.Integer, default=1, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    incident = db.relationship('Incident', backref=db.backref('intakes', lazy='dynamic'))
    event_workspace = db.relationship('EventWorkspace',
                                      backref=db.backref('intakes', lazy='dynamic'))
    event_location = db.relationship('EventLocation')
    location = db.relationship('Location')
    operator = db.relationship('User', foreign_keys=[operator_user_id])

    def to_dict(self):
        return {
            'id': self.id,
            'intake_uuid': self.intake_uuid,
            'source': self.source,
            'received_at': self.received_at.isoformat() if self.received_at else None,
            'answered_at': self.answered_at.isoformat() if self.answered_at else None,
            'caller_name': self.caller_name,
            'callback_number': self.callback_number,
            'location_text': self.location_text,
            'location_id': self.location_id,
            'event_location_id': self.event_location_id,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'problem_text': self.problem_text,
            'operator_summary': self.operator_summary,
            'hazards': self.hazards,
            'other_agencies': self.other_agencies,
            'narrative': self.narrative,
            'event_workspace_id': self.event_workspace_id,
            'priority_code': self.priority_code,
            'priority_rank': self.priority_rank,
            'incident_type_id': self.incident_type_id,
            'state': self.state,
            'closure_reason': self.closure_reason,
            'routed_application': self.routed_application,
            'routed_at': self.routed_at.isoformat() if self.routed_at else None,
            'incident_id': self.incident_id,
            'operator_user_id': self.operator_user_id,
            'row_version': self.row_version,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Response(db.Model):
    """One unit's response to an incident (design sections 6.2, 9.2, 12.3)."""
    __tablename__ = 'response'

    STATUS_ASSIGNED = 'ASSIGNED'
    STATUS_DISPATCHED = 'DISPATCHED'
    STATUS_ACKNOWLEDGED = 'ACKNOWLEDGED'
    STATUS_EN_ROUTE = 'EN_ROUTE'
    STATUS_ARRIVED_SCENE = 'ARRIVED_SCENE'
    STATUS_DEPARTED_SCENE = 'DEPARTED_SCENE'
    STATUS_ARRIVED_DESTINATION = 'ARRIVED_DESTINATION'
    STATUS_CLEAR = 'CLEAR'
    STATUS_CANCELLED = 'CANCELLED'
    STATUS_DEALLOCATED = 'DEALLOCATED'
    TERMINAL_STATES = (STATUS_CLEAR, STATUS_CANCELLED, STATUS_DEALLOCATED)

    PROGRESSION = {
        STATUS_ASSIGNED: (STATUS_DISPATCHED, STATUS_ACKNOWLEDGED, STATUS_CANCELLED,
                          STATUS_DEALLOCATED),
        STATUS_DISPATCHED: (STATUS_ACKNOWLEDGED, STATUS_EN_ROUTE, STATUS_CANCELLED,
                            STATUS_DEALLOCATED),
        STATUS_ACKNOWLEDGED: (STATUS_EN_ROUTE, STATUS_CANCELLED, STATUS_DEALLOCATED),
        STATUS_EN_ROUTE: (STATUS_ARRIVED_SCENE, STATUS_CANCELLED, STATUS_DEALLOCATED),
        STATUS_ARRIVED_SCENE: (STATUS_DEPARTED_SCENE, STATUS_CLEAR,
                               STATUS_DEALLOCATED),
        STATUS_DEPARTED_SCENE: (STATUS_ARRIVED_DESTINATION, STATUS_CLEAR),
        STATUS_ARRIVED_DESTINATION: (STATUS_CLEAR,),
        STATUS_CLEAR: (),
        STATUS_CANCELLED: (),
        STATUS_DEALLOCATED: (),
    }

    STATUS_TIMESTAMP = {
        STATUS_ASSIGNED: 'assigned_at',
        STATUS_DISPATCHED: 'dispatched_at',
        STATUS_ACKNOWLEDGED: 'acknowledged_at',
        STATUS_EN_ROUTE: 'enroute_at',
        STATUS_ARRIVED_SCENE: 'arrived_scene_at',
        STATUS_DEPARTED_SCENE: 'departed_scene_at',
        STATUS_ARRIVED_DESTINATION: 'arrived_destination_at',
        STATUS_CLEAR: 'cleared_at',
        STATUS_CANCELLED: 'cleared_at',
        STATUS_DEALLOCATED: 'cleared_at',
    }

    id = db.Column(db.Integer, primary_key=True)
    response_uuid = db.Column(db.String(36), unique=True, nullable=False, default=_uuid)
    incident_id = db.Column(db.Integer, db.ForeignKey('incidents.id'),
                            nullable=False, index=True)
    unit_id = db.Column(db.Integer, db.ForeignKey('unit.id'), nullable=False, index=True)
    response_role = db.Column(db.String(32), default='primary')
    sequence_no = db.Column(db.Integer, default=1)
    status = db.Column(db.String(24), default=STATUS_ASSIGNED, index=True)
    outcome = db.Column(db.String(64))
    cancellation_reason = db.Column(db.String(255))
    notes = db.Column(db.Text)
    assigned_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    dispatched_at = db.Column(db.DateTime)
    acknowledged_at = db.Column(db.DateTime)
    enroute_at = db.Column(db.DateTime)
    arrived_scene_at = db.Column(db.DateTime)
    departed_scene_at = db.Column(db.DateTime)
    arrived_destination_at = db.Column(db.DateTime)
    cleared_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    incident = db.relationship('Incident', backref=db.backref('responses', lazy='dynamic'))
    unit = db.relationship('Unit', backref=db.backref('responses', lazy='dynamic'))
    assigned_by = db.relationship('User', foreign_keys=[assigned_by_id])

    def is_active(self):
        return self.status not in self.TERMINAL_STATES

    def to_dict(self):
        return {
            'id': self.id,
            'response_uuid': self.response_uuid,
            'incident_id': self.incident_id,
            'unit_id': self.unit_id,
            'unit_name': self.unit.name if self.unit else None,
            'response_role': self.response_role,
            'sequence_no': self.sequence_no,
            'status': self.status,
            'outcome': self.outcome,
            'assigned_at': self.assigned_at.isoformat() if self.assigned_at else None,
            'dispatched_at': self.dispatched_at.isoformat() if self.dispatched_at else None,
            'acknowledged_at': self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            'enroute_at': self.enroute_at.isoformat() if self.enroute_at else None,
            'arrived_scene_at': self.arrived_scene_at.isoformat() if self.arrived_scene_at else None,
            'departed_scene_at': self.departed_scene_at.isoformat() if self.departed_scene_at else None,
            'arrived_destination_at': self.arrived_destination_at.isoformat() if self.arrived_destination_at else None,
            'cleared_at': self.cleared_at.isoformat() if self.cleared_at else None,
        }


class Alert(db.Model):
    """Scoped safety/clinical/location alert (design section 13)."""
    __tablename__ = 'alert'

    SCOPE_ADDRESS = 'ADDRESS'
    SCOPE_SUBLOCATION = 'SUBLOCATION'
    SCOPE_PERSON = 'PERSON'
    SCOPE_EVENT_LOCATION = 'EVENT_LOCATION'
    SCOPE_ZONE = 'ZONE'
    SCOPE_PERSON_LOCATION = 'PERSON_LOCATION'

    STATE_INTERIM = 'INTERIM'
    STATE_PENDING_REVIEW = 'PENDING_REVIEW'
    STATE_ACTIVE = 'ACTIVE'
    STATE_EXPIRED = 'EXPIRED'
    STATE_DEACTIVATED = 'DEACTIVATED'

    id = db.Column(db.Integer, primary_key=True)
    alert_uuid = db.Column(db.String(36), unique=True, nullable=False, default=_uuid)
    scope_type = db.Column(db.String(24), default=SCOPE_ADDRESS)
    category = db.Column(db.String(50), index=True)
    severity = db.Column(db.String(24), default='attention')
    instruction = db.Column(db.Text, nullable=False)
    address_text = db.Column(db.String(255))
    sublocation_text = db.Column(db.String(128))
    person_ref = db.Column(db.String(128))
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'))
    event_location_id = db.Column(db.Integer, db.ForeignKey('event_location.id'))
    event_workspace_id = db.Column(db.Integer, db.ForeignKey('event_workspace.id'))
    state = db.Column(db.String(20), default=STATE_INTERIM, index=True)
    start_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)
    review_at = db.Column(db.DateTime)
    requires_acknowledgement = db.Column(db.Boolean, default=False)
    allow_no_match = db.Column(db.Boolean, default=True)
    source = db.Column(db.String(128))
    evidence_json = db.Column(db.Text)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    location = db.relationship('Location')
    event_location = db.relationship('EventLocation')
    created_by = db.relationship('User', foreign_keys=[created_by_id])

    def is_active(self, now=None):
        now = now or datetime.utcnow()
        if self.state != self.STATE_ACTIVE and self.state != self.STATE_INTERIM:
            return False
        if self.expires_at and self.expires_at <= now:
            return False
        return True

    def to_dict(self):
        return {
            'id': self.id,
            'alert_uuid': self.alert_uuid,
            'scope_type': self.scope_type,
            'category': self.category,
            'severity': self.severity,
            'instruction': self.instruction,
            'address_text': self.address_text,
            'sublocation_text': self.sublocation_text,
            'person_ref': self.person_ref,
            'location_id': self.location_id,
            'event_location_id': self.event_location_id,
            'event_workspace_id': self.event_workspace_id,
            'state': self.state,
            'start_at': self.start_at.isoformat() if self.start_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'review_at': self.review_at.isoformat() if self.review_at else None,
            'requires_acknowledgement': self.requires_acknowledgement,
            'allow_no_match': self.allow_no_match,
            'source': self.source,
        }


class AlertAcknowledgement(db.Model):
    """Operator acknowledgement/no-match/override of an alert (section 13.3)."""
    __tablename__ = 'alert_acknowledgement'

    RESULT_OPENED = 'OPENED'
    RESULT_ACKNOWLEDGED = 'ACKNOWLEDGED'
    RESULT_NO_MATCH = 'NO_MATCH'
    RESULT_OVERRIDDEN = 'OVERRIDDEN'

    id = db.Column(db.Integer, primary_key=True)
    alert_id = db.Column(db.Integer, db.ForeignKey('alert.id'), nullable=False, index=True)
    incident_id = db.Column(db.Integer, db.ForeignKey('incidents.id'), index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    result = db.Column(db.String(20), nullable=False)
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    alert = db.relationship('Alert', backref=db.backref('acknowledgements', lazy='dynamic'))
    user = db.relationship('User')

    def to_dict(self):
        return {
            'id': self.id,
            'alert_id': self.alert_id,
            'incident_id': self.incident_id,
            'user_id': self.user_id,
            'result': self.result,
            'note': self.note,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class OperatorAssignment(db.Model):
    """Ownership offer/transfer of a call or incident (design section 16.2)."""
    __tablename__ = 'operator_assignment'

    STATE_OFFERED = 'OFFERED'
    STATE_ACCEPTED = 'ACCEPTED'
    STATE_DECLINED = 'DECLINED'
    STATE_FORCED = 'FORCED'
    STATE_CANCELLED = 'CANCELLED'

    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey('incidents.id'), index=True)
    intake_id = db.Column(db.Integer, db.ForeignKey('intake.id'), index=True)
    from_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    to_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    from_application = db.Column(db.String(16))
    to_application = db.Column(db.String(16))
    reason = db.Column(db.String(255))
    handover_note = db.Column(db.Text)
    outstanding_urgent = db.Column(db.Boolean, default=False)
    forced = db.Column(db.Boolean, default=False)
    state = db.Column(db.String(16), default=STATE_OFFERED, index=True)
    offered_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)

    from_user = db.relationship('User', foreign_keys=[from_user_id])
    to_user = db.relationship('User', foreign_keys=[to_user_id])
    incident = db.relationship('Incident')
    intake = db.relationship('Intake')

    def to_dict(self):
        return {
            'id': self.id,
            'incident_id': self.incident_id,
            'intake_id': self.intake_id,
            'from_user_id': self.from_user_id,
            'to_user_id': self.to_user_id,
            'from_application': self.from_application,
            'to_application': self.to_application,
            'reason': self.reason,
            'outstanding_urgent': self.outstanding_urgent,
            'forced': self.forced,
            'state': self.state,
            'offered_at': self.offered_at.isoformat() if self.offered_at else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
        }


class AgencyNotification(db.Model):
    """External agency notification record (design section 5.3)."""
    __tablename__ = 'agency_notification'

    STATUS_REQUESTED = 'REQUESTED'
    STATUS_SENT = 'SENT'
    STATUS_ACKNOWLEDGED = 'ACKNOWLEDGED'
    STATUS_ARRIVED = 'ARRIVED'
    STATUS_CANCELLED = 'CANCELLED'

    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey('incidents.id'),
                            nullable=False, index=True)
    agency_type = db.Column(db.String(64))
    agency_name = db.Column(db.String(200), nullable=False)
    contact_method = db.Column(db.String(64))
    requested_action = db.Column(db.Text)
    status = db.Column(db.String(20), default=STATUS_REQUESTED, index=True)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    sent_at = db.Column(db.DateTime)
    acknowledged_at = db.Column(db.DateTime)
    arrived_at = db.Column(db.DateTime)
    cancelled_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)

    incident = db.relationship('Incident',
                               backref=db.backref('agency_notifications', lazy='dynamic'))

    def to_dict(self):
        return {
            'id': self.id,
            'incident_id': self.incident_id,
            'agency_type': self.agency_type,
            'agency_name': self.agency_name,
            'contact_method': self.contact_method,
            'requested_action': self.requested_action,
            'status': self.status,
            'requested_at': self.requested_at.isoformat() if self.requested_at else None,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'acknowledged_at': self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            'arrived_at': self.arrived_at.isoformat() if self.arrived_at else None,
            'cancelled_at': self.cancelled_at.isoformat() if self.cancelled_at else None,
        }


class IncidentLink(db.Model):
    """Relationship between two incidents (design section 14)."""
    __tablename__ = 'incident_link'

    REL_RELATED = 'related'
    REL_SAME_EVENT = 'same_event'
    REL_SECONDARY = 'secondary_incident'
    REL_DUPLICATE = 'duplicate_of'
    REL_DEPENDENT = 'dependent'

    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey('incidents.id'),
                            nullable=False, index=True)
    related_incident_id = db.Column(db.Integer, db.ForeignKey('incidents.id'),
                                    nullable=False, index=True)
    relationship = db.Column(db.String(32), nullable=False)
    reason = db.Column(db.String(255))
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    incident = db.relationship('Incident', foreign_keys=[incident_id])
    related_incident = db.relationship('Incident', foreign_keys=[related_incident_id])
    created_by = db.relationship('User')


class IncidentPerson(db.Model):
    """Person/patient involvement with privacy controls (design section 9.1)."""
    __tablename__ = 'incident_person'

    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey('incidents.id'),
                            nullable=False, index=True)
    role = db.Column(db.String(32), default='patient')
    name = db.Column(db.String(200))
    contact = db.Column(db.String(64))
    details_json = db.Column(db.Text)
    privacy_flag = db.Column(db.Boolean, default=False)

    incident = db.relationship('Incident',
                               backref=db.backref('persons', lazy='dynamic'))


class UrgentMessage(db.Model):
    """Urgent update on a routed incident requiring acknowledgement (section 6.1)."""
    __tablename__ = 'urgent_message'

    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey('incidents.id'),
                            nullable=False, index=True)
    intake_id = db.Column(db.Integer, db.ForeignKey('intake.id'))
    message = db.Column(db.Text, nullable=False)
    target_application = db.Column(db.String(16))
    added_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    acknowledged_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    acknowledged_at = db.Column(db.DateTime)

    incident = db.relationship('Incident',
                               backref=db.backref('urgent_messages', lazy='dynamic'))
    intake = db.relationship('Intake')
    added_by = db.relationship('User', foreign_keys=[added_by_id])
    acknowledged_by = db.relationship('User', foreign_keys=[acknowledged_by_id])

    def to_dict(self):
        return {
            'id': self.id,
            'incident_id': self.incident_id,
            'intake_id': self.intake_id,
            'message': self.message,
            'target_application': self.target_application,
            'added_by_id': self.added_by_id,
            'added_at': self.added_at.isoformat() if self.added_at else None,
            'acknowledged_by_id': self.acknowledged_by_id,
            'acknowledged_at': self.acknowledged_at.isoformat() if self.acknowledged_at else None,
        }


class CodeSet(db.Model):
    """A versioned controlled dictionary (design section 11, Appendix A)."""
    __tablename__ = 'code_set'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    version = db.Column(db.Integer, default=1)
    active = db.Column(db.Boolean, default=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    entries = db.relationship('CodeSetEntry', back_populates='code_set',
                              cascade='all, delete-orphan', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'key': self.key,
            'name': self.name,
            'version': self.version,
            'active': self.active,
            'entries': [e.to_dict() for e in self.entries],
        }


class CodeSetEntry(db.Model):
    """One entry in a controlled dictionary."""
    __tablename__ = 'code_set_entry'

    id = db.Column(db.Integer, primary_key=True)
    code_set_id = db.Column(db.Integer, db.ForeignKey('code_set.id'),
                            nullable=False, index=True)
    code = db.Column(db.String(64), nullable=False)
    label = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    rank_order = db.Column(db.Integer, default=0)
    attributes_json = db.Column(db.Text)
    effective_from = db.Column(db.DateTime, default=datetime.utcnow)
    effective_to = db.Column(db.DateTime)
    active = db.Column(db.Boolean, default=True)

    code_set = db.relationship('CodeSet', back_populates='entries')

    __table_args__ = (
        db.UniqueConstraint('code_set_id', 'code', name='uq_code_set_entry'),
    )

    def attributes(self):
        return json.loads(self.attributes_json) if self.attributes_json else {}

    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'label': self.label,
            'description': self.description,
            'rank_order': self.rank_order,
            'attributes': self.attributes(),
            'active': self.active,
        }


class ChronologyEntry(db.Model):
    """Immutable audit spine entry (design section 8).

    Entries are append-only: the service layer assigns sequence numbers and
    row hashes, and ORM listeners reject updates and deletes.
    """
    __tablename__ = 'chronology_entry'

    SEVERITY_ROUTINE = 'routine'
    SEVERITY_ATTENTION = 'attention'
    SEVERITY_URGENT = 'urgent'
    SEVERITY_WARNING = 'warning'
    SEVERITY_ERROR = 'error'

    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey('incidents.id'), index=True)
    intake_id = db.Column(db.Integer, db.ForeignKey('intake.id'), index=True)
    sequence_no = db.Column(db.Integer, nullable=False)
    occurred_at_utc = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    recorded_at_utc = db.Column(db.DateTime, default=datetime.utcnow)
    display_timezone = db.Column(db.String(64), default='UTC')
    actor_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    actor_is_system = db.Column(db.Boolean, default=False)
    operator_session_id = db.Column(db.String(100))
    workstation = db.Column(db.String(128))
    source_application = db.Column(db.String(16), default=Applications.MAIN, index=True)
    action_type = db.Column(db.String(64), nullable=False, index=True)
    entity_type = db.Column(db.String(50), index=True)
    entity_id = db.Column(db.String(64))
    summary_text = db.Column(db.Text)
    payload_json = db.Column(db.Text)
    sensitive_payload_json = db.Column(db.Text)
    severity = db.Column(db.String(16), default=SEVERITY_ROUTINE, index=True)
    correlation_id = db.Column(db.String(36), index=True)
    corrects_entry_id = db.Column(db.Integer, db.ForeignKey('chronology_entry.id'))
    row_hash = db.Column(db.String(64))
    prior_entry_hash = db.Column(db.String(64))

    incident = db.relationship('Incident', foreign_keys=[incident_id],
                               backref=db.backref('chronology', lazy='dynamic'))
    intake = db.relationship('Intake', foreign_keys=[intake_id])
    actor = db.relationship('User', foreign_keys=[actor_user_id])
    corrected_entry = db.relationship('ChronologyEntry', remote_side=[id])

    __table_args__ = (
        db.UniqueConstraint('incident_id', 'sequence_no', name='uq_chronology_seq'),
    )

    def payload(self):
        return json.loads(self.payload_json) if self.payload_json else {}

    def sensitive_payload(self):
        return (json.loads(self.sensitive_payload_json)
                if self.sensitive_payload_json else None)

    def to_dict(self, include_sensitive=False):
        result = {
            'id': self.id,
            'incident_id': self.incident_id,
            'intake_id': self.intake_id,
            'sequence_no': self.sequence_no,
            'occurred_at_utc': self.occurred_at_utc.isoformat() if self.occurred_at_utc else None,
            'recorded_at_utc': self.recorded_at_utc.isoformat() if self.recorded_at_utc else None,
            'display_timezone': self.display_timezone,
            'actor_user_id': self.actor_user_id,
            'actor': self.actor.username if self.actor else ('system' if self.actor_is_system else None),
            'actor_is_system': self.actor_is_system,
            'operator_session_id': self.operator_session_id,
            'workstation': self.workstation,
            'source_application': self.source_application,
            'action_type': self.action_type,
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'summary_text': self.summary_text,
            'payload': self.payload(),
            'severity': self.severity,
            'correlation_id': self.correlation_id,
            'corrects_entry_id': self.corrects_entry_id,
            'row_hash': self.row_hash,
            'prior_entry_hash': self.prior_entry_hash,
        }
        if include_sensitive:
            result['sensitive_payload'] = self.sensitive_payload()
        return result


class OutboxEvent(db.Model):
    """Reliable outbound domain event (design sections 4.1, 20)."""
    __tablename__ = 'outbox_event'

    STATUS_PENDING = 'PENDING'
    STATUS_PUBLISHED = 'PUBLISHED'
    STATUS_FAILED = 'FAILED'

    id = db.Column(db.Integer, primary_key=True)
    event_uuid = db.Column(db.String(36), unique=True, nullable=False, default=_uuid)
    event_type = db.Column(db.String(64), nullable=False, index=True)
    schema_version = db.Column(db.Integer, default=1)
    occurred_at = db.Column(db.DateTime, default=datetime.utcnow)
    published_at = db.Column(db.DateTime)
    source_application = db.Column(db.String(16), default=Applications.MAIN)
    actor_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    correlation_id = db.Column(db.String(36), index=True)
    entity_type = db.Column(db.String(50))
    entity_id = db.Column(db.String(64))
    incident_id = db.Column(db.Integer)
    payload_json = db.Column(db.Text)
    security_classification = db.Column(db.String(32), default='operational')
    idempotency_key = db.Column(db.String(64), unique=True)
    status = db.Column(db.String(16), default=STATUS_PENDING, index=True)
    retry_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    actor = db.relationship('User', foreign_keys=[actor_user_id])

    def payload(self):
        return json.loads(self.payload_json) if self.payload_json else {}

    def to_dict(self):
        return {
            'id': self.id,
            'event_uuid': self.event_uuid,
            'event_type': self.event_type,
            'schema_version': self.schema_version,
            'occurred_at': self.occurred_at.isoformat() if self.occurred_at else None,
            'published_at': self.published_at.isoformat() if self.published_at else None,
            'source_application': self.source_application,
            'actor_user_id': self.actor_user_id,
            'correlation_id': self.correlation_id,
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'incident_id': self.incident_id,
            'payload': self.payload(),
            'security_classification': self.security_classification,
            'idempotency_key': self.idempotency_key,
            'status': self.status,
            'retry_count': self.retry_count,
        }


class NumberSequence(db.Model):
    """Server-side daily/workspace sequence for canonical identifiers."""
    __tablename__ = 'number_sequence'

    scope = db.Column(db.String(64), primary_key=True)
    last_value = db.Column(db.Integer, default=0, nullable=False)
