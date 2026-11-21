"""CAD Core API: shared services for Call Taker, Event and Main.

All endpoints perform state changes through core.service, which wraps each
command, its chronology entries and its outbox events in one transaction.
"""
import logging

from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user

from extensions import db
from models import Permission, Incident
from utils.decorators import permission_required
from core import service
from core.models import (Alert, EventLocationPack, EventWorkspace, Intake,
                         OperatorAssignment, Response, UrgentMessage,
                         ChronologyEntry)
from core import chronology

logger = logging.getLogger(__name__)

core_api = Blueprint('core_api', __name__)


def _err(exc):
    return jsonify({'success': False, 'message': str(exc)}), exc.status


def _commit():
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.exception('core_api commit failed')
        return jsonify({'success': False, 'message': f'Commit failed: {e}'}), 500
    return None


# ---------------------------------------------------------------------------
# Event workspaces and location packs
# ---------------------------------------------------------------------------

@core_api.route('/events', methods=['GET'])
@login_required
def list_events():
    status = request.args.get('status')
    query = EventWorkspace.query
    if status:
        query = query.filter_by(status=status)
    return jsonify({'success': True,
                    'events': [w.to_dict() for w in
                               query.order_by(EventWorkspace.name).all()]})


@core_api.route('/events', methods=['POST'])
@login_required
@permission_required(Permission.ADMIN)
def create_event():
    data = request.get_json(silent=True) or {}
    if not data.get('code') or not data.get('name'):
        return jsonify({'success': False,
                        'message': 'code and name are required'}), 400
    try:
        workspace = service.create_event_workspace(data, actor=current_user)
    except service.CoreError as e:
        return _err(e)
    commit_err = _commit()
    if commit_err:
        return commit_err
    return jsonify({'success': True, 'event': workspace.to_dict()}), 201


@core_api.route('/events/<int:event_id>/status', methods=['POST'])
@login_required
@permission_required(Permission.ADMIN)
def set_event_status(event_id):
    data = request.get_json(silent=True) or {}
    try:
        workspace = service.set_event_workspace_status(
            event_id, data.get('status'), actor=current_user)
    except service.CoreError as e:
        return _err(e)
    commit_err = _commit()
    if commit_err:
        return commit_err
    return jsonify({'success': True, 'event': workspace.to_dict()})


@core_api.route('/events/<int:event_id>/packs/import', methods=['POST'])
@login_required
@permission_required(Permission.ADMIN)
def import_location_pack(event_id):
    """Stage a CSV location pack for validation and preview."""
    data = request.get_json(silent=True) or {}
    csv_text = data.get('csv')
    if csv_text is None and request.files:
        uploaded = request.files.get('file')
        if uploaded is not None:
            csv_text = uploaded.read().decode('utf-8', errors='replace')
            data['filename'] = uploaded.filename
    if not csv_text:
        return jsonify({'success': False,
                        'message': 'Provide CSV content as {"csv": ...} or '
                                   'a file upload'}), 400
    try:
        pack, stats = service.stage_location_pack(
            event_id, csv_text, source_filename=data.get('filename'),
            actor=current_user)
    except service.CoreError as e:
        return _err(e)
    commit_err = _commit()
    if commit_err:
        return commit_err
    return jsonify({'success': True, 'pack': pack.to_dict(),
                    'preview': stats}), 201


@core_api.route('/packs/<int:pack_id>', methods=['GET'])
@login_required
def get_pack(pack_id):
    pack = EventLocationPack.query.get_or_404(pack_id)
    result = pack.to_dict()
    result['locations'] = [loc.to_dict() for loc in pack.locations.all()]
    return jsonify({'success': True, 'pack': result})


@core_api.route('/packs/<int:pack_id>/activate', methods=['POST'])
@login_required
@permission_required(Permission.ADMIN)
def activate_pack(pack_id):
    try:
        pack = service.activate_location_pack(pack_id, actor=current_user)
    except service.CoreError as e:
        return _err(e)
    commit_err = _commit()
    if commit_err:
        return commit_err
    return jsonify({'success': True, 'pack': pack.to_dict()})


@core_api.route('/events/<int:event_id>/locations', methods=['GET'])
@login_required
def event_locations(event_id):
    locations = service.active_event_locations(event_id)
    return jsonify({'success': True,
                    'locations': [loc.to_dict() for loc in locations]})


@core_api.route('/events/<int:event_id>/resolve-response', methods=['GET'])
@login_required
def resolve_response(event_id):
    result = service.resolve_event_response(
        event_id,
        map_reference=request.args.get('map_reference'),
        response_area=request.args.get('response_area'),
        event_location_id=request.args.get('event_location_id', type=int))
    db.session.commit()
    return jsonify({'success': True, 'resolution': result})


# ---------------------------------------------------------------------------
# Intakes (CAD - Call Taker)
# ---------------------------------------------------------------------------

@core_api.route('/intakes', methods=['GET'])
@login_required
def list_intakes():
    state = request.args.get('state')
    query = Intake.query
    if state:
        query = query.filter_by(state=state)
    return jsonify({'success': True,
                    'intakes': [i.to_dict() for i in
                                query.order_by(Intake.created_at.desc())
                                .limit(200).all()]})


@core_api.route('/intakes', methods=['POST'])
@login_required
@permission_required(Permission.CREATE_INCIDENT)
def create_intake():
    data = request.get_json(silent=True) or {}
    intake = service.create_intake(data, actor=current_user)
    commit_err = _commit()
    if commit_err:
        return commit_err
    return jsonify({'success': True, 'intake': intake.to_dict()}), 201


@core_api.route('/intakes/<int:intake_id>', methods=['GET'])
@login_required
def get_intake(intake_id):
    intake = Intake.query.get_or_404(intake_id)
    result = intake.to_dict()
    result['alerts'] = [a.to_dict() for a in
                        service.applicable_alerts(intake)]
    return jsonify({'success': True, 'intake': result})


@core_api.route('/intakes/<int:intake_id>', methods=['PATCH'])
@login_required
@permission_required(Permission.CREATE_INCIDENT)
def update_intake(intake_id):
    data = request.get_json(silent=True) or {}
    try:
        intake = service.update_intake(
            intake_id, data, actor=current_user,
            expected_version=data.get('row_version'))
    except service.CoreError as e:
        return _err(e)
    commit_err = _commit()
    if commit_err:
        return commit_err
    return jsonify({'success': True, 'intake': intake.to_dict()})


@core_api.route('/intakes/<int:intake_id>/route', methods=['POST'])
@login_required
@permission_required(Permission.CREATE_INCIDENT)
def route_intake(intake_id):
    data = request.get_json(silent=True) or {}
    target = data.get('target')
    if not target:
        return jsonify({'success': False,
                        'message': "target is required ('MAIN' or an "
                                   'event workspace id)'}), 400
    try:
        intake, incident = service.route_intake(
            intake_id, target, actor=current_user)
    except service.CoreError as e:
        return _err(e)
    commit_err = _commit()
    if commit_err:
        return commit_err
    return jsonify({'success': True, 'intake': intake.to_dict(),
                    'incident': incident.to_dict()}), 201


@core_api.route('/intakes/<int:intake_id>/close', methods=['POST'])
@login_required
@permission_required(Permission.CREATE_INCIDENT)
def close_intake(intake_id):
    data = request.get_json(silent=True) or {}
    try:
        intake = service.close_intake(
            intake_id, data.get('state'), reason=data.get('reason'),
            actor=current_user)
    except service.CoreError as e:
        return _err(e)
    commit_err = _commit()
    if commit_err:
        return commit_err
    return jsonify({'success': True, 'intake': intake.to_dict()})


@core_api.route('/intakes/<int:intake_id>/transfer', methods=['POST'])
@login_required
@permission_required(Permission.CREATE_INCIDENT)
def transfer_intake(intake_id):
    intake = Intake.query.get_or_404(intake_id)
    data = request.get_json(silent=True) or {}
    try:
        transfer = service.offer_transfer(
            intake, data.get('to_user_id'), actor=current_user,
            reason=data.get('reason'), handover_note=data.get('handover_note'))
    except service.CoreError as e:
        return _err(e)
    commit_err = _commit()
    if commit_err:
        return commit_err
    return jsonify({'success': True, 'transfer': transfer.to_dict()}), 201


# ---------------------------------------------------------------------------
# Incidents: updates, urgent messages, escalation, transfer, closure
# ---------------------------------------------------------------------------

@core_api.route('/incidents/<int:incident_id>', methods=['PATCH'])
@login_required
@permission_required(Permission.EDIT_INCIDENT)
def update_incident(incident_id):
    data = request.get_json(silent=True) or {}
    expected_version = data.pop('row_version', None)
    if expected_version is None:
        return jsonify({'success': False,
                        'message': 'row_version is required for optimistic '
                                   'concurrency'}), 400
    try:
        incident = service.update_incident_fields(
            incident_id, data, actor=current_user,
            expected_version=expected_version,
            source_application=data.pop('_source_application', 'MAIN'))
    except service.CoreError as e:
        return _err(e)
    commit_err = _commit()
    if commit_err:
        return commit_err
    return jsonify({'success': True, 'incident': incident.to_dict()})


@core_api.route('/incidents/<int:incident_id>/alerts', methods=['GET'])
@login_required
def incident_alerts(incident_id):
    incident = Incident.query.get_or_404(incident_id)
    return jsonify({'success': True, 'alerts': [
        a.to_dict() for a in service.applicable_alerts(incident)]})


@core_api.route('/incidents/<int:incident_id>/chronology', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_INCIDENTS)
def incident_chronology(incident_id):
    Incident.query.get_or_404(incident_id)
    newest_first = request.args.get('order', 'asc') == 'desc'
    filters = {}
    for key in ('action_type', 'severity', 'entity_type'):
        if request.args.get(key):
            filters[key] = request.args.get(key)
    if request.args.get('actor_user_id'):
        filters['actor_user_id'] = request.args.get('actor_user_id', type=int)
    if request.args.get('intake_id'):
        filters['intake_id'] = request.args.get('intake_id', type=int)
    include_sensitive = current_user.can(Permission.ADMIN) and \
        request.args.get('include_sensitive') == 'true'
    entries = chronology.history(incident_id, newest_first=newest_first,
                                 filters=filters)
    return jsonify({'success': True,
                    'filtered': bool(filters),
                    'entries': [e.to_dict(include_sensitive=include_sensitive)
                                for e in entries]})


@core_api.route('/incidents/<int:incident_id>/urgent-messages',
                methods=['POST'])
@login_required
def add_urgent_message(incident_id):
    data = request.get_json(silent=True) or {}
    if not data.get('message'):
        return jsonify({'success': False,
                        'message': 'message is required'}), 400
    try:
        urgent = service.add_urgent_message(
            incident_id, data['message'], actor=current_user,
            intake_id=data.get('intake_id'))
    except service.CoreError as e:
        return _err(e)
    commit_err = _commit()
    if commit_err:
        return commit_err
    return jsonify({'success': True, 'urgent_message': urgent.to_dict()}), 201


@core_api.route('/urgent-messages/<int:urgent_id>/acknowledge',
                methods=['POST'])
@login_required
def acknowledge_urgent(urgent_id):
    try:
        urgent = service.acknowledge_urgent_message(urgent_id,
                                                  actor=current_user)
    except service.CoreError as e:
        return _err(e)
    commit_err = _commit()
    if commit_err:
        return commit_err
    return jsonify({'success': True, 'urgent_message': urgent.to_dict()})


@core_api.route('/incidents/<int:incident_id>/escalate', methods=['POST'])
@login_required
@permission_required(Permission.EDIT_INCIDENT)
def escalate_incident(incident_id):
    data = request.get_json(silent=True) or {}
    try:
        incident = service.escalate_to_main(
            incident_id, data.get('mode'), data.get('reason'),
            actor=current_user)
    except service.CoreError as e:
        return _err(e)
    commit_err = _commit()
    if commit_err:
        return commit_err
    return jsonify({'success': True, 'incident': incident.to_dict()})


@core_api.route('/incidents/<int:incident_id>/responses', methods=['POST'])
@login_required
@permission_required(Permission.ASSIGN_UNITS)
def assign_unit(incident_id):
    data = request.get_json(silent=True) or {}
    if not data.get('unit_id'):
        return jsonify({'success': False,
                        'message': 'unit_id is required'}), 400
    try:
        response = service.assign_unit(
            incident_id, data['unit_id'], actor=current_user,
            role=data.get('role', 'primary'))
    except service.CoreError as e:
        return _err(e)
    commit_err = _commit()
    if commit_err:
        return commit_err
    return jsonify({'success': True, 'response': response.to_dict()}), 201


@core_api.route('/responses/<int:response_id>/status', methods=['PATCH'])
@login_required
@permission_required(Permission.ASSIGN_UNITS)
def update_response_status(response_id):
    data = request.get_json(silent=True) or {}
    if not data.get('status'):
        return jsonify({'success': False,
                        'message': 'status is required'}), 400
    try:
        response = service.update_response_status(
            response_id, data['status'], actor=current_user,
            reason=data.get('reason'),
            retrospective=bool(data.get('retrospective')))
    except service.CoreError as e:
        return _err(e)
    commit_err = _commit()
    if commit_err:
        return commit_err
    return jsonify({'success': True, 'response': response.to_dict()})


@core_api.route('/incidents/<int:incident_id>/transfer', methods=['POST'])
@login_required
@permission_required(Permission.EDIT_INCIDENT)
def transfer_incident(incident_id):
    incident = Incident.query.get_or_404(incident_id)
    data = request.get_json(silent=True) or {}
    try:
        transfer = service.offer_transfer(
            incident, data.get('to_user_id'), actor=current_user,
            reason=data.get('reason'), handover_note=data.get('handover_note'))
    except service.CoreError as e:
        return _err(e)
    commit_err = _commit()
    if commit_err:
        return commit_err
    return jsonify({'success': True, 'transfer': transfer.to_dict()}), 201


@core_api.route('/transfers/<int:transfer_id>/resolve', methods=['POST'])
@login_required
def resolve_transfer(transfer_id):
    data = request.get_json(silent=True) or {}
    try:
        transfer = service.resolve_transfer(
            transfer_id, bool(data.get('accept')), actor=current_user)
    except service.CoreError as e:
        return _err(e)
    commit_err = _commit()
    if commit_err:
        return commit_err
    return jsonify({'success': True, 'transfer': transfer.to_dict()})


@core_api.route('/incidents/<int:incident_id>/duplicates', methods=['GET'])
@login_required
def duplicate_candidates(incident_id):
    try:
        matches = service.suggest_duplicates(
            incident_id,
            window_minutes=request.args.get('window_minutes', 60, type=int))
    except service.CoreError as e:
        return _err(e)
    db.session.commit()
    return jsonify({'success': True, 'candidates': matches})


@core_api.route('/incidents/<int:incident_id>/link', methods=['POST'])
@login_required
@permission_required(Permission.EDIT_INCIDENT)
def link_incident(incident_id):
    data = request.get_json(silent=True) or {}
    try:
        link = service.link_incidents(
            incident_id, data.get('related_incident_id'),
            data.get('relationship', 'related'), actor=current_user,
            reason=data.get('reason'))
    except service.CoreError as e:
        return _err(e)
    commit_err = _commit()
    if commit_err:
        return commit_err
    return jsonify({'success': True, 'link_id': link.id}), 201


@core_api.route('/incidents/<int:incident_id>/cancel-duplicate',
                methods=['POST'])
@login_required
@permission_required(Permission.EDIT_INCIDENT)
def cancel_duplicate(incident_id):
    data = request.get_json(silent=True) or {}
    if not data.get('surviving_incident_id'):
        return jsonify({'success': False,
                        'message': 'surviving_incident_id is required'}), 400
    try:
        incident = service.cancel_as_duplicate(
            incident_id, data['surviving_incident_id'], actor=current_user,
            reason=data.get('reason'))
    except service.CoreError as e:
        return _err(e)
    commit_err = _commit()
    if commit_err:
        return commit_err
    return jsonify({'success': True, 'incident': incident.to_dict()})


@core_api.route('/incidents/<int:incident_id>/close', methods=['POST'])
@login_required
@permission_required(Permission.CLOSE_INCIDENT)
def close_incident(incident_id):
    data = request.get_json(silent=True) or {}
    try:
        incident = service.close_incident(
            incident_id, data.get('outcome'), data.get('closure_note'),
            actor=current_user)
    except service.CoreError as e:
        return _err(e)
    commit_err = _commit()
    if commit_err:
        return commit_err
    return jsonify({'success': True, 'incident': incident.to_dict()})


@core_api.route('/incidents/<int:incident_id>/reopen', methods=['POST'])
@login_required
@permission_required(Permission.EDIT_INCIDENT)
def reopen_incident(incident_id):
    data = request.get_json(silent=True) or {}
    try:
        incident = service.reopen_incident(
            incident_id, data.get('reason'), actor=current_user)
    except service.CoreError as e:
        return _err(e)
    commit_err = _commit()
    if commit_err:
        return commit_err
    return jsonify({'success': True, 'incident': incident.to_dict()})


@core_api.route('/alerts/<int:alert_id>/acknowledge', methods=['POST'])
@login_required
def acknowledge_alert(alert_id):
    data = request.get_json(silent=True) or {}
    try:
        ack = service.acknowledge_alert(
            alert_id, data.get('incident_id'), data.get('result'),
            actor=current_user, note=data.get('note'))
    except service.CoreError as e:
        return _err(e)
    commit_err = _commit()
    if commit_err:
        return commit_err
    return jsonify({'success': True,
                    'acknowledgement': ack.to_dict()}), 201


# ---------------------------------------------------------------------------
# Code sets and outbox (read-only views)
# ---------------------------------------------------------------------------

@core_api.route('/code-sets', methods=['GET'])
@login_required
def list_code_sets():
    from core.models import CodeSet
    return jsonify({'success': True,
                    'code_sets': [cs.to_dict() for cs in
                                  CodeSet.query.filter_by(active=True).all()]})


@core_api.route('/outbox', methods=['GET'])
@login_required
@permission_required(Permission.ADMIN)
def list_outbox():
    from core.models import OutboxEvent
    status = request.args.get('status', 'PENDING')
    events = (OutboxEvent.query.filter_by(status=status)
              .order_by(OutboxEvent.occurred_at.asc()).limit(200).all())
    return jsonify({'success': True,
                    'events': [e.to_dict() for e in events]})


# ---------------------------------------------------------------------------
# PCR integration (spec: PCR CAD integration API v0.1)
# ---------------------------------------------------------------------------

@core_api.route('/integrations/pcr/status', methods=['GET'])
@login_required
@permission_required(Permission.ADMIN)
def pcr_status():
    from core import pcr
    return jsonify({'success': True, **pcr.queue_stats()})


@core_api.route('/integrations/pcr/flush', methods=['POST'])
@login_required
@permission_required(Permission.ADMIN)
def pcr_flush():
    """Deliver due pending PCR outbox messages now."""
    from core import pcr
    return jsonify({'success': True, **pcr.deliver_pending(limit=200)})


@core_api.route('/integrations/pcr/reconcile', methods=['POST'])
@login_required
@permission_required(Permission.ADMIN)
def pcr_reconcile():
    """Pull PCR's job list and re-send any job whose seq lags (spec §9)."""
    from core import pcr
    try:
        return jsonify({'success': True, **pcr.reconcile()})
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 502


# ---------------------------------------------------------------------------
# Queues, search and export (Phase 1 main-MVP surface)
# ---------------------------------------------------------------------------

@core_api.route('/incidents', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_INCIDENTS)
def list_incidents():
    """Incident queue with filters.

    Query params: lifecycle_status, owning_application, event_workspace_id,
    priority, open (1 => not closed/cancelled), limit (default 50, max 200).
    """
    query = Incident.query
    if request.args.get('open') == '1':
        query = query.filter(Incident.lifecycle_status.notin_(
            ('CLOSED', 'CANCELLED', 'DUPLICATE_CANCELLED')))
    for arg, col in (('lifecycle_status', Incident.lifecycle_status),
                     ('owning_application', Incident.owning_application),
                     ('event_workspace_id', Incident.event_workspace_id),
                     ('priority', Incident.priority)):
        value = request.args.get(arg)
        if value:
            query = query.filter(col == value)
    limit = min(int(request.args.get('limit', 50)), 200)
    incidents = query.order_by(Incident.created_at.desc()).limit(limit).all()
    return jsonify({'success': True,
                    'incidents': [i.to_dict() for i in incidents],
                    'count': len(incidents)})


@core_api.route('/incidents/search', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_INCIDENTS)
def search_incidents():
    """Free-text search over number, location, caller, description."""
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify({'success': False,
                        'message': 'q must be at least 2 characters'}), 400
    like = f'%{q}%'
    incidents = (Incident.query.filter(
        db.or_(Incident.incident_number.like(like),
               Incident.location.like(like),
               Incident.caller.like(like),
               Incident.description.like(like)))
        .order_by(Incident.created_at.desc()).limit(50).all())
    return jsonify({'success': True,
                    'incidents': [i.to_dict() for i in incidents]})


@core_api.route('/queue', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_INCIDENTS)
def dispatch_queue():
    """Dispatcher's queue summary: unassigned + in-flight per workspace."""
    unassigned = (Incident.query
                  .filter(Incident.lifecycle_status.in_(('NEW', 'PENDING')))
                  .order_by(Incident.priority.desc(),
                            Incident.created_at.asc()).all())
    inflight = (Incident.query
                .filter(Incident.lifecycle_status.in_(
                    ('ASSIGNED', 'DISPATCHED', 'EN_ROUTE', 'ON_SCENE')))
                .order_by(Incident.created_at.asc()).all())
    urgent = Incident.query.filter_by(urgent_update=True).filter(
        Incident.lifecycle_status.notin_(
            ('CLOSED', 'CANCELLED', 'DUPLICATE_CANCELLED'))).all()
    return jsonify({'success': True,
                    'unassigned': [i.to_dict() for i in unassigned],
                    'in_flight': [i.to_dict() for i in inflight],
                    'urgent': [i.to_dict() for i in urgent]})


@core_api.route('/incidents/<int:incident_id>/export', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_INCIDENTS)
def export_incident(incident_id):
    """Full incident bundle: record, chronology, responses, intake, messages."""
    incident = Incident.query.get_or_404(incident_id)
    from core.models import Response, UrgentMessage
    bundle = {
        'incident': incident.to_dict(),
        'chronology': [e.to_dict() for e in
                       chronology.history(incident_id, newest_first=False)],
        'responses': [r.to_dict() for r in
                      Response.query.filter_by(incident_id=incident_id).all()],
        'intakes': [i.to_dict() for i in
                    Intake.query.filter_by(incident_id=incident_id).all()],
        'urgent_messages': [u.to_dict() for u in
                            UrgentMessage.query.filter_by(
                                incident_id=incident_id).all()],
    }
    return jsonify({'success': True, 'bundle': bundle})
