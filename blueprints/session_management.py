"""
Session Management Blueprint

This module provides endpoints for managing user sessions,
including viewing active sessions, force logout, and session timeouts.
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from models import User, db, Role, Permission
from utils.decorators import permission_required
from utils.session_manager import get_active_sessions, force_logout_session, update_session_activity
from utils.audit_log import log_audit_event, AuditCategory, AuditSeverity
from utils.security import secure_endpoint

bp = Blueprint('sessions', __name__)

@bp.before_request
def update_activity():
    """Update session activity timestamp on each request."""
    update_session_activity()

@bp.route('/active', methods=['GET'])
@login_required
@permission_required(Permission.ADMIN)
@secure_endpoint(limit="15/minute")
def active_sessions():
    """Get all active sessions."""
    try:
        sessions = get_active_sessions()
        
        return jsonify({
            'success': True,
            'sessions': sessions,
            'count': len(sessions)
        })
    except Exception as e:
        current_app.logger.error(f"Error retrieving active sessions: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error retrieving active sessions: {str(e)}"
        }), 500

@bp.route('/user/<int:user_id>', methods=['GET'])
@login_required
@permission_required(Permission.ADMIN)
@secure_endpoint(limit="15/minute")
def user_sessions(user_id):
    """Get active sessions for a specific user."""
    try:
        user = User.query.get_or_404(user_id)
        
        # Check permission: admin or self
        if not current_user.is_administrator() and current_user.id != user_id:
            log_audit_event(
                category=AuditCategory.SECURITY,
                action="Unauthorized session access attempt",
                severity=AuditSeverity.WARNING,
                user_id=current_user.id,
                details={'target_user_id': user_id}
            )
            return jsonify({
                'success': False,
                'message': "You do not have permission to view this user's sessions"
            }), 403
        
        sessions = get_active_sessions(user_id)
        
        return jsonify({
            'success': True,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email
            },
            'sessions': sessions,
            'count': len(sessions)
        })
    except Exception as e:
        current_app.logger.error(f"Error retrieving user sessions: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error retrieving user sessions: {str(e)}"
        }), 500

@bp.route('/logout/<string:session_id>', methods=['POST'])
@login_required
@permission_required(Permission.ADMIN)
@secure_endpoint(limit="10/minute")
def force_logout(session_id):
    """Force logout a session by session ID."""
    try:
        # Find the user associated with this session
        user = User.query.filter_by(session_id=session_id).first()
        
        if not user:
            return jsonify({
                'success': False,
                'message': "Session not found or already terminated"
            }), 404
        
        # Check permission: admin or self
        if not current_user.is_administrator() and current_user.id != user.id:
            log_audit_event(
                category=AuditCategory.SECURITY,
                action="Unauthorized session termination attempt",
                severity=AuditSeverity.WARNING,
                user_id=current_user.id,
                details={'target_user_id': user.id, 'session_id': session_id}
            )
            return jsonify({
                'success': False,
                'message': "You do not have permission to terminate this session"
            }), 403
        
        # Force logout the session
        success = force_logout_session(session_id)
        
        if success:
            log_audit_event(
                category=AuditCategory.SECURITY,
                action="Forced session logout",
                severity=AuditSeverity.INFO,
                user_id=current_user.id,
                details={'target_user_id': user.id, 'session_id': session_id}
            )
            
            return jsonify({
                'success': True,
                'message': f"Session for user {user.username} has been terminated"
            })
        else:
            return jsonify({
                'success': False,
                'message': "Failed to terminate session"
            }), 500
    except Exception as e:
        current_app.logger.error(f"Error terminating session: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error terminating session: {str(e)}"
        }), 500

@bp.route('/logout/all', methods=['POST'])
@login_required
@permission_required(Permission.ADMIN)
@secure_endpoint(limit="5/minute")
def force_logout_all():
    """Force logout all sessions except current user's session."""
    try:
        # Get all active sessions except current user
        users_with_sessions = User.query.filter(User.session_id.isnot(None)).filter(User.id != current_user.id).all()
        
        terminated_count = 0
        failed_count = 0
        
        for user in users_with_sessions:
            if force_logout_session(user.session_id):
                terminated_count += 1
            else:
                failed_count += 1
        
        log_audit_event(
            category=AuditCategory.SECURITY,
            action="Forced all sessions logout",
            severity=AuditSeverity.WARNING,
            user_id=current_user.id,
            details={
                'terminated_count': terminated_count,
                'failed_count': failed_count
            }
        )
        
        return jsonify({
            'success': True,
            'message': f"Terminated {terminated_count} sessions, failed to terminate {failed_count} sessions",
            'terminated_count': terminated_count,
            'failed_count': failed_count
        })
    except Exception as e:
        current_app.logger.error(f"Error terminating all sessions: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error terminating all sessions: {str(e)}"
        }), 500

@bp.route('/my-sessions', methods=['GET'])
@login_required
@secure_endpoint(limit="15/minute")
def my_sessions():
    """Get the current user's active sessions."""
    try:
        sessions = get_active_sessions(current_user.id)
        
        return jsonify({
            'success': True,
            'sessions': sessions,
            'count': len(sessions)
        })
    except Exception as e:
        current_app.logger.error(f"Error retrieving your sessions: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error retrieving your sessions: {str(e)}"
        }), 500

@bp.route('/logout/my-session/<string:session_id>', methods=['POST'])
@login_required
@secure_endpoint(limit="10/minute")
def logout_my_session(session_id):
    """Logout a specific session of the current user."""
    try:
        # Verify the session belongs to the current user
        user = User.query.filter_by(session_id=session_id).first()
        
        if not user or user.id != current_user.id:
            log_audit_event(
                category=AuditCategory.SECURITY,
                action="Unauthorized session termination attempt",
                severity=AuditSeverity.WARNING,
                user_id=current_user.id,
                details={'session_id': session_id}
            )
            return jsonify({
                'success': False,
                'message': "Invalid session or not your session"
            }), 403
        
        # Force logout the session
        success = force_logout_session(session_id)
        
        if success:
            log_audit_event(
                category=AuditCategory.SECURITY,
                action="User terminated own session",
                severity=AuditSeverity.INFO,
                user_id=current_user.id,
                details={'session_id': session_id}
            )
            
            return jsonify({
                'success': True,
                'message': "Your session has been terminated"
            })
        else:
            return jsonify({
                'success': False,
                'message': "Failed to terminate session"
            }), 500
    except Exception as e:
        current_app.logger.error(f"Error terminating your session: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error terminating your session: {str(e)}"
        }), 500

@bp.route('/logout/my-other-sessions', methods=['POST'])
@login_required
@secure_endpoint(limit="5/minute")
def logout_my_other_sessions():
    """Logout all other sessions of the current user except the current session."""
    try:
        current_session_id = request.cookies.get('session_id') or ''
        users_with_sessions = User.query.filter_by(id=current_user.id).filter(User.session_id != current_session_id).all()
        
        terminated_count = 0
        for user in users_with_sessions:
            if force_logout_session(user.session_id):
                terminated_count += 1
        
        log_audit_event(
            category=AuditCategory.SECURITY,
            action="User terminated other sessions",
            severity=AuditSeverity.INFO,
            user_id=current_user.id,
            details={
                'terminated_count': terminated_count
            }
        )
        
        return jsonify({
            'success': True,
            'message': f"Terminated {terminated_count} other sessions",
            'terminated_count': terminated_count
        })
    except Exception as e:
        current_app.logger.error(f"Error terminating other sessions: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error terminating other sessions: {str(e)}"
        }), 500
