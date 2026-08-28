"""
Reporting Service Module

This module provides reporting capabilities for the CAD system, including:
- PDF report generation for incidents
- CSV data export
- Statistical reporting
- Daily log report generation
- Data visualization endpoints
"""

from models import Incident, Unit, User, IncidentLog, UnitAssignment, IncidentType, UnitType
from datetime import datetime, timedelta
from flask import current_app
import io
import csv
import json
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import base64
from sqlalchemy import func, and_, or_
from collections import defaultdict
import logging

class ReportingService:
    """Service class for generating various reports and data exports."""
    
    @staticmethod
    def generate_incident_pdf(incident_id):
        """
        Generate a PDF report for a specific incident.
        
        Args:
            incident_id: ID of the incident to generate report for
            
        Returns:
            BytesIO object containing the PDF data
        """
        incident = Incident.query.get(incident_id)
        if not incident:
            return None
            
        # Get related data
        logs = IncidentLog.query.filter_by(incident_id=incident_id).order_by(IncidentLog.timestamp).all()
        unit_assignments = UnitAssignment.query.filter_by(incident_id=incident_id).all()
        units = [Unit.query.get(ua.unit_id) for ua in unit_assignments]
        
        # Create PDF
        pdf_buffer = io.BytesIO()
        
        with PdfPages(pdf_buffer) as pdf:
            # Title page
            plt.figure(figsize=(8.5, 11))
            plt.axis('off')
            plt.text(0.5, 0.9, f"Incident Report", fontsize=24, ha='center')
            plt.text(0.5, 0.8, f"Incident #{incident.incident_number}", fontsize=18, ha='center')
            plt.text(0.5, 0.7, f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}", fontsize=12, ha='center')
            
            # Incident details
            details = [
                f"Type: {incident.incident_type}",
                f"Priority: {incident.priority}",
                f"Status: {incident.status}",
                f"Location: {incident.location}",
                f"Reported: {incident.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
                f"Description: {incident.description if hasattr(incident, 'description') else 'N/A'}"
            ]
            
            y_pos = 0.6
            for detail in details:
                plt.text(0.1, y_pos, detail, fontsize=12)
                y_pos -= 0.05
                
            pdf.savefig()
            plt.close()
            
            # Incident timeline
            plt.figure(figsize=(8.5, 11))
            plt.axis('off')
            plt.text(0.5, 0.95, f"Incident Timeline", fontsize=18, ha='center')
            
            y_pos = 0.9
            
            if logs:
                for log in logs:
                    plt.text(0.1, y_pos, f"{log.timestamp.strftime('%Y-%m-%d %H:%M:%S')}", fontsize=10)
                    plt.text(0.3, y_pos, f"{log.log_type}: {log.message}", fontsize=10)
                    y_pos -= 0.03
                    if y_pos < 0.1:  # Start a new page if needed
                        pdf.savefig()
                        plt.close()
                        plt.figure(figsize=(8.5, 11))
                        plt.axis('off')
                        plt.text(0.5, 0.95, f"Incident Timeline (Continued)", fontsize=18, ha='center')
                        y_pos = 0.9
            else:
                plt.text(0.1, y_pos, "No timeline entries available", fontsize=10)
                
            pdf.savefig()
            plt.close()
            
            # Unit assignments
            plt.figure(figsize=(8.5, 11))
            plt.axis('off')
            plt.text(0.5, 0.95, f"Unit Assignments", fontsize=18, ha='center')
            
            y_pos = 0.9
            
            if units:
                headers = ["Unit", "Assigned", "Arrived", "Cleared", "Status"]
                col_positions = [0.1, 0.25, 0.4, 0.55, 0.7]
                
                for i, header in enumerate(headers):
                    plt.text(col_positions[i], y_pos, header, fontsize=10, fontweight='bold')
                
                y_pos -= 0.04
                
                for i, unit in enumerate(units):
                    assignment = unit_assignments[i]
                    plt.text(col_positions[0], y_pos, unit.name, fontsize=10)
                    plt.text(col_positions[1], y_pos, assignment.assigned_at.strftime('%H:%M:%S') if assignment.assigned_at else "N/A", fontsize=10)
                    plt.text(col_positions[2], y_pos, assignment.arrived_at.strftime('%H:%M:%S') if assignment.arrived_at else "N/A", fontsize=10)
                    plt.text(col_positions[3], y_pos, assignment.cleared_at.strftime('%H:%M:%S') if assignment.cleared_at else "N/A", fontsize=10)
                    plt.text(col_positions[4], y_pos, assignment.status, fontsize=10)
                    y_pos -= 0.04
            else:
                plt.text(0.1, y_pos, "No units assigned to this incident", fontsize=10)
                
            pdf.savefig()
            plt.close()
            
            # Map page if coordinates are available
            if incident.latitude and incident.longitude:
                plt.figure(figsize=(8.5, 11))
                plt.axis('off')
                plt.text(0.5, 0.95, f"Incident Location", fontsize=18, ha='center')
                
                # In a real implementation, you would generate a map image here
                plt.text(0.5, 0.5, f"Map would be displayed here for coordinates: {incident.latitude}, {incident.longitude}", 
                       fontsize=10, ha='center', bbox=dict(facecolor='white', alpha=0.5))
                
                pdf.savefig()
                plt.close()
        
        # Reset buffer position to the beginning
        pdf_buffer.seek(0)
        return pdf_buffer
    
    @staticmethod
    def export_incidents_csv(start_date=None, end_date=None, status=None, incident_type=None):
        """
        Export incidents to CSV format.
        
        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter
            status: Optional status filter
            incident_type: Optional incident type filter
            
        Returns:
            CSV data as a string
        """
        query = Incident.query
        
        # Apply filters
        if start_date:
            query = query.filter(Incident.created_at >= start_date)
        if end_date:
            query = query.filter(Incident.created_at <= end_date)
        if status:
            query = query.filter(Incident.status == status)
        if incident_type:
            query = query.filter(Incident.incident_type == incident_type)
            
        incidents = query.order_by(Incident.created_at.desc()).all()
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header row
        writer.writerow([
            'Incident Number', 'Type', 'Priority', 'Status',
            'Location', 'Latitude', 'Longitude', 'Created At',
            'Updated At', 'Reported By'
        ])
        
        # Write data rows
        for incident in incidents:
            reporter = User.query.get(incident.reported_by_id) if incident.reported_by_id else None
            reporter_name = f"{reporter.first_name} {reporter.last_name}" if reporter else "Unknown"
            
            writer.writerow([
                incident.incident_number,
                incident.incident_type,
                incident.priority,
                incident.status,
                incident.location,
                incident.latitude,
                incident.longitude,
                incident.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                incident.updated_at.strftime('%Y-%m-%d %H:%M:%S') if incident.updated_at else '',
                reporter_name
            ])
            
        return output.getvalue()
    
    @staticmethod
    def export_units_csv(unit_type=None, status=None):
        """
        Export units to CSV format.
        
        Args:
            unit_type: Optional unit type filter
            status: Optional status filter
            
        Returns:
            CSV data as a string
        """
        query = Unit.query
        
        # Apply filters
        if unit_type:
            query = query.filter(Unit.unit_type == unit_type)
        if status:
            query = query.filter(Unit.status == status)
            
        units = query.all()
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header row
        writer.writerow([
            'Unit ID', 'Name', 'Type', 'Status', 'Location',
            'Assigned Incident', 'Last Status Change'
        ])
        
        # Write data rows
        for unit in units:
            incident = Incident.query.get(unit.assigned_incident_id) if unit.assigned_incident_id else None
            incident_number = incident.incident_number if incident else "None"
            
            writer.writerow([
                unit.id,
                unit.name,
                unit.unit_type,
                unit.status,
                unit.current_location if hasattr(unit, 'current_location') else "Unknown",
                incident_number,
                unit.status_timestamp.strftime('%Y-%m-%d %H:%M:%S') if unit.status_timestamp else ''
            ])
            
        return output.getvalue()

    @staticmethod
    def generate_incident_statistics(start_date=None, end_date=None, group_by='day'):
        """
        Generate statistics about incidents for reporting and data visualization.
        
        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter
            group_by: Time grouping - 'day', 'week', 'month'
            
        Returns:
            Dictionary with statistical data
        """
        if not start_date:
            start_date = datetime.now() - timedelta(days=30)  # Default to last 30 days
        if not end_date:
            end_date = datetime.now()
            
        incidents = Incident.query.filter(
            Incident.created_at >= start_date,
            Incident.created_at <= end_date
        ).all()
        
        # Count incidents by type
        incidents_by_type = defaultdict(int)
        for incident in incidents:
            incidents_by_type[incident.incident_type] += 1
            
        # Count incidents by priority
        incidents_by_priority = defaultdict(int)
        for incident in incidents:
            incidents_by_priority[incident.priority] += 1
            
        # Count incidents by status
        incidents_by_status = defaultdict(int)
        for incident in incidents:
            incidents_by_status[incident.status] += 1
            
        # Time series data
        time_series = []
        
        # Set up the date range based on group_by
        if group_by == 'day':
            delta = timedelta(days=1)
            format_str = '%Y-%m-%d'
        elif group_by == 'week':
            delta = timedelta(weeks=1)
            format_str = '%Y-W%U'
        elif group_by == 'month':
            # For simplicity, use 30 days for a month in this mock implementation
            delta = timedelta(days=30)
            format_str = '%Y-%m'
        else:
            delta = timedelta(days=1)
            format_str = '%Y-%m-%d'
            
        # Generate time series data
        current_date = start_date
        while current_date <= end_date:
            next_date = current_date + delta
            
            # Count incidents in this time period
            period_incidents = [i for i in incidents if current_date <= i.created_at < next_date]
            
            # Format the date according to the grouping
            if group_by == 'day':
                period_label = current_date.strftime(format_str)
            elif group_by == 'week':
                period_label = f"Week {current_date.strftime('%U')}, {current_date.year}"
            elif group_by == 'month':
                period_label = current_date.strftime(format_str)
                
            # Add data point
            time_series.append({
                'period': period_label,
                'count': len(period_incidents),
                'by_type': {t: sum(1 for i in period_incidents if i.incident_type == t) 
                           for t in set(i.incident_type for i in period_incidents)},
                'by_priority': {p: sum(1 for i in period_incidents if i.priority == p)
                              for p in set(i.priority for i in period_incidents)}
            })
            
            current_date = next_date
        
        # Calculate response time statistics
        response_times = []
        for incident in incidents:
            assignments = UnitAssignment.query.filter_by(incident_id=incident.id).all()
            for assignment in assignments:
                if assignment.assigned_at and assignment.arrived_at:
                    response_time = (assignment.arrived_at - assignment.assigned_at).total_seconds() / 60  # in minutes
                    response_times.append(response_time)
                    
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        # Compile statistics
        statistics = {
            'total_incidents': len(incidents),
            'by_type': dict(incidents_by_type),
            'by_priority': dict(incidents_by_priority),
            'by_status': dict(incidents_by_status),
            'time_series': time_series,
            'avg_response_time': avg_response_time,
            'min_response_time': min(response_times) if response_times else 0,
            'max_response_time': max(response_times) if response_times else 0,
        }
        
        return statistics
    
    @staticmethod
    def generate_unit_statistics(start_date=None, end_date=None):
        """
        Generate statistics about units for reporting and data visualization.
        
        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            Dictionary with statistical data
        """
        if not start_date:
            start_date = datetime.now() - timedelta(days=30)  # Default to last 30 days
        if not end_date:
            end_date = datetime.now()
            
        # Get all units
        units = Unit.query.all()
        
        # Get assignments in date range
        assignments = UnitAssignment.query.join(Incident).filter(
            Incident.created_at >= start_date,
            Incident.created_at <= end_date
        ).all()
        
        # Count assignments per unit
        assignments_by_unit = defaultdict(int)
        for assignment in assignments:
            assignments_by_unit[assignment.unit_id] += 1
            
        # Calculate utilization (time assigned to incidents / total time)
        utilization_by_unit = {}
        for unit in units:
            unit_assignments = [a for a in assignments if a.unit_id == unit.id]
            
            # Calculate total assigned time in minutes
            total_assigned_time = 0
            for assignment in unit_assignments:
                if assignment.assigned_at:
                    start_time = assignment.assigned_at
                    if assignment.cleared_at:
                        end_time = assignment.cleared_at
                    else:
                        end_time = end_date if assignment.status != 'cleared' else start_date
                        
                    # Ensure times are within our date range
                    start_time = max(start_time, start_date)
                    end_time = min(end_time, end_date)
                    
                    assignment_duration = (end_time - start_time).total_seconds() / 60  # in minutes
                    total_assigned_time += assignment_duration
            
            # Calculate total period time in minutes
            total_period_time = (end_date - start_date).total_seconds() / 60
            
            # Calculate utilization percentage
            utilization = (total_assigned_time / total_period_time) * 100 if total_period_time > 0 else 0
            utilization_by_unit[unit.id] = round(utilization, 2)
        
        # Count statuses
        current_statuses = defaultdict(int)
        for unit in units:
            current_statuses[unit.status] += 1
        
        # Count by type
        units_by_type = defaultdict(int)
        for unit in units:
            units_by_type[unit.unit_type] += 1
        
        # Compile statistics
        statistics = {
            'total_units': len(units),
            'by_type': dict(units_by_type),
            'by_status': dict(current_statuses),
            'assignments': {
                'total': sum(assignments_by_unit.values()),
                'by_unit': assignments_by_unit
            },
            'utilization': {
                'by_unit': utilization_by_unit,
                'avg': sum(utilization_by_unit.values()) / len(utilization_by_unit) if utilization_by_unit else 0
            }
        }
        
        return statistics
    
    @staticmethod
    def generate_data_visualization(data_type, data, output_format='png'):
        """
        Generate data visualizations for reports.
        
        Args:
            data_type: Type of visualization ('incident_by_type', 'incident_by_priority', etc.)
            data: Data to visualize
            output_format: Output format ('png', 'svg', 'pdf')
            
        Returns:
            Visualization data in the specified format
        """
        plt.figure(figsize=(10, 6))
        
        if data_type == 'incident_by_type':
            # Incident count by type
            types = list(data.keys())
            counts = list(data.values())
            
            plt.bar(types, counts)
            plt.title('Incidents by Type')
            plt.xlabel('Incident Type')
            plt.ylabel('Count')
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            
        elif data_type == 'incident_by_priority':
            # Incident count by priority
            priorities = list(data.keys())
            counts = list(data.values())
            
            plt.bar(priorities, counts)
            plt.title('Incidents by Priority')
            plt.xlabel('Priority')
            plt.ylabel('Count')
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            
        elif data_type == 'incident_time_series':
            # Time series of incidents
            periods = [d['period'] for d in data]
            counts = [d['count'] for d in data]
            
            plt.plot(periods, counts, marker='o')
            plt.title('Incident Count Over Time')
            plt.xlabel('Period')
            plt.ylabel('Count')
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            
        elif data_type == 'unit_utilization':
            # Unit utilization
            units = list(data.keys())
            utilization = list(data.values())
            
            plt.bar(units, utilization)
            plt.title('Unit Utilization (%)')
            plt.xlabel('Unit ID')
            plt.ylabel('Utilization %')
            plt.ylim(0, 100)
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            
        elif data_type == 'response_time_histogram':
            # Response time histogram
            plt.hist(data, bins=20)
            plt.title('Response Time Distribution')
            plt.xlabel('Response Time (minutes)')
            plt.ylabel('Frequency')
            plt.tight_layout()
            
        else:
            plt.text(0.5, 0.5, "Unsupported visualization type", ha='center', va='center')
            
        # Save plot to buffer
        buffer = io.BytesIO()
        plt.savefig(buffer, format=output_format)
        plt.close()
        
        buffer.seek(0)
        
        if output_format == 'png' or output_format == 'pdf':
            return buffer
        elif output_format == 'svg':
            return buffer.getvalue().decode('utf-8')
        elif output_format == 'base64':
            return base64.b64encode(buffer.getvalue()).decode('utf-8')
            
    @staticmethod
    def generate_daily_log_report(date=None):
        """
        Generate a daily log report for the specified date.
        
        Args:
            date: Date to generate report for, defaults to yesterday
            
        Returns:
            PDF buffer containing the daily log report
        """
        if not date:
            date = datetime.now().date() - timedelta(days=1)
            
        # Get incidents created on the specified date
        start_datetime = datetime.combine(date, datetime.min.time())
        end_datetime = datetime.combine(date, datetime.max.time())
        
        incidents = Incident.query.filter(
            Incident.created_at >= start_datetime,
            Incident.created_at <= end_datetime
        ).order_by(Incident.created_at).all()
        
        # Create PDF
        pdf_buffer = io.BytesIO()
        
        with PdfPages(pdf_buffer) as pdf:
            # Title page
            plt.figure(figsize=(8.5, 11))
            plt.axis('off')
            plt.text(0.5, 0.9, "Daily Log Report", fontsize=24, ha='center')
            plt.text(0.5, 0.8, date.strftime('%A, %B %d, %Y'), fontsize=18, ha='center')
            
            # Summary statistics
            plt.text(0.5, 0.7, "Summary Statistics", fontsize=14, ha='center')
            
            stats = [
                f"Total Incidents: {len(incidents)}",
                f"High Priority: {sum(1 for i in incidents if i.priority == 'high')}",
                f"Medium Priority: {sum(1 for i in incidents if i.priority == 'medium')}",
                f"Low Priority: {sum(1 for i in incidents if i.priority == 'low')}"
            ]
            
            y_pos = 0.65
            for stat in stats:
                plt.text(0.5, y_pos, stat, fontsize=12, ha='center')
                y_pos -= 0.05
                
            pdf.savefig()
            plt.close()
            
            # Incident list
            plt.figure(figsize=(8.5, 11))
            plt.axis('off')
            plt.text(0.5, 0.95, "Incidents", fontsize=18, ha='center')
            
            if incidents:
                # Headers
                headers = ["Time", "Number", "Type", "Priority", "Location", "Status"]
                col_positions = [0.05, 0.15, 0.3, 0.45, 0.6, 0.85]
                
                y_pos = 0.9
                for i, header in enumerate(headers):
                    plt.text(col_positions[i], y_pos, header, fontsize=10, fontweight='bold')
                
                y_pos -= 0.03
                
                # Draw a line under headers
                plt.axhline(y=y_pos, xmin=0.05, xmax=0.95, color='black', alpha=0.3)
                
                y_pos -= 0.02
                
                # Incidents
                for incident in incidents:
                    plt.text(col_positions[0], y_pos, incident.created_at.strftime('%H:%M'), fontsize=9)
                    plt.text(col_positions[1], y_pos, incident.incident_number, fontsize=9)
                    plt.text(col_positions[2], y_pos, incident.incident_type, fontsize=9)
                    plt.text(col_positions[3], y_pos, incident.priority, fontsize=9)
                    
                    # Truncate location if too long
                    location = incident.location
                    if len(location) > 25:
                        location = location[:22] + '...'
                    plt.text(col_positions[4], y_pos, location, fontsize=9)
                    
                    plt.text(col_positions[5], y_pos, incident.status, fontsize=9)
                    
                    y_pos -= 0.03
                    
                    # Start a new page if needed
                    if y_pos < 0.1:
                        pdf.savefig()
                        plt.close()
                        plt.figure(figsize=(8.5, 11))
                        plt.axis('off')
                        plt.text(0.5, 0.95, "Incidents (Continued)", fontsize=18, ha='center')
                        
                        # Headers again
                        y_pos = 0.9
                        for i, header in enumerate(headers):
                            plt.text(col_positions[i], y_pos, header, fontsize=10, fontweight='bold')
                        
                        y_pos -= 0.03
                        
                        # Draw a line under headers
                        plt.axhline(y=y_pos, xmin=0.05, xmax=0.95, color='black', alpha=0.3)
                        
                        y_pos -= 0.02
            else:
                plt.text(0.5, 0.5, "No incidents recorded on this date", fontsize=12, ha='center')
                
            pdf.savefig()
            plt.close()
            
            # Add visualizations
            incident_types = defaultdict(int)
            for incident in incidents:
                incident_types[incident.incident_type] += 1
                
            if incident_types:
                plt.figure(figsize=(8.5, 11))
                plt.axis('off')
                plt.text(0.5, 0.95, "Daily Statistics", fontsize=18, ha='center')
                
                # Incident type chart
                ax1 = plt.axes([0.1, 0.6, 0.8, 0.3])
                types = list(incident_types.keys())
                counts = list(incident_types.values())
                ax1.bar(types, counts)
                ax1.set_title('Incidents by Type')
                ax1.set_ylabel('Count')
                plt.setp(ax1.get_xticklabels(), rotation=45, ha='right')
                
                # Incident hour of day chart
                hours = defaultdict(int)
                for incident in incidents:
                    hour = incident.created_at.hour
                    hours[hour] += 1
                    
                ax2 = plt.axes([0.1, 0.1, 0.8, 0.3])
                hour_labels = list(range(24))
                hour_counts = [hours.get(hour, 0) for hour in hour_labels]
                ax2.bar(hour_labels, hour_counts)
                ax2.set_title('Incidents by Hour of Day')
                ax2.set_xlabel('Hour (24-hour format)')
                ax2.set_ylabel('Count')
                ax2.set_xticks(range(0, 24, 2))
                
                pdf.savefig()
                plt.close()
        
        # Reset buffer position to the beginning
        pdf_buffer.seek(0)
        return pdf_buffer
