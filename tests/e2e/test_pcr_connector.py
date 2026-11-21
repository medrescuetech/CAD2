"""Tests for the PCR outbound connector (spec: PCR CAD integration API v0.1)."""
import os
from unittest.mock import patch

import pytest

from extensions import db
from models import Incident, Unit
from core import pcr, service
from core.models import OutboxEvent, PcrJob, Response


@pytest.fixture
def pcr_enabled():
    os.environ['PCR_ENABLED'] = '1'
    os.environ['PCR_CLIENT'] = 'testclient'
    os.environ['PCR_API_KEY'] = 'pcrk_k1_secret'
    yield
    for k in ('PCR_ENABLED', 'PCR_CLIENT', 'PCR_API_KEY'):
        os.environ.pop(k, None)


def _incident(app, admin, via_route=True):
    with app.app_context():
        if via_route:
            intake = service.create_intake(
                {'location_text': '1 Test St', 'problem_text': 'Chest pain',
                 'caller_name': 'A Caller', 'callback_number': '0400000000'},
                actor=admin)
            db.session.commit()
            intake, incident = service.route_intake(intake.id, 'MAIN',
                                                    actor=admin)
            db.session.commit()
            return intake.id, incident.id
        inc = Incident(location='x', description='d')
        db.session.add(inc)
        db.session.commit()
        return None, inc.id


@pytest.mark.e2e
def test_enqueue_job_update_increments_seq(app, pcr_enabled):
    with app.app_context():
        admin = __import__('models').User.query.filter_by(
            username='admin').first()
        _, inc_id = _incident(app, admin)
        job = PcrJob.query.filter_by(incident_id=inc_id).one()
        assert job.cad_job_id == Incident.query.get(inc_id).incident_uuid
        assert job.seq == 1
        events = OutboxEvent.query.filter_by(
            event_type=pcr.EVT_JOB_UPDATE, incident_id=inc_id).all()
        assert len(events) == 1
        payload = events[0].payload()
        assert payload['seq'] == 1
        assert payload['location']['address'] == '1 Test St'
        assert payload['times']['call_received'].endswith('+00:00')
        assert payload['case_given_as'] == 'Chest pain'

        service.update_incident_fields(
            inc_id, {'description': 'updated'}, actor=admin,
            expected_version=Incident.query.get(inc_id).row_version)
        db.session.commit()
        db.session.refresh(job)
        assert job.seq == 2


@pytest.mark.e2e
def test_status_events_and_cancel(app, pcr_enabled):
    with app.app_context():
        admin = __import__('models').User.query.filter_by(
            username='admin').first()
        _, inc_id = _incident(app, admin)
        unit = Unit(name='Event Amb 1', active=True)
        db.session.add(unit)
        db.session.commit()
        resp = service.assign_unit(inc_id, unit.id, actor=admin)
        db.session.commit()
        service.update_response_status(resp.id, Response.STATUS_DISPATCHED,
                                       actor=admin)
        db.session.commit()
        evt = OutboxEvent.query.filter_by(
            event_type=pcr.EVT_STATUS, incident_id=inc_id).one()
        payload = evt.payload()
        assert payload['type'] == 'dispatched'
        assert payload['unit'] == 'Event Amb 1'
        assert payload['at'].endswith('+00:00')

        service.cancel_as_duplicate(inc_id, inc_id if False else
                                    _second_incident(app), actor=admin)
        db.session.commit()
        assert OutboxEvent.query.filter_by(
            event_type=pcr.EVT_CANCEL, incident_id=inc_id).count() == 1


def _second_incident(app):
    admin = __import__('models').User.query.filter_by(
        username='admin').first()
    intake = service.create_intake({'location_text': 'y'}, actor=admin)
    db.session.commit()
    _, inc = service.route_intake(intake.id, 'MAIN', actor=admin)
    db.session.commit()
    return inc.id


class _Resp:
    def __init__(self, code, body=None):
        self.status_code = code
        self._body = body or {}
        self.content = bool(body is not None)
        self.text = __import__('json').dumps(self._body)

    def json(self):
        return self._body


@pytest.mark.e2e
def test_deliver_pending_marks_published(app, pcr_enabled):
    with app.app_context():
        admin = __import__('models').User.query.filter_by(
            username='admin').first()
        _, inc_id = _incident(app, admin)
        with patch('core.pcr.requests.request',
                   return_value=_Resp(201, {'ok': True, 'pcr': {
                       'case_id': 'ACM-26-0143'}})) as mock_req:
            stats = pcr.deliver_pending()
        assert stats['sent'] >= 1
        assert OutboxEvent.query.filter_by(
            event_type=pcr.EVT_JOB_UPDATE, incident_id=inc_id,
            status=OutboxEvent.STATUS_PUBLISHED).count() >= 1
        job = PcrJob.query.filter_by(incident_id=inc_id).one()
        assert job.delivered_seq == 1
        assert job.pcr_case_id == 'ACM-26-0143'
        assert job.status == 'SYNCED'
        call = mock_req.call_args
        assert call.args[0] == 'PUT'
        assert call.args[1].endswith(
            f'/testclient/cad/v1/jobs/{job.cad_job_id}')
        assert call.kwargs['headers']['Authorization'].startswith(
            'Bearer pcrk_')


@pytest.mark.e2e
def test_deliver_stale_sequence_drops(app, pcr_enabled):
    with app.app_context():
        admin = __import__('models').User.query.filter_by(
            username='admin').first()
        _, inc_id = _incident(app, admin)
        with patch('core.pcr.requests.request',
                   return_value=_Resp(409, {'error': 'stale_sequence'})):
            stats = pcr.deliver_pending()
        assert stats['dropped'] >= 1
        event = OutboxEvent.query.filter_by(
            event_type=pcr.EVT_JOB_UPDATE, incident_id=inc_id).order_by(
            OutboxEvent.id.desc()).first()
        assert event.status == OutboxEvent.STATUS_PUBLISHED


@pytest.mark.e2e
def test_deliver_retryable_error_backs_off(app, pcr_enabled):
    from requests import ConnectionError as CE
    with app.app_context():
        admin = __import__('models').User.query.filter_by(
            username='admin').first()
        _, inc_id = _incident(app, admin)
        with patch('core.pcr.requests.request', side_effect=CE('down')):
            stats = pcr.deliver_pending()
        assert stats['retried'] >= 1
        event = OutboxEvent.query.filter_by(
            event_type=pcr.EVT_JOB_UPDATE, incident_id=inc_id).one()
        assert event.status == OutboxEvent.STATUS_PENDING
        assert event.retry_count == 1
        assert event.next_attempt_at is not None


@pytest.mark.e2e
def test_disabled_by_default(app):
    """Without PCR_ENABLED the connector is a no-op."""
    os.environ.pop('PCR_ENABLED', None)
    with app.app_context():
        admin = __import__('models').User.query.filter_by(
            username='admin').first()
        intake = service.create_intake({'location_text': 'x'}, actor=admin)
        db.session.commit()
        _, incident = service.route_intake(intake.id, 'MAIN', actor=admin)
        db.session.commit()
        assert OutboxEvent.query.filter(
            OutboxEvent.event_type.like('pcr.%'),
            OutboxEvent.incident_id == incident.id).count() == 0
        assert PcrJob.query.filter_by(incident_id=incident.id).count() == 0
