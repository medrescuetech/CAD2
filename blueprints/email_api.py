"""
Email and Notification API Blueprint

This module defines API endpoints for:
- Email testing
- Email log management
- Notification preferences
- Notification management
"""

from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from models import Permission, EmailLog, NotificationPreference, Notification, AuditLog, db
from blueprints.admin import permission_required
from datetime import datetime, timedelta
import logging
from services.email_service import EmailService
from services.notification_service import NotificationService

# Create a blueprint for email and notification API endpoints
bp = Blueprint('email_api', __name__)

# Logger
logger = logging.getLogger('email_api')

# Email API endpoints
@bp.route('/email/test', methods=['POST'])
@login_required
@permission_required(Permission.TEST_EMAIL_SERVICE)
def test_email():
    """
    Test the email service configuration.
    
    Request JSON: 
    {
        "recipient": "email@example.com"
    }
    
    Response:
    {
        "success": true/false,
        "message": "Success/error message"
    }
    """
    data = request.get_json()
    if not data or 'recipient' not in data:
        return jsonify({'success': False, 'message': 'Recipient email is required'}), 400
        
    recipient = data['recipient']
    include_html = data.get('include_html', True)
    
    success, message = EmailService.send_test_email(recipient, include_html)
    
    # Create an audit log entry
    audit_log = AuditLog(
        user_id=current_user.id,
        action='test_email',
        resource_type='email',
        resource_id=None,
        details=f"Tested email service to recipient: {recipient}. Result: {message}"
    )
    db.session.add(audit_log)
    db.session.commit()
    
    return jsonify({
        'success': success,
        'message': message
    })

@bp.route('/email/logs', methods=['GET'])
@login_required
@permission_required(Permission.MANAGE_NOTIFICATIONS)
def get_email_logs():
    """
    Get email logs with optional filtering.
    
    Query parameters:
    - status: Filter by status (queued, sent, failed, sent_test)
    - days: Number of days to look back (default 7)
    - page: Page number (default 1)
    - per_page: Items per page (default 20)
    
    Response:
    {
        "success": true,
        "logs": [list of email log objects],
        "total": total count,
        "page": current page,
        "pages": total pages
    }
    """
    # Get query parameters
    status = request.args.get('status')
    days = int(request.args.get('days', 7))
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    
    # Build query
    query = EmailLog.query
    
    # Apply filters
    if status:
        query = query.filter(EmailLog.status == status)
        
    if days:
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        query = query.filter(EmailLog.created_at >= cutoff_date)
        
    # Order by most recent first
    query = query.order_by(EmailLog.created_at.desc())
    
    # Paginate results
    pagination = query.paginate(page=page, per_page=per_page)
    
    return jsonify({
        'success': True,
        'logs': [log.to_dict() for log in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'pages': pagination.pages
    })

# Notification API endpoints
@bp.route('/notifications/settings', methods=['GET'])
@login_required
def get_notification_settings():
    """
    Get the current user's notification preferences.
    
    Response:
    {
        "success": true,
        "settings": notification settings object
    }
    """
    preferences = NotificationPreference.query.filter_by(user_id=current_user.id).first()
    
    if not preferences:
        # Create default preferences if they don't exist
        preferences = NotificationPreference(user_id=current_user.id)
        db.session.add(preferences)
        db.session.commit()
        
    return jsonify({
        'success': True,
        'settings': preferences.to_dict()
    })

@bp.route('/notifications/settings', methods=['PUT'])
@login_required
def update_notification_settings():
    """
    Update the current user's notification preferences.
    
    Request JSON:
    {
        "app_incident_created": true/false,
        "app_incident_updated": true/false,
        "app_incident_closed": true/false,
        "app_unit_assigned": true/false,
        "app_unit_status_changed": true/false,
        "email_incident_created": true/false,
        "email_incident_updated": true/false,
        "email_incident_closed": true/false,
        "email_unit_assigned": true/false,
        "email_unit_status_changed": true/false,
        "audio_incident_created": true/false,
        "audio_incident_closed": true/false,
        "audio_unit_assigned": true/false
    }
    
    Response:
    {
        "success": true,
        "settings": updated notification settings object
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'No data provided'}), 400
        
    # Get or create preferences
    preferences = NotificationPreference.query.filter_by(user_id=current_user.id).first()
    if not preferences:
        preferences = NotificationPreference(user_id=current_user.id)
        db.session.add(preferences)
        
    # Update preferences
    for key, value in data.items():
        if hasattr(preferences, key):
            setattr(preferences, key, bool(value))
            
    db.session.commit()
    
    return jsonify({
        'success': True,
        'settings': preferences.to_dict()
    })

@bp.route('/notifications', methods=['GET'])
@login_required
def get_user_notifications():
    """
    Get notifications for the current user.
    
    Query parameters:
    - unread_only: If true, only return unread notifications (default false)
    - page: Page number (default 1)
    - per_page: Items per page (default 20)
    
    Response:
    {
        "success": true,
        "notifications": [list of notification objects],
        "total": total count,
        "unread_count": count of unread notifications,
        "page": current page,
        "pages": total pages
    }
    """
    # Get query parameters
    unread_only = request.args.get('unread_only', 'false').lower() == 'true'
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    
    # Build query
    query = Notification.query.filter_by(user_id=current_user.id)
    
    if unread_only:
        query = query.filter_by(is_read=False)
        
    # Get unread count for badge
    unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    
    # Order by most recent first
    query = query.order_by(Notification.created_at.desc())
    
    # Paginate results
    pagination = query.paginate(page=page, per_page=per_page)
    
    return jsonify({
        'success': True,
        'notifications': [notification.to_dict() for notification in pagination.items],
        'total': pagination.total,
        'unread_count': unread_count,
        'page': pagination.page,
        'pages': pagination.pages
    })

@bp.route('/notifications/mark-read', methods=['POST'])
@login_required
def mark_notifications_read():
    """
    Mark notifications as read.
    
    Request JSON:
    {
        "notification_ids": [list of notification IDs] (optional),
        "mark_all": true/false (optional)
    }
    
    Response:
    {
        "success": true,
        "message": "Success message",
        "count": number of notifications marked as read
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'No data provided'}), 400
        
    notification_ids = data.get('notification_ids', [])
    mark_all = data.get('mark_all', False)
    
    if not notification_ids and not mark_all:
        return jsonify({'success': False, 'message': 'Either notification_ids or mark_all must be provided'}), 400
        
    # Mark specific notifications as read
    count = 0
    if notification_ids:
        # Only allow marking the user's own notifications
        notifications = Notification.query.filter(
            Notification.id.in_(notification_ids),
            Notification.user_id == current_user.id,
            Notification.is_read == False
        ).all()
        
        for notification in notifications:
            notification.is_read = True
            count += 1
            
    # Mark all user's notifications as read
    elif mark_all:
        count = Notification.query.filter_by(
            user_id=current_user.id,
            is_read=False
        ).update({'is_read': True})
        
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f"Marked {count} notifications as read",
        'count': count
    })

# Notification Preference API endpoints
@bp.route('/notification/preferences', methods=['GET'])
@login_required
def get_notification_preferences():
    """
    Get the current user's notification preferences.
    
    Returns:
        JSON of user notification preferences
    """
    prefs = NotificationPreference.get_or_create(current_user.id)
    
    # Convert to dictionary for JSON
    prefs_dict = {
        'app_notifications_enabled': prefs.app_notifications_enabled,
        'app_incident_created': prefs.app_incident_created,
        'app_incident_updated': prefs.app_incident_updated,
        'app_incident_closed': prefs.app_incident_closed,
        'app_unit_assigned': prefs.app_unit_assigned,
        'app_unit_status_changed': prefs.app_unit_status_changed,
        'app_system_notifications': prefs.app_system_notifications,
        
        'email_notifications_enabled': prefs.email_notifications_enabled,
        'email_incident_created': prefs.email_incident_created,
        'email_incident_updated': prefs.email_incident_updated,
        'email_incident_closed': prefs.email_incident_closed,
        'email_unit_assigned': prefs.email_unit_assigned,
        'email_unit_status_changed': prefs.email_unit_status_changed,
        'email_system_notifications': prefs.email_system_notifications,
        
        'sound_notifications_enabled': prefs.sound_notifications_enabled,
        'sound_incident_created': prefs.sound_incident_created,
        'sound_incident_updated': prefs.sound_incident_updated,
        'sound_incident_closed': prefs.sound_incident_closed,
        'sound_unit_assigned': prefs.sound_unit_assigned,
        'sound_unit_status_changed': prefs.sound_unit_status_changed
    }
    
    return jsonify({
        'success': True,
        'preferences': prefs_dict
    })

@bp.route('/notification/preferences', methods=['PUT'])
@login_required
def update_notification_preferences():
    """
    Update the current user's notification preferences.
    
    Expected JSON payload:
    {
        "app_notifications_enabled": true,
        "app_incident_created": true,
        ...and other preference fields
    }
    
    Returns:
        JSON with success status and message
    """
    if not request.is_json:
        return jsonify({'success': False, 'message': 'Request must be JSON'}), 400
    
    data = request.get_json()
    prefs = NotificationPreference.get_or_create(current_user.id)
    
    # Update app notification preferences
    if 'app_notifications_enabled' in data:
        prefs.app_notifications_enabled = bool(data['app_notifications_enabled'])
    if 'app_incident_created' in data:
        prefs.app_incident_created = bool(data['app_incident_created'])
    if 'app_incident_updated' in data:
        prefs.app_incident_updated = bool(data['app_incident_updated'])
    if 'app_incident_closed' in data:
        prefs.app_incident_closed = bool(data['app_incident_closed'])
    if 'app_unit_assigned' in data:
        prefs.app_unit_assigned = bool(data['app_unit_assigned'])
    if 'app_unit_status_changed' in data:
        prefs.app_unit_status_changed = bool(data['app_unit_status_changed'])
    if 'app_system_notifications' in data:
        prefs.app_system_notifications = bool(data['app_system_notifications'])
    
    # Update email notification preferences
    if 'email_notifications_enabled' in data:
        prefs.email_notifications_enabled = bool(data['email_notifications_enabled'])
    if 'email_incident_created' in data:
        prefs.email_incident_created = bool(data['email_incident_created'])
    if 'email_incident_updated' in data:
        prefs.email_incident_updated = bool(data['email_incident_updated'])
    if 'email_incident_closed' in data:
        prefs.email_incident_closed = bool(data['email_incident_closed'])
    if 'email_unit_assigned' in data:
        prefs.email_unit_assigned = bool(data['email_unit_assigned'])
    if 'email_unit_status_changed' in data:
        prefs.email_unit_status_changed = bool(data['email_unit_status_changed'])
    if 'email_system_notifications' in data:
        prefs.email_system_notifications = bool(data['email_system_notifications'])
    
    # Update sound notification preferences
    if 'sound_notifications_enabled' in data:
        prefs.sound_notifications_enabled = bool(data['sound_notifications_enabled'])
    if 'sound_incident_created' in data:
        prefs.sound_incident_created = bool(data['sound_incident_created'])
    if 'sound_incident_updated' in data:
        prefs.sound_incident_updated = bool(data['sound_incident_updated'])
    if 'sound_incident_closed' in data:
        prefs.sound_incident_closed = bool(data['sound_incident_closed'])
    if 'sound_unit_assigned' in data:
        prefs.sound_unit_assigned = bool(data['sound_unit_assigned'])
    if 'sound_unit_status_changed' in data:
        prefs.sound_unit_status_changed = bool(data['sound_unit_status_changed'])
    
    # Save changes
    try:
        db.session.commit()
        
        # Log the change
        AuditLog.create(
            action="notification_preferences_updated",
            user_id=current_user.id,
            description=f"User updated notification preferences",
            target_id=prefs.id,
            target_type="notification_preferences"
        )
        
        return jsonify({
            'success': True,
            'message': 'Notification preferences updated successfully'
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating notification preferences: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error updating preferences: {str(e)}'
        }), 500

@bp.route("/notification/preferences-alt", methods=["PUT"])
@login_required
def update_notification_preferences_alt():
    """Update the user's notification preferences."""
    # Get the JSON data from the request
    data = request.get_json()
    
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400
    
    # Get the user's notification preferences
    prefs = NotificationPreference.get_or_create(current_user.id)
    
    # Update the preferences - app notifications
    if "app_notifications" in data:
        app_data = data["app_notifications"]
        prefs.app_enabled = app_data.get("enabled", prefs.app_enabled)
        prefs.app_notify_incident_created = app_data.get("incident_created", prefs.app_notify_incident_created)
        prefs.app_notify_incident_updated = app_data.get("incident_updated", prefs.app_notify_incident_updated)
        prefs.app_notify_incident_closed = app_data.get("incident_closed", prefs.app_notify_incident_closed)
        prefs.app_notify_unit_assigned = app_data.get("unit_assigned", prefs.app_notify_unit_assigned)
        prefs.app_notify_unit_cleared = app_data.get("unit_cleared", prefs.app_notify_unit_cleared)
        prefs.app_notify_system_events = app_data.get("system_events", prefs.app_notify_system_events)
    
    # Update the preferences - email notifications
    if "email_notifications" in data:
        email_data = data["email_notifications"]
        prefs.email_enabled = email_data.get("enabled", prefs.email_enabled)
        prefs.email_notify_incident_created = email_data.get("incident_created", prefs.email_notify_incident_created)
        prefs.email_notify_incident_updated = email_data.get("incident_updated", prefs.email_notify_incident_updated)
        prefs.email_notify_incident_closed = email_data.get("incident_closed", prefs.email_notify_incident_closed)
        prefs.email_notify_unit_assigned = email_data.get("unit_assigned", prefs.email_notify_unit_assigned)
        prefs.email_notify_unit_cleared = email_data.get("unit_cleared", prefs.email_notify_unit_cleared)
        prefs.email_notify_system_events = email_data.get("system_events", prefs.email_notify_system_events)
    
    # Update the preferences - sound notifications
    if "sound_notifications" in data:
        sound_data = data["sound_notifications"]
        prefs.sound_enabled = sound_data.get("enabled", prefs.sound_enabled)
        prefs.sound_notify_incident_created = sound_data.get("incident_created", prefs.sound_notify_incident_created)
        prefs.sound_notify_incident_updated = sound_data.get("incident_updated", prefs.sound_notify_incident_updated)
        prefs.sound_notify_incident_closed = sound_data.get("incident_closed", prefs.sound_notify_incident_closed)
        prefs.sound_notify_unit_assigned = sound_data.get("unit_assigned", prefs.sound_notify_unit_assigned)
        prefs.sound_notify_unit_cleared = sound_data.get("unit_cleared", prefs.sound_notify_unit_cleared)
        prefs.sound_notify_system_events = sound_data.get("system_events", prefs.sound_notify_system_events)
    
    # Save the changes
    db.session.commit()
    
    return jsonify({"success": True, "message": "Notification preferences updated successfully"})

# Notification API Endpoints

@bp.route("/notifications", methods=["GET"])
@login_required
def get_notifications():
    """Get a paginated list of notifications for the current user."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    notification_type = request.args.get("type", None)
    
    # Query notifications
    query = Notification.query.filter_by(user_id=current_user.id)
    
    # Filter by type if specified
    if notification_type:
        query = query.filter_by(notification_type=notification_type)
    
    # Order by created_at descending (newest first)
    query = query.order_by(Notification.created_at.desc())
    
    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    notifications = pagination.items
    
    # Format notifications
    formatted_notifications = []
    for notification in notifications:
        formatted_notifications.append({
            "id": notification.id,
            "title": notification.title,
            "message": notification.message,
            "type": notification.notification_type,
            "read": notification.read,
            "created_at": notification.created_at.isoformat(),
            "reference_id": notification.reference_id,
            "reference_type": notification.reference_type
        })
    
    return jsonify({
        "success": True,
        "notifications": formatted_notifications,
        "has_more": pagination.has_next,
        "total": pagination.total
    })

@bp.route("/notifications/<int:notification_id>/read", methods=["PUT"])
@login_required
def mark_notification_read(notification_id):
    """Mark a notification as read."""
    notification = Notification.query.get_or_404(notification_id)
    
    # Ensure the notification belongs to the current user
    if notification.user_id != current_user.id:
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    # Mark as read
    notification.read = True
    db.session.commit()
    
    return jsonify({"success": True, "message": "Notification marked as read"})

@bp.route("/notifications/read-all", methods=["PUT"])
@login_required
def mark_all_notifications_read():
    """Mark all notifications as read for the current user."""
    Notification.query.filter_by(user_id=current_user.id, read=False).update({"read": True})
    db.session.commit()
    
    return jsonify({"success": True, "message": "All notifications marked as read"})

@bp.route("/notifications/unread-count", methods=["GET"])
@login_required
def get_unread_notification_count():
    """Get the count of unread notifications for the current user."""
    count = Notification.query.filter_by(user_id=current_user.id, read=False).count()
    
    return jsonify({"success": True, "count": count})
