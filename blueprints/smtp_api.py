"""
SMTP API Blueprint

This module defines API endpoints for:
- SMTP settings management
- SMTP connection testing
"""

from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from models import Permission, AuditLog, db
from blueprints.admin import permission_required
import logging
from services.email_service import EmailService

# Create a blueprint for SMTP API endpoints
bp = Blueprint('smtp_api', __name__)

# Logger
logger = logging.getLogger('smtp_api')

@bp.route('/api/smtp/settings', methods=['GET'])
@login_required
@permission_required(Permission.MANAGE_SETTINGS)
def get_smtp_settings():
    """
    Get SMTP server configuration.
    
    Response:
    {
        "success": true,
        "settings": {
            "smtp_server": "server value",
            "smtp_port": port value,
            "smtp_username": "username value",
            "smtp_encryption": "tls/ssl/none",
            "sender_name": "name value",
            "sender_email": "email value"
        }
    }
    """
    # Get current SMTP settings
    settings = {
        'smtp_server': current_app.config.get('MAIL_SERVER', ''),
        'smtp_port': current_app.config.get('MAIL_PORT', 587),
        'smtp_username': current_app.config.get('MAIL_USERNAME', ''),
        'smtp_encryption': 'tls' if current_app.config.get('MAIL_USE_TLS', True) else 
                          ('ssl' if current_app.config.get('MAIL_USE_SSL', False) else 'none'),
        'sender_name': current_app.config.get('MAIL_DEFAULT_SENDER_NAME', 'CAD System'),
        'sender_email': current_app.config.get('MAIL_DEFAULT_SENDER', '')
    }
    
    return jsonify({
        'success': True,
        'settings': settings
    })

@bp.route('/api/smtp/settings', methods=['POST'])
@login_required
@permission_required(Permission.MANAGE_SETTINGS)
def update_smtp_settings():
    """
    Update SMTP server configuration.
    
    Request JSON:
    {
        "smtp_server": "server value",
        "smtp_port": port value,
        "smtp_username": "username value",
        "smtp_password": "password value",
        "smtp_encryption": "tls/ssl/none",
        "sender_name": "name value",
        "sender_email": "email value"
    }
    
    Response:
    {
        "success": true,
        "message": "SMTP settings updated successfully"
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    try:
        # Update settings in database or config file
        # This is a placeholder - actual implementation would depend on how settings are stored
        current_app.config['MAIL_SERVER'] = data.get('smtp_server', current_app.config.get('MAIL_SERVER', ''))
        current_app.config['MAIL_PORT'] = int(data.get('smtp_port', current_app.config.get('MAIL_PORT', 587)))
        current_app.config['MAIL_USERNAME'] = data.get('smtp_username', current_app.config.get('MAIL_USERNAME', ''))
        
        # Only update password if provided and not empty
        if 'smtp_password' in data and data['smtp_password']:
            current_app.config['MAIL_PASSWORD'] = data['smtp_password']
            
        # Handle encryption settings
        encryption = data.get('smtp_encryption', 'tls')
        current_app.config['MAIL_USE_TLS'] = encryption == 'tls'
        current_app.config['MAIL_USE_SSL'] = encryption == 'ssl'
        
        # Sender information
        current_app.config['MAIL_DEFAULT_SENDER_NAME'] = data.get('sender_name', current_app.config.get('MAIL_DEFAULT_SENDER_NAME', 'CAD System'))
        current_app.config['MAIL_DEFAULT_SENDER'] = data.get('sender_email', current_app.config.get('MAIL_DEFAULT_SENDER', ''))
        
        # Create audit log entry
        audit_log = AuditLog(
            user_id=current_user.id,
            action='update_smtp_settings',
            resource_type='settings',
            resource_id=None,
            details="Updated SMTP server settings"
        )
        db.session.add(audit_log)
        db.session.commit()
        
        logger.info(f"User {current_user.username} updated SMTP settings")
        
        return jsonify({
            'success': True,
            'message': 'SMTP settings updated successfully'
        })
    except Exception as e:
        logger.error(f"Error updating SMTP settings: {str(e)}")
        return jsonify({
            'success': False,
            'error': f"Error updating settings: {str(e)}"
        }), 500

@bp.route('/api/smtp/test', methods=['POST'])
@login_required
@permission_required(Permission.MANAGE_SETTINGS)
def test_smtp_connection():
    """
    Test SMTP connection by sending a test email.
    
    Request JSON:
    {
        "recipient": "test@example.com"
    }
    
    Response:
    {
        "success": true/false,
        "message": "Success/error message"
    }
    """
    data = request.get_json()
    if not data or 'recipient' not in data:
        return jsonify({'success': False, 'error': 'Recipient email is required'}), 400
    
    recipient = data['recipient']
    
    try:
        # Send a test email using the EmailService
        success, message = EmailService.send_test_email(recipient)
        
        # Create audit log entry
        audit_log = AuditLog(
            user_id=current_user.id,
            action='test_smtp_connection',
            resource_type='smtp',
            resource_id=None,
            details=f"Tested SMTP connection by sending email to {recipient}. Result: {'Success' if success else 'Failed'}"
        )
        db.session.add(audit_log)
        db.session.commit()
        
        if success:
            logger.info(f"SMTP test email sent successfully to {recipient}")
            return jsonify({
                'success': True,
                'message': f"Test email sent successfully to {recipient}"
            })
        else:
            logger.error(f"Failed to send SMTP test email: {message}")
            return jsonify({
                'success': False,
                'error': message
            })
    except Exception as e:
        error_msg = f"Error testing SMTP connection: {str(e)}"
        logger.error(error_msg)
        return jsonify({
            'success': False,
            'error': error_msg
        }), 500
