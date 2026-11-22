"""Event CAD screen (Phase 3): event workspaces, location packs, posts."""
import logging

from flask import Blueprint, current_app
from flask_login import login_required

logger = logging.getLogger(__name__)

bp = Blueprint('eventcad', __name__)


@bp.route('/event-cad')
@login_required
def index():
    return current_app.custom_render_template('eventcad/index.html',
                                              title='Event CAD')
