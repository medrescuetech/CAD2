from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import desc, and_
from models import DailyLog, User, DailyLogEntry
from extensions import db, csrf
from utils.validation import validate_request_json, validate_date
from utils.decorators import role_required, rate_limit
from utils.logging import log_activity
from utils.auto_logger import get_recent_system_events, EVENT_TYPES
import json
from werkzeug.utils import secure_filename
import os
from uuid import uuid4

# Configure upload settings
UPLOAD_FOLDER = 'uploads/daily_log_attachments'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'xls', 'xlsx', 'csv'}
MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB max size

def allowed_file(filename):
    """Check if the file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

daily_log_api = Blueprint('daily_log_api', __name__)

# Initialize function to be called when the app is available
def init_daily_log_api(app):
    """Initialize the daily log API with the app context."""
    # Make sure the upload directory exists
    os.makedirs(os.path.join(app.root_path, UPLOAD_FOLDER), exist_ok=True)

@daily_log_api.route('/api/daily_logs', methods=['GET'])
@login_required
@role_required('VIEW_DASHBOARD')
@rate_limit(limit=60, period=60)
def get_daily_logs():
    """Get a list of daily logs with filtering options."""
    try:
        # Parse query parameters
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        shift = request.args.get('shift')
        user_id = request.args.get('user_id', type=int)
        
        # Build query
        query = DailyLog.query
        
        # Apply filters
        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                query = query.filter(DailyLog.date >= start_date)
            except ValueError:
                return jsonify({'error': 'Invalid start_date format, use YYYY-MM-DD'}), 400
        
        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                query = query.filter(DailyLog.date <= end_date)
            except ValueError:
                return jsonify({'error': 'Invalid end_date format, use YYYY-MM-DD'}), 400
        
        if shift:
            query = query.filter(DailyLog.shift == shift)
        
        if user_id:
            query = query.filter(DailyLog.user_id == user_id)
            
        # Check permissions
        if not current_user.is_administrator():
            # If not admin, only show user's own logs
            query = query.filter(DailyLog.user_id == current_user.id)
        
        # Order by date (newest first)
        query = query.order_by(desc(DailyLog.date), DailyLog.shift)
        
        # Paginate results
        logs_pagination = query.paginate(page=page, per_page=per_page)
        
        # Prepare response
        logs = [log.to_dict() for log in logs_pagination.items]
        
        return jsonify({
            'logs': logs,
            'total': logs_pagination.total,
            'pages': logs_pagination.pages,
            'current_page': page
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in get_daily_logs: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@daily_log_api.route('/api/daily_logs/<int:id>', methods=['GET'])
@login_required
@role_required('VIEW_DASHBOARD')
@rate_limit(limit=30, period=60)
def get_daily_log(id):
    """Get a specific daily log by ID."""
    try:
        log = DailyLog.query.get(id)
        
        if not log:
            return jsonify({'error': 'Daily log not found'}), 404
        
        # Check permissions
        if not current_user.is_administrator() and log.user_id != current_user.id:
            return jsonify({'error': 'You do not have permission to view this log'}), 403
        
        return jsonify(log.to_dict())
        
    except Exception as e:
        current_app.logger.error(f"Error in get_daily_log: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@daily_log_api.route('/api/daily_logs', methods=['POST'])
@login_required
@role_required('VIEW_DASHBOARD')
@csrf.exempt
@rate_limit(limit=10, period=60)
def create_daily_log():
    """Create a new daily log entry."""
    try:
        # Validate request
        schema = {
            'type': 'object',
            'required': ['date', 'shift', 'notes'],
            'properties': {
                'date': {'type': 'string', 'format': 'date'},
                'shift': {'type': 'string', 'enum': ['morning', 'day', 'evening', 'night']},
                'notes': {'type': 'string'}
            }
        }
        
        data = request.get_json()
        validation_result = validate_request_json(data, schema)
        
        if validation_result:
            return jsonify({'error': validation_result}), 400
        
        # Parse date
        try:
            log_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format, use YYYY-MM-DD'}), 400
        
        # Check if a log already exists for this user/date/shift
        existing_log = DailyLog.query.filter(
            and_(
                DailyLog.user_id == current_user.id,
                DailyLog.date == log_date,
                DailyLog.shift == data['shift']
            )
        ).first()
        
        if existing_log:
            return jsonify({'error': 'A log already exists for this date and shift'}), 409
        
        # Create new log
        log = DailyLog(
            date=log_date,
            shift=data['shift'],
            user_id=current_user.id,
            notes=data['notes']
        )
        
        db.session.add(log)
        db.session.commit()
        
        # Log activity
        log_activity(
            category='daily_log',
            action='create',
            user_id=current_user.id,
            resource_type='daily_log',
            resource_id=str(log.id)
        )
        
        return jsonify(log.to_dict()), 201
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in create_daily_log: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@daily_log_api.route('/api/daily_logs/<int:id>', methods=['PUT'])
@login_required
@role_required('VIEW_DASHBOARD')
@csrf.exempt
@rate_limit(limit=20, period=60)
def update_daily_log(id):
    """Update an existing daily log entry."""
    try:
        log = DailyLog.query.get(id)
        
        if not log:
            return jsonify({'error': 'Daily log not found'}), 404
        
        # Check permissions
        if log.user_id != current_user.id:
            if not current_user.is_administrator():
                return jsonify({'error': 'You do not have permission to update this log'}), 403
        
        # Validate request
        schema = {
            'type': 'object',
            'properties': {
                'date': {'type': 'string', 'format': 'date'},
                'shift': {'type': 'string', 'enum': ['morning', 'day', 'evening', 'night']},
                'notes': {'type': 'string'}
            }
        }
        
        data = request.get_json()
        validation_result = validate_request_json(data, schema)
        
        if validation_result:
            return jsonify({'error': validation_result}), 400
        
        # Update log
        if 'date' in data:
            try:
                log_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
                log.date = log_date
            except ValueError:
                return jsonify({'error': 'Invalid date format, use YYYY-MM-DD'}), 400
        
        if 'shift' in data:
            log.shift = data['shift']
        
        if 'notes' in data:
            log.notes = data['notes']
        
        db.session.commit()
        
        # Log activity
        log_activity(
            category='daily_log',
            action='update',
            user_id=current_user.id,
            resource_type='daily_log',
            resource_id=str(log.id)
        )
        
        return jsonify(log.to_dict())
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in update_daily_log: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@daily_log_api.route('/api/daily_logs/<int:id>', methods=['DELETE'])
@login_required
@role_required('VIEW_DASHBOARD')
@csrf.exempt
@rate_limit(limit=10, period=60)
def delete_daily_log(id):
    """Delete a daily log entry."""
    try:
        log = DailyLog.query.get(id)
        
        if not log:
            return jsonify({'error': 'Daily log not found'}), 404
        
        # Check permissions
        if log.user_id != current_user.id:
            if not current_user.is_administrator():
                return jsonify({'error': 'You do not have permission to delete this log'}), 403
        
        # Store log ID for activity log
        log_id = log.id
        
        # Delete log
        db.session.delete(log)
        db.session.commit()
        
        # Log activity
        log_activity(
            category='daily_log',
            action='delete',
            user_id=current_user.id,
            resource_type='daily_log',
            resource_id=str(log_id)
        )
        
        return jsonify({'message': 'Daily log deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in delete_daily_log: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@daily_log_api.route('/api/daily_logs/user/<int:user_id>', methods=['GET'])
@login_required
@role_required('VIEW_DASHBOARD')
@rate_limit(limit=30, period=60)
def get_user_daily_logs(user_id):
    """Get daily logs for a specific user."""
    try:
        # Check permissions
        if user_id != current_user.id and not current_user.is_administrator():
            return jsonify({'error': 'You do not have permission to view this user\'s logs'}), 403
        
        # Check if user exists
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Parse query parameters
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        shift = request.args.get('shift')
        
        # Build query
        query = DailyLog.query.filter(DailyLog.user_id == user_id)
        
        # Apply filters
        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                query = query.filter(DailyLog.date >= start_date)
            except ValueError:
                return jsonify({'error': 'Invalid start_date format, use YYYY-MM-DD'}), 400
        
        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                query = query.filter(DailyLog.date <= end_date)
            except ValueError:
                return jsonify({'error': 'Invalid end_date format, use YYYY-MM-DD'}), 400
        
        if shift:
            query = query.filter(DailyLog.shift == shift)
        
        # Order by date (newest first)
        query = query.order_by(desc(DailyLog.date), DailyLog.shift)
        
        # Paginate results
        logs_pagination = query.paginate(page=page, per_page=per_page)
        
        # Prepare response
        logs = [log.to_dict() for log in logs_pagination.items]
        
        return jsonify({
            'logs': logs,
            'total': logs_pagination.total,
            'pages': logs_pagination.pages,
            'current_page': page,
            'user': user.username
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in get_user_daily_logs: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@daily_log_api.route('/api/daily_logs/search', methods=['GET'])
@login_required
@role_required('VIEW_DASHBOARD')
@rate_limit(limit=15, period=60)
def search_daily_logs():
    """Search daily logs by content."""
    try:
        # Parse query parameters
        query_term = request.args.get('q', '')
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        shift = request.args.get('shift')
        entry_type = request.args.get('entry_type')
        user_id = request.args.get('user_id', type=int)
        search_entries = request.args.get('search_entries', 'true').lower() == 'true'
        
        if not query_term and not any([start_date, end_date, shift, entry_type, user_id]):
            return jsonify({'error': 'Search query or at least one filter is required'}), 400
        
        # Build base query for logs
        logs_with_matching_entries = None
        
        # If we should search entries
        if search_entries and query_term:
            # Find logs that have entries matching the search term
            search_pattern = f"%{query_term}%"
            matching_entries = db.session.query(DailyLogEntry.log_id).filter(
                DailyLogEntry.text.ilike(search_pattern)
            ).distinct()
            
            # Get the log IDs that have matching entries
            log_ids_with_entries = [entry.log_id for entry in matching_entries]
            
            # Create a query for logs with matching entries or matching notes
            logs_with_matching_entries = DailyLog.query.filter(
                db.or_(
                    DailyLog.id.in_(log_ids_with_entries),
                    DailyLog.notes.ilike(f"%{query_term}%")
                )
            )
        else:
            # Only search in log notes
            logs_with_matching_entries = DailyLog.query
            if query_term:
                logs_with_matching_entries = logs_with_matching_entries.filter(
                    DailyLog.notes.ilike(f"%{query_term}%")
                )
        
        # Apply additional filters to the logs query
        if start_date:
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
                logs_with_matching_entries = logs_with_matching_entries.filter(
                    DailyLog.date >= start_date_obj
                )
            except ValueError:
                return jsonify({'error': 'Invalid start_date format, use YYYY-MM-DD'}), 400
        
        if end_date:
            try:
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
                logs_with_matching_entries = logs_with_matching_entries.filter(
                    DailyLog.date <= end_date_obj
                )
            except ValueError:
                return jsonify({'error': 'Invalid end_date format, use YYYY-MM-DD'}), 400
        
        if shift:
            logs_with_matching_entries = logs_with_matching_entries.filter(
                DailyLog.shift == shift
            )
        
        if user_id:
            logs_with_matching_entries = logs_with_matching_entries.filter(
                DailyLog.user_id == user_id
            )
        
        # Apply entry_type filter if searching entries
        if search_entries and entry_type:
            # Find logs with entries of the specified type that match the search term
            matching_entries_by_type = db.session.query(DailyLogEntry.log_id).filter(
                DailyLogEntry.type == entry_type
            )
            
            if query_term:
                matching_entries_by_type = matching_entries_by_type.filter(
                    DailyLogEntry.text.ilike(f"%{query_term}%")
                )
            
            # Get the log IDs that have matching entries of the specified type
            log_ids_with_entries_by_type = [entry.log_id for entry in matching_entries_by_type]
            
            logs_with_matching_entries = logs_with_matching_entries.filter(
                DailyLog.id.in_(log_ids_with_entries_by_type)
            )
        
        # Check permissions
        if not current_user.is_administrator():
            # If not admin, only search user's own logs
            logs_with_matching_entries = logs_with_matching_entries.filter(
                DailyLog.user_id == current_user.id
            )
        
        # Order by date (newest first)
        logs_with_matching_entries = logs_with_matching_entries.order_by(
            desc(DailyLog.date), DailyLog.shift
        )
        
        # Paginate results
        logs_pagination = logs_with_matching_entries.paginate(page=page, per_page=per_page)
        
        # Prepare response with highlighting for search term
        logs_result = []
        for log in logs_pagination.items:
            log_dict = log.to_dict()
            
            # Highlight search term in notes if present
            if query_term and log.notes and query_term.lower() in log.notes.lower():
                log_dict['notes_highlight'] = True
            
            # Highlight search term in entries if present and searching entries
            if search_entries and query_term:
                for entry in log_dict['entries']:
                    if query_term.lower() in entry['text'].lower():
                        entry['text_highlight'] = True
            
            logs_result.append(log_dict)
        
        return jsonify({
            'logs': logs_result,
            'total': logs_pagination.total,
            'pages': logs_pagination.pages,
            'current_page': page,
            'query': query_term,
            'filters': {
                'start_date': start_date,
                'end_date': end_date,
                'shift': shift,
                'entry_type': entry_type,
                'user_id': user_id,
                'search_entries': search_entries
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in search_daily_logs: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@daily_log_api.route('/api/daily_logs/date/<date>', methods=['GET'])
@login_required
@role_required('VIEW_DASHBOARD')
@rate_limit(limit=30, period=60)
def get_logs_by_date(date):
    """Get all logs for a specific date."""
    try:
        try:
            log_date = datetime.strptime(date, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format, use YYYY-MM-DD'}), 400
        
        # Build query
        query = DailyLog.query.filter(DailyLog.date == log_date)
        
        # Check permissions
        if not current_user.is_administrator():
            # If not admin, only show user's own logs
            query = query.filter(DailyLog.user_id == current_user.id)
        
        # Order by shift
        query = query.order_by(DailyLog.shift)
        
        # Execute query
        logs = query.all()
        
        # Prepare response
        result = [log.to_dict() for log in logs]
        
        return jsonify({
            'date': date,
            'logs': result,
            'count': len(result)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in get_logs_by_date: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@daily_log_api.route('/api/daily_log/current', methods=['GET'])
@login_required
@role_required('VIEW_DASHBOARD')
@rate_limit(limit=30, period=60)
def get_current_log():
    """Get the current active daily log for the user based on date and shift."""
    try:
        # Determine current shift based on time of day
        now = datetime.now()
        current_date = now.date()
        
        # Define shift times (can be configured in settings if needed)
        if 6 <= now.hour < 12:
            current_shift = 'morning'
        elif 12 <= now.hour < 18:
            current_shift = 'day'
        elif 18 <= now.hour < 24:
            current_shift = 'evening'
        else:  # 0-6
            current_shift = 'night'
        
        # Check if log exists for current date and shift
        log = DailyLog.query.filter(
            DailyLog.user_id == current_user.id,
            DailyLog.date == current_date,
            DailyLog.shift == current_shift
        ).first()
        
        # If no log exists, create one
        if not log:
            log = DailyLog(
                date=current_date,
                shift=current_shift,
                user_id=current_user.id,
                notes=""
            )
            db.session.add(log)
            db.session.commit()
            
            # Log activity
            log_activity(
                category='daily_log',
                action='create',
                user_id=current_user.id,
                resource_type='daily_log',
                resource_id=str(log.id)
            )
        
        return jsonify({
            'success': True,
            'log': log.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in get_current_log: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@daily_log_api.route('/api/daily_log/entry', methods=['POST'])
@login_required
@role_required('VIEW_DASHBOARD')
@csrf.exempt
@rate_limit(limit=60, period=60)
def add_log_entry():
    """Add a new entry to a daily log."""
    try:
        # Validate request
        schema = {
            'type': 'object',
            'required': ['text', 'type'],
            'properties': {
                'text': {'type': 'string', 'minLength': 1},
                'type': {'type': 'string'},
                'log_id': {'type': ['integer', 'null']}
            }
        }
        
        data = request.get_json()
        validation_result = validate_request_json(data, schema)
        
        if validation_result:
            return jsonify({'error': validation_result}), 400
        
        # Get log ID or create a new log if needed
        log_id = data.get('log_id')
        log = None
        
        if log_id:
            log = DailyLog.query.get(log_id)
            if not log:
                return jsonify({'error': 'Daily log not found'}), 404
                
            # Check permissions
            if log.user_id != current_user.id and not current_user.is_administrator():
                return jsonify({'error': 'You do not have permission to add entries to this log'}), 403
        else:
            # No log ID provided, get or create current log
            response = get_current_log()
            if isinstance(response, tuple) and response[1] != 200:
                # Error occurred in get_current_log
                return response
                
            response_data = json.loads(response.data)
            log = DailyLog.query.get(response_data['log']['id'])
        
        # Create new entry
        entry = DailyLogEntry(
            log_id=log.id,
            user_id=current_user.id,
            type=data['type'],
            text=data['text']
        )
        
        db.session.add(entry)
        db.session.commit()
        
        # Log activity
        log_activity(
            category='daily_log',
            action='add_entry',
            user_id=current_user.id,
            resource_type='daily_log_entry',
            resource_id=str(entry.id)
        )
        
        return jsonify({
            'success': True,
            'entry': entry.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in add_log_entry: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@daily_log_api.route('/api/daily_log/entry/<int:id>', methods=['PUT'])
@login_required
@role_required('VIEW_DASHBOARD')
@csrf.exempt
@rate_limit(limit=30, period=60)
def update_log_entry(id):
    """Update an existing log entry."""
    try:
        entry = DailyLogEntry.query.get(id)
        if not entry:
            return jsonify({'error': 'Log entry not found'}), 404
            
        # Check permissions
        if entry.user_id != current_user.id and not current_user.is_administrator():
            return jsonify({'error': 'You do not have permission to update this entry'}), 403
        
        # Validate request
        schema = {
            'type': 'object',
            'properties': {
                'text': {'type': 'string', 'minLength': 1},
                'type': {'type': 'string'}
            }
        }
        
        data = request.get_json()
        validation_result = validate_request_json(data, schema)
        
        if validation_result:
            return jsonify({'error': validation_result}), 400
        
        # Update entry
        if 'text' in data:
            entry.text = data['text']
            
        if 'type' in data:
            entry.type = data['type']
        
        db.session.commit()
        
        # Log activity
        log_activity(
            category='daily_log',
            action='update_entry',
            user_id=current_user.id,
            resource_type='daily_log_entry',
            resource_id=str(entry.id)
        )
        
        return jsonify({
            'success': True,
            'entry': entry.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in update_log_entry: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@daily_log_api.route('/api/daily_log/entry/<int:id>', methods=['DELETE'])
@login_required
@role_required('VIEW_DASHBOARD')
@csrf.exempt
@rate_limit(limit=20, period=60)
def delete_log_entry(id):
    """Delete a log entry."""
    try:
        entry = DailyLogEntry.query.get(id)
        if not entry:
            return jsonify({'error': 'Log entry not found'}), 404
            
        # Check permissions
        if entry.user_id != current_user.id and not current_user.is_administrator():
            return jsonify({'error': 'You do not have permission to delete this entry'}), 403
        
        # Store ID for activity log
        entry_id = entry.id
        
        # Delete entry
        db.session.delete(entry)
        db.session.commit()
        
        # Log activity
        log_activity(
            category='daily_log',
            action='delete_entry',
            user_id=current_user.id,
            resource_type='daily_log_entry',
            resource_id=str(entry_id)
        )
        
        return jsonify({
            'success': True,
            'message': 'Log entry deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in delete_log_entry: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@daily_log_api.route('/api/daily_log/<int:id>/pdf', methods=['GET'])
@login_required
@role_required('VIEW_DASHBOARD')
@rate_limit(limit=10, period=60)
def generate_log_pdf(id):
    """Generate a PDF of a daily log."""
    try:
        log = DailyLog.query.get(id)
        if not log:
            return jsonify({'error': 'Daily log not found'}), 404
            
        # Check permissions
        if log.user_id != current_user.id and not current_user.is_administrator():
            return jsonify({'error': 'You do not have permission to view this log'}), 403
        
        # Render PDF template
        from flask import render_template
        from weasyprint import HTML, CSS
        import tempfile
        
        # Get user details
        log_user = User.query.get(log.user_id)
        
        html = render_template(
            'pdf/daily_log.html',
            log=log,
            user=log_user,
            current_user=current_user,
            title=f"Daily Log {log.date.strftime('%Y-%m-%d')} - {log.shift.upper()}"
        )
        
        # Generate PDF
        pdf_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
        HTML(string=html).write_pdf(pdf_file.name)
        
        # Log activity
        log_activity(
            category='daily_log',
            action='generate_pdf',
            user_id=current_user.id,
            resource_type='daily_log',
            resource_id=str(log.id)
        )
        
        from flask import send_file
        return send_file(
            pdf_file.name,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"daily_log_{log.date.strftime('%Y%m%d')}_{log.shift}.pdf"
        )
        
    except Exception as e:
        current_app.logger.error(f"Error in generate_log_pdf: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@daily_log_api.route('/api/daily_logs/system-events', methods=['GET'])
@login_required
@role_required('VIEW_DASHBOARD')
@rate_limit(limit=15, period=60)
def get_system_events():
    """Get recent system events."""
    try:
        # Parse query parameters
        limit = min(request.args.get('limit', 50, type=int), 100)
        event_type = request.args.get('event_type')
        
        # Validate event type if provided
        if event_type and event_type not in EVENT_TYPES.values():
            return jsonify({'error': f'Invalid event type. Valid types: {", ".join(EVENT_TYPES.values())}'}), 400
            
        # Get system events
        events = get_recent_system_events(limit=limit, event_type=event_type)
        
        return jsonify({
            'events': events,
            'count': len(events),
            'types': list(EVENT_TYPES.values())
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in get_system_events: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@daily_log_api.route('/api/daily_log/<int:id>/archive', methods=['PUT'])
@login_required
@role_required('VIEW_DASHBOARD')
@csrf.exempt
@rate_limit(limit=10, period=60)
def archive_daily_log(id):
    """Archive a daily log."""
    try:
        # Get the log
        log = DailyLog.query.get(id)
        if not log:
            return jsonify({'error': 'Daily log not found'}), 404
            
        # Check permissions
        if log.user_id != current_user.id and not current_user.is_administrator():
            return jsonify({'error': 'You do not have permission to archive this log'}), 403
        
        # Check if already archived
        if log.is_archived:
            return jsonify({'message': 'Log is already archived', 'log': log.to_dict()}), 200
        
        # Archive the log
        log.is_archived = True
        log.archived_at = datetime.utcnow()
        db.session.commit()
        
        # Log activity
        log_activity(
            category='daily_log',
            action='archive',
            user_id=current_user.id,
            resource_type='daily_log',
            resource_id=str(log.id)
        )
        
        return jsonify({
            'success': True,
            'message': 'Log archived successfully',
            'log': log.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in archive_daily_log: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@daily_log_api.route('/api/daily_log/<int:id>/restore', methods=['PUT'])
@login_required
@role_required('VIEW_DASHBOARD')
@csrf.exempt
@rate_limit(limit=10, period=60)
def restore_daily_log(id):
    """Restore an archived daily log."""
    try:
        # Get the log
        log = DailyLog.query.get(id)
        if not log:
            return jsonify({'error': 'Daily log not found'}), 404
            
        # Check permissions
        if log.user_id != current_user.id and not current_user.is_administrator():
            return jsonify({'error': 'You do not have permission to restore this log'}), 403
        
        # Check if already active
        if not log.is_archived:
            return jsonify({'message': 'Log is already active', 'log': log.to_dict()}), 200
        
        # Restore the log
        log.is_archived = False
        log.archived_at = None
        db.session.commit()
        
        # Log activity
        log_activity(
            category='daily_log',
            action='restore',
            user_id=current_user.id,
            resource_type='daily_log',
            resource_id=str(log.id)
        )
        
        return jsonify({
            'success': True,
            'message': 'Log restored successfully',
            'log': log.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in restore_daily_log: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@daily_log_api.route('/api/daily_logs/archived', methods=['GET'])
@login_required
@role_required('VIEW_DASHBOARD')
@rate_limit(limit=15, period=60)
def get_archived_logs():
    """Get a list of archived daily logs."""
    try:
        # Parse query parameters
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        
        # Build query - only archived logs
        query = DailyLog.query.filter(DailyLog.is_archived == True)
        
        # Apply user filter if not admin
        if not current_user.is_administrator():
            query = query.filter(DailyLog.user_id == current_user.id)
        
        # Apply date range filters if provided
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                query = query.filter(DailyLog.date >= start_date)
            except ValueError:
                return jsonify({'error': 'Invalid start_date format, use YYYY-MM-DD'}), 400
        
        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                query = query.filter(DailyLog.date <= end_date)
            except ValueError:
                return jsonify({'error': 'Invalid end_date format, use YYYY-MM-DD'}), 400
        
        # Apply shift filter if provided
        shift = request.args.get('shift')
        if shift:
            query = query.filter(DailyLog.shift == shift)
        
        # Apply user_id filter if admin and user_id provided
        user_id = request.args.get('user_id', type=int)
        if current_user.is_administrator() and user_id:
            query = query.filter(DailyLog.user_id == user_id)
        
        # Order by archive date (newest first)
        query = query.order_by(desc(DailyLog.archived_at), desc(DailyLog.date), DailyLog.shift)
        
        # Paginate results
        logs_pagination = query.paginate(page=page, per_page=per_page)
        
        # Prepare response
        logs = [log.to_dict() for log in logs_pagination.items]
        
        return jsonify({
            'logs': logs,
            'total': logs_pagination.total,
            'pages': logs_pagination.pages,
            'current_page': page
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in get_archived_logs: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@daily_log_api.route('/api/daily_logs/auto-archive', methods=['POST'])
@login_required
@role_required('ADMIN')
@csrf.exempt
@rate_limit(limit=1, period=3600)  # Limit to once per hour
def auto_archive_logs():
    """Automatically archive logs older than the specified date."""
    try:
        # Parse request body
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body is required'}), 400
        
        days_old = data.get('days_old', 30)
        max_logs = data.get('max_logs', 100)
        
        if not isinstance(days_old, int) or days_old < 1:
            return jsonify({'error': 'days_old must be a positive integer'}), 400
        
        if not isinstance(max_logs, int) or max_logs < 1:
            return jsonify({'error': 'max_logs must be a positive integer'}), 400
        
        # Calculate the cutoff date
        cutoff_date = datetime.now().date() - timedelta(days=days_old)
        
        # Get logs older than cutoff_date and not already archived
        logs_to_archive = DailyLog.query.filter(
            DailyLog.date < cutoff_date,
            DailyLog.is_archived == False
        ).order_by(DailyLog.date).limit(max_logs).all()
        
        archived_count = 0
        current_time = datetime.utcnow()
        
        # Archive logs
        for log in logs_to_archive:
            log.is_archived = True
            log.archived_at = current_time
            archived_count += 1
            
            # Log activity
            log_activity(
                category='daily_log',
                action='auto_archive',
                user_id=current_user.id,
                resource_type='daily_log',
                resource_id=str(log.id)
            )
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Successfully archived {archived_count} logs',
            'archived_count': archived_count,
            'cutoff_date': cutoff_date.strftime('%Y-%m-%d')
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in auto_archive_logs: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@daily_log_api.route('/api/daily_log_entry/<int:entry_id>/attachment', methods=['POST'])
@login_required
@role_required('VIEW_DASHBOARD')
@csrf.exempt
@rate_limit(limit=10, period=60)
def upload_attachment(entry_id):
    """Upload an attachment for a log entry."""
    try:
        # Get the entry
        entry = DailyLogEntry.query.get(entry_id)
        if not entry:
            return jsonify({'error': 'Log entry not found'}), 404
            
        # Check permissions
        log = DailyLog.query.get(entry.log_id)
        if not log:
            return jsonify({'error': 'Parent log not found'}), 404
            
        if log.user_id != current_user.id and not current_user.is_administrator():
            return jsonify({'error': 'You do not have permission to modify this log entry'}), 403
            
        # Check if entry already has an attachment
        if entry.has_attachment:
            # Delete the old attachment if it exists
            if entry.attachment_path and os.path.exists(os.path.join(current_app.root_path, entry.attachment_path)):
                os.remove(os.path.join(current_app.root_path, entry.attachment_path))
        
        # Check if the post request has the file part
        if 'file' not in request.files:
            return jsonify({'error': 'No file part in the request'}), 400
            
        file = request.files['file']
        
        # If the user does not select a file, the browser submits an
        # empty file without a filename.
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
            
        if file and allowed_file(file.filename):
            # Create a secure filename with a UUID to prevent filename collisions
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid4().hex}_{filename}"
            
            # Create year/month subfolder structure
            now = datetime.now()
            year_month = now.strftime('%Y/%m')
            subfolder_path = os.path.join(UPLOAD_FOLDER, year_month)
            os.makedirs(os.path.join(current_app.root_path, subfolder_path), exist_ok=True)
            
            # Full path to save the file
            file_path = os.path.join(subfolder_path, unique_filename)
            full_path = os.path.join(current_app.root_path, file_path)
            
            # Save the file
            file.save(full_path)
            
            # Update the entry with attachment info
            entry.has_attachment = True
            entry.attachment_filename = filename
            entry.attachment_path = file_path
            entry.attachment_type = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'unknown'
            entry.attachment_size = os.path.getsize(full_path)
            
            db.session.commit()
            
            # Log activity
            log_activity(
                category='daily_log',
                action='add_attachment',
                user_id=current_user.id,
                resource_type='log_entry',
                resource_id=str(entry.id)
            )
            
            return jsonify({
                'success': True,
                'message': 'Attachment uploaded successfully',
                'entry': entry.to_dict()
            })
        else:
            return jsonify({'error': f'File type not allowed. Allowed types: {", ".join(ALLOWED_EXTENSIONS)}'}), 400
            
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in upload_attachment: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@daily_log_api.route('/api/daily_log_entry/<int:entry_id>/attachment', methods=['DELETE'])
@login_required
@role_required('VIEW_DASHBOARD')
@csrf.exempt
@rate_limit(limit=10, period=60)
def delete_attachment(entry_id):
    """Delete an attachment from a log entry."""
    try:
        # Get the entry
        entry = DailyLogEntry.query.get(entry_id)
        if not entry:
            return jsonify({'error': 'Log entry not found'}), 404
            
        # Check permissions
        log = DailyLog.query.get(entry.log_id)
        if not log:
            return jsonify({'error': 'Parent log not found'}), 404
            
        if log.user_id != current_user.id and not current_user.is_administrator():
            return jsonify({'error': 'You do not have permission to modify this log entry'}), 403
            
        # Check if entry has an attachment
        if not entry.has_attachment:
            return jsonify({'message': 'Entry has no attachment to delete'}), 200
            
        # Delete the file if it exists
        if entry.attachment_path and os.path.exists(os.path.join(current_app.root_path, entry.attachment_path)):
            os.remove(os.path.join(current_app.root_path, entry.attachment_path))
            
        # Update the entry
        entry.has_attachment = False
        entry.attachment_filename = None
        entry.attachment_path = None
        entry.attachment_type = None
        entry.attachment_size = None
        
        db.session.commit()
        
        # Log activity
        log_activity(
            category='daily_log',
            action='delete_attachment',
            user_id=current_user.id,
            resource_type='log_entry',
            resource_id=str(entry.id)
        )
        
        return jsonify({
            'success': True,
            'message': 'Attachment deleted successfully',
            'entry': entry.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in delete_attachment: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@daily_log_api.route('/api/daily_log_entry/<int:entry_id>/attachment', methods=['GET'])
@login_required
@role_required('VIEW_DASHBOARD')
def get_attachment(entry_id):
    """Get an attachment for a log entry."""
    try:
        # Get the entry
        entry = DailyLogEntry.query.get(entry_id)
        if not entry:
            return jsonify({'error': 'Log entry not found'}), 404
            
        # Check permissions
        log = DailyLog.query.get(entry.log_id)
        if not log:
            return jsonify({'error': 'Parent log not found'}), 404
            
        # For viewing attachments, we allow anyone with VIEW_DASHBOARD to view
        # as long as the log is not archived or the user is an admin
        if log.is_archived and not current_user.is_administrator():
            return jsonify({'error': 'Log is archived. Contact an administrator to view attachments'}), 403
            
        # Check if entry has an attachment
        if not entry.has_attachment or not entry.attachment_path:
            return jsonify({'error': 'Entry has no attachment'}), 404
            
        # Check if file exists
        file_path = os.path.join(current_app.root_path, entry.attachment_path)
        if not os.path.exists(file_path):
            # Update entry to reflect missing attachment
            entry.has_attachment = False
            entry.attachment_path = None
            db.session.commit()
            return jsonify({'error': 'Attachment file not found'}), 404
            
        # Determine if we should download or display inline
        as_attachment = request.args.get('download', 'false').lower() == 'true'
        
        # Log activity
        log_activity(
            category='daily_log',
            action='view_attachment',
            user_id=current_user.id,
            resource_type='log_entry',
            resource_id=str(entry.id)
        )
        
        # Return the file
        return send_file(
            file_path,
            as_attachment=as_attachment,
            download_name=entry.attachment_filename if as_attachment else None
        )
        
    except Exception as e:
        current_app.logger.error(f"Error in get_attachment: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500
