"""
Audit Log Management Blueprint

This module provides endpoints for administrators to view and search security audit logs.
"""

from flask import Blueprint, jsonify, request, current_app, render_template
from flask_login import login_required, current_user
from models import AuditLog, Permission, db
from blueprints.admin import permission_required
from utils.security import ajax_csrf_protect
from utils.decorators import read_endpoint
from utils.audit_log import log_audit_event, AuditCategory, AuditSeverity
from datetime import datetime, timedelta
import json

bp = Blueprint('audit', __name__)

@bp.route('/logs', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_SYSTEM_LOGS)
@read_endpoint(limit="60/minute")
def get_audit_logs():
    """Get audit logs with optional filtering."""
    try:
        # Log this access to audit trail
        log_audit_event(
            category=AuditCategory.DATA_ACCESS,
            action="Viewed audit logs",
            severity=AuditSeverity.INFO,
            user_id=current_user.id
        )
        
        # Get query parameters
        category = request.args.get('category')
        severity = request.args.get('severity')
        user_id = request.args.get('user_id')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        resource_type = request.args.get('resource_type')
        page = int(request.args.get('page', 1))
        per_page = min(int(request.args.get('per_page', 50)), 100)  # Limit to 100 max
        
        # Build the query
        query = AuditLog.query
        
        if category:
            query = query.filter(AuditLog.category == category)
        
        if severity:
            query = query.filter(AuditLog.severity == severity)
        
        if user_id:
            query = query.filter(AuditLog.user_id == user_id)
        
        if resource_type:
            query = query.filter(AuditLog.resource_type == resource_type)
        
        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(AuditLog.timestamp >= start_date)
            except ValueError:
                pass
        
        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d')
                # Add one day to include the entire end date
                end_date = end_date + timedelta(days=1)
                query = query.filter(AuditLog.timestamp < end_date)
            except ValueError:
                pass
        
        # Order by timestamp in descending order
        query = query.order_by(AuditLog.timestamp.desc())
        
        # Paginate the results
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        logs = pagination.items
        
        return jsonify({
            'success': True,
            'logs': [log.to_dict() for log in logs],
            'total': pagination.total,
            'pages': pagination.pages,
            'current_page': page
        })
    except Exception as e:
        current_app.logger.error(f"Error retrieving audit logs: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error retrieving audit logs: {str(e)}"
        }), 500

@bp.route('/logs/search', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_SYSTEM_LOGS)
@read_endpoint(limit="60/minute")
def search_audit_logs():
    """Search audit logs by keyword."""
    try:
        search_term = request.args.get('q', '')
        if not search_term or len(search_term) < 3:
            return jsonify({
                'success': False,
                'message': "Search term must be at least 3 characters"
            }), 400
        
        # Log this search to audit trail
        log_audit_event(
            category=AuditCategory.DATA_ACCESS,
            action="Searched audit logs",
            severity=AuditSeverity.INFO,
            user_id=current_user.id,
            details={'search_term': search_term}
        )
        
        page = int(request.args.get('page', 1))
        per_page = min(int(request.args.get('per_page', 50)), 100)
        
        # Perform search using SQLAlchemy
        query = AuditLog.query.filter(
            db.or_(
                AuditLog.action.ilike(f'%{search_term}%'),
                AuditLog.details.ilike(f'%{search_term}%'),
                AuditLog.endpoint.ilike(f'%{search_term}%'),
                AuditLog.resource_type.ilike(f'%{search_term}%')
            )
        ).order_by(AuditLog.timestamp.desc())
        
        # Paginate the results
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        logs = pagination.items
        
        return jsonify({
            'success': True,
            'logs': [log.to_dict() for log in logs],
            'total': pagination.total,
            'pages': pagination.pages,
            'current_page': page
        })
    except Exception as e:
        current_app.logger.error(f"Error searching audit logs: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error searching audit logs: {str(e)}"
        }), 500

@bp.route('/logs/<int:log_id>', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_SYSTEM_LOGS)
@ajax_csrf_protect
def get_audit_log(log_id):
    """Get a specific audit log by ID."""
    try:
        log = AuditLog.query.get_or_404(log_id)
        
        # Log this access to audit trail
        log_audit_event(
            category=AuditCategory.DATA_ACCESS,
            action="Viewed audit log details",
            severity=AuditSeverity.INFO,
            user_id=current_user.id,
            resource_id=str(log_id),
            resource_type='audit_log'
        )
        
        return jsonify({
            'success': True,
            'log': log.to_dict()
        })
    except Exception as e:
        current_app.logger.error(f"Error retrieving audit log {log_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error retrieving audit log: {str(e)}"
        }), 500

@bp.route('/logs/categories', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_SYSTEM_LOGS)
@ajax_csrf_protect
def get_audit_categories():
    """Get all unique audit log categories."""
    try:
        categories = db.session.query(AuditLog.category).distinct().all()
        return jsonify({
            'success': True,
            'categories': [cat[0] for cat in categories]
        })
    except Exception as e:
        current_app.logger.error(f"Error retrieving audit categories: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error retrieving audit categories: {str(e)}"
        }), 500

@bp.route('/logs/severities', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_SYSTEM_LOGS)
@ajax_csrf_protect
def get_audit_severities():
    """Get all unique audit log severities."""
    try:
        severities = db.session.query(AuditLog.severity).distinct().all()
        return jsonify({
            'success': True,
            'severities': [sev[0] for sev in severities]
        })
    except Exception as e:
        current_app.logger.error(f"Error retrieving audit severities: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error retrieving audit severities: {str(e)}"
        }), 500

@bp.route('/logs/summary', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_SYSTEM_LOGS)
@read_endpoint(limit="60/minute")
def get_audit_summary():
    """Get a summary of recent audit activity."""
    try:
        # Log this access to audit trail
        log_audit_event(
            category=AuditCategory.DATA_ACCESS,
            action="Viewed audit logs summary",
            severity=AuditSeverity.INFO,
            user_id=current_user.id
        )
        
        # Get counts for different severity levels in the last 24 hours
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        
        critical_count = AuditLog.query.filter(
            AuditLog.severity == AuditSeverity.CRITICAL,
            AuditLog.timestamp >= yesterday
        ).count()
        
        error_count = AuditLog.query.filter(
            AuditLog.severity == AuditSeverity.ERROR,
            AuditLog.timestamp >= yesterday
        ).count()
        
        warning_count = AuditLog.query.filter(
            AuditLog.severity == AuditSeverity.WARNING,
            AuditLog.timestamp >= yesterday
        ).count()
        
        # Get counts by category
        category_counts = db.session.query(
            AuditLog.category, db.func.count(AuditLog.id)
        ).filter(
            AuditLog.timestamp >= yesterday
        ).group_by(AuditLog.category).all()
        
        # Get recent critical events
        critical_events = AuditLog.query.filter(
            AuditLog.severity == AuditSeverity.CRITICAL
        ).order_by(AuditLog.timestamp.desc()).limit(5).all()
        
        return jsonify({
            'success': True,
            'summary': {
                'critical_count': critical_count,
                'error_count': error_count,
                'warning_count': warning_count,
                'category_counts': {cat: count for cat, count in category_counts},
                'critical_events': [event.to_dict() for event in critical_events],
                'time_period': {
                    'start': yesterday.isoformat(),
                    'end': now.isoformat()
                }
            }
        })
    except Exception as e:
        current_app.logger.error(f"Error retrieving audit summary: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error retrieving audit summary: {str(e)}"
        }), 500

@bp.route('/logs/export', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_SYSTEM_LOGS)
@read_endpoint(limit="10/minute")
def export_audit_logs():
    """Export audit logs to JSON format."""
    try:
        # Get query parameters
        category = request.args.get('category')
        severity = request.args.get('severity')
        user_id = request.args.get('user_id')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        resource_type = request.args.get('resource_type')
        limit = min(int(request.args.get('limit', 1000)), 5000)  # Limit to 5000 max
        
        # Build the query
        query = AuditLog.query
        
        if category:
            query = query.filter(AuditLog.category == category)
        
        if severity:
            query = query.filter(AuditLog.severity == severity)
        
        if user_id:
            query = query.filter(AuditLog.user_id == user_id)
        
        if resource_type:
            query = query.filter(AuditLog.resource_type == resource_type)
        
        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(AuditLog.timestamp >= start_date)
            except ValueError:
                pass
        
        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d')
                # Add one day to include the entire end date
                end_date = end_date + timedelta(days=1)
                query = query.filter(AuditLog.timestamp < end_date)
            except ValueError:
                pass
        
        # Order by timestamp in descending order and limit
        logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
        
        # Log this export to audit trail
        log_audit_event(
            category=AuditCategory.DATA_ACCESS,
            action="Exported audit logs",
            severity=AuditSeverity.INFO,
            user_id=current_user.id,
            details={
                'record_count': len(logs),
                'filters': {
                    'category': category,
                    'severity': severity,
                    'user_id': user_id,
                    'start_date': start_date,
                    'end_date': end_date,
                    'resource_type': resource_type
                }
            }
        )
        
        # Create formatted export
        export_data = {
            'metadata': {
                'exported_at': datetime.utcnow().isoformat(),
                'exported_by': current_user.username,
                'record_count': len(logs),
                'filters': {
                    'category': category,
                    'severity': severity,
                    'user_id': user_id,
                    'start_date': start_date.isoformat() if isinstance(start_date, datetime) else start_date,
                    'end_date': end_date.isoformat() if isinstance(end_date, datetime) else end_date,
                    'resource_type': resource_type
                }
            },
            'logs': [log.to_dict() for log in logs]
        }
        
        return jsonify(export_data)
    except Exception as e:
        current_app.logger.error(f"Error exporting audit logs: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error exporting audit logs: {str(e)}"
        }), 500
