"""CAD reporting screen (Phase 4): filtered incident list + CSV exports."""
import logging

from flask import Blueprint, current_app
from flask_login import login_required

from models import Permission
from utils.decorators import permission_required

logger = logging.getLogger(__name__)

bp = Blueprint('cadreports', __name__)


@bp.route('/cad-reports')
@login_required
@permission_required(Permission.VIEW_INCIDENTS)
def index():
    return current_app.custom_render_template('cadreports/index.html',
                                              title='CAD Reports')
