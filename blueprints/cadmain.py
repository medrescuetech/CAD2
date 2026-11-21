"""CAD Main console (Phase 1 MVP): dispatch queue + incident control."""
import logging
import os

from flask import Blueprint, current_app
from flask_login import login_required

from models import Permission
from utils.decorators import permission_required

logger = logging.getLogger(__name__)

bp = Blueprint('cadmain', __name__)


@bp.route('/cad-main')
@login_required
@permission_required(Permission.VIEW_INCIDENTS)
def index():
    map_enabled = (current_app.config.get('CAD_MAP_ENABLED') or
                   os.environ.get('CAD_MAP_ENABLED', '').lower()
                   in ('1', 'true', 'yes'))
    return current_app.custom_render_template(
        'cadmain/index.html', title='CAD Main', map_enabled=map_enabled)
