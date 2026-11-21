"""Server-side canonical identifier generation (design section 7).

Incident numbers use INC-YYYYMMDD-NNNN generated from a daily sequence in
the operational timezone. Event workspaces get EVT-<code>-NNNN aliases; the
immutable incident_id/uuid never carries meaning.
"""
from datetime import datetime

from extensions import db
from core.models import NumberSequence


def next_value(scope, session=None):
    """Atomically increment and return the next value for a scope.

    The sequence row is locked where the backend supports SELECT ... FOR
    UPDATE; on SQLite single-writer semantics already serialize increments.
    """
    sess = session or db.session
    row = (sess.query(NumberSequence)
           .filter_by(scope=scope)
           .with_for_update()
           .first())
    if row is None:
        row = NumberSequence(scope=scope, last_value=0)
        sess.add(row)
        sess.flush()
    row.last_value += 1
    sess.flush()
    return row.last_value


def new_incident_number(now=None, session=None):
    """Generate the next INC-YYYYMMDD-NNNN incident number (server time)."""
    now = now or datetime.utcnow()
    seq = next_value(f'INC:{now.strftime("%Y%m%d")}', session=session)
    return f'INC-{now.strftime("%Y%m%d")}-{seq:04d}'


def new_event_case_alias(event_code, session=None):
    """Generate the next EVT-<code>-NNNN alias for an event workspace."""
    seq = next_value(f'EVT:{event_code}', session=session)
    return f'EVT-{event_code}-{seq:04d}'
