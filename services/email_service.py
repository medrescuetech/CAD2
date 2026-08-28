"""
Email Service Module

This module handles all email-related operations including:
- Sending email notifications for incidents, units, and system events
- Email templating with context
- Email queue management
- Email delivery status tracking

This service works in conjunction with NotificationService to manage email-based alerts.
"""

import smtplib
import threading
import queue
import time
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app, render_template
from datetime import datetime
from models import EmailLog
from extensions import db

# Get a logger for this module
logger = logging.getLogger('email_service')

# Email queue for asynchronous sending
email_queue = queue.Queue()
queue_running = False
queue_thread = None

class EmailService:
    """Service class for handling all email operations."""
    
    @staticmethod
    def send_email(recipients, subject, template_name, context, priority='normal', attachments=None):
        """
        Send an email using a template.
        
        Args:
            recipients: List of email addresses or single email address
            subject: Email subject
            template_name: Name of the template to use (without .html extension)
            context: Dictionary of context variables for the template
            priority: Email priority (high, normal, low)
            attachments: List of attachments
            
        Returns:
            Boolean indicating success or failure and email log ID
        """
        try:
            # Convert single recipient to list
            if isinstance(recipients, str):
                recipients = [recipients]
                
            # Add current timestamp to context
            context['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            context['year'] = datetime.now().year
                
            # Render email template
            html_content = render_template(f"email/{template_name}.html", **context)
            
            # Create email log entry
            email_log = EmailLog(
                recipients=', '.join(recipients),
                subject=subject,
                template=template_name,
                context=str(context),
                status='queued',
                priority=priority
            )
            db.session.add(email_log)
            db.session.commit()
            
            # Add to queue
            email_data = {
                'log_id': email_log.id,
                'recipients': recipients,
                'subject': subject,
                'html_content': html_content,
                'priority': priority,
                'attachments': attachments
            }
            
            email_queue.put(email_data)
            
            # Ensure queue processor is running
            EmailService.ensure_queue_processor()
            
            return True, email_log.id
            
        except Exception as e:
            logger.error(f"Failed to queue email: {str(e)}")
            return False, None
    
    @staticmethod
    def send_incident_notification(user, incident, notification_type, base_url=None):
        """
        Send an incident notification email.
        
        Args:
            user: User object to send notification to
            incident: Incident object
            notification_type: Type of notification (created, updated, closed)
            base_url: Base URL for incident link
            
        Returns:
            Boolean indicating success or failure
        """
        if not user.email:
            logger.warning(f"Cannot send email to user {user.id}: No email address")
            return False
            
        # Set up context
        context = {
            'user': user,
            'incident': incident,
            'notification_type': notification_type,
            'url': f"{base_url or ''}/incident/{incident.id}"
        }
        
        # Set priority based on incident priority
        email_priority = 'normal'
        if hasattr(incident, 'priority') and incident.priority:
            if incident.priority >= 4:  # High or critical
                email_priority = 'high'
                
        # Create subject
        subject = f"Incident {notification_type.capitalize()}: {incident.incident_number}"
        
        # Send email
        success, log_id = EmailService.send_email(
            recipients=user.email,
            subject=subject,
            template_name='incident_notification',
            context=context,
            priority=email_priority
        )
        
        return success
    
    @staticmethod
    def send_unit_notification(user, unit, notification_type, incident=None, old_status=None, new_status=None, base_url=None):
        """
        Send a unit notification email.
        
        Args:
            user: User object to send notification to
            unit: Unit object
            notification_type: Type of notification (assigned, status_change, location_change)
            incident: Related incident (if applicable)
            old_status: Previous status (for status_change)
            new_status: New status (for status_change)
            base_url: Base URL for unit link
            
        Returns:
            Boolean indicating success or failure
        """
        if not user.email:
            logger.warning(f"Cannot send email to user {user.id}: No email address")
            return False
            
        # Set up context
        context = {
            'user': user,
            'unit': unit,
            'notification_type': notification_type,
            'incident': incident,
            'old_status': old_status,
            'new_status': new_status,
            'url': f"{base_url or ''}/unit/{unit.id}"
        }
        
        # Set priority
        email_priority = 'normal'
        if incident and hasattr(incident, 'priority') and incident.priority:
            if incident.priority >= 4:  # High or critical
                email_priority = 'high'
                
        # Create subject based on notification type
        if notification_type == 'assigned':
            subject = f"Unit Assigned: {unit.name} to Incident {incident.incident_number if incident else 'Unknown'}"
        elif notification_type == 'status_change':
            subject = f"Unit Status Change: {unit.name}"
        else:
            subject = f"Unit Update: {unit.name}"
        
        # Send email
        success, log_id = EmailService.send_email(
            recipients=user.email,
            subject=subject,
            template_name='unit_notification',
            context=context,
            priority=email_priority
        )
        
        return success
    
    @staticmethod
    def send_password_reset_email(user, reset_token, base_url=None):
        """
        Send a password reset email with a secure token.
        
        Args:
            user: User object to send reset email to
            reset_token: Secure token for password reset
            base_url: Base URL for password reset link
            
        Returns:
            Boolean indicating success or failure
        """
        if not user.email:
            logger.warning(f"Cannot send password reset to user {user.id}: No email address")
            return False
            
        # Build the reset URL
        reset_url = f"{base_url or ''}/auth/reset/{reset_token}"
        
        # Set up context
        context = {
            'user': user,
            'reset_url': reset_url
        }
        
        # Send email
        success, log_id = EmailService.send_email(
            recipients=user.email,
            subject="Password Reset - CAD System",
            template_name='password_reset',
            context=context,
            priority='high'  # Password resets are high priority
        )
        
        return success
        
    @staticmethod
    def send_test_email(recipient, include_html=True):
        """
        Send a test email to verify SMTP configuration.
        
        Args:
            recipient: Email address to send test to
            include_html: Whether to include HTML content
            
        Returns:
            Boolean indicating success or failure and status message
        """
        try:
            # Get SMTP settings from the current app config
            smtp_server = current_app.config.get('MAIL_SERVER')
            smtp_port = current_app.config.get('MAIL_PORT')
            smtp_username = current_app.config.get('MAIL_USERNAME')
            smtp_password = current_app.config.get('MAIL_PASSWORD')
            use_tls = current_app.config.get('MAIL_USE_TLS', True)
            use_ssl = current_app.config.get('MAIL_USE_SSL', False)
            
            # Get sender information
            sender_name = current_app.config.get('MAIL_DEFAULT_SENDER_NAME', 'CAD System')
            sender_email = current_app.config.get('MAIL_DEFAULT_SENDER', '')
            
            # Combine sender name and email if both exist
            from_address = f"{sender_name} <{sender_email}>" if sender_name and sender_email else sender_email
            
            if not all([smtp_server, smtp_port, smtp_username, smtp_password, sender_email]):
                logger.error("SMTP configuration incomplete")
                return False, "SMTP configuration incomplete. Please check all required settings."
                
            # Create email
            msg = MIMEMultipart('alternative')
            msg['From'] = from_address
            msg['To'] = recipient
            msg['Subject'] = "CAD System: SMTP Test Email"
            
            # Email content
            text_content = (
                "This is a test email from the CAD System to validate SMTP settings.\n\n"
                "If you're seeing this message, email delivery is working correctly.\n\n"
                "Configuration details:\n"
                f"- SMTP Server: {smtp_server}\n"
                f"- SMTP Port: {smtp_port}\n"
                f"- Sender: {sender_email}\n"
                f"- TLS Enabled: {use_tls}\n"
                f"- SSL Enabled: {use_ssl}\n"
                f"- Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
                "This is an automated message. Please do not reply."
            )
            msg.attach(MIMEText(text_content, 'plain'))
            
            if include_html:
                html_content = f"""
                <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px;">
                        <h2 style="color: #0056b3;">CAD System SMTP Test Email</h2>
                        <p>This is a test email from the CAD System to validate SMTP settings.</p>
                        <p><strong>If you're seeing this message, email delivery is working correctly.</strong></p>
                        
                        <div style="background-color: #f8f9fa; padding: 15px; margin: 15px 0; border-left: 4px solid #0056b3; border-radius: 3px;">
                            <h3 style="margin-top: 0;">Configuration Details</h3>
                            <ul style="padding-left: 20px;">
                                <li><strong>SMTP Server:</strong> {smtp_server}</li>
                                <li><strong>SMTP Port:</strong> {smtp_port}</li>
                                <li><strong>Sender:</strong> {sender_email}</li>
                                <li><strong>TLS Enabled:</strong> {use_tls}</li>
                                <li><strong>SSL Enabled:</strong> {use_ssl}</li>
                                <li><strong>Time:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</li>
                            </ul>
                        </div>
                        
                        <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
                        <p style="font-size: 12px; color: #777;">This is an automated message. Please do not reply.</p>
                    </div>
                </body>
                </html>
                """
                msg.attach(MIMEText(html_content, 'html'))
            
            # Create an email log entry
            email_log = EmailLog(
                recipients=recipient,
                subject="CAD System: SMTP Test Email",
                sender=from_address,
                content_text=text_content,
                content_html=html_content if include_html else None,
                status="queued",
                priority="high",
                email_type="test"
            )
            db.session.add(email_log)
            db.session.commit()
            
            # Connect to server and send
            if use_ssl:
                server = smtplib.SMTP_SSL(smtp_server, smtp_port)
            else:
                server = smtplib.SMTP(smtp_server, smtp_port)
                
            if use_tls:
                server.starttls()
                
            server.login(smtp_username, smtp_password)
            server.send_message(msg)
            server.quit()
            
            # Update email log status
            email_log.status = "sent"
            email_log.sent_at = datetime.utcnow()
            db.session.commit()
            
            logger.info(f"Test email sent successfully to {recipient}")
            return True, "Test email sent successfully"
            
        except Exception as e:
            error_message = f"Failed to send test email: {str(e)}"
            logger.error(error_message)
            
            # Update email log status if it exists
            try:
                if 'email_log' in locals():
                    email_log.status = "failed" 
                    email_log.error_message = str(e)[:255]  # Limit error message length
                    db.session.commit()
            except Exception as db_err:
                logger.error(f"Failed to update email log: {str(db_err)}")
                
            return False, error_message
    
    @staticmethod
    def ensure_queue_processor():
        """Ensure the email queue processor is running."""
        global queue_running, queue_thread
        
        if not queue_running:
            queue_running = True
            queue_thread = threading.Thread(target=EmailService._process_email_queue)
            queue_thread.daemon = True
            queue_thread.start()
            
    @staticmethod
    def _process_email_queue():
        """Process emails in the queue in a background thread."""
        global queue_running
        
        logger.info("Email queue processor started")
        
        while queue_running:
            try:
                # Get the next email from the queue (wait for up to 1 second)
                try:
                    email_data = email_queue.get(block=True, timeout=1)
                except queue.Empty:
                    continue
                
                # Send the email
                try:
                    EmailService._send_email_direct(email_data)
                    email_queue.task_done()
                except Exception as e:
                    logger.error(f"Failed to send email: {str(e)}")
                    
                    # Update email log
                    try:
                        with current_app.app_context():
                            email_log = EmailLog.query.get(email_data['log_id'])
                            if email_log:
                                email_log.status = 'failed'
                                email_log.error_message = str(e)
                                email_log.updated_at = datetime.now()
                                db.session.commit()
                    except Exception as db_error:
                        logger.error(f"Failed to update email log: {str(db_error)}")
                    
                    # Requeue the email for retry if it's important
                    if email_data.get('priority') == 'high' and email_data.get('retry_count', 0) < 3:
                        email_data['retry_count'] = email_data.get('retry_count', 0) + 1
                        logger.info(f"Requeuing high priority email, attempt {email_data['retry_count']}")
                        email_queue.put(email_data)
                        
            except Exception as e:
                logger.error(f"Error in email queue processor: {str(e)}")
                
        logger.info("Email queue processor stopped")
    
    @staticmethod
    def _send_email_direct(email_data):
        """
        Send an email directly using SMTP.
        
        Args:
            email_data: Dictionary containing email details
            
        Returns:
            Boolean indicating success or failure
        """
        try:
            # Create a new app context for database operations
            with current_app.app_context():
                # Get SMTP settings
                smtp_server = current_app.config.get('MAIL_SERVER')
                smtp_port = current_app.config.get('MAIL_PORT')
                smtp_username = current_app.config.get('MAIL_USERNAME')
                smtp_password = current_app.config.get('MAIL_PASSWORD')
                use_tls = current_app.config.get('MAIL_USE_TLS', True)
                use_ssl = current_app.config.get('MAIL_USE_SSL', False)
                
                # Skip actual sending in testing mode
                if current_app.config.get('EMAIL_TESTING', False):
                    logger.info(f"Test mode: Would send email to {email_data['recipients']} with subject: {email_data['subject']}")
                    
                    # Update email log
                    email_log = EmailLog.query.get(email_data['log_id'])
                    if email_log:
                        email_log.status = 'sent_test'
                        email_log.sent_at = datetime.now()
                        email_log.updated_at = datetime.now()
                        db.session.commit()
                        
                    return True
                
                # Create email
                msg = MIMEMultipart()
                msg['From'] = current_app.config.get('MAIL_DEFAULT_SENDER', '')
                msg['To'] = ", ".join(email_data['recipients'])
                msg['Subject'] = email_data['subject']
                
                # Add HTML content
                msg.attach(MIMEText(email_data['html_content'], 'html'))
                
                # Connect to server and send
                if use_ssl:
                    server = smtplib.SMTP_SSL(smtp_server, smtp_port)
                else:
                    server = smtplib.SMTP(smtp_server, smtp_port)
                    
                if use_tls:
                    server.starttls()
                    
                server.login(smtp_username, smtp_password)
                server.send_message(msg)
                server.quit()
                
                # Update email log
                email_log = EmailLog.query.get(email_data['log_id'])
                if email_log:
                    email_log.status = 'sent'
                    email_log.sent_at = datetime.now()
                    email_log.updated_at = datetime.now()
                    db.session.commit()
                
                logger.info(f"Email sent successfully to {email_data['recipients']}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to send email directly: {str(e)}")
            raise
