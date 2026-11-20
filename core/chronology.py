"""Append-only chronology service (design section 8).

Every operational action is recorded as a `ChronologyEntry` inside the same
transaction as the change itself. Sequence numbers are per-incident, server
time is authoritative, and each row carries a hash chained to the prior
entry for tamper evidence.

ORM listeners on ChronologyEntry reject updates and deletes, so entries can
never be edited or removed through the application.
"""
import hashlib
import json
import uuid
from datetime import datetime

from sqlalchemy import event, func
from sqlalchemy.orm import Session as _Session

from extensions import db
from core.models import ChronologyEntry, Applications


class ChronologyAction:
    """Action types required by the design (section 8.2)."""

    # Intake
    INTAKE_CREATED = 'intake_created'
    INTAKE_ANSWERED = 'intake_answered'
    INTAKE_ABANDONED = 'intake_abandoned'
    INTAKE_ROUTED = 'intake_routed'
    INTAKE_REROUTED = 'intake_rerouted'
    INTAKE_LINKED = 'intake_linked'
    INTAKE_CLOSED = 'intake_closed'

    # Incident lifecycle
    INCIDENT_CREATED = 'incident_created'
    INCIDENT_VIEWED = 'incident_viewed'
    INCIDENT_SAVED = 'incident_saved'
    INCIDENT_HELD = 'incident_held'
    INCIDENT_RESUMED = 'incident_resumed'
    INCIDENT_ESCALATED = 'incident_escalated'
    INCIDENT_TRANSFERRED = 'incident_transferred'
    INCIDENT_REOPENED = 'incident_reopened'
    INCIDENT_CLOSED = 'incident_closed'

    # Fields and narrative
    FIELD_ADDED = 'field_added'
    FIELD_CHANGED = 'field_changed'
    FIELD_CLEARED = 'field_cleared'
    FIELD_CORRECTED = 'field_corrected'
    NARRATIVE_ADDED = 'narrative_added'
    REMARK_ADDED = 'remark_added'
    QUICK_NOTE_ADDED = 'quick_note_added'
    URGENT_MESSAGE_ADDED = 'urgent_message_added'
    URGENT_MESSAGE_ACKNOWLEDGED = 'urgent_message_acknowledged'
    SITUATION_REPORT_ADDED = 'situation_report_added'

    # Location
    LOCATION_SELECTED = 'location_selected'
    LOCATION_CHANGED = 'location_changed'
    LOCATION_UNLISTED = 'location_unlisted_entered'
    LOCATION_VALIDATED = 'location_validated'

    # Alerts
    ALERT_PRESENTED = 'alert_presented'
    ALERT_OPENED = 'alert_opened'
    ALERT_ACKNOWLEDGED = 'alert_acknowledged'
    ALERT_NO_MATCH = 'alert_no_match_selected'
    ALERT_OVERRIDDEN = 'alert_overridden'

    # Classification
    TYPE_CHANGED = 'incident_type_changed'
    PROBLEM_CHANGED = 'problem_changed'
    CODE_CHANGED = 'dispatch_code_changed'
    PRIORITY_CHANGED = 'priority_changed'

    # Duplicates
    DUPLICATE_SUGGESTED = 'duplicate_suggested'
    DUPLICATE_LINKED = 'duplicate_linked'
    DUPLICATE_MERGED = 'duplicate_merged'
    DUPLICATE_CANCELLED = 'duplicate_cancelled'

    # Units / responses
    UNIT_RECOMMENDED = 'unit_recommended'
    UNIT_ASSIGNED = 'unit_assigned'
    UNIT_DISPATCHED = 'unit_dispatched'
    UNIT_ACKNOWLEDGED = 'unit_acknowledged'
    UNIT_STATUS_CHANGED = 'unit_status_changed'
    UNIT_REASSIGNED = 'unit_reassigned'
    UNIT_DEALLOCATED = 'unit_deallocated'
    UNIT_CLEARED = 'unit_cleared'

    # Operator ownership
    TRANSFER_OFFERED = 'operator_transfer_offered'
    TRANSFER_ACCEPTED = 'operator_transfer_accepted'
    TRANSFER_DECLINED = 'operator_transfer_declined'
    TRANSFER_FORCED = 'operator_transfer_forced'
    OPERATOR_HANDOVER = 'operator_handover'

    # Agency
    AGENCY_REQUESTED = 'agency_notification_requested'
    AGENCY_SENT = 'agency_notification_sent'
    AGENCY_ACKNOWLEDGED = 'agency_notification_acknowledged'
    AGENCY_ARRIVED = 'agency_notification_arrived'
    AGENCY_CANCELLED = 'agency_notification_cancelled'

    # Event workspace
    EVENT_CREATED = 'event_workspace_created'
    EVENT_ACTIVATED = 'event_pack_activated'
    EVENT_PACK_STAGED = 'event_pack_staged'
    EVENT_PACK_ROLLBACK = 'event_pack_rollback'

    # Files, config, auth
    FILE_CREATED = 'file_created'
    REPORT_CREATED = 'report_created'
    EXPORT_CREATED = 'export_created'
    CONFIG_CHANGED = 'config_changed'
    AUTHENTICATION = 'authentication'
    ACCESS_DENIED = 'access_denied'
    ELEVATED_ACTION = 'elevated_action'


class ChronologyImmutable(Exception):
    """Raised when code attempts to modify or delete a chronology entry."""


def _hash_entry(prior_hash, entry_values):
    canonical = json.dumps(
        {'prior': prior_hash, **entry_values},
        sort_keys=True, default=str, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def record(action_type, incident_id=None, intake_id=None, entity_type=None,
           entity_id=None, summary=None, payload=None, sensitive_payload=None,
           severity=ChronologyEntry.SEVERITY_ROUTINE, actor_id=None,
           actor_is_system=False, operator_session_id=None, workstation=None,
           source_application=Applications.MAIN, display_timezone=None,
           occurred_at=None, correlation_id=None, corrects_entry_id=None,
           session=None):
    """Append a chronology entry inside the caller's transaction.

    Callers own the commit; this function only adds to the session so the
    entry commits atomically with the operational change it describes.
    """
    sess = session or db.session
    now = occurred_at or datetime.utcnow()
    correlation_id = correlation_id or uuid.uuid4().hex

    last = (sess.query(ChronologyEntry)
            .filter(ChronologyEntry.incident_id == incident_id)
            .order_by(ChronologyEntry.sequence_no.desc())
            .first()) if incident_id else None
    sequence_no = (last.sequence_no + 1) if last else 1
    prior_hash = last.row_hash if last else None

    entry = ChronologyEntry(
        incident_id=incident_id,
        intake_id=intake_id,
        sequence_no=sequence_no,
        occurred_at_utc=now,
        recorded_at_utc=datetime.utcnow(),
        display_timezone=display_timezone or 'UTC',
        actor_user_id=actor_id,
        actor_is_system=actor_is_system,
        operator_session_id=operator_session_id,
        workstation=workstation,
        source_application=source_application,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        summary_text=summary,
        payload_json=json.dumps(payload, default=str) if payload is not None else None,
        sensitive_payload_json=(json.dumps(sensitive_payload, default=str)
                                if sensitive_payload is not None else None),
        severity=severity,
        correlation_id=correlation_id,
        corrects_entry_id=corrects_entry_id,
        prior_entry_hash=prior_hash,
    )
    entry.row_hash = _hash_entry(prior_hash, {
        'sequence_no': sequence_no,
        'occurred_at_utc': now.isoformat(),
        'action_type': action_type,
        'entity_type': entity_type,
        'entity_id': entry.entity_id,
        'summary_text': summary,
        'payload': payload,
        'actor_user_id': actor_id,
        'actor_is_system': actor_is_system,
    })
    sess.add(entry)
    return entry


def field_change(incident_id, field, old_value, new_value, actor_id=None,
                 sensitive=False, correlation_id=None, session=None, **kwargs):
    """Record a committed field edit with safe before/after representation."""
    payload = {'field': field}
    if sensitive:
        payload['before'] = '***'
        payload['after'] = '***'
        sensitive_payload = {'before': old_value, 'after': new_value}
    else:
        payload['before'] = old_value
        payload['after'] = new_value
        sensitive_payload = None
    return record(
        ChronologyAction.FIELD_CHANGED,
        incident_id=incident_id,
        entity_type='incident',
        entity_id=incident_id,
        summary=f'{field} changed',
        payload=payload,
        sensitive_payload=sensitive_payload,
        actor_id=actor_id,
        correlation_id=correlation_id,
        session=session,
        **kwargs)


def history(incident_id, newest_first=False, filters=None, session=None):
    """Read the chronology for an incident, oldest-first by default.

    `filters` may contain keys: action_type, severity, actor_user_id,
    entity_type, entity_id, intake_id.
    """
    sess = session or db.session
    query = sess.query(ChronologyEntry).filter(
        ChronologyEntry.incident_id == incident_id)
    for key in ('action_type', 'severity', 'actor_user_id', 'entity_type',
                'entity_id', 'intake_id'):
        if filters and filters.get(key) is not None:
            query = query.filter(getattr(ChronologyEntry, key) == filters[key])
    order = ChronologyEntry.sequence_no.desc() if newest_first \
        else ChronologyEntry.sequence_no.asc()
    return query.order_by(order).all()


def verify_chain(incident_id, session=None):
    """Recompute row hashes for an incident's entries; return True if intact."""
    sess = session or db.session
    entries = (sess.query(ChronologyEntry)
               .filter(ChronologyEntry.incident_id == incident_id)
               .order_by(ChronologyEntry.sequence_no.asc()).all())
    prior = None
    for entry in entries:
        expected = _hash_entry(prior, {
            'sequence_no': entry.sequence_no,
            'occurred_at_utc': entry.occurred_at_utc.isoformat()
            if entry.occurred_at_utc else None,
            'action_type': entry.action_type,
            'entity_type': entry.entity_type,
            'entity_id': entry.entity_id,
            'summary_text': entry.summary_text,
            'payload': entry.payload() or None,
            'actor_user_id': entry.actor_user_id,
            'actor_is_system': entry.actor_is_system,
        })
        if entry.row_hash != expected or entry.prior_entry_hash != prior:
            return False
        prior = entry.row_hash
    return True


@event.listens_for(ChronologyEntry, 'before_update')
def _chronology_no_update(mapper, connection, target):
    raise ChronologyImmutable(
        'chronology_entry is append-only: entries cannot be updated')


@event.listens_for(ChronologyEntry, 'before_delete')
def _chronology_no_delete(mapper, connection, target):
    raise ChronologyImmutable(
        'chronology_entry is append-only: entries cannot be deleted')
