"""Shared CAD Core domain services.

All operational commands go through these functions: they perform the state
change, append chronology entries and enqueue outbox events inside a single
transaction. Callers own `db.session.commit()` so each command stays
atomic with whatever else the endpoint does.
"""
import csv
import io
import json
import uuid
from datetime import datetime

from extensions import db
from models import Incident, Unit, User
from core import chronology
from core import pcr
from core.chronology import ChronologyAction as CA
from core.identifiers import new_incident_number, new_event_case_alias
from core.models import (Alert, AlertAcknowledgement, AgencyNotification,
                         Applications, ChronologyEntry, CodeSet, CodeSetEntry,
                         EventLocation, EventLocationPack, EventResponseRule,
                         EventWorkspace, IncidentLink, Intake,
                         OperatorAssignment, OutboxEvent, Response,
                         UrgentMessage)


class CoreError(Exception):
    """Domain rule violation. Carries an HTTP-ish status for API mapping."""
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class NotFoundError(CoreError):
    def __init__(self, what='Record'):
        super().__init__(f'{what} not found', status=404)


class ConflictError(CoreError):
    def __init__(self, message='Conflict: record was modified by another user'):
        super().__init__(message, status=409)


def _get(model, ident, name='Record'):
    obj = model.query.get(ident)
    if obj is None:
        raise NotFoundError(name)
    return obj


def _actor_id(actor):
    return actor.id if actor else None


def emit_outbox(event_type, entity_type=None, entity_id=None, incident_id=None,
                payload=None, actor=None, source_application=Applications.MAIN,
                correlation_id=None, idempotency_key=None, session=None):
    """Enqueue a domain event for the real-time/integration outbox."""
    sess = session or db.session
    event = OutboxEvent(
        event_type=event_type,
        occurred_at=datetime.utcnow(),
        source_application=source_application,
        actor_user_id=_actor_id(actor),
        correlation_id=correlation_id or uuid.uuid4().hex,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        incident_id=incident_id,
        payload_json=json.dumps(payload, default=str) if payload else None,
        idempotency_key=idempotency_key or uuid.uuid4().hex,
    )
    sess.add(event)
    return event


def _chron(action, incident_id=None, actor=None, session=None, **kwargs):
    return chronology.record(action, incident_id=incident_id,
                             actor_id=_actor_id(actor),
                             actor_is_system=actor is None,
                             session=session, **kwargs)


# ---------------------------------------------------------------------------
# Event workspaces and location packs
# ---------------------------------------------------------------------------

def create_event_workspace(data, actor=None, session=None):
    sess = session or db.session
    if EventWorkspace.query.filter_by(code=data['code']).first():
        raise CoreError(f"Event code '{data['code']}' already exists", 409)
    workspace = EventWorkspace(
        code=data['code'],
        name=data['name'],
        venue_name=data.get('venue_name'),
        start_date=data.get('start_date'),
        end_date=data.get('end_date'),
        timezone=data.get('timezone', 'UTC'),
        command_location=data.get('command_location'),
        responsible_agency=data.get('responsible_agency'),
        terminology_json=(json.dumps(data['terminology'])
                          if data.get('terminology') else None),
        created_by_id=_actor_id(actor),
    )
    sess.add(workspace)
    sess.flush()
    _chron(CA.EVENT_CREATED, entity_type='event_workspace',
           entity_id=workspace.id, actor=actor, session=sess,
           source_application=Applications.EVENT,
           summary=f"Event workspace '{workspace.code}' created")
    emit_outbox('EventPackActivated', entity_type='event_workspace',
                entity_id=workspace.id, actor=actor,
                source_application=Applications.EVENT, session=sess)
    return workspace


def set_event_workspace_status(workspace_id, status, actor=None, session=None):
    sess = session or db.session
    workspace = _get(EventWorkspace, workspace_id, 'Event workspace')
    valid = (EventWorkspace.STATUS_DRAFT, EventWorkspace.STATUS_ACTIVE,
             EventWorkspace.STATUS_SUSPENDED, EventWorkspace.STATUS_CLOSED)
    if status not in valid:
        raise CoreError(f'Invalid workspace status: {status}')
    old = workspace.status
    workspace.status = status
    _chron(CA.CONFIG_CHANGED, entity_type='event_workspace',
           entity_id=workspace.id, actor=actor, session=sess,
           source_application=Applications.EVENT,
           summary=f"Event workspace '{workspace.code}' {old} -> {status}",
           payload={'before': old, 'after': status})
    return workspace


EVENT_LOCATION_FIELDS = ('location_name', 'location_key', 'venue_id', 'level',
                         'aisle', 'stand_or_zone', 'map_reference',
                         'alternate_reference', 'other_details', 'response_area',
                         'primary_responder', 'secondary_responder',
                         'latitude', 'longitude', 'active')


def _parse_bool(value, default=True):
    if value is None or value == '':
        return default
    return str(value).strip().lower() in ('1', 'true', 'yes', 'y', 't')


def stage_location_pack(workspace_id, csv_text, source_filename=None,
                        actor=None, session=None):
    """Stage a CSV location-pack import and validate it (design 10.2).

    Returns (pack, stats). Nothing is activated until activate_location_pack.
    """
    sess = session or db.session
    workspace = _get(EventWorkspace, workspace_id, 'Event workspace')
    reader = csv.DictReader(io.StringIO(csv_text))
    headers = set(reader.fieldnames or [])
    errors = []
    if 'location_name' not in headers:
        errors.append("Missing required header: 'location_name'")

    next_version = (EventLocationPack.query
                    .filter_by(event_workspace_id=workspace.id)
                    .order_by(EventLocationPack.version.desc())
                    .first())
    pack = EventLocationPack(
        event_workspace_id=workspace.id,
        version=(next_version.version + 1) if next_version else 1,
        source_filename=source_filename,
        imported_by_id=_actor_id(actor),
    )
    sess.add(pack)
    sess.flush()

    seen_keys = set()
    rows = 0
    staged = []
    for i, row in enumerate(reader, start=2):
        rows += 1
        name = (row.get('location_name') or '').strip()
        key = (row.get('location_key') or '').strip()
        if not name:
            errors.append(f'Row {i}: location_name is required')
            continue
        if not key:
            key = uuid.uuid4().hex[:12]
        if key in seen_keys:
            errors.append(f'Row {i}: duplicate location_key {key}')
            continue
        seen_keys.add(key)
        loc_kwargs = {f: (row.get(f) or '').strip() or None
                      for f in EVENT_LOCATION_FIELDS
                      if f not in ('latitude', 'longitude', 'active')}
        try:
            loc_kwargs['latitude'] = (float(row['latitude'])
                                      if row.get('latitude') else None)
            loc_kwargs['longitude'] = (float(row['longitude'])
                                       if row.get('longitude') else None)
        except ValueError:
            errors.append(f'Row {i}: invalid latitude/longitude')
            continue
        active = _parse_bool(row.get('active'), default=True)
        loc = EventLocation(
            pack_id=pack.id,
            event_workspace_id=workspace.id,
            active=active,
            **loc_kwargs)
        loc.needs_confirmation = loc.is_placeholder()
        loc.is_fallback = (row.get('is_fallback') or '').strip().lower() in \
            ('1', 'true', 'yes', 'y')
        staged.append(loc)

        if any([row.get('primary_responder'), row.get('secondary_responder'),
                row.get('response_area'), row.get('map_reference')]):
            staged_rule = EventResponseRule(
                event_workspace_id=workspace.id,
                pack_id=pack.id,
                map_reference=loc_kwargs.get('map_reference'),
                response_area=loc_kwargs.get('response_area'),
                primary_responder=loc_kwargs.get('primary_responder'),
                secondary_responder=loc_kwargs.get('secondary_responder'),
            )
            sess.add(staged_rule)

    sess.add_all(staged)
    stats = {
        'rows': rows,
        'create': len(staged),
        'rejected': len(errors),
        'errors': errors[:50],
    }
    pack.preview_stats_json = json.dumps(stats)
    _chron(CA.EVENT_PACK_STAGED, entity_type='event_location_pack',
           entity_id=pack.id, actor=actor, session=sess,
           source_application=Applications.EVENT,
           summary=f"Location pack v{pack.version} staged for "
                   f"'{workspace.code}': {stats['create']} locations, "
                   f"{stats['rejected']} rejected")
    return pack, stats


def activate_location_pack(pack_id, actor=None, session=None):
    """Activate a staged pack: retire the prior pack, bump config version."""
    sess = session or db.session
    pack = _get(EventLocationPack, pack_id, 'Location pack')
    if pack.status != EventLocationPack.STATUS_STAGED:
        raise CoreError(f'Pack v{pack.version} is not staged '
                        f'(status={pack.status})', 409)
    workspace = pack.workspace
    for other in workspace.packs.filter_by(status=EventLocationPack.STATUS_ACTIVE):
        other.status = EventLocationPack.STATUS_RETIRED
    pack.status = EventLocationPack.STATUS_ACTIVE
    pack.activated_at = datetime.utcnow()
    workspace.config_version = pack.version
    _chron(CA.EVENT_ACTIVATED, entity_type='event_location_pack',
           entity_id=pack.id, actor=actor, session=sess,
           source_application=Applications.EVENT,
           summary=f"Location pack v{pack.version} activated for "
                   f"'{workspace.code}'")
    emit_outbox('EventPackActivated', entity_type='event_workspace',
                entity_id=workspace.id, actor=actor,
                payload={'pack_version': pack.version},
                source_application=Applications.EVENT, session=sess)
    return pack


def active_event_locations(workspace_id, session=None):
    sess = session or db.session
    active_pack = (EventLocationPack.query
                   .filter_by(event_workspace_id=workspace_id,
                              status=EventLocationPack.STATUS_ACTIVE)
                   .first())
    if active_pack is None:
        return []
    return (EventLocation.query
            .filter_by(pack_id=active_pack.id, active=True)
            .order_by(EventLocation.location_name).all())


def resolve_event_response(workspace_id, map_reference=None,
                           response_area=None, event_location_id=None,
                           session=None):
    """Resolve a location to its response area and advisory responders."""
    sess = session or db.session
    rules = EventResponseRule.query.filter_by(
        event_workspace_id=workspace_id, active=True)
    rule = None
    if map_reference:
        rule = rules.filter_by(map_reference=map_reference).first()
    if rule is None and response_area:
        rule = rules.filter_by(response_area=response_area).first()
    location = None
    if event_location_id:
        location = EventLocation.query.get(event_location_id)
        if location and rule is None and location.response_area:
            rule = rules.filter_by(response_area=location.response_area).first()
    result = {
        'response_area': (rule.response_area if rule else
                          getattr(location, 'response_area', None)),
        'primary_responder': (rule.primary_responder if rule else
                              getattr(location, 'primary_responder', None)),
        'secondary_responder': (rule.secondary_responder if rule else
                                getattr(location, 'secondary_responder', None)),
    }
    if rule or (location and (location.primary_responder
                            or location.secondary_responder)):
        _chron(CA.UNIT_RECOMMENDED, entity_type='event_response_rule',
               entity_id=rule.id if rule else None, session=sess,
               source_application=Applications.EVENT,
               summary='Responder recommendation resolved',
               payload=result)
    return result


# ---------------------------------------------------------------------------
# Intakes (CAD - Call Taker)
# ---------------------------------------------------------------------------

def create_intake(data, actor, session=None):
    """Create a Call Taker intake (design 6.1 step 1)."""
    sess = session or db.session
    intake = Intake(
        source=data.get('source', 'telephone'),
        received_at=data.get('received_at') or datetime.utcnow(),
        answered_at=data.get('answered_at'),
        caller_name=data.get('caller_name'),
        callback_number=data.get('callback_number'),
        location_text=data.get('location_text'),
        location_id=data.get('location_id'),
        event_location_id=data.get('event_location_id'),
        latitude=data.get('latitude'),
        longitude=data.get('longitude'),
        problem_text=data.get('problem_text'),
        operator_summary=data.get('operator_summary'),
        person_details_json=(json.dumps(data['person_details'])
                             if data.get('person_details') else None),
        hazards=data.get('hazards'),
        other_agencies=data.get('other_agencies'),
        narrative=data.get('narrative'),
        event_workspace_id=data.get('event_workspace_id'),
        priority_code=data.get('priority_code'),
        priority_rank=data.get('priority_rank'),
        incident_type_id=data.get('incident_type_id'),
        operator_user_id=_actor_id(actor),
    )
    sess.add(intake)
    sess.flush()
    _chron(CA.INTAKE_CREATED, intake_id=intake.id, entity_type='intake',
           entity_id=intake.id, actor=actor, session=sess,
           source_application=Applications.CALL_TAKER,
           summary=f"Intake from {intake.source}: "
                   f"{intake.location_text or 'location pending'}",
           payload={'source': intake.source,
                    'callback_number': intake.callback_number})
    emit_outbox('IntakeCreated', entity_type='intake', entity_id=intake.id,
                actor=actor, source_application=Applications.CALL_TAKER,
                session=sess)
    return intake


def update_intake(intake_id, data, actor, expected_version=None, session=None):
    """Update an open intake; optimistic concurrency via row_version."""
    sess = session or db.session
    intake = _get(Intake, intake_id, 'Intake')
    if intake.state != Intake.STATE_OPEN and intake.state != Intake.STATE_ROUTED:
        raise ConflictError(f'Intake is {intake.state}; it cannot be edited')
    if expected_version is not None and intake.row_version != expected_version:
        raise ConflictError(
            f'Intake was modified (version {intake.row_version}); '
            'refresh and retry')
    editable = ('caller_name', 'callback_number', 'location_text',
                'problem_text', 'operator_summary', 'hazards',
                'other_agencies', 'narrative', 'priority_code',
                'priority_rank', 'incident_type_id', 'event_workspace_id',
                'location_id', 'event_location_id', 'latitude', 'longitude')
    changed = []
    for field in editable:
        if field in data and getattr(intake, field) != data[field]:
            old = getattr(intake, field)
            setattr(intake, field, data[field])
            changed.append((field, old, data[field]))
    if not changed:
        return intake
    intake.row_version += 1
    correlation = uuid.uuid4().hex
    for field, old, new in changed:
        _chron(CA.FIELD_CHANGED, intake_id=intake.id,
               incident_id=intake.incident_id, entity_type='intake',
               entity_id=intake.id, actor=actor, session=sess,
               source_application=Applications.CALL_TAKER,
               correlation_id=correlation,
               summary=f'{field} changed on intake',
               payload={'field': field, 'before': old, 'after': new})
    emit_outbox('IntakeUpdated', entity_type='intake', entity_id=intake.id,
                incident_id=intake.incident_id, actor=actor,
                source_application=Applications.CALL_TAKER,
                correlation_id=correlation, session=sess)
    return intake


def applicable_alerts(intake_or_incident, session=None):
    """Alerts whose scope matches this intake/incident (design 13.2)."""
    sess = session or db.session
    now = datetime.utcnow()
    query = Alert.query.filter(Alert.state.in_([Alert.STATE_ACTIVE,
                                                Alert.STATE_INTERIM]),
                               db.or_(Alert.expires_at.is_(None),
                                      Alert.expires_at > now))
    clauses = []
    address = getattr(intake_or_incident, 'location_text', None) or \
        getattr(intake_or_incident, 'location', None)
    if address:
        clauses.append(db.and_(Alert.scope_type.in_([Alert.SCOPE_ADDRESS,
                                                    Alert.SCOPE_SUBLOCATION]),
                               Alert.address_text.ilike(f'%{address}%')))
    event_location_id = getattr(intake_or_incident, 'event_location_id', None)
    if event_location_id:
        clauses.append(db.and_(Alert.scope_type == Alert.SCOPE_EVENT_LOCATION,
                               Alert.event_location_id == event_location_id))
    location_id = getattr(intake_or_incident, 'location_id', None)
    if location_id and str(location_id).isdigit():
        clauses.append(Alert.location_id == int(location_id))
    workspace_id = getattr(intake_or_incident, 'event_workspace_id', None)
    if workspace_id:
        clauses.append(Alert.event_workspace_id == workspace_id)
    if not clauses:
        return []
    return query.filter(db.or_(*clauses)).all()


def route_intake(intake_id, target, actor, session=None):
    """Route an intake to CAD Main or an event workspace (design 6.1 step 5).

    Creates the incident in the same transaction; one incident, one identity.
    """
    sess = session or db.session
    intake = _get(Intake, intake_id, 'Intake')
    if intake.state == Intake.STATE_ROUTED:
        raise ConflictError('Intake is already routed')
    if intake.state in Intake.CLOSED_STATES:
        raise ConflictError(f'Intake is {intake.state}; it cannot be routed')

    if target == 'MAIN':
        workspace = None
        owning_app = Applications.MAIN
    else:
        workspace = _get(EventWorkspace, int(target), 'Event workspace')
        if workspace.status != EventWorkspace.STATUS_ACTIVE:
            raise CoreError(f"Event workspace '{workspace.code}' is not active",
                            409)
        owning_app = Applications.EVENT

    correlation = uuid.uuid4().hex
    incident = Incident(
        incident_number=new_incident_number(session=sess),
        incident_type_id=intake.incident_type_id,
        priority=intake.priority_rank or Incident.PRIORITY_MEDIUM,
        status=Incident.STATUS_OPEN,
        location=intake.location_text,
        latitude=intake.latitude,
        longitude=intake.longitude,
        caller=intake.caller_name,
        callback_number=intake.callback_number,
        description=intake.operator_summary or intake.problem_text,
        created_by_id=_actor_id(actor),
    )
    incident.owning_application = owning_app
    incident.event_workspace_id = workspace.id if workspace else \
        intake.event_workspace_id
    incident.event_location_id = intake.event_location_id
    incident.lifecycle_status = 'NEW'
    incident.responsible_user_id = _actor_id(actor)
    sess.add(incident)
    sess.flush()

    intake.state = Intake.STATE_ROUTED
    intake.routed_application = owning_app
    intake.routed_at = datetime.utcnow()
    intake.incident_id = incident.id
    intake.row_version += 1

    _chron(CA.INTAKE_ROUTED, incident_id=incident.id, intake_id=intake.id,
           entity_type='intake', entity_id=intake.id, actor=actor, session=sess,
           source_application=Applications.CALL_TAKER,
           correlation_id=correlation,
           summary=f'Intake routed to {owning_app}'
                   + (f' ({workspace.code})' if workspace else ''),
           payload={'target': owning_app,
                    'event_workspace_id': workspace.id if workspace else None})
    _chron(CA.INCIDENT_CREATED, incident_id=incident.id, intake_id=intake.id,
           entity_type='incident', entity_id=incident.id, actor=actor,
           session=sess, source_application=Applications.CALL_TAKER,
           correlation_id=correlation,
           summary=f'Incident {incident.incident_number} created from intake',
           payload={'incident_number': incident.incident_number,
                    'owning_application': owning_app})

    pcr.enqueue_job_update(incident, session=sess)

    for alert in applicable_alerts(incident, session=sess):
        _chron(CA.ALERT_PRESENTED, incident_id=incident.id, intake_id=intake.id,
               entity_type='alert', entity_id=alert.id, actor=actor,
               session=sess, source_application=Applications.CALL_TAKER,
               correlation_id=correlation,
               severity=ChronologyEntry.SEVERITY_WARNING,
               summary=f'Alert presented: {alert.category}',
               payload={'alert_uuid': alert.alert_uuid,
                        'scope_type': alert.scope_type})

    emit_outbox('IntakeUpdated', entity_type='intake', entity_id=intake.id,
                incident_id=incident.id, actor=actor,
                source_application=Applications.CALL_TAKER,
                correlation_id=correlation, session=sess)
    emit_outbox('IncidentRouted', entity_type='incident', entity_id=incident.id,
                incident_id=incident.id, actor=actor,
                payload={'target': owning_app,
                         'event_workspace_id':
                             workspace.id if workspace else None},
                source_application=Applications.CALL_TAKER,
                correlation_id=correlation, session=sess)
    return intake, incident


def close_intake(intake_id, state, reason=None, actor=None, session=None):
    """Mark an intake abandoned/hoax/info-only/duplicate/cancelled."""
    sess = session or db.session
    intake = _get(Intake, intake_id, 'Intake')
    if state not in Intake.CLOSED_STATES:
        raise CoreError(f'Invalid intake closure state: {state}')
    if intake.state != Intake.STATE_OPEN:
        raise ConflictError(f'Intake is {intake.state}; it cannot be closed')
    intake.state = state
    intake.closure_reason = reason
    intake.row_version += 1
    action = (CA.INTAKE_ABANDONED if state == Intake.STATE_ABANDONED
              else CA.INTAKE_CLOSED)
    _chron(action, intake_id=intake.id, entity_type='intake',
           entity_id=intake.id, actor=actor, session=sess,
           source_application=Applications.CALL_TAKER,
           summary=f'Intake closed as {state}',
           payload={'state': state, 'reason': reason})
    return intake


def add_urgent_message(incident_id, message, actor, intake_id=None,
                       session=None):
    """Add an urgent update to a routed incident (design 6.1 step 7)."""
    sess = session or db.session
    incident = _get(Incident, incident_id, 'Incident')
    urgent = UrgentMessage(
        incident_id=incident.id,
        intake_id=intake_id,
        message=message,
        target_application=incident.owning_application,
        added_by_id=_actor_id(actor),
    )
    sess.add(urgent)
    incident.urgent_update = True
    sess.flush()
    _chron(CA.URGENT_MESSAGE_ADDED, incident_id=incident.id,
           intake_id=intake_id, entity_type='urgent_message',
           entity_id=urgent.id, actor=actor, session=sess,
           severity=ChronologyEntry.SEVERITY_URGENT,
           summary=f'URGENT: {message[:120]}')
    emit_outbox('UrgentMessageAdded', entity_type='urgent_message',
                entity_id=urgent.id, incident_id=incident.id, actor=actor,
                session=sess)
    return urgent


def acknowledge_urgent_message(urgent_message_id, actor, session=None):
    sess = session or db.session
    urgent = _get(UrgentMessage, urgent_message_id, 'Urgent message')
    if urgent.acknowledged_at:
        raise ConflictError('Urgent message already acknowledged')
    urgent.acknowledged_by_id = _actor_id(actor)
    urgent.acknowledged_at = datetime.utcnow()
    incident = urgent.incident
    incident.urgent_update = incident.urgent_messages.filter(
        UrgentMessage.acknowledged_at.is_(None),
        UrgentMessage.id != urgent.id).count() > 0
    _chron(CA.URGENT_MESSAGE_ACKNOWLEDGED, incident_id=incident.id,
           entity_type='urgent_message', entity_id=urgent.id, actor=actor,
           session=sess, summary='Urgent message acknowledged',
           source_application=incident.owning_application or Applications.MAIN)
    return urgent


# ---------------------------------------------------------------------------
# Incident field edits and concurrency
# ---------------------------------------------------------------------------

def update_incident_fields(incident_id, fields, actor, expected_version,
                           source_application=Applications.MAIN, session=None):
    """Update incident fields with optimistic concurrency (design 16.3)."""
    sess = session or db.session
    incident = _get(Incident, incident_id, 'Incident')
    if incident.lifecycle_status in ('CLOSED', 'CANCELLED',
                                     'DUPLICATE_CANCELLED'):
        raise ConflictError(
            'Closed incidents are immutable; use reopen/correction')
    if incident.row_version != expected_version:
        raise ConflictError(
            f'Incident was modified (version {incident.row_version}); '
            'refresh and retry')
    editable = ('location', 'description', 'caller', 'callback_number',
                'latitude', 'longitude', 'priority', 'resolution',
                'type_text', 'ampds_code', 'event_location_id')
    correlation = uuid.uuid4().hex
    changed = False
    for field, new_value in fields.items():
        if field not in editable:
            continue
        old_value = getattr(incident, field)
        if old_value == new_value:
            continue
        setattr(incident, field, new_value)
        sensitive = field in ('caller', 'callback_number')
        chronology.field_change(            incident.id, field, old_value, new_value,
            actor_id=_actor_id(actor), sensitive=sensitive,
            correlation_id=correlation, session=sess,
            source_application=source_application)
        changed = True
    if not changed:
        return incident
    incident.row_version += 1
    incident.updated_by_id = _actor_id(actor)
    incident.updated_at = datetime.utcnow()
    emit_outbox('IncidentUpdated', entity_type='incident',
                entity_id=incident.id, incident_id=incident.id, actor=actor,
                correlation_id=correlation, source_application=source_application,
                session=sess)
    pcr.enqueue_job_update(incident, session=sess)
    return incident


# ---------------------------------------------------------------------------
# Escalation: Event -> Main (design 6.3)
# ---------------------------------------------------------------------------

ESCALATION_MODES = ('MAIN_LEAD', 'FULL_TRANSFER', 'SHARED_MAJOR')


def escalate_to_main(incident_id, mode, reason, actor, session=None):
    """Escalate an event incident to CAD Main preserving identity."""
    sess = session or db.session
    incident = _get(Incident, incident_id, 'Incident')
    if mode not in ESCALATION_MODES:
        raise CoreError(f'Invalid escalation mode: {mode}')
    if incident.owning_application == Applications.MAIN:
        raise ConflictError('Incident is already owned by CAD Main')
    if incident.owning_application != Applications.EVENT:
        raise ConflictError(
            f'Incident is owned by {incident.owning_application}; '
            'only event incidents escalate to Main')

    correlation = uuid.uuid4().hex
    previous_owner = incident.owning_application
    incident.owning_application = Applications.MAIN
    incident.escalation_mode = mode
    incident.escalated_at = datetime.utcnow()
    incident.row_version += 1

    _chron(CA.INCIDENT_ESCALATED, incident_id=incident.id,
           entity_type='incident', entity_id=incident.id, actor=actor,
           session=sess, source_application=Applications.EVENT,
           correlation_id=correlation,
           severity=ChronologyEntry.SEVERITY_ATTENTION,
           summary=f'Escalated to CAD Main ({mode})',
           payload={'mode': mode, 'reason': reason,
                    'previous_owner': previous_owner,
                    'event_workspace_id': incident.event_workspace_id})
    emit_outbox('IncidentEscalated', entity_type='incident',
                entity_id=incident.id, incident_id=incident.id, actor=actor,
                correlation_id=correlation,
                payload={'mode': mode, 'reason': reason,
                         'event_workspace_id': incident.event_workspace_id},
                source_application=Applications.EVENT, session=sess)
    return incident


# ---------------------------------------------------------------------------
# Responses and unit progression
# ---------------------------------------------------------------------------

def assign_unit(incident_id, unit_id, actor, role='primary', session=None):
    """Assign a unit: creates a Response with its own lifecycle (design 9.2)."""
    sess = session or db.session
    incident = _get(Incident, incident_id, 'Incident')
    unit = _get(Unit, unit_id, 'Unit')
    if incident.lifecycle_status in ('CLOSED', 'CANCELLED',
                                     'DUPLICATE_CANCELLED'):
        raise ConflictError('Cannot assign units to a closed incident')
    existing = Response.query.filter_by(
        incident_id=incident.id, unit_id=unit.id).filter(
        Response.status.notin_(Response.TERMINAL_STATES)).first()
    if existing:
        raise ConflictError(
            f'Unit {unit.name} already has active response '
            f'{existing.response_uuid}')

    max_seq = (sess.query(db.func.max(Response.sequence_no))
               .filter_by(incident_id=incident.id).scalar() or 0)
    response = Response(
        incident_id=incident.id,
        unit_id=unit.id,
        response_role=role,
        sequence_no=max_seq + 1,
        status=Response.STATUS_ASSIGNED,
        assigned_by_id=_actor_id(actor),
        assigned_at=datetime.utcnow(),
    )
    sess.add(response)
    if incident.lifecycle_status in ('NEW', 'PENDING'):
        incident.lifecycle_status = 'ASSIGNED'
    if unit.status != 'assigned':
        unit.status = 'assigned'
    sess.flush()
    _chron(CA.UNIT_ASSIGNED, incident_id=incident.id,
           entity_type='response', entity_id=response.id, actor=actor,
           session=sess,
           source_application=incident.owning_application or Applications.MAIN,
           summary=f'Unit {unit.name} assigned as {role}',
           payload={'unit_id': unit.id, 'unit_name': unit.name,
                    'response_uuid': response.response_uuid, 'role': role})
    pcr.enqueue_job_update(incident, session=sess)
    emit_outbox('UnitAssigned', entity_type='response', entity_id=response.id,
                incident_id=incident.id, actor=actor,
                source_application=incident.owning_application or Applications.MAIN,
                session=sess)
    return response


def update_response_status(response_id, new_status, actor, reason=None,
                           retrospective=False, session=None):
    """Progress a response through its lifecycle (design 6.2)."""
    sess = session or db.session
    response = _get(Response, response_id, 'Response')
    incident = response.incident
    if new_status not in Response.PROGRESSION:
        raise CoreError(f'Invalid response status: {new_status}')
    allowed = Response.PROGRESSION.get(response.status, ())
    if new_status not in allowed and not retrospective:
        raise CoreError(
            f'Invalid transition {response.status} -> {new_status}; '
            'use retrospective correction with a reason', 409)
    if retrospective and not reason:
        raise CoreError('Retrospective corrections require a reason')

    correlation = uuid.uuid4().hex
    old_status = response.status
    response.status = new_status
    timestamp_field = Response.STATUS_TIMESTAMP.get(new_status)
    if timestamp_field:
        setattr(response, timestamp_field, datetime.utcnow())
    if new_status == Response.STATUS_DEALLOCATED:
        active = Response.query.filter_by(incident_id=incident.id).filter(
            Response.status.notin_(Response.TERMINAL_STATES),
            Response.id != response.id).count()
        if active == 0 and incident.lifecycle_status == 'ASSIGNED':
            incident.lifecycle_status = 'PENDING'
    if new_status in Response.TERMINAL_STATES:
        response.cleared_at = response.cleared_at or datetime.utcnow()
    response.updated_at = datetime.utcnow()

    action = CA.UNIT_STATUS_CHANGED
    if new_status == Response.STATUS_DISPATCHED:
        action = CA.UNIT_DISPATCHED
    elif new_status == Response.STATUS_ACKNOWLEDGED:
        action = CA.UNIT_ACKNOWLEDGED
    elif new_status == Response.STATUS_CLEAR:
        action = CA.UNIT_CLEARED
    elif new_status == Response.STATUS_DEALLOCATED:
        action = CA.UNIT_DEALLOCATED

    unit_name = response.unit.name if response.unit else response.unit_id
    _chron(action, incident_id=incident.id,
           entity_type='response', entity_id=response.id, actor=actor,
           session=sess, correlation_id=correlation,
           source_application=incident.owning_application or Applications.MAIN,
           summary=f'{unit_name}: {old_status} -> {new_status}',
           payload={'unit_id': response.unit_id, 'unit_name': unit_name,
                    'before': old_status, 'after': new_status,
                    'retrospective': retrospective, 'reason': reason})
    emit_outbox('UnitStatusChanged' if new_status not in Response.TERMINAL_STATES
                else 'ResponseCleared',
                entity_type='response', entity_id=response.id,
                incident_id=incident.id, actor=actor,
                correlation_id=correlation,
                source_application=incident.owning_application
                or Applications.MAIN, session=sess)
    pcr.enqueue_status_event(incident, new_status, datetime.utcnow(),
                             unit_callsign=str(unit_name), session=sess)
    return response


# ---------------------------------------------------------------------------
# Operator ownership transfer (design 16.2)
# ---------------------------------------------------------------------------

def offer_transfer(target, to_user_id, actor, reason=None, handover_note=None,
                   session=None):
    """Offer incident or intake ownership to another operator."""
    sess = session or db.session
    if to_user_id == _actor_id(actor):
        raise CoreError('Cannot transfer to the current operator')
    _get(User, to_user_id, 'User')
    kwargs = {}
    if isinstance(target, Incident):
        kwargs['incident_id'] = target.id
        kwargs['from_application'] = target.owning_application
        kwargs['to_application'] = target.owning_application
        kwargs['outstanding_urgent'] = bool(target.urgent_update)
    elif isinstance(target, Intake):
        kwargs['intake_id'] = target.id
        kwargs['from_application'] = Applications.CALL_TAKER
        kwargs['to_application'] = Applications.CALL_TAKER
        kwargs['outstanding_urgent'] = False
    else:
        raise CoreError('Unsupported transfer target')
    transfer = OperatorAssignment(
        from_user_id=_actor_id(actor),
        to_user_id=to_user_id,
        reason=reason,
        handover_note=handover_note,
        **kwargs)
    sess.add(transfer)
    sess.flush()
    _chron(CA.TRANSFER_OFFERED, incident_id=transfer.incident_id,
           intake_id=transfer.intake_id, entity_type='operator_assignment',
           entity_id=transfer.id, actor=actor, session=sess,
           summary=f'Ownership offered to user {to_user_id}',
           payload={'to_user_id': to_user_id, 'reason': reason})
    emit_outbox('OperatorTransferOffered', entity_type='operator_assignment',
                entity_id=transfer.id, incident_id=transfer.incident_id,
                actor=actor, session=sess)
    return transfer


def resolve_transfer(transfer_id, accept, actor, session=None):
    """Accept or decline an ownership offer."""
    sess = session or db.session
    transfer = _get(OperatorAssignment, transfer_id, 'Transfer')
    if transfer.state != OperatorAssignment.STATE_OFFERED:
        raise ConflictError(f'Transfer is {transfer.state}')
    if transfer.to_user_id != _actor_id(actor):
        raise CoreError('Only the recipient may resolve this transfer', 403)
    transfer.state = (OperatorAssignment.STATE_ACCEPTED if accept
                      else OperatorAssignment.STATE_DECLINED)
    transfer.resolved_at = datetime.utcnow()
    if accept and transfer.incident_id:
        transfer.incident.responsible_user_id = transfer.to_user_id
    if accept and transfer.intake_id:
        transfer.intake.operator_user_id = transfer.to_user_id
    action = (CA.TRANSFER_ACCEPTED if accept else CA.TRANSFER_DECLINED)
    _chron(action, incident_id=transfer.incident_id,
           intake_id=transfer.intake_id, entity_type='operator_assignment',
           entity_id=transfer.id, actor=actor, session=sess,
           summary=f'Transfer {transfer.state.lower()}',
           payload={'transfer_id': transfer.id})
    if accept:
        emit_outbox('OperatorTransferAccepted',
                    entity_type='operator_assignment', entity_id=transfer.id,
                    incident_id=transfer.incident_id, actor=actor, session=sess)
    return transfer


# ---------------------------------------------------------------------------
# Duplicates and linking (design 14)
# ---------------------------------------------------------------------------

def suggest_duplicates(incident_id, window_minutes=60, session=None):
    """Return candidate duplicate open incidents with match reasons."""
    sess = session or db.session
    incident = _get(Incident, incident_id, 'Incident')
    candidates = sess.query(Incident).filter(
        Incident.id != incident.id,
        Incident.lifecycle_status.notin_(('CLOSED', 'CANCELLED',
                                          'DUPLICATE_CANCELLED'))).all()
    matches = []
    for other in candidates:
        reasons = []
        if incident.location and other.location and \
                incident.location.strip().lower() == \
                other.location.strip().lower():
            reasons.append('same location')
        if incident.callback_number and \
                incident.callback_number == other.callback_number:
            reasons.append('same callback number')
        if incident.event_workspace_id and \
                incident.event_workspace_id == other.event_workspace_id:
            reasons.append('same event workspace')
        if reasons:
            matches.append({'incident': other.to_dict(), 'reasons': reasons})
    if matches:
        _chron(CA.DUPLICATE_SUGGESTED, incident_id=incident.id,
               entity_type='incident', entity_id=incident.id, session=sess,
               summary=f'{len(matches)} possible duplicate(s) suggested',
               payload={'candidates': [m['incident']['id'] for m in matches]})
    return matches


def suggest_intake_duplicates(intake_id, session=None):
    """Duplicate candidates for an open intake (design 14): match open
    incidents on location text, callback number, or event workspace.
    Read-only: no chronology write (unlike incident-side suggestion)."""
    sess = session or db.session
    intake = _get(Intake, intake_id, 'Intake')
    candidates = sess.query(Incident).filter(
        Incident.lifecycle_status.notin_(('CLOSED', 'CANCELLED',
                                          'DUPLICATE_CANCELLED'))).all()
    matches = []
    loc = (intake.location_text or '').strip().lower()
    for other in candidates:
        reasons = []
        if loc and other.location and \
                loc == other.location.strip().lower():
            reasons.append('same location')
        if intake.callback_number and \
                intake.callback_number == other.callback_number:
            reasons.append('same callback number')
        if intake.event_workspace_id and \
                intake.event_workspace_id == other.event_workspace_id:
            reasons.append('same event workspace')
        if reasons:
            matches.append({'incident': other.to_dict(), 'reasons': reasons})
    return matches


def link_incidents(incident_id, related_id, relationship, actor, reason=None,
                   session=None):
    """Link two incidents (related, same_event, secondary, duplicate)."""
    sess = session or db.session
    if incident_id == related_id:
        raise CoreError('Cannot link an incident to itself')
    valid = (IncidentLink.REL_RELATED, IncidentLink.REL_SAME_EVENT,
             IncidentLink.REL_SECONDARY, IncidentLink.REL_DUPLICATE,
             IncidentLink.REL_DEPENDENT)
    if relationship not in valid:
        raise CoreError(f'Invalid relationship: {relationship}')
    _get(Incident, incident_id, 'Incident')
    _get(Incident, related_id, 'Related incident')
    link = IncidentLink(
        incident_id=incident_id,
        related_incident_id=related_id,
        relationship=relationship,
        reason=reason,
        created_by_id=_actor_id(actor),
    )
    sess.add(link)
    sess.flush()
    for iid in (incident_id, related_id):
        _chron(CA.DUPLICATE_LINKED, incident_id=iid, entity_type='incident_link',
               entity_id=link.id, actor=actor, session=sess,
               summary=f'Linked to incident {related_id if iid == incident_id else incident_id} '
                       f'({relationship})',
               payload={'link_id': link.id, 'relationship': relationship})
    return link


def cancel_as_duplicate(incident_id, surviving_id, actor, reason=None,
                        session=None):
    """Cancel one incident as a duplicate of another (design 14)."""
    sess = session or db.session
    incident = _get(Incident, incident_id, 'Incident')
    _get(Incident, surviving_id, 'Surviving incident')
    if incident.lifecycle_status == 'DUPLICATE_CANCELLED':
        raise ConflictError('Incident already cancelled as duplicate')
    link_incidents(incident_id, surviving_id, IncidentLink.REL_DUPLICATE,
                   actor=actor, reason=reason, session=sess)
    old_status = incident.lifecycle_status
    incident.lifecycle_status = 'DUPLICATE_CANCELLED'
    incident.status = Incident.STATUS_CLOSED
    incident.row_version += 1
    _chron(CA.DUPLICATE_CANCELLED, incident_id=incident.id,
           entity_type='incident', entity_id=incident.id, actor=actor,
           session=sess,
           severity=ChronologyEntry.SEVERITY_ATTENTION,
           summary=f'Cancelled as duplicate of incident {surviving_id}',
           payload={'before': old_status, 'surviving_incident_id': surviving_id,
                    'reason': reason})
    pcr.enqueue_cancel(incident, reason or 'Cancelled by control',
                       datetime.utcnow(), session=sess)
    return incident


# ---------------------------------------------------------------------------
# Closure and reopening (design 6.4)
# ---------------------------------------------------------------------------

def validate_closure(incident, session=None):
    """Return the list of unmet closure requirements (design 6.4)."""
    sess = session or db.session
    blockers = []
    open_responses = Response.query.filter_by(incident_id=incident.id).filter(
        Response.status.notin_(Response.TERMINAL_STATES)).count()
    if open_responses:
        blockers.append(f'{open_responses} response(s) still active')
    open_urgents = UrgentMessage.query.filter_by(
        incident_id=incident.id, acknowledged_at=None).count()
    if open_urgents:
        blockers.append(f'{open_urgents} urgent message(s) unacknowledged')
    open_transfers = OperatorAssignment.query.filter_by(
        incident_id=incident.id, state=OperatorAssignment.STATE_OFFERED).count()
    if open_transfers:
        blockers.append(f'{open_transfers} operator transfer(s) unresolved')
    return blockers


def close_incident(incident_id, outcome, closure_note, actor, session=None):
    """Close an incident once all closure requirements are met."""
    sess = session or db.session
    incident = _get(Incident, incident_id, 'Incident')
    if incident.lifecycle_status == 'CLOSED':
        raise ConflictError('Incident is already closed')
    if not outcome:
        raise CoreError('A controlled closure outcome is required')
    blockers = validate_closure(incident, session=sess)
    if blockers:
        raise ConflictError('Cannot close: ' + '; '.join(blockers))
    old_status = incident.lifecycle_status
    incident.lifecycle_status = 'CLOSED'
    incident.status = Incident.STATUS_CLOSED
    incident.closed_at = datetime.utcnow()
    incident.closed_by_id = _actor_id(actor)
    incident.closure_outcome = outcome
    incident.resolution = closure_note or incident.resolution
    incident.row_version += 1
    _chron(CA.INCIDENT_CLOSED, incident_id=incident.id,
           entity_type='incident', entity_id=incident.id, actor=actor,
           session=sess,
           source_application=incident.owning_application or Applications.MAIN,
           summary=f'Incident closed ({outcome})',
           payload={'before': old_status, 'outcome': outcome,
                    'closure_note': closure_note})
    emit_outbox('IncidentClosed', entity_type='incident',
                entity_id=incident.id, incident_id=incident.id, actor=actor,
                source_application=incident.owning_application
                or Applications.MAIN, session=sess)
    return incident


def reopen_incident(incident_id, reason, actor, session=None):
    """Reopen a closed incident with reason (design 6.4)."""
    sess = session or db.session
    incident = _get(Incident, incident_id, 'Incident')
    if incident.lifecycle_status != 'CLOSED':
        raise ConflictError(f'Incident is {incident.lifecycle_status}')
    if not reason:
        raise CoreError('Reopening requires a reason')
    old_status = incident.lifecycle_status
    incident.lifecycle_status = 'ACTIVE'
    incident.status = Incident.STATUS_OPEN
    incident.closed_at = None
    incident.row_version += 1
    _chron(CA.INCIDENT_REOPENED, incident_id=incident.id,
           entity_type='incident', entity_id=incident.id, actor=actor,
           session=sess,
           severity=ChronologyEntry.SEVERITY_ATTENTION,
           source_application=incident.owning_application or Applications.MAIN,
           summary=f'Incident reopened: {reason}',
           payload={'before': old_status, 'reason': reason})
    return incident


# ---------------------------------------------------------------------------
# Alert workflow
# ---------------------------------------------------------------------------

def acknowledge_alert(alert_id, incident_id, result, actor, note=None,
                      session=None):
    """Record an alert acknowledgement/no-match/override (design 13.3)."""
    sess = session or db.session
    alert = _get(Alert, alert_id, 'Alert')
    valid = (AlertAcknowledgement.RESULT_ACKNOWLEDGED,
             AlertAcknowledgement.RESULT_NO_MATCH,
             AlertAcknowledgement.RESULT_OVERRIDDEN,
             AlertAcknowledgement.RESULT_OPENED)
    if result not in valid:
        raise CoreError(f'Invalid acknowledgement result: {result}')
    if result == AlertAcknowledgement.RESULT_NO_MATCH and not alert.allow_no_match:
        raise CoreError('No-match selection is not permitted for this alert', 403)
    ack = AlertAcknowledgement(
        alert_id=alert.id,
        incident_id=incident_id,
        user_id=_actor_id(actor),
        result=result,
        note=note,
    )
    sess.add(ack)
    sess.flush()
    action = {
        AlertAcknowledgement.RESULT_ACKNOWLEDGED: CA.ALERT_ACKNOWLEDGED,
        AlertAcknowledgement.RESULT_NO_MATCH: CA.ALERT_NO_MATCH,
        AlertAcknowledgement.RESULT_OVERRIDDEN: CA.ALERT_OVERRIDDEN,
        AlertAcknowledgement.RESULT_OPENED: CA.ALERT_OPENED,
    }[result]
    _chron(action, incident_id=incident_id, entity_type='alert',
           entity_id=alert.id, actor=actor, session=sess,
           severity=(ChronologyEntry.SEVERITY_WARNING
                     if result == AlertAcknowledgement.RESULT_OVERRIDDEN
                     else ChronologyEntry.SEVERITY_ROUTINE),
           summary=f'Alert {result.lower().replace("_", " ")}',
           payload={'alert_uuid': alert.alert_uuid, 'result': result,
                    'note': note})
    emit_outbox('AlertAcknowledged', entity_type='alert', entity_id=alert.id,
                incident_id=incident_id, actor=actor, session=sess)
    return ack
