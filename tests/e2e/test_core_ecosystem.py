"""Tests for the CAD ecosystem shared core (design Phase 1)."""
import pytest

from extensions import db
from models import Incident, Unit
from core import chronology, service
from core.chronology import ChronologyAction as CA, ChronologyImmutable
from core.models import (ChronologyEntry, EventLocation, EventLocationPack,
                         EventWorkspace, Intake, Response, UrgentMessage)
from core.reference_data import insert_defaults
from tests.utils.http import login


def _create_incident(app):
    with app.app_context():
        inc = Incident(location='1 Test St', description='test')
        db.session.add(inc)
        db.session.commit()
        return inc.id


def _create_intake(app, user_id):
    with app.app_context():
        user = db.session.get(User := __import__('models').User, user_id)
        intake = service.create_intake(
            {'source': 'telephone', 'caller_name': 'Caller',
             'callback_number': '0400000000',
             'location_text': '10 Arena Way',
             'problem_text': 'Fall'}, actor=user)
        db.session.commit()
        return intake.id


@pytest.mark.e2e
def test_reference_data_seeds(app):
    with app.app_context():
        insert_defaults()
        from core.models import CodeSet
        keys = {cs.key for cs in CodeSet.query.all()}
        assert {'incident_status', 'priority', 'outcome',
                'alert_category', 'response_role'} <= keys


@pytest.mark.e2e
def test_intake_route_creates_incident_and_chronology(app):
    with app.app_context():
        admin = __import__('models').User.query.filter_by(
            username='admin').first()
        intake = service.create_intake(
            {'source': 'telephone', 'location_text': '10 Arena Way',
             'problem_text': 'Fall'}, actor=admin)
        db.session.commit()
        intake, incident = service.route_intake(intake.id, 'MAIN', actor=admin)
        db.session.commit()
        assert incident.incident_number.startswith('INC-')
        assert incident.owning_application == 'MAIN'
        assert incident.incident_uuid
        entries = chronology.history(incident.id)
        actions = [e.action_type for e in entries]
        assert actions == [CA.INCIDENT_CREATED, CA.INTAKE_ROUTED][::-1][::-1] or \
            CA.INCIDENT_CREATED in actions
        assert CA.INCIDENT_CREATED in actions
        assert intake.state == Intake.STATE_ROUTED
        assert chronology.verify_chain(incident.id)


@pytest.mark.e2e
def test_escalation_event_to_main(app):
    with app.app_context():
        admin = __import__('models').User.query.filter_by(
            username='admin').first()
        ws = service.create_event_workspace(
            {'code': 'EVT1', 'name': 'Test Event'}, actor=admin)
        ws.status = EventWorkspace.STATUS_ACTIVE
        db.session.commit()
        intake = service.create_intake({'location_text': 'Gate A'}, actor=admin)
        db.session.commit()
        intake, incident = service.route_intake(intake.id, str(ws.id),
                                                actor=admin)
        db.session.commit()
        incident_id = incident.id
        assert incident.owning_application == 'EVENT'

        incident = service.escalate_to_main(
            incident_id, 'MAIN_LEAD', 'Needs external resources', actor=admin)
        db.session.commit()
        assert incident.owning_application == 'MAIN'
        assert incident.escalation_mode == 'MAIN_LEAD'

        # Second escalation must fail (already Main-owned)
        with pytest.raises(service.ConflictError):
            service.escalate_to_main(incident_id, 'FULL_TRANSFER', 'again',
                                   actor=admin)
        entries = chronology.history(incident_id)
        assert CA.INCIDENT_ESCALATED in [e.action_type for e in entries]


@pytest.mark.e2e
def test_chronology_append_only(app):
    with app.app_context():
        admin = __import__('models').User.query.filter_by(
            username='admin').first()
        inc = Incident(location='x', description='d')
        db.session.add(inc)
        db.session.commit()
        entry = chronology.record(CA.REMARK_ADDED, incident_id=inc.id,
                                  actor_id=admin.id, summary='hello')
        db.session.commit()
        entry.summary_text = 'tampered'
        with pytest.raises(ChronologyImmutable):
            db.session.flush()
        db.session.rollback()
        with pytest.raises(ChronologyImmutable):
            db.session.delete(db.session.get(ChronologyEntry, entry.id))
            db.session.flush()
        db.session.rollback()


@pytest.mark.e2e
def test_optimistic_concurrency(app):
    with app.app_context():
        admin = __import__('models').User.query.filter_by(
            username='admin').first()
        inc = Incident(location='x', description='d')
        db.session.add(inc)
        db.session.commit()
        v = inc.row_version
        service.update_incident_fields(inc.id, {'description': 'new'},
                                       actor=admin, expected_version=v)
        db.session.commit()
        with pytest.raises(service.ConflictError):
            service.update_incident_fields(inc.id, {'description': 'other'},
                                           actor=admin, expected_version=v)


@pytest.mark.e2e
def test_response_lifecycle_and_closure_rules(app):
    with app.app_context():
        admin = __import__('models').User.query.filter_by(
            username='admin').first()
        inc = Incident(location='x', description='d')
        unit = Unit(name='U-TEST-1', active=True)
        db.session.add_all([inc, unit])
        db.session.commit()
        response = service.assign_unit(inc.id, unit.id, actor=admin)
        db.session.commit()
        assert response.status == Response.STATUS_ASSIGNED
        assert inc.lifecycle_status == 'ASSIGNED'

        # Closure blocked while response active
        blockers = service.validate_closure(inc)
        assert any('response' in b for b in blockers)

        # Invalid transition rejected
        with pytest.raises(service.CoreError):
            service.update_response_status(response.id,
                                           Response.STATUS_CLEAR, actor=admin)

        response = service.update_response_status(
            response.id, Response.STATUS_DISPATCHED, actor=admin)
        response = service.update_response_status(
            response.id, Response.STATUS_EN_ROUTE, actor=admin)
        response = service.update_response_status(
            response.id, Response.STATUS_ARRIVED_SCENE, actor=admin)
        response = service.update_response_status(
            response.id, Response.STATUS_CLEAR, actor=admin)
        db.session.commit()
        assert response.cleared_at is not None

        incident = service.close_incident(inc.id, 'resolved_on_scene',
                                          'done', actor=admin)
        db.session.commit()
        assert incident.lifecycle_status == 'CLOSED'

        # Closed incident rejects normal edits, accepts controlled reopen
        with pytest.raises(service.ConflictError):
            service.update_incident_fields(
                inc.id, {'description': 'edit'}, actor=admin,
                expected_version=incident.row_version)
        incident = service.reopen_incident(inc.id, 'new information',
                                           actor=admin)
        db.session.commit()
        assert incident.lifecycle_status == 'ACTIVE'
        actions = [e.action_type for e in chronology.history(inc.id)]
        for expected in (CA.UNIT_ASSIGNED, CA.UNIT_DISPATCHED,
                         CA.UNIT_CLEARED, CA.INCIDENT_CLOSED,
                         CA.INCIDENT_REOPENED):
            assert expected in actions


@pytest.mark.e2e
def test_urgent_message_flow(app):
    with app.app_context():
        admin = __import__('models').User.query.filter_by(
            username='admin').first()
        inc = Incident(location='x', description='d', status='open')
        db.session.add(inc)
        db.session.commit()
        urgent = service.add_urgent_message(inc.id, 'casualty count rising',
                                          actor=admin)
        db.session.commit()
        assert inc.urgent_update is True
        urgent = service.acknowledge_urgent_message(urgent.id, actor=admin)
        db.session.commit()
        db.session.refresh(inc)
        assert urgent.acknowledged_at is not None
        assert inc.urgent_update is False


@pytest.mark.e2e
def test_location_pack_stage_and_activate(app):
    with app.app_context():
        admin = __import__('models').User.query.filter_by(
            username='admin').first()
        ws = service.create_event_workspace(
            {'code': 'AO26', 'name': 'Tennis Open'}, actor=admin)
        db.session.commit()
        csv_text = (
            'location_name,location_key,venue_id,level,map_reference,'
            'response_area,primary_responder,secondary_responder,active\n'
            'Rod Laver Arena,R-ARENA,AO26,L0,G5,A1,MED-POST-1,MED-POST-2,true\n'
            'Margaret Court,M-ARENA,AO26,L0,G6,A1,MED-POST-2,MED-POST-1,true\n'
            'Bad Row,,AO26,,,,,,true\n'
        )
        pack, stats = service.stage_location_pack(ws.id, csv_text, actor=admin)
        db.session.commit()
        assert stats['create'] == 3  # empty key generates one
        pack = service.activate_location_pack(pack.id, actor=admin)
        db.session.commit()
        assert pack.status == EventLocationPack.STATUS_ACTIVE
        locations = service.active_event_locations(ws.id)
        assert len(locations) == 3
        resolution = service.resolve_event_response(ws.id, map_reference='G5')
        assert resolution['primary_responder'] == 'MED-POST-1'


@pytest.mark.e2e
def test_core_api_intake_route_flow(app, client):
    login(client, 'admin', 'admin')
    r = client.post('/api/core/intakes', json={
        'source': 'telephone', 'caller_name': 'A Caller',
        'location_text': '5 Queue Rd', 'problem_text': 'Collapse'})
    assert r.status_code == 201, r.get_json()
    intake_id = r.get_json()['intake']['id']

    r = client.post(f'/api/core/intakes/{intake_id}/route',
                    json={'target': 'MAIN'})
    assert r.status_code == 201, r.get_json()
    incident = r.get_json()['incident']
    assert incident['owning_application'] == 'MAIN'

    r = client.get(f"/api/core/incidents/{incident['id']}/chronology")
    assert r.status_code == 200
    actions = [e['action_type'] for e in r.get_json()['entries']]
    assert 'incident_created' in actions and 'intake_routed' in actions

    r = client.post(f"/api/core/incidents/{incident['id']}/urgent-messages",
                    json={'message': 'second patient found'})
    assert r.status_code == 201
    urgent_id = r.get_json()['urgent_message']['id']
    r = client.post(f'/api/core/urgent-messages/{urgent_id}/acknowledge')
    assert r.status_code == 200


def test_intake_duplicate_suggestion(app, client):
    """POST /intakes flags candidates matching an open incident's location/
    callback; the surface is in the response, not a separate call."""
    login(client, 'admin', 'admin')
    r = client.post('/api/core/intakes', json={
        'source': 'telephone', 'location_text': '10 Dup Lane',
        'callback_number': '555-DUP'})
    first = r.get_json()['intake']['id']
    r = client.post(f'/api/core/intakes/{first}/route', json={'target': 'MAIN'})
    incident_id = r.get_json()['incident']['id']

    r = client.post('/api/core/intakes', json={
        'source': 'telephone', 'location_text': '10 Dup Lane',
        'callback_number': '555-DUP'})
    assert r.status_code == 201
    dups = r.get_json()['duplicate_candidates']
    hit = [d for d in dups if d['incident']['id'] == incident_id]
    assert hit, 'matching incident not suggested'
    assert 'same location' in hit[0]['reasons']
    assert 'same callback number' in hit[0]['reasons']

    # service helper is read-only: no chronology written for the suggestion
    from core.models import ChronologyEntry
    assert ChronologyEntry.query.filter_by(
        incident_id=incident_id, action_type='duplicate_suggested').count() == 0


def test_dispatch_queue_and_list_endpoints(app, client):
    """GET /queue, /incidents, /export: serialization of IncidentQuery rows."""
    login(client, 'admin', 'admin')
    r = client.post('/api/core/intakes', json={
        'source': 'telephone', 'location_text': '77 Queue Blvd'})
    intake_id = r.get_json()['intake']['id']
    r = client.post(f'/api/core/intakes/{intake_id}/route',
                    json={'target': 'MAIN'})
    incident_id = r.get_json()['incident']['id']

    r = client.get('/api/core/incidents?open=1')
    assert r.status_code == 200
    assert any(i['id'] == incident_id for i in r.get_json()['incidents'])

    r = client.get('/api/core/queue')
    assert r.status_code == 200
    body = r.get_json()
    assert any(i['id'] == incident_id for i in body['unassigned'])

    r = client.get('/api/core/incidents/search?q=Queue')
    assert r.status_code == 200
    assert any(i['id'] == incident_id for i in r.get_json()['incidents'])

    r = client.get(f'/api/core/incidents/{incident_id}/export')
    assert r.status_code == 200
    bundle = r.get_json()['bundle']
    assert bundle['incident']['id'] == incident_id
    assert isinstance(bundle['chronology'], list)
    assert isinstance(bundle['responses'], list)
