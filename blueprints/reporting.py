from flask import Blueprint, jsonify, request, current_app, render_template, send_file, flash, redirect, url_for
from flask_login import login_required, current_user
from models import Permission, Incident, Unit, IncidentType, UnitAssignment, IncidentLog, DailyLog, User, AMPDSProtocol, db
from blueprints.admin import permission_required
from datetime import datetime, timedelta
from sqlalchemy import func, desc, asc, and_, or_
import pandas as pd
import io
import csv
import tempfile
import json
import os
from collections import defaultdict
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns
from extensions import limiter
from utils.scheduler import scheduler
from utils.security import ajax_csrf_protect
from utils.file_utils import ensure_directory_exists
import logging

# Import ReportLab for PDF generation
import reportlab
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
# Import BeautifulSoup for HTML parsing
from bs4 import BeautifulSoup

# Create blueprint
bp = Blueprint('reporting', __name__)

# Apply rate limiting to all routes in this blueprint
limiter.limit("300/hour")(bp)
limiter.limit("5/second")(bp)

# Security decorator for sensitive endpoints
def secure_endpoint(limit="60/minute"):
    """Decorator that combines CSRF protection and rate limiting for sensitive endpoints."""
    def decorator(f):
        csrf_protected = ajax_csrf_protect(f)
        rate_limited = limiter.limit(limit)(csrf_protected)
        return rate_limited
    return decorator

# Decorator for read-only endpoints
def read_endpoint(limit="120/minute"):
    """Decorator for read-only endpoints with higher rate limits."""
    def decorator(f):
        csrf_protected = ajax_csrf_protect(f)
        rate_limited = limiter.limit(limit)(csrf_protected)
        return rate_limited
    return decorator

# Helper function to generate PDF from HTML
def generate_pdf(html_content, css_content=None, title="Report"):
    """
    Generate a PDF from HTML content using ReportLab.
    
    Args:
        html_content: HTML content to convert to PDF
        css_content: CSS content (not directly used by ReportLab but kept for API compatibility)
        title: Title of the report
        
    Returns:
        bytes: PDF content as bytes or None if generation fails
    """
    try:
        # Parse HTML
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Create buffer for PDF
        buffer = io.BytesIO()
        
        # Create PDF document
        doc = SimpleDocTemplate(buffer, pagesize=letter, 
                               rightMargin=72, leftMargin=72,
                               topMargin=72, bottomMargin=72,
                               title=title)
        
        # Define styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'Title',
            parent=styles['Heading1'],
            fontSize=16,
            alignment=TA_CENTER,
            spaceAfter=12
        )
        normal_style = styles["Normal"]
        heading_style = styles["Heading2"]
        
        # Prepare content
        content = []
        
        # Add title
        content.append(Paragraph(title, title_style))
        content.append(Spacer(1, 0.25*inch))
        
        # Process text content
        for element in soup.find_all(['h1', 'h2', 'h3', 'p', 'table']):
            if element.name.startswith('h'):
                content.append(Paragraph(element.get_text().strip(), heading_style))
                content.append(Spacer(1, 0.1*inch))
            elif element.name == 'p':
                text = element.get_text().strip()
                if text:  # Only add non-empty paragraphs
                    content.append(Paragraph(text, normal_style))
                    content.append(Spacer(1, 0.1*inch))
            elif element.name == 'table':
                # Process table element
                rows = element.find_all('tr')
                table_data = []
                
                for row in rows:
                    row_data = []
                    cells = row.find_all(['td', 'th'])
                    for cell in cells:
                        row_data.append(cell.get_text().strip())
                    if row_data:  # Only add non-empty rows
                        table_data.append(row_data)
                
                if table_data:
                    # Create ReportLab Table
                    pdf_table = Table(table_data)
                    
                    # Add style to the table
                    style = TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, 0), 12),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black)
                    ])
                    pdf_table.setStyle(style)
                    
                    content.append(pdf_table)
                    content.append(Spacer(1, 0.2*inch))
        
        # Build the PDF
        doc.build(content)
        
        # Get the value from the BytesIO buffer
        pdf = buffer.getvalue()
        buffer.close()
        
        logging.info("Successfully generated PDF with ReportLab")
        return pdf
    except Exception as e:
        logging.error(f"ReportLab failed to generate PDF: {str(e)}")
        return None

# Helper function to format date ranges
def format_date_range(start_date, end_date):
    """Format a date range as a string."""
    if start_date == end_date:
        return start_date.strftime('%Y-%m-%d')
    else:
        return f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"

# ===== Incident Report Endpoints =====

@bp.route('/reports/incidents/<int:incident_id>/pdf', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_REPORTS)
@read_endpoint()
def generate_incident_pdf(incident_id):
    """Generate a PDF report for a specific incident."""
    try:
        # Get incident with all related data
        incident = Incident.query.get_or_404(incident_id)
        
        # Collect all relevant information
        incident_data = incident.to_dict()
        
        # Get unit assignments
        assignments = UnitAssignment.query.filter_by(incident_id=incident_id).all()
        assignment_data = [a.to_dict() for a in assignments]
        
        # Get logs
        logs = IncidentLog.query.filter_by(incident_id=incident_id).order_by(IncidentLog.timestamp).all()
        log_data = [log.to_dict() for log in logs]
        
        # Get AMPDS protocol data if incident has an AMPDS code
        protocol_data = None
        if incident.ampds_code:
            protocol = AMPDSProtocol.query.filter_by(unique_id=incident.ampds_code).first()
            if protocol:
                protocol_data = {
                    'unique_id': protocol.unique_id,
                    'category': protocol.category,
                    'subcategory': protocol.subcategory,
                    'card_number': protocol.card_number,
                    'priority': protocol.priority,
                    'dispatch_advice': protocol.dispatch_advice
                }
        
        # Render HTML template with incident data
        html_content = render_template(
            'reports/incident_report.html',
            incident=incident_data,
            assignments=assignment_data,
            logs=log_data,
            protocol=protocol_data,
            generated_at=datetime.utcnow(),
            generated_by=current_user.full_name()
        )
        
        # Generate PDF from HTML
        pdf_content = generate_pdf(html_content)
        
        # Check if PDF generation was successful
        if pdf_content is None:
            # If ReportLab fails, return a JSON error response
            return jsonify({
                'success': False,
                'message': 'PDF generation failed. Please check the logs for errors.'
            }), 500
        
        # Create a BytesIO object
        pdf_io = io.BytesIO(pdf_content)
        pdf_io.seek(0)
        
        # Return the PDF file
        return send_file(
            pdf_io,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"Incident_{incident.incident_number}_Report.pdf"
        )
        
    except Exception as e:
        current_app.logger.error(f"Error generating incident PDF: {str(e)}")
        return jsonify({'success': False, 'message': f'Error generating PDF: {str(e)}'}), 500

@bp.route('/reports/incidents/csv', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_REPORTS)
@read_endpoint()
def export_incidents_csv():
    """Export incidents to CSV file with filtering options."""
    try:
        # Get filter parameters
        date_start = request.args.get('date_start')
        date_end = request.args.get('date_end')
        status = request.args.get('status')
        incident_type = request.args.get('incident_type')
        priority = request.args.get('priority')
        
        # Build the query
        query = Incident.query
        
        # Apply filters if provided
        if date_start:
            try:
                start_date = datetime.strptime(date_start, '%Y-%m-%d')
                query = query.filter(Incident.created_at >= start_date)
            except ValueError:
                return jsonify({'success': False, 'message': 'Invalid date_start format. Use YYYY-MM-DD'}), 400
                
        if date_end:
            try:
                end_date = datetime.strptime(date_end, '%Y-%m-%d')
                end_date = end_date.replace(hour=23, minute=59, second=59)
                query = query.filter(Incident.created_at <= end_date)
            except ValueError:
                return jsonify({'success': False, 'message': 'Invalid date_end format. Use YYYY-MM-DD'}), 400
                
        if status:
            query = query.filter(Incident.status == status)
            
        if incident_type:
            query = query.filter(Incident.incident_type_id == incident_type)
            
        if priority:
            if priority.isdigit():
                query = query.filter(Incident.priority == int(priority))
            else:
                priority_value = Incident.PRIORITY_MAP.get(priority.upper())
                if priority_value:
                    query = query.filter(Incident.priority == priority_value)
        
        # Execute query
        incidents = query.order_by(Incident.created_at.desc()).all()
        
        # Create a CSV in memory
        csv_output = io.StringIO()
        fieldnames = [
            'Incident Number', 'Type', 'Priority', 'Status', 'Location', 
            'Caller', 'Callback Number', 'Description', 'Resolution',
            'AMPDS Code', 'Created At', 'Created By', 'Updated At'
        ]
        
        writer = csv.DictWriter(csv_output, fieldnames=fieldnames)
        writer.writeheader()
        
        # Add incident data
        for incident in incidents:
            incident_type = IncidentType.query.get(incident.incident_type_id).name if incident.incident_type_id else 'Unknown'
            created_by = User.query.get(incident.created_by_id).full_name() if incident.created_by_id else 'System'
            
            writer.writerow({
                'Incident Number': incident.incident_number,
                'Type': incident_type,
                'Priority': incident.get_priority_string(),
                'Status': incident.status,
                'Location': incident.location or '',
                'Caller': incident.caller or '',
                'Callback Number': incident.callback_number or '',
                'Description': incident.description or '',
                'Resolution': incident.resolution or '',
                'AMPDS Code': incident.ampds_code or '',
                'Created At': incident.created_at.strftime('%Y-%m-%d %H:%M:%S') if incident.created_at else '',
                'Created By': created_by,
                'Updated At': incident.updated_at.strftime('%Y-%m-%d %H:%M:%S') if incident.updated_at else ''
            })
        
        # Prepare response
        csv_output.seek(0)
        
        # Create a BytesIO object
        mem = io.BytesIO()
        mem.write(csv_output.getvalue().encode('utf-8'))
        mem.seek(0)
        
        # Generate filename with date range
        if date_start and date_end:
            filename = f"Incidents_{date_start}_to_{date_end}.csv"
        else:
            filename = f"Incidents_Export_{datetime.now().strftime('%Y%m%d')}.csv"
        
        return send_file(
            mem,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        current_app.logger.error(f"Error exporting incidents to CSV: {str(e)}")
        return jsonify({'success': False, 'message': f'Error exporting to CSV: {str(e)}'}), 500

# ===== Statistical Reporting Endpoints =====

@bp.route('/reports/statistics/incidents', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_REPORTS)
@read_endpoint()
def get_incident_statistics():
    """Get incident statistics with filtering options."""
    try:
        # Get filter parameters
        date_start = request.args.get('date_start')
        date_end = request.args.get('date_end')
        group_by = request.args.get('group_by', 'day')  # day, week, month
        
        # Parse dates
        if date_start:
            try:
                start_date = datetime.strptime(date_start, '%Y-%m-%d')
            except ValueError:
                return jsonify({'success': False, 'message': 'Invalid date_start format. Use YYYY-MM-DD'}), 400
        else:
            # Default to last 30 days
            start_date = datetime.utcnow() - timedelta(days=30)
            
        if date_end:
            try:
                end_date = datetime.strptime(date_end, '%Y-%m-%d')
                end_date = end_date.replace(hour=23, minute=59, second=59)
            except ValueError:
                return jsonify({'success': False, 'message': 'Invalid date_end format. Use YYYY-MM-DD'}), 400
        else:
            end_date = datetime.utcnow()
        
        # Build query for incidents in date range
        incidents = Incident.query.filter(
            Incident.created_at >= start_date,
            Incident.created_at <= end_date
        ).all()
        
        # Aggregate data
        stats = {
            'total_incidents': len(incidents),
            'by_status': defaultdict(int),
            'by_priority': defaultdict(int),
            'by_type': defaultdict(int),
            'time_series': [],
            'average_resolution_time': None,
            'peak_hours': defaultdict(int)
        }
        
        # Group by status, priority, and type
        for incident in incidents:
            stats['by_status'][incident.status] += 1
            stats['by_priority'][incident.get_priority_string()] += 1
            
            if incident.incident_type_id:
                incident_type = IncidentType.query.get(incident.incident_type_id)
                if incident_type:
                    stats['by_type'][incident_type.name] += 1
                else:
                    stats['by_type']['Unknown'] += 1
            else:
                stats['by_type']['Unknown'] += 1
            
            # Track hour of day for peak hour analysis
            if incident.created_at:
                hour = incident.created_at.hour
                stats['peak_hours'][hour] += 1
        
        # Convert defaultdicts to regular dicts for JSON serialization
        stats['by_status'] = dict(stats['by_status'])
        stats['by_priority'] = dict(stats['by_priority'])
        stats['by_type'] = dict(stats['by_type'])
        stats['peak_hours'] = dict(stats['peak_hours'])
        
        # Calculate average resolution time for closed incidents
        closed_incidents = [inc for inc in incidents if inc.status == 'closed' and inc.created_at]
        if closed_incidents:
            resolution_times = []
            for incident in closed_incidents:
                if incident.updated_at and incident.created_at:
                    delta = incident.updated_at - incident.created_at
                    resolution_times.append(delta.total_seconds() / 60)  # in minutes
            
            if resolution_times:
                stats['average_resolution_time'] = sum(resolution_times) / len(resolution_times)
        
        # Group incidents by time period for time series
        if group_by == 'day':
            # Group by day
            date_groups = defaultdict(int)
            for incident in incidents:
                if incident.created_at:
                    date_key = incident.created_at.strftime('%Y-%m-%d')
                    date_groups[date_key] += 1
            
            # Convert to time series format
            for date_str, count in sorted(date_groups.items()):
                stats['time_series'].append({
                    'date': date_str,
                    'count': count
                })
                
        elif group_by == 'week':
            # Group by week
            week_groups = defaultdict(int)
            for incident in incidents:
                if incident.created_at:
                    year = incident.created_at.isocalendar()[0]
                    week = incident.created_at.isocalendar()[1]
                    week_key = f"{year}-W{week:02d}"
                    week_groups[week_key] += 1
            
            # Convert to time series format
            for week_str, count in sorted(week_groups.items()):
                stats['time_series'].append({
                    'date': week_str,
                    'count': count
                })
                
        elif group_by == 'month':
            # Group by month
            month_groups = defaultdict(int)
            for incident in incidents:
                if incident.created_at:
                    month_key = incident.created_at.strftime('%Y-%m')
                    month_groups[month_key] += 1
            
            # Convert to time series format
            for month_str, count in sorted(month_groups.items()):
                stats['time_series'].append({
                    'date': month_str,
                    'count': count
                })
        
        # Add metadata
        stats['date_range'] = {
            'start': start_date.strftime('%Y-%m-%d'),
            'end': end_date.strftime('%Y-%m-%d')
        }
        stats['group_by'] = group_by
        
        return jsonify({
            'success': True,
            'statistics': stats
        })
        
    except Exception as e:
        current_app.logger.error(f"Error generating incident statistics: {str(e)}")
        return jsonify({'success': False, 'message': f'Error generating statistics: {str(e)}'}), 500

@bp.route('/api/statistics/incidents/by-type', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_REPORTS)
@read_endpoint()
def incidents_by_type():
    """Get statistics on incidents by incident type."""
    try:
        # Get filter parameters
        date_start = request.args.get('date_start')
        date_end = request.args.get('date_end')
        status = request.args.get('status')
        
        # Build base query to count incidents by type
        query = db.session.query(
            IncidentType.name.label('type_name'),
            IncidentType.id.label('type_id'),
            func.count(Incident.id).label('count')
        ).join(
            Incident, Incident.incident_type_id == IncidentType.id
        ).group_by(
            IncidentType.id,
            IncidentType.name
        )
        
        # Apply filters if provided
        if date_start:
            try:
                start_date = datetime.strptime(date_start, '%Y-%m-%d')
                query = query.filter(Incident.created_at >= start_date)
            except ValueError:
                return jsonify({'success': False, 'message': 'Invalid date_start format. Use YYYY-MM-DD'}), 400
                
        if date_end:
            try:
                end_date = datetime.strptime(date_end, '%Y-%m-%d')
                end_date = end_date.replace(hour=23, minute=59, second=59)
                query = query.filter(Incident.created_at <= end_date)
            except ValueError:
                return jsonify({'success': False, 'message': 'Invalid date_end format. Use YYYY-MM-DD'}), 400
                
        if status:
            query = query.filter(Incident.status == status)
        
        # Execute query
        results = query.all()
        
        # Format results
        data = [
            {
                'type_id': result.type_id,
                'type_name': result.type_name, 
                'count': result.count
            } for result in results
        ]
        
        # Find total for calculating percentages
        total = sum(item['count'] for item in data)
        
        # Add percentage to each data point
        for item in data:
            item['percentage'] = round((item['count'] / total * 100), 1) if total > 0 else 0
        
        return jsonify({
            'success': True,
            'data': data,
            'total': total
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting incident statistics by type: {str(e)}")
        return jsonify({'success': False, 'message': f'Error getting statistics: {str(e)}'}), 500

@bp.route('/api/statistics/incidents/by-priority', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_REPORTS)
@read_endpoint()
def incidents_by_priority():
    """Get statistics on incidents by priority level."""
    try:
        # Get filter parameters
        date_start = request.args.get('date_start')
        date_end = request.args.get('date_end')
        status = request.args.get('status')
        incident_type = request.args.get('incident_type')
        priority = request.args.get('priority')
        
        # Build base query
        query = db.session.query(
            Incident.priority.label('priority_value'),
            func.count(Incident.id).label('count')
        ).group_by(
            Incident.priority
        )
        
        # Apply filters if provided
        if date_start:
            try:
                start_date = datetime.strptime(date_start, '%Y-%m-%d')
                query = query.filter(Incident.created_at >= start_date)
            except ValueError:
                return jsonify({'success': False, 'message': 'Invalid date_start format. Use YYYY-MM-DD'}), 400
                
        if date_end:
            try:
                end_date = datetime.strptime(date_end, '%Y-%m-%d')
                end_date = end_date.replace(hour=23, minute=59, second=59)
                query = query.filter(Incident.created_at <= end_date)
            except ValueError:
                return jsonify({'success': False, 'message': 'Invalid date_end format. Use YYYY-MM-DD'}), 400
                
        if status:
            query = query.filter(Incident.status == status)
            
        if incident_type:
            if incident_type.isdigit():
                query = query.filter(Incident.incident_type_id == int(incident_type))
        
        # Execute query
        results = query.all()
        
        # Format results with priority labels
        priority_labels = {
            1: 'Emergency',
            2: 'Urgent',
            3: 'Non-urgent'
        }
        
        data = [
            {
                'priority_value': result.priority_value,
                'priority_label': priority_labels.get(result.priority_value, 'Unknown'), 
                'count': result.count
            } for result in results
        ]
        
        # Find total for calculating percentages
        total = sum(item['count'] for item in data)
        
        # Add percentage to each data point
        for item in data:
            item['percentage'] = round((item['count'] / total * 100), 1) if total > 0 else 0
        
        return jsonify({
            'success': True,
            'data': data,
            'total': total
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting incident statistics by priority: {str(e)}")
        return jsonify({'success': False, 'message': f'Error getting statistics: {str(e)}'}), 500

@bp.route('/api/statistics/incidents/by-status', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_REPORTS)
@read_endpoint()
def incidents_by_status():
    """Get statistics on incidents by status."""
    try:
        # Get filter parameters
        date_start = request.args.get('date_start')
        date_end = request.args.get('date_end')
        incident_type = request.args.get('incident_type')
        priority = request.args.get('priority')
        
        # Build base query
        query = db.session.query(
            Incident.status.label('status'),
            func.count(Incident.id).label('count')
        ).group_by(
            Incident.status
        )
        
        # Apply filters if provided
        if date_start:
            try:
                start_date = datetime.strptime(date_start, '%Y-%m-%d')
                query = query.filter(Incident.created_at >= start_date)
            except ValueError:
                return jsonify({'success': False, 'message': 'Invalid date_start format. Use YYYY-MM-DD'}), 400
                
        if date_end:
            try:
                end_date = datetime.strptime(date_end, '%Y-%m-%d')
                end_date = end_date.replace(hour=23, minute=59, second=59)
                query = query.filter(Incident.created_at <= end_date)
            except ValueError:
                return jsonify({'success': False, 'message': 'Invalid date_end format. Use YYYY-MM-DD'}), 400
                
        if incident_type:
            if incident_type.isdigit():
                query = query.filter(Incident.incident_type_id == int(incident_type))
            
        if priority:
            if priority.isdigit():
                query = query.filter(Incident.priority == int(priority))
            else:
                priority_value = Incident.PRIORITY_MAP.get(priority.upper())
                if priority_value:
                    query = query.filter(Incident.priority == priority_value)
        
        # Execute query
        results = query.all()
        
        # Format results
        data = [
            {
                'status': result.status,
                'count': result.count
            } for result in results
        ]
        
        # Find total for calculating percentages
        total = sum(item['count'] for item in data)
        
        # Add percentage to each data point
        for item in data:
            item['percentage'] = round((item['count'] / total * 100), 1) if total > 0 else 0
        
        return jsonify({
            'success': True,
            'data': data,
            'total': total
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting incident statistics by status: {str(e)}")
        return jsonify({'success': False, 'message': f'Error getting statistics: {str(e)}'}), 500

@bp.route('/api/statistics/incidents/activity', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_REPORTS)
@read_endpoint()
def incident_activity():
    """Get incident activity statistics (count by day)."""
    try:
        # Get filter parameters
        date_start = request.args.get('date_start')
        date_end = request.args.get('date_end')
        status = request.args.get('status')
        incident_type = request.args.get('incident_type')
        priority = request.args.get('priority')
        
        # Default to last 30 days if no date range provided
        if not date_start:
            date_start = (datetime.utcnow() - timedelta(days=30)).strftime('%Y-%m-%d')
        if not date_end:
            date_end = datetime.utcnow().strftime('%Y-%m-%d')
            
        # Parse dates
        try:
            start_date = datetime.strptime(date_start, '%Y-%m-%d')
            end_date = datetime.strptime(date_end, '%Y-%m-%d')
            end_date = end_date.replace(hour=23, minute=59, second=59)
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid date format. Use YYYY-MM-DD'}), 400
                
        # Build query to count incidents by day
        query = db.session.query(
            func.date(Incident.created_at).label('date'),
            func.count(Incident.id).label('count')
        ).filter(
            Incident.created_at.between(start_date, end_date)
        ).group_by(
            func.date(Incident.created_at)
        )
        
        # Apply additional filters if provided
        if status:
            query = query.filter(Incident.status == status)
            
        if incident_type:
            if incident_type.isdigit():
                query = query.filter(Incident.incident_type_id == int(incident_type))
            
        if priority:
            if priority.isdigit():
                query = query.filter(Incident.priority == int(priority))
            else:
                priority_value = Incident.PRIORITY_MAP.get(priority.upper())
                if priority_value:
                    query = query.filter(Incident.priority == priority_value)
        
        # Execute query
        results = query.all()
        
        # Create a list of all dates in the range
        date_range = []
        current_date = start_date
        while current_date <= end_date:
            date_range.append(current_date.strftime('%Y-%m-%d'))
            current_date += timedelta(days=1)
        
        # Build data with all dates, default count to 0
        data = {date: 0 for date in date_range}
        
        # Update counts from query results
        for result in results:
            data[result.date.strftime('%Y-%m-%d')] = result.count
        
        # Convert to list format for API response
        formatted_data = [
            {
                'date': date,
                'count': count
            } for date, count in data.items()
        ]
        
        # Sort by date
        formatted_data.sort(key=lambda x: x['date'])
        
        return jsonify({
            'success': True,
            'data': formatted_data,
            'total': sum(item['count'] for item in formatted_data)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting incident activity statistics: {str(e)}")
        return jsonify({'success': False, 'message': f'Error getting statistics: {str(e)}'}), 500

# ===== Data Visualization Endpoints =====

@bp.route('/reports/visualizations/incidents', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_REPORTS)
@read_endpoint()
def generate_incident_visualization():
    """Generate a visualization for incident data."""
    try:
        # Get filter parameters
        chart_type = request.args.get('type', 'bar')  # bar, pie, line
        date_start = request.args.get('date_start')
        date_end = request.args.get('date_end')
        dimension = request.args.get('dimension', 'type')  # type, status, priority
        
        # Parse dates
        if date_start:
            try:
                start_date = datetime.strptime(date_start, '%Y-%m-%d')
            except ValueError:
                return jsonify({'success': False, 'message': 'Invalid date_start format. Use YYYY-MM-DD'}), 400
        else:
            # Default to last 30 days
            start_date = datetime.utcnow() - timedelta(days=30)
            
        if date_end:
            try:
                end_date = datetime.strptime(date_end, '%Y-%m-%d')
                end_date = end_date.replace(hour=23, minute=59, second=59)
            except ValueError:
                return jsonify({'success': False, 'message': 'Invalid date_end format. Use YYYY-MM-DD'}), 400
        else:
            end_date = datetime.utcnow()
            
        # Build query for incidents in date range
        incidents = Incident.query.filter(
            Incident.created_at >= start_date,
            Incident.created_at <= end_date
        ).all()
        
        if not incidents:
            return jsonify({'success': False, 'message': 'No data found for the specified criteria'}), 404
            
        # Prepare data based on dimension
        if dimension == 'type':
            # Group by incident type
            data = defaultdict(int)
            for incident in incidents:
                if incident.incident_type_id:
                    incident_type = IncidentType.query.get(incident.incident_type_id)
                    if incident_type:
                        data[incident_type.name] += 1
                    else:
                        data['Unknown'] += 1
                else:
                    data['Unknown'] += 1
                    
        elif dimension == 'status':
            # Group by status
            data = defaultdict(int)
            for incident in incidents:
                data[incident.status] += 1
                
        elif dimension == 'priority':
            # Group by priority
            data = defaultdict(int)
            for incident in incidents:
                data[incident.get_priority_string()] += 1
                
        else:
            return jsonify({'success': False, 'message': 'Invalid dimension parameter'}), 400
            
        # Convert to sorted list for visualization
        labels = []
        values = []
        
        # Sort by values in descending order
        for label, value in sorted(data.items(), key=lambda x: x[1], reverse=True):
            labels.append(label)
            values.append(value)
            
        # Create visualization
        plt.figure(figsize=(10, 6))
        
        if chart_type == 'bar':
            # Create bar chart
            plt.bar(labels, values)
            plt.xlabel(dimension.capitalize())
            plt.ylabel('Count')
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            
        elif chart_type == 'pie':
            # Create pie chart
            plt.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)
            plt.axis('equal')
            plt.tight_layout()
            
        elif chart_type == 'line':
            # For line chart, we need time series data
            # Group by day
            date_groups = defaultdict(int)
            for incident in incidents:
                if incident.created_at:
                    date_key = incident.created_at.strftime('%Y-%m-%d')
                    date_groups[date_key] += 1
                    
            # Sort by date
            dates = []
            counts = []
            for date_str, count in sorted(date_groups.items()):
                dates.append(date_str)
                counts.append(count)
                
            plt.plot(dates, counts, marker='o')
            plt.xlabel('Date')
            plt.ylabel('Count')
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            
        else:
            return jsonify({'success': False, 'message': 'Invalid chart type parameter'}), 400
            
        # Save the plot to a bytes buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
        
        # Return the image
        return send_file(
            buf,
            mimetype='image/png',
            as_attachment=False,
            download_name='incident_visualization.png'
        )
        
    except Exception as e:
        current_app.logger.error(f"Error generating visualization: {str(e)}")
        return jsonify({'success': False, 'message': f'Error generating visualization: {str(e)}'}), 500

@bp.route('/reports/visualizations/unit-activity', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_REPORTS)
@read_endpoint()
def generate_unit_activity_visualization():
    """Generate a visualization for unit activity data."""
    try:
        # Get filter parameters
        chart_type = request.args.get('type', 'bar')  # bar, pie, line
        date_start = request.args.get('date_start')
        date_end = request.args.get('date_end')
        unit_id = request.args.get('unit_id')
        
        # Parse dates
        if date_start:
            try:
                start_date = datetime.strptime(date_start, '%Y-%m-%d')
            except ValueError:
                return jsonify({'success': False, 'message': 'Invalid date_start format. Use YYYY-MM-DD'}), 400
        else:
            # Default to last 30 days
            start_date = datetime.utcnow() - timedelta(days=30)
            
        if date_end:
            try:
                end_date = datetime.strptime(date_end, '%Y-%m-%d')
                end_date = end_date.replace(hour=23, minute=59, second=59)
            except ValueError:
                return jsonify({'success': False, 'message': 'Invalid date_end format. Use YYYY-MM-DD'}), 400
        else:
            end_date = datetime.utcnow()
            
        # Build query for unit assignments in date range
        query = UnitAssignment.query.filter(
            UnitAssignment.dispatched_at >= start_date,
            UnitAssignment.dispatched_at <= end_date
        )
        
        # Filter by unit if provided
        if unit_id:
            query = query.filter(UnitAssignment.unit_id == unit_id)
            
        assignments = query.all()
        
        if not assignments:
            return jsonify({'success': False, 'message': 'No data found for the specified criteria'}), 404
            
        if chart_type == 'bar':
            # Group by unit
            data = defaultdict(int)
            for assignment in assignments:
                if assignment.unit:
                    data[assignment.unit.name] += 1
                else:
                    data['Unknown'] += 1
                    
            # Convert to sorted list for visualization
            labels = []
            values = []
            
            # Sort by values in descending order
            for label, value in sorted(data.items(), key=lambda x: x[1], reverse=True):
                labels.append(label)
                values.append(value)
                
            # Create bar chart
            plt.figure(figsize=(10, 6))
            plt.bar(labels, values)
            plt.xlabel('Unit')
            plt.ylabel('Number of Assignments')
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            
        elif chart_type == 'pie':
            # Group by unit type
            data = defaultdict(int)
            for assignment in assignments:
                if assignment.unit and assignment.unit.type:
                    data[assignment.unit.type.name] += 1
                else:
                    data['Unknown'] += 1
                    
            # Convert to sorted list for visualization
            labels = []
            values = []
            
            # Sort by values in descending order
            for label, value in sorted(data.items(), key=lambda x: x[1], reverse=True):
                labels.append(label)
                values.append(value)
                
            # Create pie chart
            plt.figure(figsize=(10, 6))
            plt.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)
            plt.axis('equal')
            plt.tight_layout()
            
        elif chart_type == 'line':
            # Group by day
            date_groups = defaultdict(int)
            for assignment in assignments:
                if assignment.dispatched_at:
                    date_key = assignment.dispatched_at.strftime('%Y-%m-%d')
                    date_groups[date_key] += 1
                    
            # Sort by date
            dates = []
            counts = []
            for date_str, count in sorted(date_groups.items()):
                dates.append(date_str)
                counts.append(count)
                
            # Create line chart
            plt.figure(figsize=(10, 6))
            plt.plot(dates, counts, marker='o')
            plt.xlabel('Date')
            plt.ylabel('Number of Assignments')
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            
        else:
            return jsonify({'success': False, 'message': 'Invalid chart type parameter'}), 400
            
        # Save the plot to a bytes buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
        
        # Return the image
        return send_file(
            buf,
            mimetype='image/png',
            as_attachment=False,
            download_name='unit_activity_visualization.png'
        )
        
    except Exception as e:
        current_app.logger.error(f"Error generating unit activity visualization: {str(e)}")
        return jsonify({'success': False, 'message': f'Error generating visualization: {str(e)}'}), 500

# ===== Daily Log Report Endpoints =====

@bp.route('/reports/daily-logs/pdf', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_REPORTS)
@read_endpoint()
def generate_daily_log_pdf():
    """Generate a PDF report for daily logs with filtering options."""
    try:
        # Get filter parameters
        date_str = request.args.get('date')
        shift = request.args.get('shift')
        
        # Validate date
        if date_str:
            try:
                report_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'success': False, 'message': 'Invalid date format. Use YYYY-MM-DD'}), 400
        else:
            # Default to current date
            report_date = datetime.utcnow().date()
            
        # Build query
        query = DailyLog.query.filter(DailyLog.date == report_date)
        
        # Apply shift filter if provided
        if shift:
            query = query.filter(DailyLog.shift == shift)
            
        # Execute query
        logs = query.order_by(DailyLog.shift).all()
        
        if not logs:
            return jsonify({'success': False, 'message': 'No daily logs found for the specified criteria'}), 404
            
        # Convert logs to dictionaries
        log_data = []
        for log in logs:
            log_dict = log.to_dict()
            # Add user name
            if log.user:
                log_dict['user_name'] = log.user.full_name()
            else:
                log_dict['user_name'] = 'Unknown'
            log_data.append(log_dict)
            
        # Get incidents for the same date
        incidents = Incident.query.filter(
            func.date(Incident.created_at) == report_date
        ).all()
        
        incident_data = [incident.to_dict() for incident in incidents]
        
        # Render HTML template with log data
        html_content = render_template(
            'reports/daily_log_report.html',
            logs=log_data,
            incidents=incident_data,
            date=report_date.strftime('%Y-%m-%d'),
            shift=shift if shift else 'All Shifts',
            generated_at=datetime.utcnow(),
            generated_by=current_user.full_name()
        )
        
        # Generate PDF from HTML
        pdf_content = generate_pdf(html_content)
        
        # Check if PDF generation was successful
        if pdf_content is None:
            # If ReportLab fails, return a JSON error response
            return jsonify({
                'success': False,
                'message': 'PDF generation failed. Please check the logs for errors.'
            }), 500
        
        # Create a BytesIO object
        pdf_io = io.BytesIO(pdf_content)
        pdf_io.seek(0)
        
        # Return the PDF file
        return send_file(
            pdf_io,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"DailyLog_{report_date.strftime('%Y%m%d')}_{shift if shift else 'AllShifts'}.pdf"
        )
        
    except Exception as e:
        current_app.logger.error(f"Error generating daily log PDF: {str(e)}")
        return jsonify({'success': False, 'message': f'Error generating PDF: {str(e)}'}), 500

@bp.route('/reports/daily-logs/csv', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_REPORTS)
@read_endpoint()
def export_daily_logs_csv():
    """Export daily logs to CSV file with filtering options."""
    try:
        # Get filter parameters
        date_start = request.args.get('date_start')
        date_end = request.args.get('date_end')
        shift = request.args.get('shift')
        user_id = request.args.get('user_id')
        
        # Build the query
        query = DailyLog.query
        
        # Apply filters if provided
        if date_start:
            try:
                start_date = datetime.strptime(date_start, '%Y-%m-%d').date()
                query = query.filter(DailyLog.date >= start_date)
            except ValueError:
                return jsonify({'success': False, 'message': 'Invalid date_start format. Use YYYY-MM-DD'}), 400
                
        if date_end:
            try:
                end_date = datetime.strptime(date_end, '%Y-%m-%d').date()
                query = query.filter(DailyLog.date <= end_date)
            except ValueError:
                return jsonify({'success': False, 'message': 'Invalid date_end format. Use YYYY-MM-DD'}), 400
                
        if shift:
            query = query.filter(DailyLog.shift == shift)
            
        if user_id:
            try:
                user_id = int(user_id)
                query = query.filter(DailyLog.user_id == user_id)
            except ValueError:
                return jsonify({'success': False, 'message': 'Invalid user_id. Must be an integer'}), 400
        
        # Execute query
        logs = query.order_by(DailyLog.date.desc(), DailyLog.shift).all()
        
        # Create a CSV in memory
        csv_output = io.StringIO()
        fieldnames = ['Date', 'Shift', 'User', 'Notes', 'Created At', 'Updated At']
        
        writer = csv.DictWriter(csv_output, fieldnames=fieldnames)
        writer.writeheader()
        
        # Add log data
        for log in logs:
            user = User.query.get(log.user_id).full_name() if log.user_id else 'Unknown'
            
            writer.writerow({
                'Date': log.date.strftime('%Y-%m-%d') if log.date else '',
                'Shift': log.shift,
                'User': user,
                'Notes': log.notes or '',
                'Created At': log.created_at.strftime('%Y-%m-%d %H:%M:%S') if log.created_at else '',
                'Updated At': log.updated_at.strftime('%Y-%m-%d %H:%M:%S') if log.updated_at else ''
            })
        
        # Prepare response
        csv_output.seek(0)
        
        # Create a BytesIO object
        mem = io.BytesIO()
        mem.write(csv_output.getvalue().encode('utf-8'))
        mem.seek(0)
        
        # Generate filename with date range
        if date_start and date_end:
            filename = f"DailyLogs_{date_start}_to_{date_end}.csv"
        else:
            filename = f"DailyLogs_Export_{datetime.now().strftime('%Y%m%d')}.csv"
        
        return send_file(
            mem,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        current_app.logger.error(f"Error exporting daily logs to CSV: {str(e)}")
        return jsonify({'success': False, 'message': f'Error exporting to CSV: {str(e)}'}), 500

# ===== Scheduled Report Generation =====

def generate_and_save_daily_report():
    """Generate daily report for the previous day and save it to the file system."""
    try:
        current_app.logger.info("Generating scheduled daily report")
        
        # Get yesterday's date
        yesterday = datetime.utcnow().date() - timedelta(days=1)
        
        # Get logs for yesterday
        logs = DailyLog.query.filter(DailyLog.date == yesterday).all()
        
        # Get incidents created yesterday
        incidents = Incident.query.filter(
            func.date(Incident.created_at) == yesterday
        ).all()
        
        # Skip if no data
        if not logs and not incidents:
            current_app.logger.info(f"No data for {yesterday}, skipping scheduled report")
            return
        
        # Prepare log data
        log_data = []
        for log in logs:
            log_dict = log.to_dict()
            # Add user name
            if log.user:
                log_dict['user_name'] = log.user.full_name()
            else:
                log_dict['user_name'] = 'Unknown'
            log_data.append(log_dict)
            
        # Prepare incident data
        incident_data = [incident.to_dict() for incident in incidents]
        
        # Render HTML template
        html_content = render_template(
            'reports/daily_log_report.html',
            logs=log_data,
            incidents=incident_data,
            date=yesterday.strftime('%Y-%m-%d'),
            shift='All Shifts',
            generated_at=datetime.utcnow(),
            generated_by='System'
        )
        
        # Generate PDF from HTML
        pdf_content = generate_pdf(html_content)
        
        # Check if PDF generation was successful
        if pdf_content is None:
            # If ReportLab fails, return a JSON error response
            return jsonify({
                'success': False,
                'message': 'PDF generation failed. Please check the logs for errors.'
            }), 500
        
        # Ensure reports directory exists
        reports_dir = os.path.join(current_app.root_path, 'static', 'reports')
        ensure_directory_exists(reports_dir)
        
        # Save the PDF file
        filename = f"DailyReport_{yesterday.strftime('%Y%m%d')}.pdf"
        file_path = os.path.join(reports_dir, filename)
        
        with open(file_path, 'wb') as f:
            f.write(pdf_content)
            
        current_app.logger.info(f"Scheduled daily report saved to {file_path}")
        
        # Also generate and save CSV exports
        
        # Incident CSV
        if incidents:
            incident_csv = io.StringIO()
            fieldnames = [
                'Incident Number', 'Type', 'Priority', 'Status', 'Location', 
                'Caller', 'Callback Number', 'Description', 'Resolution',
                'AMPDS Code', 'Created At', 'Created By', 'Updated At'
            ]
            
            writer = csv.DictWriter(incident_csv, fieldnames=fieldnames)
            writer.writeheader()
            
            for incident in incidents:
                incident_type = IncidentType.query.get(incident.incident_type_id).name if incident.incident_type_id else 'Unknown'
                created_by = User.query.get(incident.created_by_id).full_name() if incident.created_by_id else 'System'
                
                writer.writerow({
                    'Incident Number': incident.incident_number,
                    'Type': incident_type,
                    'Priority': incident.get_priority_string(),
                    'Status': incident.status,
                    'Location': incident.location or '',
                    'Caller': incident.caller or '',
                    'Callback Number': incident.callback_number or '',
                    'Description': incident.description or '',
                    'Resolution': incident.resolution or '',
                    'AMPDS Code': incident.ampds_code or '',
                    'Created At': incident.created_at.strftime('%Y-%m-%d %H:%M:%S') if incident.created_at else '',
                    'Created By': created_by,
                    'Updated At': incident.updated_at.strftime('%Y-%m-%d %H:%M:%S') if incident.updated_at else ''
                })
                
            incident_csv_filename = f"Incidents_{yesterday.strftime('%Y%m%d')}.csv"
            incident_csv_path = os.path.join(reports_dir, incident_csv_filename)
            
            with open(incident_csv_path, 'w', newline='') as f:
                f.write(incident_csv.getvalue())
                
            current_app.logger.info(f"Scheduled incident CSV saved to {incident_csv_path}")
        
        # Generate statistical visualizations
        if incidents:
            # Incidents by type
            try:
                plt.figure(figsize=(10, 6))
                
                # Group by incident type
                data = defaultdict(int)
                for incident in incidents:
                    if incident.incident_type_id:
                        incident_type = IncidentType.query.get(incident.incident_type_id)
                        if incident_type:
                            data[incident_type.name] += 1
                        else:
                            data['Unknown'] += 1
                    else:
                        data['Unknown'] += 1
                
                # Convert to sorted list for visualization
                labels = []
                values = []
                
                # Sort by values in descending order
                for label, value in sorted(data.items(), key=lambda x: x[1], reverse=True):
                    labels.append(label)
                    values.append(value)
                
                plt.bar(labels, values)
                plt.xlabel('Incident Type')
                plt.ylabel('Count')
                plt.xticks(rotation=45, ha='right')
                plt.title(f'Incidents by Type - {yesterday.strftime("%Y-%m-%d")}')
                plt.tight_layout()
                
                # Save the visualization
                viz_filename = f"IncidentsByType_{yesterday.strftime('%Y%m%d')}.png"
                viz_path = os.path.join(reports_dir, viz_filename)
                plt.savefig(viz_path)
                plt.close()
                
                current_app.logger.info(f"Incident type visualization saved to {viz_path}")
            except Exception as e:
                current_app.logger.error(f"Error generating incident type visualization: {str(e)}")
        
        return True
        
    except Exception as e:
        current_app.logger.error(f"Error in scheduled daily report generation: {str(e)}")
        return False

# Register the scheduled task
def register_scheduled_tasks():
    """Register scheduled report generation tasks."""
    try:
        # Schedule daily report generation at 1:00 AM UTC
        scheduler.add_job(
            generate_and_save_daily_report,
            'cron',
            hour=1,
            minute=0,
            id='daily_report_generation',
            replace_existing=True
        )
        current_app.logger.info("Scheduled daily report generation task registered")
    except Exception as e:
        current_app.logger.error(f"Error registering scheduled tasks: {str(e)}")

# Route to manually trigger report generation (for testing)
@bp.route('/reports/generate/daily', methods=['POST'])
@login_required
@permission_required(Permission.MANAGE_REPORTS)
@secure_endpoint()
def trigger_daily_report_generation():
    """Manually trigger daily report generation."""
    try:
        # Get specific date or default to yesterday
        date_str = request.json.get('date') if request.is_json else None
        
        if date_str:
            try:
                report_date = datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                return jsonify({'success': False, 'message': 'Invalid date format. Use YYYY-MM-DD'}), 400
        else:
            report_date = datetime.utcnow().date() - timedelta(days=1)
            
        # Override yesterday's date in the generation function
        yesterday = report_date
        
        # Get logs for the specified date
        logs = DailyLog.query.filter(DailyLog.date == yesterday).all()
        
        # Get incidents created on the specified date
        incidents = Incident.query.filter(
            func.date(Incident.created_at) == yesterday
        ).all()
        
        # Skip if no data
        if not logs and not incidents:
            return jsonify({
                'success': False, 
                'message': f'No data found for {yesterday.strftime("%Y-%m-%d")}'
            }), 404
        
        # Prepare log data
        log_data = []
        for log in logs:
            log_dict = log.to_dict()
            # Add user name
            if log.user:
                log_dict['user_name'] = log.user.full_name()
            else:
                log_dict['user_name'] = 'Unknown'
            log_data.append(log_dict)
            
        # Prepare incident data
        incident_data = [incident.to_dict() for incident in incidents]
        
        # Render HTML template
        html_content = render_template(
            'reports/daily_log_report.html',
            logs=log_data,
            incidents=incident_data,
            date=yesterday.strftime('%Y-%m-%d'),
            shift='All Shifts',
            generated_at=datetime.utcnow(),
            generated_by=current_user.full_name()
        )
        
        # Generate PDF from HTML
        pdf_content = generate_pdf(html_content)
        
        # Check if PDF generation was successful
        if pdf_content is None:
            # If ReportLab fails, return a JSON error response
            return jsonify({
                'success': False,
                'message': 'PDF generation failed. Please check the logs for errors.'
            }), 500
        
        # Ensure reports directory exists
        reports_dir = os.path.join(current_app.root_path, 'static', 'reports')
        ensure_directory_exists(reports_dir)
        
        # Save the PDF file
        filename = f"DailyReport_{yesterday.strftime('%Y%m%d')}.pdf"
        file_path = os.path.join(reports_dir, filename)
        
        with open(file_path, 'wb') as f:
            f.write(pdf_content)
            
        return jsonify({
            'success': True,
            'message': f'Daily report generated for {yesterday.strftime("%Y-%m-%d")}',
            'file_path': file_path
        })
        
    except Exception as e:
        current_app.logger.error(f"Error triggering daily report generation: {str(e)}")
        return jsonify({'success': False, 'message': f'Error generating report: {str(e)}'}), 500

@bp.route('/daily-log-alt', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_REPORTS)
@read_endpoint()
def generate_daily_log_pdf_alt():
    """Generate a daily log report in PDF format."""
    try:
        # Get date parameter (default to yesterday)
        report_date_str = request.args.get('date')
        if not report_date_str:
            yesterday = datetime.utcnow() - timedelta(days=1)
            report_date_str = yesterday.strftime('%Y-%m-%d')
            
        # Parse the date
        try:
            report_date = datetime.strptime(report_date_str, '%Y-%m-%d')
            
            # Set start and end time for the day
            start_time = report_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = report_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid date format. Use YYYY-MM-DD'}), 400
        
        # Get incidents for the day
        incidents = Incident.query.filter(
            Incident.created_at.between(start_time, end_time)
        ).order_by(Incident.created_at).all()
        
        # Prepare incident data for the template
        incident_data = []
        for incident in incidents:
            incident_type = IncidentType.query.get(incident.incident_type_id)
            incident_type_name = incident_type.name if incident_type else 'Unknown'
            
            incident_data.append({
                'id': incident.id,
                'incident_number': incident.incident_number,
                'incident_type': incident_type_name,
                'priority': incident.get_priority_string(),
                'status': incident.status,
                'location': incident.location,
                'created_at': incident.created_at
            })
        
        # Get incident summary (by type)
        incident_summary = []
        incident_types = {}
        for incident in incidents:
            incident_type = IncidentType.query.get(incident.incident_type_id)
            type_name = incident_type.name if incident_type else 'Unknown'
            type_id = incident_type.id if incident_type else 0
            
            if type_id in incident_types:
                incident_types[type_id]['count'] += 1
            else:
                incident_types[type_id] = {
                    'type_id': type_id,
                    'type_name': type_name,
                    'count': 1
                }
        
        for type_id, data in incident_types.items():
            incident_summary.append(data)
        
        # Calculate percentages for incident summary
        total_incidents = len(incidents)
        for item in incident_summary:
            if total_incidents > 0:
                item['percentage'] = round((item['count'] / total_incidents * 100), 1)
            else:
                item['percentage'] = 0
        
        # Get unit activity
        unit_assignments = UnitAssignment.query.filter(
            UnitAssignment.created_at.between(start_time, end_time)
        ).all()
        
        unit_status_changes = UnitStatusLog.query.filter(
            UnitStatusLog.created_at.between(start_time, end_time)
        ).all()
        
        # Organize unit activity by unit
        units_data = {}
        
        # Count incident assignments by unit
        for assignment in unit_assignments:
            unit = Unit.query.get(assignment.unit_id)
            if not unit:
                continue
                
            if unit.id in units_data:
                units_data[unit.id]['incidents_assigned'] += 1
            else:
                unit_type = UnitType.query.get(unit.unit_type_id)
                unit_type_name = unit_type.name if unit_type else 'Unknown'
                
                units_data[unit.id] = {
                    'unit_id': unit.id,
                    'unit_number': unit.unit_number,
                    'unit_type': unit_type_name,
                    'incidents_assigned': 1,
                    'status_changes': 0
                }
        
        # Count status changes by unit
        for status_change in unit_status_changes:
            if status_change.unit_id in units_data:
                units_data[status_change.unit_id]['status_changes'] += 1
            else:
                unit = Unit.query.get(status_change.unit_id)
                if not unit:
                    continue
                    
                unit_type = UnitType.query.get(unit.unit_type_id)
                unit_type_name = unit_type.name if unit_type else 'Unknown'
                
                units_data[status_change.unit_id] = {
                    'unit_id': unit.id,
                    'unit_number': unit.unit_number,
                    'unit_type': unit_type_name,
                    'incidents_assigned': 0,
                    'status_changes': 1
                }
        
        # Convert to list for the template
        unit_activity = list(units_data.values())
        
        # Get system logs
        system_logs = AuditLog.query.filter(
            AuditLog.timestamp.between(start_time, end_time)
        ).order_by(AuditLog.timestamp).all()
        
        # Prepare system logs for the template
        system_logs_data = []
        for log in system_logs:
            user = User.query.get(log.user_id)
            user_name = user.full_name() if user else 'System'
            
            system_logs_data.append({
                'id': log.id,
                'timestamp': log.timestamp,
                'user': user_name,
                'action': log.action,
                'details': log.details
            })
        
        # Format the date for display
        formatted_date = report_date.strftime('%A, %B %d, %Y')
        
        # Render the HTML template
        html_content = render_template(
            'pdf/daily_log.html',
            report_date=formatted_date,
            incidents=incident_data,
            incident_summary=incident_summary,
            unit_activity=unit_activity,
            system_logs=system_logs_data,
            generated_at=datetime.utcnow(),
            generated_by=current_user.full_name()
        )
        
        # Generate PDF from HTML
        pdf_content = generate_pdf(html_content)
        
        # Check if PDF generation was successful
        if pdf_content is None:
            # If ReportLab fails, return a JSON error response
            return jsonify({
                'success': False,
                'message': 'PDF generation failed. Please check the logs for errors.'
            }), 500
        
        # Create a BytesIO object
        pdf_io = io.BytesIO(pdf_content)
        pdf_io.seek(0)
        
        # Return the PDF file
        return send_file(
            pdf_io,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"Daily_Log_{report_date_str}.pdf"
        )
        
    except Exception as e:
        current_app.logger.error(f"Error generating daily log PDF: {str(e)}")
        return jsonify({'success': False, 'message': f'Error generating PDF: {str(e)}'}), 500

@bp.route('/reports/daily/csv', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_REPORTS)
@read_endpoint()
def generate_daily_log_csv():
    """Generate a daily log report in CSV format."""
    try:
        # Get date parameter (default to yesterday)
        report_date_str = request.args.get('date')
        if not report_date_str:
            yesterday = datetime.utcnow() - timedelta(days=1)
            report_date_str = yesterday.strftime('%Y-%m-%d')
            
        # Parse the date
        try:
            report_date = datetime.strptime(report_date_str, '%Y-%m-%d')
            
            # Set start and end time for the day
            start_time = report_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = report_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid date format. Use YYYY-MM-DD'}), 400
        
        # Get incidents for the day
        incidents = Incident.query.filter(
            Incident.created_at.between(start_time, end_time)
        ).order_by(Incident.created_at).all()
        
        # Create a CSV in memory
        csv_output = io.StringIO()
        
        # Write incidents section
        fieldnames = [
            'Incident Number', 'Type', 'Priority', 'Status', 'Location', 
            'Time Created', 'Created By', 'Resolution'
        ]
        
        writer = csv.DictWriter(csv_output, fieldnames=fieldnames)
        writer.writeheader()
        
        # Write a separator row
        writer.writerow({fieldname: 'INCIDENTS' for fieldname in fieldnames})
        
        # Add incident data
        for incident in incidents:
            incident_type = IncidentType.query.get(incident.incident_type_id)
            incident_type_name = incident_type.name if incident_type else 'Unknown'
            
            created_by = User.query.get(incident.created_by_id)
            created_by_name = created_by.full_name() if created_by else 'System'
            
            writer.writerow({
                'Incident Number': incident.incident_number,
                'Type': incident_type_name,
                'Priority': incident.get_priority_string(),
                'Status': incident.status,
                'Location': incident.location or '',
                'Time Created': incident.created_at.strftime('%H:%M:%S') if incident.created_at else '',
                'Created By': created_by_name,
                'Resolution': incident.resolution or ''
            })
        
        # Add a blank row as separator
        writer.writerow({fieldname: '' for fieldname in fieldnames})
        
        # Unit activity section
        unit_fieldnames = [
            'Unit Number', 'Unit Type', 'Status Changes', 'Incidents Assigned'
        ]
        
        unit_writer = csv.DictWriter(csv_output, fieldnames=unit_fieldnames)
        unit_writer.writeheader()
        
        # Write a separator row
        unit_writer.writerow({fieldname: 'UNIT ACTIVITY' for fieldname in unit_fieldnames})
        
        # Get unit assignments and status changes
        unit_assignments = UnitAssignment.query.filter(
            UnitAssignment.created_at.between(start_time, end_time)
        ).all()
        
        unit_status_changes = UnitStatusLog.query.filter(
            UnitStatusLog.created_at.between(start_time, end_time)
        ).all()
        
        # Organize unit activity by unit
        units_data = {}
        
        # Count incident assignments by unit
        for assignment in unit_assignments:
            unit = Unit.query.get(assignment.unit_id)
            if not unit:
                continue
                
            if unit.id in units_data:
                units_data[unit.id]['incidents_assigned'] += 1
            else:
                unit_type = UnitType.query.get(unit.unit_type_id)
                unit_type_name = unit_type.name if unit_type else 'Unknown'
                
                units_data[unit.id] = {
                    'unit_id': unit.id,
                    'unit_number': unit.unit_number,
                    'unit_type': unit_type_name,
                    'incidents_assigned': 1,
                    'status_changes': 0
                }
        
        # Count status changes by unit
        for status_change in unit_status_changes:
            if status_change.unit_id in units_data:
                units_data[status_change.unit_id]['status_changes'] += 1
            else:
                unit = Unit.query.get(status_change.unit_id)
                if not unit:
                    continue
                    
                unit_type = UnitType.query.get(unit.unit_type_id)
                unit_type_name = unit_type.name if unit_type else 'Unknown'
                
                units_data[status_change.unit_id] = {
                    'unit_id': unit.id,
                    'unit_number': unit.unit_number,
                    'unit_type': unit_type_name,
                    'incidents_assigned': 0,
                    'status_changes': 1
                }
        
        # Write unit activity data
        for unit_id, data in units_data.items():
            unit_writer.writerow({
                'Unit Number': data['unit_number'],
                'Unit Type': data['unit_type'],
                'Status Changes': data['status_changes'],
                'Incidents Assigned': data['incidents_assigned']
            })
            
        # Prepare response
        csv_output.seek(0)
        
        # Create a BytesIO object
        mem = io.BytesIO()
        mem.write(csv_output.getvalue().encode('utf-8'))
        mem.seek(0)
        
        return send_file(
            mem,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f"Daily_Log_{report_date_str}.csv"
        )
        
    except Exception as e:
        current_app.logger.error(f"Error generating daily log CSV: {str(e)}")
        return jsonify({'success': False, 'message': f'Error generating CSV: {str(e)}'}), 500

# Add visualizations page route
@bp.route('/visualizations')
@login_required
@permission_required(Permission.VIEW_REPORTS)
def visualizations():
    """Render the data visualizations page"""
    return current_app.custom_render_template('reporting/visualizations.html', title='Data Visualizations')

# Add reports landing page
@bp.route('/reports')
@login_required
@permission_required(Permission.VIEW_REPORTS)
def reports():
    """Render the main reports landing page"""
    return current_app.custom_render_template('reporting/reports.html', title='Reports')

@bp.route('/analytics/incidents-by-type-viz', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_REPORTS)
@read_endpoint()
def incidents_by_type_viz():
    """Get incident counts by type - used for visualization"""
    try:
        # Parse query parameters
        date_start = request.args.get('date_start')
        date_end = request.args.get('date_end')
        status = request.args.get('status')
        
        # Build query
        query = db.session.query(
            IncidentType.id.label('type_id'),
            IncidentType.name.label('type_name'),
            db.func.count(Incident.id).label('count')
        ).join(
            Incident, Incident.incident_type_id == IncidentType.id
        ).group_by(
            IncidentType.id, IncidentType.name
        )
        
        # Apply filters
        if date_start:
            try:
                start_date = datetime.strptime(date_start, '%Y-%m-%d')
                query = query.filter(Incident.created_at >= start_date)
            except ValueError:
                pass
                
        if date_end:
            try:
                end_date = datetime.strptime(date_end, '%Y-%m-%d')
                # Add one day to include the entire end date
                end_date = end_date + timedelta(days=1)
                query = query.filter(Incident.created_at < end_date)
            except ValueError:
                pass
                
        if status:
            query = query.filter(Incident.status == status)
        
        # Execute query
        results = query.all()
        
        # Convert to JSON-serializable format
        data = [
            {
                'type_id': row.type_id,
                'type_name': row.type_name,
                'count': row.count
            }
            for row in results
        ]
        
        return jsonify({
            'success': True,
            'data': data
        })
        
    except Exception as e:
        current_app.logger.error(f"Error retrieving incident type statistics: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'An error occurred while retrieving incident statistics'
        }), 500

@bp.route('/analytics/incidents-by-priority-viz', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_REPORTS)
@read_endpoint()
def incidents_by_priority_viz():
    """Get incident counts by priority - used for visualization"""
    try:
        # Parse query parameters
        date_start = request.args.get('date_start')
        date_end = request.args.get('date_end')
        incident_type = request.args.get('incident_type')
        status = request.args.get('status')
        
        # Build query
        query = db.session.query(
            Incident.priority.label('priority_value'),
            db.case(
                [(Incident.priority == 1, 'Emergency'),
                 (Incident.priority == 2, 'Urgent'),
                 (Incident.priority == 3, 'Non-urgent')],
                else_='Unknown'
            ).label('priority_label'),
            db.func.count(Incident.id).label('count')
        ).group_by(
            Incident.priority
        ).order_by(
            Incident.priority
        )
        
        # Apply filters
        if date_start:
            try:
                start_date = datetime.strptime(date_start, '%Y-%m-%d')
                query = query.filter(Incident.created_at >= start_date)
            except ValueError:
                pass
                
        if date_end:
            try:
                end_date = datetime.strptime(date_end, '%Y-%m-%d')
                # Add one day to include the entire end date
                end_date = end_date + timedelta(days=1)
                query = query.filter(Incident.created_at < end_date)
            except ValueError:
                pass
                
        if incident_type:
            query = query.filter(Incident.incident_type_id == incident_type)
                
        if status:
            query = query.filter(Incident.status == status)
        
        # Execute query
        results = query.all()
        
        # Convert to JSON-serializable format
        data = [
            {
                'priority_value': row.priority_value,
                'priority_label': row.priority_label,
                'count': row.count
            }
            for row in results
        ]
        
        return jsonify({
            'success': True,
            'data': data
        })
        
    except Exception as e:
        current_app.logger.error(f"Error retrieving incident priority statistics: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'An error occurred while retrieving incident statistics'
        }), 500

@bp.route('/analytics/incidents-by-status-viz', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_REPORTS)
@read_endpoint()
def incidents_by_status_viz():
    """Get incident counts by status - used for visualization"""
    try:
        # Parse query parameters
        date_start = request.args.get('date_start')
        date_end = request.args.get('date_end')
        incident_type = request.args.get('incident_type')
        
        # Build query
        query = db.session.query(
            Incident.status,
            db.func.count(Incident.id).label('count')
        ).group_by(
            Incident.status
        )
        
        # Apply filters
        if date_start:
            try:
                start_date = datetime.strptime(date_start, '%Y-%m-%d')
                query = query.filter(Incident.created_at >= start_date)
            except ValueError:
                pass
                
        if date_end:
            try:
                end_date = datetime.strptime(date_end, '%Y-%m-%d')
                # Add one day to include the entire end date
                end_date = end_date + timedelta(days=1)
                query = query.filter(Incident.created_at < end_date)
            except ValueError:
                pass
                
        if incident_type:
            query = query.filter(Incident.incident_type_id == incident_type)
        
        # Execute query
        results = query.all()
        
        # Convert to JSON-serializable format
        data = [
            {
                'status': row.status,
                'count': row.count
            }
            for row in results
        ]
        
        return jsonify({
            'success': True,
            'data': data
        })
        
    except Exception as e:
        current_app.logger.error(f"Error retrieving incident status statistics: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'An error occurred while retrieving incident statistics'
        }), 500

@bp.route('/api/statistics/incidents/activity', methods=['GET'])
@login_required
@permission_required(Permission.VIEW_REPORTS)
@read_endpoint()
def incidents_activity():
    """Get incident counts by date for the last 30 days - used for visualization"""
    try:
        # Parse query parameters
        date_start = request.args.get('date_start')
        date_end = request.args.get('date_end')
        incident_type = request.args.get('incident_type')
        status = request.args.get('status')
        
        # Default to last 30 days if not specified
        if not date_start:
            start_date = datetime.now() - timedelta(days=30)
        else:
            try:
                start_date = datetime.strptime(date_start, '%Y-%m-%d')
            except ValueError:
                start_date = datetime.now() - timedelta(days=30)
                
        if not date_end:
            end_date = datetime.now()
        else:
            try:
                end_date = datetime.strptime(date_end, '%Y-%m-%d')
                # Add one day to include the entire end date
                end_date = end_date + timedelta(days=1)
            except ValueError:
                end_date = datetime.now()
        
        # Generate list of dates to include
        date_list = []
        current_date = start_date
        while current_date < end_date:
            date_list.append(current_date.strftime('%Y-%m-%d'))
            current_date += timedelta(days=1)
        
        # Build query to get counts by date
        query = db.session.query(
            db.func.date(Incident.created_at).label('date'),
            db.func.count(Incident.id).label('count')
        ).filter(
            Incident.created_at >= start_date,
            Incident.created_at < end_date
        ).group_by(
            db.func.date(Incident.created_at)
        ).order_by(
            db.func.date(Incident.created_at)
        )
        
        # Apply additional filters
        if incident_type:
            query = query.filter(Incident.incident_type_id == incident_type)
                
        if status:
            query = query.filter(Incident.status == status)
        
        # Execute query
        results = query.all()
        
        # Create a mapping of date to count
        date_counts = {row.date.strftime('%Y-%m-%d'): row.count for row in results}
        
        # Fill in missing dates with zero counts
        data = [
            {
                'date': date,
                'count': date_counts.get(date, 0)
            }
            for date in date_list
        ]
        
        return jsonify({
            'success': True,
            'data': data
        })
        
    except Exception as e:
        current_app.logger.error(f"Error retrieving incident activity statistics: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'An error occurred while retrieving incident statistics'
        }), 500
