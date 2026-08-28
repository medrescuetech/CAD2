from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from models import User, db, Role, Permission, PasswordHistory
from forms import LoginForm, RegistrationForm, PasswordResetRequestForm, PasswordResetForm, ChangePasswordForm
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.fields import EmailField
from wtforms.validators import DataRequired, Length, Email, EqualTo, Regexp
from datetime import datetime, timedelta
import uuid
import logging
import re
from werkzeug.urls import url_parse
from extensions import limiter
from utils.security import secure_endpoint, ajax_csrf_protect, rate_limit_by_ip
from utils.audit_log import log_audit_event, AuditCategory, AuditSeverity
from utils.password_policy import validate_password_complexity, check_password_history, add_password_to_history, is_password_expired
from utils.session_manager import initialize_session, end_session, check_session_timeout

auth = Blueprint('auth', __name__)

# Get loggers
audit_logger = logging.getLogger('audit')
error_logger = logging.getLogger('error')

class PasswordResetRequestForm(FlaskForm):
    email = EmailField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Request Password Reset')

class PasswordResetForm(FlaskForm):
    password = PasswordField('New Password', validators=[
        DataRequired(),
        Length(min=10, message="Password must be at least 10 characters long"),
        Regexp(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]', 
               message='Password must include at least one lowercase letter, one uppercase letter, one number, and one special character')
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(),
        EqualTo('password', message='Passwords must match')
    ])
    submit = SubmitField('Reset Password')

class ChangePasswordForm(FlaskForm):
    old_password = PasswordField('Current Password', validators=[DataRequired()])
    password = PasswordField('New Password', validators=[
        DataRequired(),
        Length(min=10, message="Password must be at least 10 characters long"),
        Regexp(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]', 
               message='Password must include at least one lowercase letter, one uppercase letter, one number, and one special character')
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(),
        EqualTo('password', message='Passwords must match')
    ])
    submit = SubmitField('Update Password')

def validate_password_complexity(password):
    """
    Validates that a password meets complexity requirements:
    - At least 10 characters
    - At least one lowercase letter
    - At least one uppercase letter
    - At least one number
    - At least one special character
    """
    errors = []
    
    if len(password) < 10:
        errors.append("Password must be at least 10 characters long")
    
    if not re.search(r'[a-z]', password):
        errors.append("Password must include at least one lowercase letter")
    
    if not re.search(r'[A-Z]', password):
        errors.append("Password must include at least one uppercase letter")
    
    if not re.search(r'\d', password):
        errors.append("Password must include at least one number")
    
    if not re.search(r'[@$!%*?&#]', password):
        errors.append("Password must include at least one special character (@$!%*?&#)")
    
    return errors

class ProfileForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=64)])
    email = EmailField('Email', validators=[DataRequired(), Email()])
    current_password = PasswordField('Current Password')
    new_password = PasswordField('New Password', validators=[Length(min=10, message="Password must be at least 10 characters long")])
    confirm_password = PasswordField('Confirm Password', validators=[EqualTo('new_password', message='Passwords must match')])
    submit = SubmitField('Update Profile')

@auth.route('/login', methods=['GET', 'POST'])
@rate_limit_by_ip(limit="10/minute")
def login():
    try:
        if current_user.is_authenticated:
            return redirect(url_for('pages.index'))
        
        # Only process form if it's a POST request
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            remember = request.form.get('remember', False)
            
            user = User.query.filter_by(username=username).first()
            
            if user is None or not user.verify_password(password):
                audit_logger.warning(
                    f"Failed login attempt for username: {username}",
                    extra={
                        'username': 'anonymous',
                        'ip': request.remote_addr,
                        'audit_type': 'AUTH_FAILURE'
                    }
                )
                log_audit_event(
                    category=AuditCategory.AUTHENTICATION,
                    action="Login failed - invalid username or password",
                    severity=AuditSeverity.WARNING,
                    user_id=None,
                    details={'attempted_username': username, 'reason': 'Invalid username or password'}
                )
                flash('Invalid username or password', 'danger')
                return current_app.custom_render_template('auth/login.html', title='Sign In')
                
            if not user.active:
                audit_logger.warning(
                    f"Login attempt for inactive user: {username}",
                    extra={
                        'username': 'anonymous',
                        'ip': request.remote_addr,
                        'audit_type': 'AUTH_FAILURE'
                    }
                )
                log_audit_event(
                    category=AuditCategory.AUTHENTICATION,
                    action="Login failed - user is inactive",
                    severity=AuditSeverity.WARNING,
                    user_id=user.id,
                    details={'reason': 'User is inactive'}
                )
                flash('This account has been deactivated', 'danger')
                return current_app.custom_render_template('auth/login.html', title='Sign In')
            
            # Check if password is expired
            if is_password_expired(user):
                # Generate password reset token
                token = user.get_reset_token()
                
                # Log password expiration
                log_audit_event(
                    category=AuditCategory.AUTHENTICATION,
                    action="Password expired",
                    severity=AuditSeverity.INFO,
                    user_id=user.id,
                    details={'ip': request.remote_addr}
                )
                
                flash('Your password has expired. Please reset your password.', 'warning')
                return redirect(url_for('auth.password_reset', token=token))
            
            login_user(user, remember=remember)
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            # Initialize user session
            initialize_session(user)
            
            audit_logger.info(
                f"User {user.username} logged in",
                extra={
                    'username': user.username,
                    'ip': request.remote_addr,
                    'audit_type': 'AUTH_SUCCESS'
                }
            )
            log_audit_event(
                category=AuditCategory.AUTHENTICATION,
                action="User logged in",
                severity=AuditSeverity.INFO,
                user_id=user.id,
                details={'ip': request.remote_addr}
            )
            
            next_page = request.args.get('next')
            if not next_page or url_parse(next_page).netloc != '':
                next_page = url_for('pages.index')
            
            return redirect(next_page)
        
        # GET request - render login form
        return current_app.custom_render_template('auth/login.html', title='Sign In')
    
    except Exception as e:
        error_logger.error(f"Error in login route: {str(e)}")
        flash('An error occurred during login. Please try again.', 'danger')
        return current_app.custom_render_template('auth/login.html', title='Sign In')

@auth.route('/logout')
@login_required
def logout():
    username = current_user.username
    ip = request.remote_addr
    
    # End user session
    end_session()
    
    audit_logger.info(
        f"User {username} logged out",
        extra={
            'username': username,
            'ip': ip,
            'audit_type': 'AUTH_LOGOUT'
        }
    )
    log_audit_event(
        category=AuditCategory.AUTHENTICATION,
        action="User logged out",
        severity=AuditSeverity.INFO,
        user_id=current_user.id
    )
    
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('auth.login'))

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('pages.index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        role = 'dispatcher'  # Default role

        # Check if user already exists
        user = User.query.filter_by(username=username).first()
        
        if user:
            audit_logger.warning(
                f"Failed registration attempt for username: {username}",
                extra={
                    'username': 'anonymous',
                    'ip': request.remote_addr,
                    'audit_type': 'REGISTRATION_FAILURE'
                }
            )
            log_audit_event(
                category=AuditCategory.AUTHENTICATION,
                action="Registration failed - username already exists",
                severity=AuditSeverity.WARNING,
                user_id=None,
                details={'attempted_username': username, 'reason': 'Username already exists'}
            )
            flash('Username already exists', 'danger')
            return current_app.custom_render_template('auth/register.html', title='Register')
        
        email_exists = User.query.filter_by(email=email).first()
        if email_exists:
            audit_logger.warning(
                f"Failed registration attempt for email: {email}",
                extra={
                    'username': 'anonymous',
                    'ip': request.remote_addr,
                    'audit_type': 'REGISTRATION_FAILURE'
                }
            )
            log_audit_event(
                category=AuditCategory.AUTHENTICATION,
                action="Registration failed - email already exists",
                severity=AuditSeverity.WARNING,
                user_id=None,
                details={'attempted_email': email, 'reason': 'Email already exists'}
            )
            flash('Email address already registered', 'danger')
            return current_app.custom_render_template('auth/register.html', title='Register')

        # Create new user
        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password, method='scrypt'),
            role=role
        )

        db.session.add(new_user)
        db.session.commit()

        audit_logger.info(
            f"User {username} registered successfully",
            extra={
                'username': username,
                'ip': request.remote_addr,
                'audit_type': 'REGISTRATION_SUCCESS'
            }
        )
        log_audit_event(
            category=AuditCategory.AUTHENTICATION,
            action="Registration successful",
            severity=AuditSeverity.INFO,
            user_id=new_user.id
        )
        
        flash('Account created successfully!', 'success')
        return redirect(url_for('auth.login'))

    return current_app.custom_render_template('auth/register.html', title='Register')

@auth.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = ProfileForm()
    form.username.data = current_user.username
    form.email.data = current_user.email
    
    if request.method == 'POST' and form.validate_on_submit():
        if form.current_password.data:
            if not current_user.verify_password(form.current_password.data):
                audit_logger.warning(
                    "Failed password change - incorrect current password",
                    extra={
                        'username': current_user.username,
                        'ip': request.remote_addr,
                        'audit_type': 'PASSWORD_CHANGE_FAILURE'
                    }
                )
                log_audit_event(
                    category=AuditCategory.AUTHENTICATION,
                    action="Password change failed - incorrect current password",
                    severity=AuditSeverity.WARNING,
                    user_id=current_user.id,
                    details={'reason': 'Incorrect current password'}
                )
                flash('Current password is incorrect', 'danger')
                return current_app.custom_render_template('auth/profile.html', title='Profile', form=form)
            
            validation_errors = validate_password_complexity(form.new_password.data)
            if validation_errors:
                flash(validation_errors[0], 'danger')
                return current_app.custom_render_template('auth/profile.html', title='Profile', form=form)
            
            current_user.password_hash = generate_password_hash(form.new_password.data, method='scrypt')
            audit_logger.info(
                "Password changed successfully",
                extra={
                    'username': current_user.username,
                    'ip': request.remote_addr,
                    'audit_type': 'PASSWORD_CHANGE_SUCCESS'
                }
            )
            audit_password_change(current_user.id)
            flash('Your password has been updated', 'success')
        
        current_user.username = form.username.data
        current_user.email = form.email.data
        current_user.profile_updated_at = datetime.utcnow()
        db.session.commit()
        audit_logger.info(
            "Profile updated",
            extra={
                'username': current_user.username,
                'ip': request.remote_addr,
                'audit_type': 'PROFILE_UPDATE'
            }
        )
        log_audit_event(
            category=AuditCategory.AUTHENTICATION,
            action="Profile updated",
            severity=AuditSeverity.INFO,
            user_id=current_user.id
        )
        flash('Your profile has been updated', 'success')
            
    return current_app.custom_render_template('auth/profile.html', title='Profile', form=form)

@auth.route('/change-password', methods=['POST'])
@login_required
@secure_endpoint(limit="5/minute")
def change_password():
    """Change user password."""
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if current_user.verify_password(form.old_password.data):
            try:
                # Validate new password complexity
                validate_password_complexity(
                    form.password.data,
                    username=current_user.username,
                    email=current_user.email,
                    first_name=current_user.first_name,
                    last_name=current_user.last_name
                )
                
                # Check password history
                check_password_history(current_user, form.password.data)
                
                # Set new password and update password_changed_at
                current_user.set_password(form.password.data)
                
                # Add old password to history
                add_password_to_history(current_user, form.old_password.data)
                
                db.session.commit()
                
                # Log successful password change
                log_audit_event(
                    category=AuditCategory.AUTHENTICATION,
                    action="Password changed",
                    severity=AuditSeverity.INFO,
                    user_id=current_user.id
                )
                
                flash('Your password has been updated.', 'success')
                return redirect(url_for('user.profile'))
                
            except Exception as e:
                db.session.rollback()
                
                # Log failed password change
                log_audit_event(
                    category=AuditCategory.AUTHENTICATION,
                    action="Password change failed",
                    severity=AuditSeverity.WARNING,
                    user_id=current_user.id,
                    details={'reason': str(e)}
                )
                
                flash(f'Error changing password: {str(e)}', 'danger')
        else:
            # Log failed password change due to incorrect current password
            log_audit_event(
                category=AuditCategory.AUTHENTICATION,
                action="Password change failed",
                severity=AuditSeverity.WARNING,
                user_id=current_user.id,
                details={'reason': 'Current password incorrect'}
            )
            
            flash('Invalid current password.', 'danger')
    
    return render_template('auth/change_password.html', form=form)

@auth.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit("5/hour", key_func=lambda: request.remote_addr)
def forgot_password():
    """Handle forgotten password requests"""
    if current_user.is_authenticated:
        return redirect(url_for('pages.index'))
        
    form = PasswordResetRequestForm()
    
    if request.method == 'POST' and form.validate_on_submit():
        email = form.email.data
        user = User.query.filter_by(email=email).first()
        
        # Always show a success message even if email doesn't exist (security best practice)
        # This prevents user enumeration attacks
        if user:
            # Generate token
            token = generate_reset_token(user.id)
            
            # Get the base URL from request
            base_url = request.host_url.rstrip('/')
            
            # Send password reset email
            email_sent = EmailService.send_password_reset_email(
                user=user,
                reset_token=token,
                base_url=base_url
            )
            
            if email_sent:
                audit_logger.info(
                    f"Password reset requested for user: {user.username}",
                    extra={
                        'username': user.username,
                        'ip': request.remote_addr,
                        'audit_type': 'PASSWORD_RESET_REQUEST'
                    }
                )
                log_audit_event(
                    category=AuditCategory.AUTHENTICATION,
                    action="Password reset requested",
                    severity=AuditSeverity.INFO,
                    user_id=user.id
                )
            else:
                audit_logger.warning(
                    f"Failed to send password reset email to: {email}",
                    extra={
                        'username': user.username if user else 'unknown',
                        'ip': request.remote_addr,
                        'audit_type': 'PASSWORD_RESET_REQUEST_FAILURE'
                    }
                )
                log_audit_event(
                    category=AuditCategory.AUTHENTICATION,
                    action="Password reset request failed - email not sent",
                    severity=AuditSeverity.WARNING,
                    user_id=user.id if user else None,
                    details={'email': email, 'reason': 'Email not sent'}
                )
                
        flash('If your email is registered, you will receive a password reset link shortly', 'info')
        return redirect(url_for('auth.login'))
    
    return current_app.custom_render_template('auth/forgot_password.html', title='Forgot Password', form=form)

@auth.route('/reset/<token>', methods=['GET', 'POST'])
@limiter.limit("10/hour", key_func=lambda: request.remote_addr)
def password_reset(token):
    """Reset user password with token."""
    if current_user.is_authenticated:
        return redirect(url_for('pages.index'))
        
    # Verify token and get user_id
    user_id = verify_reset_token(token)
    
    if not user_id:
        audit_logger.warning(
            "Invalid or expired password reset token",
            extra={
                'username': 'anonymous',
                'ip': request.remote_addr,
                'audit_type': 'PASSWORD_RESET_INVALID_TOKEN'
            }
        )
        log_audit_event(
            category=AuditCategory.AUTHENTICATION,
            action="Password reset failed - invalid or expired token",
            severity=AuditSeverity.WARNING,
            user_id=None,
            details={'token': token, 'reason': 'Invalid or expired token'}
        )
        flash('The password reset link is invalid or has expired', 'danger')
        return redirect(url_for('auth.forgot_password'))
    
    user = User.query.get(user_id)
    if not user:
        audit_logger.warning(
            f"Password reset requested for non-existent user ID: {user_id}",
            extra={
                'username': 'anonymous',
                'ip': request.remote_addr,
                'audit_type': 'PASSWORD_RESET_INVALID_USER'
            }
        )
        log_audit_event(
            category=AuditCategory.AUTHENTICATION,
            action="Password reset failed - user not found",
            severity=AuditSeverity.WARNING,
            user_id=user_id,
            details={'reason': 'User not found'}
        )
        flash('User not found', 'danger')
        return redirect(url_for('auth.forgot_password'))
    
    form = PasswordResetForm()
    
    if request.method == 'POST' and form.validate_on_submit():
        try:
            # Validate new password complexity
            validate_password_complexity(
                form.password.data,
                username=user.username,
                email=user.email,
                first_name=user.first_name,
                last_name=user.last_name
            )
            
            # Check password history
            check_password_history(user, form.password.data)
            
            # Set new password and update password_changed_at
            user.set_password(form.password.data)
            
            db.session.commit()
            
            # Log successful password reset
            log_audit_event(
                category=AuditCategory.AUTHENTICATION,
                action="Password reset completed",
                severity=AuditSeverity.INFO,
                user_id=user.id,
                details={'ip': request.remote_addr}
            )
            
            flash('Your password has been reset.', 'success')
            return redirect(url_for('auth.login'))
            
        except Exception as e:
            db.session.rollback()
            
            # Log failed password reset
            log_audit_event(
                category=AuditCategory.AUTHENTICATION,
                action="Password reset failed",
                severity=AuditSeverity.WARNING,
                user_id=user.id,
                details={'reason': str(e), 'ip': request.remote_addr}
            )
            
            flash(f'Error resetting password: {str(e)}', 'danger')
    
    return current_app.custom_render_template('auth/token_reset_password.html', title='Reset Password', form=form, token=token)

# API endpoints for password reset
@auth.route('/api/auth/forgot-password', methods=['POST'])
@limiter.limit("5/hour", key_func=lambda: request.remote_addr)
def api_forgot_password():
    """API endpoint for forgotten password requests"""
    if not request.is_json:
        return jsonify({'error': 'Invalid request format. JSON expected.'}), 400
        
    data = request.get_json()
    email = data.get('email')
    
    if not email:
        return jsonify({'error': 'Email address is required'}), 400
    
    user = User.query.filter_by(email=email).first()
    
    # Always return success (security best practice)
    if user:
        # Generate token
        token = generate_reset_token(user.id)
        
        # Get the base URL from request
        base_url = request.host_url.rstrip('/')
        
        # Send password reset email
        email_sent = EmailService.send_password_reset_email(
            user=user,
            reset_token=token,
            base_url=base_url
        )
        
        if email_sent:
            audit_logger.info(
                f"Password reset requested for user: {user.username}",
                extra={
                    'username': user.username,
                    'ip': request.remote_addr,
                    'audit_type': 'PASSWORD_RESET_REQUEST'
                }
            )
            log_audit_event(
                category=AuditCategory.AUTHENTICATION,
                action="Password reset requested",
                severity=AuditSeverity.INFO,
                user_id=user.id
            )
        else:
            audit_logger.warning(
                f"Failed to send password reset email to: {email}",
                extra={
                    'username': user.username if user else 'unknown',
                    'ip': request.remote_addr,
                    'audit_type': 'PASSWORD_RESET_REQUEST_FAILURE'
                }
            )
            log_audit_event(
                category=AuditCategory.AUTHENTICATION,
                action="Password reset request failed - email not sent",
                severity=AuditSeverity.WARNING,
                user_id=user.id if user else None,
                details={'email': email, 'reason': 'Email not sent'}
            )
                
    return jsonify({'success': True, 'message': 'If your email is registered, you will receive a password reset link shortly'})

@auth.route('/api/auth/reset-password', methods=['POST'])
@limiter.limit("10/hour", key_func=lambda: request.remote_addr)
def api_reset_password():
    """API endpoint for password reset with a valid token"""
    if not request.is_json:
        return jsonify({'error': 'Invalid request format. JSON expected.'}), 400
        
    data = request.get_json()
    token = data.get('token')
    password = data.get('password')
    
    if not token or not password:
        return jsonify({'error': 'Token and password are required'}), 400
    
    # Verify token and get user_id
    user_id = verify_reset_token(token)
    
    if not user_id:
        audit_logger.warning(
            "Invalid or expired password reset token",
            extra={
                'username': 'anonymous',
                'ip': request.remote_addr,
                'audit_type': 'PASSWORD_RESET_INVALID_TOKEN'
            }
        )
        log_audit_event(
            category=AuditCategory.AUTHENTICATION,
            action="Password reset failed - invalid or expired token",
            severity=AuditSeverity.WARNING,
            user_id=None,
            details={'token': token, 'reason': 'Invalid or expired token'}
        )
        return jsonify({'error': 'The password reset link is invalid or has expired'}), 400
    
    user = User.query.get(user_id)
    if not user:
        audit_logger.warning(
            f"Password reset requested for non-existent user ID: {user_id}",
            extra={
                'username': 'anonymous',
                'ip': request.remote_addr,
                'audit_type': 'PASSWORD_RESET_INVALID_USER'
            }
        )
        log_audit_event(
            category=AuditCategory.AUTHENTICATION,
            action="Password reset failed - user not found",
            severity=AuditSeverity.WARNING,
            user_id=user_id,
            details={'reason': 'User not found'}
        )
        return jsonify({'error': 'User not found'}), 400
    
    # Password validation
    validation_errors = validate_password_complexity(password)
    if validation_errors:
        return jsonify({'error': validation_errors[0], 'validation_errors': validation_errors}), 400
    
    # Update user's password
    user.password_hash = generate_password_hash(password, method='scrypt')
    user.password_reset_at = datetime.utcnow()
    
    # Blacklist the token to prevent reuse
    BlacklistedToken.blacklist_token(token)
    
    db.session.commit()
    
    audit_logger.info(
        f"Password reset completed for user: {user.username}",
        extra={
            'username': user.username,
            'ip': request.remote_addr,
            'audit_type': 'PASSWORD_RESET_SUCCESS'
        }
    )
    log_audit_event(
        category=AuditCategory.AUTHENTICATION,
        action="Password reset successful",
        severity=AuditSeverity.INFO,
        user_id=user.id
    )
    
    return jsonify({'success': True, 'message': 'Your password has been reset successfully'})
