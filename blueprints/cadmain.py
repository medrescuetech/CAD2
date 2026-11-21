"""CAD Main console (Phase 1 MVP): dispatch queue + incident control."""
import logging

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
    return current_app.custom_render_template('cadmain/index.html',
                                              title='CAD Main')
