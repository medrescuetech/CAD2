"""PCR integration sender (spec: PCR CAD integration API v0.1).

Pushes CAD jobs to https://pcr.akgmed.org/{client}/cad/v1 via the durable
outbox: every domain change enqueues a PENDING OutboxEvent inside the same
transaction, and `deliver_pending()` sends them in order, per job, with the
monotonic `seq`, Idempotency-Key and optional HMAC request signing the spec
requires. Configuration is entirely environment-driven so the connector is
inert until PCR_ENABLED=1.
"""
import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone

import requests

from extensions import db
from core.models import Intake, OutboxEvent, PcrJob, Response
from models import Incident, Unit

logger = logging.getLogger(__name__)

PCR_EVENT_PREFIX = 'pcr.'
EVT_JOB_UPDATE = PCR_EVENT_PREFIX + 'job_update'
EVT_STATUS = PCR_EVENT_PREFIX + 'status_event'
EVT_UNIT = PCR_EVENT_PREFIX + 'unit_update'
EVT_CANCEL = PCR_EVENT_PREFIX + 'cancel'

# Response.status -> PCR event type (spec 4.3)
STATUS_EVENT_TYPES = {
    Response.STATUS_DISPATCHED: 'dispatched',
    Response.STATUS_EN_ROUTE: 'mobile',
    Response.STATUS_ARRIVED_SCENE: 'at_scene',
    Response.STATUS_DEPARTED_SCENE: 'depart_scene',
    Response.STATUS_ARRIVED_DESTINATION: 'at_destination',
    Response.STATUS_CLEAR: 'clear',
    'STOOD_DOWN': 'stood_down',
}

PRIORITY_LABELS = {1: 'Priority 1', 2: 'Priority 2', 3: 'Priority 3',
                   4: 'Non-urgent'}

RETRYABLE_HTTP = {408, 429, 500, 502, 503}
BACKOFF_CAP_S = 300
JOB_TIMEOUT_S = 15


def config():
    return {
        'enabled': os.environ.get('PCR_ENABLED') == '1',
        'base_url': os.environ.get('PCR_BASE_URL',
                                   'https://pcr.akgmed.org').rstrip('/'),
        'client': os.environ.get('PCR_CLIENT', ''),
        'api_key': os.environ.get('PCR_API_KEY', ''),
        'require_signing': os.environ.get('PCR_REQUIRE_SIGNING') == '1',
        'timeout': int(os.environ.get('PCR_TIMEOUT_S', str(JOB_TIMEOUT_S))),
        'poll_seconds': int(os.environ.get('PCR_POLL_S', '5')),
    }


def _base(cfg):
    return f"{cfg['base_url']}/{cfg['client']}/cad/v1"


def _iso(dt):
    """ISO 8601 with offset, UTC (spec: never send naive local time)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


# ---------------------------------------------------------------- payload map

def job_for(incident, session=None):
    sess = session or db.session
    job = PcrJob.query.filter_by(incident_id=incident.id).first()
    if job is None:
        job = PcrJob(incident_id=incident.id, cad_job_id=incident.incident_uuid)
        sess.add(job)
        sess.flush()
    return job


def _intake_for(incident, session=None):
    sess = session or db.session
    return Intake.query.filter_by(incident_id=incident.id)\
        .order_by(Intake.created_at).first()


def _units_payload(incident):
    units = []
    for resp in Response.query.filter_by(incident_id=incident.id)\
            .filter(Response.status != Response.STATUS_CLEAR).all():
        unit = db.session.get(Unit, resp.unit_id) if resp.unit_id else None
        entry = {
            'callsign': (unit.name if unit else None) or
                        f'unit-{resp.unit_id}',
            'vehicle': unit.name if unit else None,
        }
        skill = getattr(unit, 'skill_set', None) if unit else None
        if skill:
            entry['skill_set'] = skill
        units.append({k: v for k, v in entry.items() if v is not None})
    return units[:10]


def job_payload(incident, seq, session=None):
    """PUT /jobs/{cad_job_id} body per spec section 5.1."""
    intake = _intake_for(incident, session)
    body = {
        'seq': seq,
        'incident_number': incident.incident_number or str(incident.id),
        'created_at': _iso(incident.created_at),
        'priority': PRIORITY_LABELS.get(
            getattr(incident, 'priority', None), 'Priority 3'),
        'case_given_as': (intake.problem_text if intake else None) or
                         incident.description or '',
        'event_name': incident.event_workspace.name
                      if getattr(incident, 'event_workspace', None) else None,
        'location': {
            'type': 'Event site' if incident.event_workspace_id
                    else 'Public place',
            'address': (intake.location_text if intake else None) or
                       incident.location,
            'lat': incident.latitude,
            'lon': incident.longitude,
            'access_notes': intake.operator_summary
                            if intake and intake.operator_summary else None,
        },
        'times': {
            'call_received': _iso(intake.created_at if intake
                                  else incident.created_at),
        },
        'units': _units_payload(incident),
    }
    if incident.event_workspace_id:
        body['special_event'] = 'Public event or mass gathering'
    if intake and getattr(intake, 'caller_name', None) and \
            os.environ.get('PCR_STORE_CALLER') == '1':
        body['caller'] = {'name': intake.caller_name,
                          'phone': intake.callback_number}
    body['location'] = {k: v for k, v in body['location'].items()
                        if v is not None}
    body['times'] = {k: v for k, v in body['times'].items() if v}
    return {k: v for k, v in body.items() if v is not None}


# --------------------------------------------------------------- enqueue API

def _enqueue(incident, event_type, payload, session=None,
             idempotency_key=None):
    sess = session or db.session
    event = OutboxEvent(
        event_type=event_type,
        occurred_at=datetime.utcnow(),
        source_application=incident.owning_application or 'MAIN',
        correlation_id=incident.incident_uuid,
        entity_type='incident',
        entity_id=str(incident.id),
        incident_id=incident.id,
        payload_json=json.dumps(payload, default=str),
        idempotency_key=idempotency_key,
    )
    sess.add(event)
    return event


def enqueue_job_update(incident, session=None):
    """Full-job PUT: bumps seq and queues the current snapshot."""
    if not config()['enabled']:
        return None
    job = job_for(incident, session)
    job.seq += 1
    job.status = 'PENDING'
    payload = job_payload(incident, job.seq, session)
    return _enqueue(incident, EVT_JOB_UPDATE, payload, session,
                    idempotency_key=f'pcr-job-{job.cad_job_id}-{job.seq}')


def enqueue_status_event(incident, status, at, unit_callsign=None,
                         destination=None, session=None):
    if not config()['enabled']:
        return None
    pcr_type = STATUS_EVENT_TYPES.get(status)
    if pcr_type is None:
        return None
    event_id = f'{incident.incident_uuid}-{status}'
    job = job_for(incident, session)
    job.seq += 1
    job.status = 'PENDING'
    payload = {'event_id': event_id, 'type': pcr_type, 'at': _iso(at),
               'seq': job.seq}
    if unit_callsign:
        payload['unit'] = unit_callsign
    if destination:
        payload['destination'] = destination
    return _enqueue(incident, EVT_STATUS, payload, session,
                    idempotency_key=f'pcr-evt-{event_id}-{job.seq}')


def enqueue_cancel(incident, reason, at, session=None):
    if not config()['enabled']:
        return None
    job = job_for(incident, session)
    job.seq += 1
    job.status = 'PENDING'
    return _enqueue(incident, EVT_CANCEL,
                    {'seq': job.seq,
                     'reason': reason or 'Cancelled by control',
                     'at': _iso(at)},
                    session,
                    idempotency_key=f'pcr-cancel-{job.cad_job_id}-{job.seq}')


# ----------------------------------------------------------------- delivery

def _sign(cfg, raw_body):
    ts = str(int(time.time()))
    secret = cfg['api_key'].split('_', 2)[-1]
    sig = hmac.new(secret.encode(), f'{ts}.{raw_body}'.encode(),
                   hashlib.sha256).hexdigest()
    return {'X-PCR-Timestamp': ts, 'X-PCR-Signature': f'v1={sig}'}


def _request(cfg, method, path, body, idempotency_key=None):
    raw = json.dumps(body) if body is not None else ''
    headers = {
        'Authorization': f"Bearer {cfg['api_key']}",
        'Accept': 'application/json',
    }
    if body is not None:
        headers['Content-Type'] = 'application/json'
    if idempotency_key:
        headers['Idempotency-Key'] = idempotency_key
    if cfg['require_signing']:
        headers.update(_sign(cfg, raw))
    url = _base(cfg) + path
    return requests.request(method, url, data=raw or None, headers=headers,
                            timeout=cfg['timeout'])


def _next_attempt(retry_count):
    delay = min(2 ** retry_count, BACKOFF_CAP_S)
    return datetime.utcnow() + timedelta(seconds=delay)


def _mark_failed(event, msg):
    event.retry_count += 1
    event.last_error = msg[:500]
    event.next_attempt_at = _next_attempt(event.retry_count)


def _deliver_one(cfg, event):
    """Send one outbox event; returns 'ok' | 'drop' | 'retry' | 'dead'."""
    payload = event.payload()
    job = PcrJob.query.filter_by(incident_id=event.incident_id).first()
    cad_job_id = job.cad_job_id if job else payload.get('cad_job_id')
    try:
        if event.event_type == EVT_JOB_UPDATE:
            r = _request(cfg, 'PUT', f'/jobs/{cad_job_id}', payload)
        elif event.event_type == EVT_STATUS:
            r = _request(cfg, 'POST', f'/jobs/{cad_job_id}/events', payload,
                         idempotency_key=event.idempotency_key)
        elif event.event_type == EVT_UNIT:
            callsign = payload.get('callsign', '')
            r = _request(cfg, 'PUT',
                         f'/jobs/{cad_job_id}/units/{callsign}', payload)
        elif event.event_type == EVT_CANCEL:
            r = _request(cfg, 'POST', f'/jobs/{cad_job_id}/cancel', payload)
        else:
            return 'drop'
    except requests.RequestException as exc:
        _mark_failed(event, f'network: {exc}')
        return 'retry'

    code = r.status_code
    if code in (200, 201):
        data = r.json() if r.content else {}
        if job is not None:
            job.delivered_seq = max(job.delivered_seq,
                                    payload.get('seq') or 0)
            case = (data.get('pcr') or {}).get('case_id')
            if case:
                job.pcr_case_id = case
            job.status = 'SYNCED'
            job.last_error = None
        return 'ok'
    if code == 409 and 'stale_sequence' in r.text:
        # PCR already holds a newer seq: drop per spec
        return 'drop'
    if code in RETRYABLE_HTTP:
        _mark_failed(event, f'http {code}: {r.text[:200]}')
        return 'retry'
    _mark_failed(event, f'http {code}: {r.text[:200]}')
    return 'dead'


def deliver_pending(limit=50, session=None):
    """Deliver due PENDING pcr.* events, in creation order (spec: ordered
    per job; sequential here which trivially preserves it)."""
    sess = session or db.session
    cfg = config()
    now = datetime.utcnow()
    events = (OutboxEvent.query
              .filter(OutboxEvent.event_type.like(PCR_EVENT_PREFIX + '%'),
                      OutboxEvent.status == OutboxEvent.STATUS_PENDING)
              .filter((OutboxEvent.next_attempt_at.is_(None)) |
                      (OutboxEvent.next_attempt_at <= now))
              .order_by(OutboxEvent.id)
              .limit(limit).all())
    sent = retried = dropped = dead = 0
    for event in events:
        outcome = _deliver_one(cfg, event)
        if outcome == 'ok' or outcome == 'drop':
            event.status = OutboxEvent.STATUS_PUBLISHED
            event.published_at = datetime.utcnow()
            sent += 1
            dropped += outcome == 'drop'
        elif outcome == 'retry':
            retried += 1
        else:
            event.status = OutboxEvent.STATUS_FAILED
            dead += 1
    if events:
        sess.commit()
    return {'sent': sent, 'retried': retried, 'dropped': dropped,
            'dead': dead}


def queue_stats(session=None):
    sess = session or db.session
    pending = (OutboxEvent.query
               .filter(OutboxEvent.event_type.like(PCR_EVENT_PREFIX + '%'),
                       OutboxEvent.status == OutboxEvent.STATUS_PENDING)
               .order_by(OutboxEvent.created_at).all())
    oldest = pending[0].created_at if pending else None
    return {
        'enabled': config()['enabled'],
        'depth': len(pending),
        'oldest_pending_age_s': int(
            (datetime.utcnow() - oldest).total_seconds()) if oldest else 0,
        'jobs': [j.to_dict() for j in PcrJob.query.all()],
    }


def reconcile(session=None):
    """Nightly: ask PCR for jobs updated recently and re-send any whose
    stored last_seq is behind ours (spec section 9)."""
    cfg = config()
    since = _iso(datetime.now(timezone.utc) - timedelta(hours=26))
    r = _request(cfg, 'GET', f'/jobs?updated_since={since}&limit=500', None)
    r.raise_for_status()
    resent = 0
    for entry in r.json().get('jobs', []):
        job = PcrJob.query.filter_by(
            cad_job_id=entry.get('cad_job_id')).first()
        if job and job.seq > (entry.get('last_seq') or 0):
            enqueue_job_update(job.incident, session)
            resent += 1
    return {'resent': resent}


# -------------------------------------------------------------------- worker

def run_worker(app, stop_flag=None):
    """Background loop; started by app.py when PCR_ENABLED=1."""
    poll = config()['poll_seconds']
    with app.app_context():
        logger.info('PCR delivery worker started (poll=%ss)', poll)
        while not (stop_flag and stop_flag.is_set()):
            try:
                deliver_pending()
            except Exception:
                logger.exception('PCR delivery pass failed')
            time.sleep(poll)
