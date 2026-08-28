"""
User Blueprint

This module contains routes for user-specific operations:
- User profile management
- Notification preferences
- User settings
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import current_user, login_required
from models import User, NotificationPreference, db

bp = Blueprint('user', __name__)

@bp.route('/profile')
@login_required
def profile():
    """User profile page."""
    return current_app.custom_render_template('user/profile.html', user=current_user)

@bp.route('/preferences/notifications')
@login_required
def notification_preferences():
    """User notification preferences page."""
    return current_app.custom_render_template('user/notification_preferences.html')

@bp.route('/notifications')
@login_required
def notifications():
    """User notification center."""
    return current_app.custom_render_template('user/notifications.html')

@bp.route('/settings')
@login_required
def settings():
    """User settings page."""
    return current_app.custom_render_template('user/settings.html')
