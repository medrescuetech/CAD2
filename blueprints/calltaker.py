"""Call Taker screen (Phase 2): intake capture + routing over /api/core."""
import logging

from flask import Blueprint, current_app
from flask_login import login_required

from models import Permission
from utils.decorators import permission_required

logger = logging.getLogger(__name__)

bp = Blueprint('calltaker', __name__)


@bp.route('/call-taker')
@login_required
@permission_required(Permission.CREATE_INCIDENT)
def index():
    return current_app.custom_render_template('calltaker/index.html',
                                              title='Call Taker')
