"""
Notification Service Module

This module handles all notification-related operations including:
- Creating notifications for different system events
- Sending email notifications
- Managing audio alerts
- Broadcasting notifications via WebSockets
"""

from models import Notification, NotificationPreference, User, Role, Permission, Incident, Unit
from extensions import db, socketio
from datetime import datetime, timedelta
from flask import current_app, url_for
from sqlalchemy import or_
from services.email_service import EmailService

# Check if socketio is properly initialized
if socketio is None:
    print("WARNING: socketio not available. WebSocket notifications will not work.")
    print("Missing dependencies")

class NotificationService:
    """Service class for handling all notification operations."""
    
    @staticmethod
    def create_notification(user_id, title, message, notification_type=Notification.TYPE_SYSTEM, 
                           reference_id=None, reference_type=None, broadcast=True, send_email=True):
        """
        Create a notification for a user.
        
        Args:
            user_id: ID of the user to notify
            title: Notification title
            message: Notification message
            notification_type: Type of notification (system, incident, unit, user, alert)
            reference_id: Optional ID reference to related entity
            reference_type: Type of reference (incident, unit, etc.)
            broadcast: Whether to broadcast via WebSocket
            send_email: Whether to send email notification (based on user preferences)
            
        Returns:
            The created notification object
        """
        # Check user notification preferences first
        prefs = NotificationPreference.get_or_create(user_id)
        should_create_app_notification = True
        
        # Check app notification preferences
        if not prefs.app_enabled:
            # If app notifications are disabled globally, don't create the notification
            should_create_app_notification = False
        else:
            # Check specific notification type preferences
            if notification_type == Notification.TYPE_INCIDENT:
                if 'created' in str(reference_type) and not prefs.app_notify_incident_created:
                    should_create_app_notification = False
                elif 'updated' in str(reference_type) and not prefs.app_notify_incident_updated:
                    should_create_app_notification = False
                elif 'closed' in str(reference_type) and not prefs.app_notify_incident_closed:
                    should_create_app_notification = False
            elif notification_type == Notification.TYPE_UNIT:
                if 'assigned' in str(reference_type) and not prefs.app_notify_unit_assigned:
                    should_create_app_notification = False
                elif 'cleared' in str(reference_type) and not prefs.app_notify_unit_cleared:
                    should_create_app_notification = False
            elif notification_type == Notification.TYPE_SYSTEM and not prefs.app_notify_system_events:
                should_create_app_notification = False
        
        # If user has disabled this type of notification, don't create it
        if not should_create_app_notification:
            return None
            
        # Create notification in database
        notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=notification_type,
            reference_id=reference_id,
            reference_type=reference_type
        )
        
        db.session.add(notification)
        db.session.commit()
        
        # Broadcast via WebSocket if enabled
        if broadcast and socketio is not None:
            socketio.emit('new_notification', notification.to_dict(), room=f"user_{user_id}")
        
        # Send email if enabled and user preferences allow it
        if send_email:
            # Check email preferences
            should_send_email = False
            if prefs.email_enabled:
                if notification_type == Notification.TYPE_INCIDENT:
                    if 'created' in str(reference_type) and prefs.email_notify_incident_created:
                        should_send_email = True
                    elif 'updated' in str(reference_type) and prefs.email_notify_incident_updated:
                        should_send_email = True
                    elif 'closed' in str(reference_type) and prefs.email_notify_incident_closed:
                        should_send_email = True
                elif notification_type == Notification.TYPE_UNIT:
                    if 'assigned' in str(reference_type) and prefs.email_notify_unit_assigned:
                        should_send_email = True
                    elif 'cleared' in str(reference_type) and prefs.email_notify_unit_cleared:
                        should_send_email = True
                elif notification_type == Notification.TYPE_SYSTEM and prefs.email_notify_system_events:
                    should_send_email = True
                
                if should_send_email:
                    NotificationService.send_email_notification(notification)
            
        return notification

    @staticmethod
    def create_bulk_notifications(user_ids, title, message, notification_type=Notification.TYPE_SYSTEM,
                                reference_id=None, reference_type=None, broadcast=True, send_email=True):
        """
        Create notifications for multiple users.
        
        Args:
            user_ids: List of user IDs to notify
            title: Notification title
            message: Notification message
            notification_type: Type of notification
            reference_id: Optional ID reference to related entity
            reference_type: Type of reference
            broadcast: Whether to broadcast via WebSocket
            send_email: Whether to send email notification
            
        Returns:
            List of created notification objects
        """
        created_notifications = []
        
        for user_id in user_ids:
            user = User.query.get(user_id)
            if user:
                notification = NotificationService.create_notification(
                    user_id=user_id,
                    title=title,
                    message=message,
                    notification_type=notification_type,
                    reference_id=reference_id,
                    reference_type=reference_type,
                    broadcast=broadcast,
                    send_email=send_email
                )
                if notification:
                    created_notifications.append(notification)
        
        return created_notifications
    
    @staticmethod
    def send_email_notification(notification):
        """
        Send email notification based on user preferences.
        
        Args:
            notification: The notification object to send
            
        Returns:
            Boolean indicating success or failure
        """
        user = User.query.get(notification.user_id)
        if not user or not user.email:
            return False
            
        preferences = NotificationPreference.query.filter_by(user_id=user.id).first()
        
        # Check if user has preferences and if email is enabled for this notification type
        if not preferences:
            return False
            
        # Check notification type and corresponding preference
        send_email = False
        
        # Determine notification specifics based on type and reference
        if notification.notification_type == Notification.TYPE_INCIDENT:
            if notification.reference_id:
                incident = Incident.query.get(notification.reference_id)
                if incident:
                    # Set email notification type based on reference_type
                    notification_type = None
                    if "created" in notification.reference_type and preferences.email_incident_created:
                        notification_type = "created"
                        send_email = True
                    elif "updated" in notification.reference_type and preferences.email_incident_updated:
                        notification_type = "updated"
                        send_email = True
                    elif "closed" in notification.reference_type and preferences.email_incident_closed:
                        notification_type = "closed"
                        send_email = True
                        
                    if send_email:
                        # Create base URL for links
                        try:
                            base_url = url_for('pages.index', _external=True)
                            base_url = base_url.rstrip('/')
                        except RuntimeError:
                            # If outside of request context
                            base_url = current_app.config.get('BASE_URL', '')
                            
                        success = EmailService.send_incident_notification(
                            user=user,
                            incident=incident,
                            notification_type=notification_type,
                            base_url=base_url
                        )
                        
                        if success:
                            # Mark notification as email sent
                            notification.is_email_sent = True
                            db.session.commit()
                            
                        return success
                    
        elif notification.notification_type == Notification.TYPE_UNIT:
            if notification.reference_id:
                unit = Unit.query.get(notification.reference_id)
                if unit:
                    # Set email notification type based on reference_type
                    notification_type = None
                    incident = None
                    old_status = None
                    new_status = None
                    
                    if "assigned" in notification.reference_type and preferences.email_unit_assigned:
                        notification_type = "assigned"
                        send_email = True
                        
                        # Try to find associated incident
                        assignment = unit.get_current_assignment()
                        if assignment:
                            incident = assignment.incident
                            
                    elif "status" in notification.reference_type and preferences.email_unit_status_changed:
                        notification_type = "status_change"
                        send_email = True
                        
                        # Try to extract status info from notification message
                        message_parts = notification.message.split('from ')
                        if len(message_parts) > 1:
                            status_parts = message_parts[1].split(' to ')
                            if len(status_parts) > 1:
                                old_status = status_parts[0]
                                new_status = status_parts[1]
                        
                    if send_email:
                        # Create base URL for links
                        try:
                            base_url = url_for('pages.index', _external=True)
                            base_url = base_url.rstrip('/')
                        except RuntimeError:
                            # If outside of request context
                            base_url = current_app.config.get('BASE_URL', '')
                            
                        success = EmailService.send_unit_notification(
                            user=user,
                            unit=unit,
                            notification_type=notification_type,
                            incident=incident,
                            old_status=old_status,
                            new_status=new_status,
                            base_url=base_url
                        )
                        
                        if success:
                            # Mark notification as email sent
                            notification.is_email_sent = True
                            db.session.commit()
                            
                        return success
                        
        # For system and alert notifications, create a basic email
        elif notification.notification_type in [Notification.TYPE_SYSTEM, Notification.TYPE_ALERT]:
            try:
                # Send a simple notification email
                msg = f"""
                <h2>{notification.title}</h2>
                <p>{notification.message}</p>
                <p><em>This is an automated message from the CAD System.</em></p>
                """
                
                success, _ = EmailService.send_email(
                    recipients=user.email,
                    subject=f"CAD System: {notification.title}",
                    template_name='base',
                    context={
                        'header': notification.title,
                        'content': msg,
                        'user': user
                    }
                )
                
                if success:
                    # Mark notification as email sent
                    notification.is_email_sent = True
                    db.session.commit()
                
                return success
                
            except Exception as e:
                current_app.logger.error(f"Failed to send email notification: {str(e)}")
                return False
                
        return False

    @staticmethod
    def notify_incident_created(incident, creator_id):
        """
        Send notifications when an incident is created.
        
        Args:
            incident: The incident object that was created
            creator_id: ID of the user who created the incident
            
        Returns:
            List of created notification objects
        """
        # Find users with incident notification preferences enabled
        users_to_notify = User.query.join(NotificationPreference).filter(
            User.active == True,
            or_(
                NotificationPreference.app_incident_created == True,
                NotificationPreference.email_incident_created == True
            )
        ).all()
        
        title = f"New Incident: {incident.incident_number}"
        message = f"A new {incident.get_priority_string()} priority incident has been created at {incident.location}"
        
        # Create notifications for relevant users
        notifications = []
        for user in users_to_notify:
            # Don't notify the creator
            if user.id == creator_id:
                continue
                
            notification = NotificationService.create_notification(
                user_id=user.id,
                title=title,
                message=message,
                notification_type=Notification.TYPE_INCIDENT,
                reference_id=incident.id,
                reference_type="incident_created",
                broadcast=True,
                send_email=True
            )
            if notification:
                notifications.append(notification)
            
        # If it's a high priority or critical incident, also send audio alert
        if incident.priority >= incident.PRIORITY_HIGH:
            if socketio is not None:
                socketio.emit('audio_alert', {
                    'type': 'critical_incident',
                    'incident_id': incident.id,
                    'incident_number': incident.incident_number,
                    'priority': incident.get_priority_string()
                })
                
        return notifications
        
    @staticmethod
    def notify_incident_updated(incident, updater_id):
        """Send notifications when an incident is updated."""
        users_to_notify = User.query.join(NotificationPreference).filter(
            User.active == True,
            or_(
                NotificationPreference.app_incident_updated == True,
                NotificationPreference.email_incident_updated == True
            )
        ).all()
        
        title = f"Incident Updated: {incident.incident_number}"
        message = f"The incident at {incident.location} has been updated"
        
        notifications = []
        for user in users_to_notify:
            # Don't notify the updater
            if user.id == updater_id:
                continue
                
            notification = NotificationService.create_notification(
                user_id=user.id,
                title=title,
                message=message,
                notification_type=Notification.TYPE_INCIDENT,
                reference_id=incident.id,
                reference_type="incident_updated",
                broadcast=True,
                send_email=True
            )
            if notification:
                notifications.append(notification)
            
        return notifications
        
    @staticmethod
    def notify_incident_closed(incident, closer_id):
        """Send notifications when an incident is closed."""
        users_to_notify = User.query.join(NotificationPreference).filter(
            User.active == True,
            or_(
                NotificationPreference.app_incident_closed == True,
                NotificationPreference.email_incident_closed == True
            )
        ).all()
        
        title = f"Incident Closed: {incident.incident_number}"
        message = f"The incident at {incident.location} has been closed"
        
        notifications = []
        for user in users_to_notify:
            # Don't notify the closer
            if user.id == closer_id:
                continue
                
            notification = NotificationService.create_notification(
                user_id=user.id,
                title=title,
                message=message,
                notification_type=Notification.TYPE_INCIDENT,
                reference_id=incident.id,
                reference_type="incident_closed",
                broadcast=True,
                send_email=True
            )
            if notification:
                notifications.append(notification)
            
        return notifications
        
    @staticmethod
    def notify_unit_assigned(unit, incident, dispatcher_id):
        """Send notifications when a unit is assigned to an incident."""
        users_to_notify = User.query.join(NotificationPreference).filter(
            User.active == True,
            or_(
                NotificationPreference.app_unit_assigned == True,
                NotificationPreference.email_unit_assigned == True,
                NotificationPreference.audio_unit_assigned == True
            )
        ).all()
        
        title = f"Unit Assigned: {unit.name}"
        message = f"Unit {unit.name} has been assigned to incident {incident.incident_number}"
        
        notifications = []
        for user in users_to_notify:
            # Don't notify the dispatcher
            if user.id == dispatcher_id:
                continue
                
            notification = NotificationService.create_notification(
                user_id=user.id,
                title=title,
                message=message,
                notification_type=Notification.TYPE_UNIT,
                reference_id=unit.id,
                reference_type="unit_assigned",
                broadcast=True,
                send_email=True
            )
            if notification:
                notifications.append(notification)
            
        # Send audio alert for unit assignment
        if socketio is not None:
            socketio.emit('audio_alert', {
                'type': 'unit_assigned',
                'unit_id': unit.id,
                'unit_name': unit.name,
                'incident_id': incident.id,
                'incident_number': incident.incident_number
            })
            
        return notifications
        
    @staticmethod
    def notify_unit_status_changed(unit, old_status, new_status, updater_id):
        """Send notifications when a unit's status changes."""
        users_to_notify = User.query.join(NotificationPreference).filter(
            User.active == True,
            NotificationPreference.app_unit_status_changed == True
        ).all()
        
        title = f"Unit Status Change: {unit.name}"
        message = f"Unit {unit.name} status changed from {old_status} to {new_status}"
        
        notifications = []
        for user in users_to_notify:
            # Don't notify the updater
            if user.id == updater_id:
                continue
                
            notification = NotificationService.create_notification(
                user_id=user.id,
                title=title,
                message=message,
                notification_type=Notification.TYPE_UNIT,
                reference_id=unit.id,
                reference_type="unit_status_changed",
                broadcast=True,
                send_email=False  # Email preference handled separately
            )
            if notification:
                notifications.append(notification)
            
        # Check for users who want email notifications for status changes
        email_users = User.query.join(NotificationPreference).filter(
            User.active == True,
            NotificationPreference.email_unit_status_changed == True
        ).all()
        
        for user in email_users:
            if user.id == updater_id:
                continue
                
            # Find if we already created an in-app notification for this user
            existing = next((n for n in notifications if n.user_id == user.id), None)
            
            if existing:
                # Send email for existing notification
                NotificationService.send_email_notification(existing)
            else:
                # Create a new notification with email
                notification = NotificationService.create_notification(
                    user_id=user.id,
                    title=title,
                    message=message,
                    notification_type=Notification.TYPE_UNIT,
                    reference_id=unit.id,
                    reference_type="unit_status_changed",
                    broadcast=True,
                    send_email=True
                )
                if notification:
                    notifications.append(notification)
                
        return notifications
        
    @staticmethod
    def notify_user_login(user):
        """
        Send notifications when a user logs in.
        
        Args:
            user: The user who logged in
            
        Returns:
            List of created notification objects
        """
        # Only notify administrators about login events
        admins = User.query.join(NotificationPreference).join(Role).filter(
            User.active == True,
            Role.permissions.op('&')(Permission.ADMINISTRATOR) == Permission.ADMINISTRATOR,
            NotificationPreference.app_user_login == True
        ).all()
        
        login_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        title = "User Login"
        message = f"User {user.username} logged in at {login_time}"
        
        notifications = []
        for admin in admins:
            # Don't notify users about their own logins
            if admin.id != user.id:
                notification = NotificationService.create_notification(
                    user_id=admin.id,
                    title=title,
                    message=message,
                    notification_type=Notification.TYPE_USER,
                    reference_id=user.id,
                    reference_type="user_login",
                    broadcast=True,
                    send_email=False  # Login notifications don't need emails
                )
                if notification:
                    notifications.append(notification)
                
        return notifications
        
    @staticmethod
    def send_critical_alert(title, message, alert_type="critical", users=None):
        """
        Send a critical alert to users with audio notification.
        
        Args:
            title: Alert title
            message: Alert message
            alert_type: Type of alert (critical, warning, info)
            users: Optional list of User objects to notify. If None, notifies all users with critical alerts enabled.
            
        Returns:
            List of created notification objects
        """
        if users is None:
            # Notify all users with critical incident alerts enabled
            users = User.query.join(NotificationPreference).filter(
                User.active == True,
                NotificationPreference.audio_critical_incident == True
            ).all()
        
        notifications = []
        for user in users:
            notification = NotificationService.create_notification(
                user_id=user.id,
                title=title,
                message=message,
                notification_type=Notification.TYPE_ALERT,
                reference_type="critical_alert",
                broadcast=True,
                send_email=True
            )
            if notification:
                notifications.append(notification)
        
        # Send audio alert to all connected clients
        if socketio is not None:
            socketio.emit('audio_alert', {
                'type': alert_type,
                'title': title,
                'message': message,
                'timestamp': datetime.utcnow().isoformat()
            }, broadcast=True)
            
        return notifications
    
    @staticmethod
    def send_daily_summary_emails():
        """
        Send daily summary emails to users who have enabled this preference.
        This should be called by a scheduled task.
        
        Returns:
            Number of emails sent
        """
        # Find users with daily summary preference enabled
        users = User.query.join(NotificationPreference).filter(
            User.active == True,
            NotificationPreference.email_daily_summary == True
        ).all()
        
        if not users:
            return 0
        
        # Get statistics for the last 24 hours
        yesterday = datetime.utcnow() - timedelta(days=1)
        
        # Get counts of incidents by priority
        incident_stats = db.session.query(
            Incident.priority, 
            db.func.count(Incident.id)
        ).filter(
            Incident.created_at >= yesterday
        ).group_by(Incident.priority).all()
        
        # Get counts of units by status
        unit_stats = db.session.query(
            Unit.status, 
            db.func.count(Unit.id)
        ).group_by(Unit.status).all()
        
        # Get counts of new and closed incidents
        new_incidents = Incident.query.filter(
            Incident.created_at >= yesterday
        ).count()
        
        closed_incidents = Incident.query.filter(
            Incident.closed_at >= yesterday
        ).count()
        
        # Format the email content
        email_date = datetime.utcnow().strftime('%Y-%m-%d')
        title = f"Daily CAD Summary: {email_date}"
        
        email_content = f"""
        <html>
        <body>
            <h2>CAD System Daily Summary for {email_date}</h2>
            
            <h3>Incident Summary (Last 24 Hours)</h3>
            <ul>
                <li>New incidents created: {new_incidents}</li>
                <li>Incidents closed: {closed_incidents}</li>
            </ul>
            
            <h3>Incidents by Priority</h3>
            <ul>
                {"".join([f"<li>{Incident.get_priority_string(priority)}: {count}</li>" for priority, count in incident_stats])}
            </ul>
            
            <h3>Current Unit Status</h3>
            <ul>
                {"".join([f"<li>{status}: {count}</li>" for status, count in unit_stats])}
            </ul>
            
            <hr>
            <p><small>This is an automated daily summary from the CAD System. Please do not reply.</small></p>
        </body>
        </html>
        """
        
        # Send to each user with preference enabled
        emails_sent = 0
        for user in users:
            try:
                # Get SMTP settings from app config
                smtp_server = current_app.config.get('SMTP_SERVER')
                smtp_port = current_app.config.get('SMTP_PORT')
                smtp_username = current_app.config.get('SMTP_USERNAME')
                smtp_password = current_app.config.get('SMTP_PASSWORD')
                sender_email = current_app.config.get('SMTP_SENDER')
                
                if not all([smtp_server, smtp_port, smtp_username, smtp_password, sender_email]):
                    current_app.logger.error("SMTP configuration incomplete. Daily summary email not sent.")
                    continue
                    
                # Create email message
                msg = MIMEMultipart()
                msg['From'] = sender_email
                msg['To'] = user.email
                msg['Subject'] = title
                
                msg.attach(MIMEText(email_content, 'html'))
                
                # Send email
                with smtplib.SMTP(smtp_server, smtp_port) as server:
                    server.starttls()
                    server.login(smtp_username, smtp_password)
                    server.send_message(msg)
                
                emails_sent += 1
                
            except Exception as e:
                current_app.logger.error(f"Failed to send daily summary email to {user.email}: {str(e)}")
        
        return emails_sent
