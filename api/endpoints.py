from flask import Blueprint, jsonify, request, current_app, url_for
from datetime import datetime
from flask_login import current_user, login_required
from models import Notification, NotificationPreference, User, Permission
from extensions import db

api_endpoints = Blueprint('api_endpoints', __name__)

# Authentication decorator
def auth_required(f):
    """Decorator to check if user is authenticated."""
    @login_required
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function

# Permission check decorator
def permission_required(permission):
    """Decorator to check if user has required permission."""
    def decorator(f):
        @auth_required
        def decorated_function(*args, **kwargs):
            if not current_user.role.has_permission(permission):
                return jsonify({'error': 'Permission denied'}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Original sample endpoints
@api_endpoints.route('/incidents/active')
def active_incidents():
    # TODO: Implement actual incident data retrieval
    return jsonify([
        {
            'id': 1,
            'type': 'Medical Emergency',
            'location': 'Main St & 1st Ave',
            'timestamp': datetime.utcnow().isoformat(),
            'status': 'Active'
        }
    ])

@api_endpoints.route('/units')
def available_units():
    # TODO: Implement actual unit data retrieval
    return jsonify([
        {
            'id': 101,
            'type': 'Ambulance',
            'location': 'Station 1',
            'status': 'Available'
        }
    ])

@api_endpoints.route('/pickup-points')
def pickup_points():
    # TODO: Implement actual pickup point data retrieval
    return jsonify([
        {
            'id': 201,
            'name': 'Main Hospital',
            'location': '123 Medical Dr',
            'capacity': 10
        }
    ])

# =========== NOTIFICATION API ENDPOINTS ===========

@api_endpoints.route('/notifications', methods=['GET'])
@auth_required
def get_notifications():
    """Get notifications for the current user with pagination and filtering."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status')
    
    # Query notifications for the current user
    query = Notification.query.filter_by(user_id=current_user.id)
    
    # Apply status filter if provided
    if status:
        query = query.filter_by(status=status)
        
    # Order by most recent first
    query = query.order_by(Notification.created_at.desc())
    
    # Paginate results
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Prepare response
    notifications = [n.to_dict() for n in paginated.items]
    
    return jsonify({
        'notifications': notifications,
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': paginated.total,
            'pages': paginated.pages,
            'has_next': paginated.has_next,
            'has_prev': paginated.has_prev
        },
        'unread_count': Notification.query.filter_by(
            user_id=current_user.id,
            is_read=False
        ).count()
    })

@api_endpoints.route('/notifications/unread-count', methods=['GET'])
@auth_required
def get_unread_count():
    """Get count of unread notifications for the current user."""
    unread_count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()
    
    return jsonify({'count': unread_count})

@api_endpoints.route('/notifications/<int:notification_id>', methods=['GET'])
@auth_required
def get_notification(notification_id):
    """Get a specific notification."""
    notification = Notification.query.filter_by(
        id=notification_id,
        user_id=current_user.id
    ).first_or_404(description='Notification not found')
    
    return jsonify(notification.to_dict())

@api_endpoints.route('/notifications/<int:notification_id>/read', methods=['POST'])
@auth_required
def mark_notification_read(notification_id):
    """Mark a notification as read."""
    notification = Notification.query.filter_by(
        id=notification_id,
        user_id=current_user.id
    ).first_or_404(description='Notification not found')
    
    notification.mark_as_read()
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': 'Notification marked as read',
        'notification': notification.to_dict()
    })

@api_endpoints.route('/notifications/mark-all-read', methods=['POST'])
@auth_required
def mark_all_notifications_read():
    """Mark all notifications as read for the current user."""
    notifications = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).all()
    
    for notification in notifications:
        notification.mark_as_read()
        
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': 'All notifications marked as read',
        'count': len(notifications)
    })

@api_endpoints.route('/notifications/<int:notification_id>/archive', methods=['POST'])
@auth_required
def archive_notification(notification_id):
    """Archive a notification."""
    notification = Notification.query.filter_by(
        id=notification_id,
        user_id=current_user.id
    ).first_or_404(description='Notification not found')
    
    notification.archive()
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': 'Notification archived',
        'notification': notification.to_dict()
    })

@api_endpoints.route('/notifications/<int:notification_id>', methods=['DELETE'])
@auth_required
def delete_notification(notification_id):
    """Delete a notification."""
    notification = Notification.query.filter_by(
        id=notification_id,
        user_id=current_user.id
    ).first_or_404(description='Notification not found')
    
    db.session.delete(notification)
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': 'Notification deleted'
    })

@api_endpoints.route('/notifications/preferences', methods=['GET'])
@auth_required
def get_notification_preferences():
    """Get notification preferences for the current user."""
    preferences = NotificationPreference.query.filter_by(user_id=current_user.id).first()
    
    if not preferences:
        preferences = NotificationPreference.create_default_preferences(current_user.id)
        
    return jsonify(preferences.to_dict())

@api_endpoints.route('/notifications/preferences', methods=['PUT'])
@auth_required
def update_notification_preferences():
    """Update notification preferences for the current user."""
    data = request.json
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
        
    # Get or create notification preferences for the user
    preferences = NotificationPreference.query.filter_by(user_id=current_user.id).first()
    
    if not preferences:
        preferences = NotificationPreference(user_id=current_user.id)
        db.session.add(preferences)
    
    # Update email preferences
    if 'email_preferences' in data:
        email_prefs = data['email_preferences']
        preferences.email_incident_created = email_prefs.get('incident_created', preferences.email_incident_created)
        preferences.email_incident_updated = email_prefs.get('incident_updated', preferences.email_incident_updated)
        preferences.email_incident_closed = email_prefs.get('incident_closed', preferences.email_incident_closed)
        preferences.email_unit_assigned = email_prefs.get('unit_assigned', preferences.email_unit_assigned)
        preferences.email_unit_status_changed = email_prefs.get('unit_status_changed', preferences.email_unit_status_changed)
        preferences.email_daily_summary = email_prefs.get('daily_summary', preferences.email_daily_summary)
        
    # Update in-app preferences
    if 'app_preferences' in data:
        app_prefs = data['app_preferences']
        preferences.app_incident_created = app_prefs.get('incident_created', preferences.app_incident_created)
        preferences.app_incident_updated = app_prefs.get('incident_updated', preferences.app_incident_updated)
        preferences.app_incident_closed = app_prefs.get('incident_closed', preferences.app_incident_closed)
        preferences.app_unit_assigned = app_prefs.get('unit_assigned', preferences.app_unit_assigned)
        preferences.app_unit_status_changed = app_prefs.get('unit_status_changed', preferences.app_unit_status_changed)
        preferences.app_user_login = app_prefs.get('user_login', preferences.app_user_login)
        
    # Update audio preferences
    if 'audio_preferences' in data:
        audio_prefs = data['audio_preferences']
        preferences.audio_new_incident = audio_prefs.get('new_incident', preferences.audio_new_incident)
        preferences.audio_critical_incident = audio_prefs.get('critical_incident', preferences.audio_critical_incident)
        preferences.audio_unit_assigned = audio_prefs.get('unit_assigned', preferences.audio_unit_assigned)
        
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': 'Notification preferences updated',
        'preferences': preferences.to_dict()
    })

@api_endpoints.route('/notifications', methods=['POST'])
@permission_required(Permission.ADMINISTRATOR)
def create_notification():
    """Create a new notification (admin only)."""
    data = request.json
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
        
    required_fields = ['user_id', 'title', 'message']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400
    
    user = User.query.get(data['user_id'])
    if not user:
        return jsonify({'error': 'User not found'}), 404
        
    notification = Notification(
        user_id=data['user_id'],
        title=data['title'],
        message=data['message'],
        notification_type=data.get('notification_type', Notification.TYPE_SYSTEM),
        reference_id=data.get('reference_id'),
        reference_type=data.get('reference_type')
    )
    
    db.session.add(notification)
    db.session.commit()
    
    # Emit WebSocket event if broadcast flag is set
    if data.get('broadcast', True):
        from websocket_events import socketio
        socketio.emit('new_notification', notification.to_dict())
    
    return jsonify({
        'status': 'success',
        'message': 'Notification created',
        'notification': notification.to_dict()
    }), 201

@api_endpoints.route('/notifications/bulk', methods=['POST'])
@permission_required(Permission.ADMINISTRATOR)
def create_bulk_notifications():
    """Create notifications for multiple users (admin only)."""
    data = request.json
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
        
    required_fields = ['user_ids', 'title', 'message']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400
    
    user_ids = data['user_ids']
    if not isinstance(user_ids, list) or not user_ids:
        return jsonify({'error': 'user_ids must be a non-empty list'}), 400
        
    created_notifications = []
    
    for user_id in user_ids:
        user = User.query.get(user_id)
        if user:
            notification = Notification(
                user_id=user_id,
                title=data['title'],
                message=data['message'],
                notification_type=data.get('notification_type', Notification.TYPE_SYSTEM),
                reference_id=data.get('reference_id'),
                reference_type=data.get('reference_type')
            )
            
            db.session.add(notification)
            created_notifications.append(notification)
    
    db.session.commit()
    
    # Emit WebSocket events if broadcast flag is set
    if data.get('broadcast', True):
        from websocket_events import socketio
        for notification in created_notifications:
            socketio.emit('new_notification', notification.to_dict())
    
    return jsonify({
        'status': 'success',
        'message': f'Created {len(created_notifications)} notifications',
        'created_count': len(created_notifications),
        'notifications': [n.to_dict() for n in created_notifications]
    }), 201
