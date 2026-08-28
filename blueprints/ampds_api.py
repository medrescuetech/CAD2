from flask import Blueprint, request, jsonify, current_app, send_file
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy import desc, or_
import io
import csv
import json

from models import AMPDSProtocol, Incident, Permission
from extensions import db, csrf
from utils.validation import validate_request_json
from utils.decorators import role_required, rate_limit
from utils.logging import log_activity

ampds_api = Blueprint('ampds_api', __name__)

@ampds_api.route('/api/ampds/protocols', methods=['GET'])
@login_required
@role_required('VIEW_DASHBOARD')
@rate_limit(limit=60, period=60)
def get_ampds_protocols():
    """Get a list of AMPDS protocols with filtering options."""
    try:
        # Parse query parameters
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 50, type=int), 100)
        category = request.args.get('category')
        card_number = request.args.get('card_number')
        priority = request.args.get('priority')
        search = request.args.get('search')
        
        # Build query
        query = AMPDSProtocol.query
        
        # Apply filters
        if category:
            query = query.filter(AMPDSProtocol.category == category)
        
        if card_number:
            query = query.filter(AMPDSProtocol.card_number == card_number)
        
        if priority:
            query = query.filter(AMPDSProtocol.priority == priority)
        
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    AMPDSProtocol.unique_id.ilike(search_pattern),
                    AMPDSProtocol.category.ilike(search_pattern),
                    AMPDSProtocol.subcategory.ilike(search_pattern)
                )
            )
        
        # Order by card_number and then category
        query = query.order_by(AMPDSProtocol.card_number, AMPDSProtocol.category)
        
        # Paginate results
        protocols_pagination = query.paginate(page=page, per_page=per_page)
        
        # Prepare response
        protocols = [protocol.to_dict() for protocol in protocols_pagination.items]
        
        # Get unique categories and card numbers for filtering
        categories = db.session.query(AMPDSProtocol.category).distinct().order_by(AMPDSProtocol.category).all()
        card_numbers = db.session.query(AMPDSProtocol.card_number).distinct().order_by(AMPDSProtocol.card_number).all()
        priorities = db.session.query(AMPDSProtocol.priority).distinct().order_by(AMPDSProtocol.priority).all()
        
        return jsonify({
            'protocols': protocols,
            'total': protocols_pagination.total,
            'pages': protocols_pagination.pages,
            'current_page': page,
            'filter_options': {
                'categories': [c[0] for c in categories],
                'card_numbers': [cn[0] for cn in card_numbers],
                'priorities': [p[0] for p in priorities]
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in get_ampds_protocols: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@ampds_api.route('/api/ampds/protocols/<unique_id>', methods=['GET'])
@login_required
@role_required('VIEW_DASHBOARD')
@rate_limit(limit=30, period=60)
def get_ampds_protocol(unique_id):
    """Get a specific AMPDS protocol by unique ID."""
    try:
        protocol = AMPDSProtocol.query.filter_by(unique_id=unique_id).first()
        
        if not protocol:
            return jsonify({'error': 'AMPDS protocol not found'}), 404
        
        # Check if this protocol is used in any incidents
        incident_count = Incident.query.filter_by(ampds_code=unique_id).count()
        
        return jsonify({
            'protocol': protocol.to_dict(),
            'incident_count': incident_count
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in get_ampds_protocol: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@ampds_api.route('/api/ampds/protocols/<protocol_id>', methods=['GET'])
@login_required
@role_required('VIEW_DASHBOARD')
def get_ampds_protocol_by_id(protocol_id):
    """
    Get details for a specific AMPDS protocol by its unique ID.
    """
    protocol = AMPDSProtocol.query.filter_by(unique_id=protocol_id).first()
    
    if not protocol:
        return jsonify({'error': 'Protocol not found'}), 404
    
    return jsonify({
        'protocol': {
            'unique_id': protocol.unique_id,
            'category': protocol.category,
            'subcategory': protocol.subcategory,
            'card_number': protocol.card_number,
            'priority': protocol.priority,
            'dispatch_advice': protocol.dispatch_advice
        }
    }), 200

@ampds_api.route('/api/ampds/protocols', methods=['POST'])
@login_required
@role_required('ADMIN')
@csrf.exempt
@rate_limit(limit=10, period=60)
def create_ampds_protocol():
    """Create a new AMPDS protocol."""
    try:
        # Validate request
        schema = {
            'type': 'object',
            'required': ['unique_id', 'category', 'card_number', 'priority', 'subcategory'],
            'properties': {
                'unique_id': {'type': 'string', 'minLength': 1, 'maxLength': 20},
                'category': {'type': 'string', 'minLength': 1, 'maxLength': 50},
                'card_number': {'type': 'string', 'minLength': 1, 'maxLength': 20},
                'priority': {'type': 'string', 'minLength': 1, 'maxLength': 20},
                'subcategory': {'type': 'string', 'minLength': 1, 'maxLength': 200},
                'dispatch_advice': {'type': 'string'},
                'prearrival_pdf': {'type': 'string', 'maxLength': 200}
            }
        }
        
        data = request.get_json()
        validation_result = validate_request_json(data, schema)
        
        if validation_result:
            return jsonify({'error': validation_result}), 400
        
        # Check if protocol already exists
        existing = AMPDSProtocol.query.filter_by(unique_id=data['unique_id']).first()
        if existing:
            return jsonify({'error': 'An AMPDS protocol with this unique ID already exists'}), 409
        
        # Create new protocol
        protocol = AMPDSProtocol(
            unique_id=data['unique_id'],
            category=data['category'],
            card_number=data['card_number'],
            priority=data['priority'],
            subcategory=data['subcategory'],
            dispatch_advice=data.get('dispatch_advice', ''),
            prearrival_pdf=data.get('prearrival_pdf', '')
        )
        
        db.session.add(protocol)
        db.session.commit()
        
        # Log activity
        log_activity(
            action='create ampds protocol',
            details={'category': 'ampds'},
            user_id=current_user.id,
            resource_type='ampds_protocol',
            resource_id=protocol.unique_id
        )
        
        return jsonify(protocol.to_dict()), 201
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in create_ampds_protocol: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@ampds_api.route('/api/ampds/protocols/<unique_id>', methods=['PUT'])
@login_required
@role_required('ADMIN')
@csrf.exempt
@rate_limit(limit=20, period=60)
def update_ampds_protocol(unique_id):
    """Update an existing AMPDS protocol."""
    try:
        protocol = AMPDSProtocol.query.filter_by(unique_id=unique_id).first()
        
        if not protocol:
            return jsonify({'error': 'AMPDS protocol not found'}), 404
        
        # Validate request
        schema = {
            'type': 'object',
            'properties': {
                'category': {'type': 'string', 'minLength': 1, 'maxLength': 50},
                'card_number': {'type': 'string', 'minLength': 1, 'maxLength': 20},
                'priority': {'type': 'string', 'minLength': 1, 'maxLength': 20},
                'subcategory': {'type': 'string', 'minLength': 1, 'maxLength': 200},
                'dispatch_advice': {'type': 'string'},
                'prearrival_pdf': {'type': 'string', 'maxLength': 200}
            }
        }
        
        data = request.get_json()
        validation_result = validate_request_json(data, schema)
        
        if validation_result:
            return jsonify({'error': validation_result}), 400
        
        # Update protocol
        if 'category' in data:
            protocol.category = data['category']
        if 'card_number' in data:
            protocol.card_number = data['card_number']
        if 'priority' in data:
            protocol.priority = data['priority']
        if 'subcategory' in data:
            protocol.subcategory = data['subcategory']
        if 'dispatch_advice' in data:
            protocol.dispatch_advice = data['dispatch_advice']
        if 'prearrival_pdf' in data:
            protocol.prearrival_pdf = data['prearrival_pdf']
        
        protocol.updated_at = datetime.utcnow()
        db.session.commit()
        
        # Log activity
        log_activity(
            action='update ampds protocol',
            details={'category': 'ampds'},
            user_id=current_user.id,
            resource_type='ampds_protocol',
            resource_id=protocol.unique_id
        )
        
        return jsonify(protocol.to_dict())
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in update_ampds_protocol: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@ampds_api.route('/api/ampds/protocols/<unique_id>', methods=['DELETE'])
@login_required
@role_required('ADMIN')
@csrf.exempt
@rate_limit(limit=10, period=60)
def delete_ampds_protocol(unique_id):
    """Delete an AMPDS protocol."""
    try:
        protocol = AMPDSProtocol.query.filter_by(unique_id=unique_id).first()
        
        if not protocol:
            return jsonify({'error': 'AMPDS protocol not found'}), 404
        
        # Check if the protocol is used in any incidents
        incident_count = Incident.query.filter_by(ampds_code=unique_id).count()
        if incident_count > 0:
            return jsonify({
                'error': 'Cannot delete protocol that is in use',
                'incident_count': incident_count
            }), 409
        
        # Delete protocol
        db.session.delete(protocol)
        db.session.commit()
        
        # Log activity
        log_activity(
            action='delete ampds protocol',
            details={'category': 'ampds'},
            user_id=current_user.id,
            resource_type='ampds_protocol',
            resource_id=unique_id
        )
        
        return jsonify({'message': 'AMPDS protocol deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in delete_ampds_protocol: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@ampds_api.route('/api/ampds/search', methods=['GET'])
@login_required
@role_required('VIEW_DASHBOARD')
@rate_limit(limit=30, period=60)
def search_ampds_protocols():
    """Search AMPDS protocols by query term."""
    try:
        # Get query parameters
        query = request.args.get('q', '')
        limit = min(request.args.get('limit', 20, type=int), 100)
        category = request.args.get('category')
        card_number = request.args.get('card_number')
        priority = request.args.get('priority')
        
        # Basic validation
        if not query and not category and not card_number and not priority:
            return jsonify({'error': 'At least one search parameter is required'}), 400
        
        # Call enhanced model's search method with all parameters
        results = AMPDSProtocol.search(
            query=query, 
            limit=limit,
            category=category,
            card_number=card_number,
            priority=priority
        )
        
        # Prepare response
        protocols = [protocol.to_dict() for protocol in results]
        
        return jsonify({
            'query': query,
            'count': len(protocols),
            'filters': {
                'category': category,
                'card_number': card_number,
                'priority': priority
            },
            'protocols': protocols
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in search_ampds_protocols: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@ampds_api.route('/api/ampds/suggest/<int:incident_id>', methods=['GET'])
@login_required
@role_required('VIEW_DASHBOARD')
@rate_limit(limit=20, period=60)
def suggest_protocols_for_incident(incident_id):
    """Suggest AMPDS protocols based on an incident's type."""
    try:
        # Get the incident
        incident = Incident.query.get(incident_id)
        if not incident:
            return jsonify({'error': 'Incident not found'}), 404
            
        # Get the incident type name
        if not incident.incident_type or not incident.incident_type_obj:
            return jsonify({'error': 'Incident has no type specified'}), 400
            
        incident_type_name = incident.incident_type_obj.name
        
        # Get suggested protocols
        limit = min(request.args.get('limit', 5, type=int), 20)
        suggested_protocols = AMPDSProtocol.suggest_protocols_for_incident_type(
            incident_type_name=incident_type_name,
            limit=limit
        )
        
        # Prepare response
        protocols = [protocol.to_dict() for protocol in suggested_protocols]
        
        # Log this suggestion request
        log_activity(
            action='suggest_protocols',
            details={'category': 'ampds'},
            user_id=current_user.id,
            resource_type='incident',
            resource_id=str(incident_id)
        )
        
        return jsonify({
            'incident_id': incident_id,
            'incident_type': incident_type_name,
            'count': len(protocols),
            'protocols': protocols
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in suggest_protocols_for_incident: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@ampds_api.route('/api/ampds/suggest_by_type', methods=['GET'])
@login_required
@role_required('VIEW_DASHBOARD')
@rate_limit(limit=20, period=60)
def suggest_ampds_protocols_by_type():
    """
    Suggest AMPDS protocols based on incident type.
    This endpoint returns a list of protocols that are commonly used for a given incident type.
    """
    incident_type = request.args.get('type')
    
    if not incident_type:
        return jsonify({'error': 'Incident type is required'}), 400
    
    # Map incident types to categories (this could be enhanced with a dedicated mapping table)
    type_to_category_map = {
        'MEDICAL': ['Medical'],
        'FIRE': ['Fire'],
        'POLICE': ['Police'],
        'TRAFFIC': ['Traffic Accident'],
        'HAZMAT': ['HazMat'],
        'RESCUE': ['Water/Ice/Mud Rescue', 'Confined Space/Structure Collapse'],
        'ASSAULT': ['Assault'],
        'CARDIAC': ['Chest Pain', 'Breathing Problems', 'Cardiac Arrest'],
        'TRAUMA': ['Falls', 'Traumatic Injuries'],
        'PSYCHIATRIC': ['Psychiatric'],
        'OVERDOSE': ['Overdose']
    }
    
    # Get categories for the incident type
    categories = type_to_category_map.get(incident_type.upper(), [])
    
    # If no mapping found, return empty results
    if not categories:
        return jsonify({'protocols': []}), 200
    
    # Query protocols for these categories
    protocols = []
    for category in categories:
        results = AMPDSProtocol.query.filter(
            AMPDSProtocol.category.ilike(f"%{category}%")
        ).order_by(AMPDSProtocol.card_number).all()
        protocols.extend(results)
    
    # Limit to top 10 most common protocols
    protocols = protocols[:10]
    
    # Format the results
    result_protocols = []
    for protocol in protocols:
        result_protocols.append({
            'unique_id': protocol.unique_id,
            'category': protocol.category,
            'subcategory': protocol.subcategory,
            'card_number': protocol.card_number,
            'priority': protocol.priority,
            'dispatch_advice': protocol.dispatch_advice
        })
    
    return jsonify({'protocols': result_protocols}), 200

@ampds_api.route('/api/ampds/categories', methods=['GET'])
@login_required
@role_required('VIEW_DASHBOARD')
@rate_limit(limit=30, period=60)
def get_ampds_categories():
    """Get a list of all unique AMPDS categories."""
    try:
        categories = db.session.query(AMPDSProtocol.category).distinct().order_by(AMPDSProtocol.category).all()
        
        return jsonify({
            'categories': [c[0] for c in categories],
            'count': len(categories)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in get_ampds_categories: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@ampds_api.route('/api/ampds/cards', methods=['GET'])
@login_required
@role_required('VIEW_DASHBOARD')
@rate_limit(limit=30, period=60)
def get_ampds_cards():
    """Get a list of all unique AMPDS card numbers."""
    try:
        cards = db.session.query(AMPDSProtocol.card_number).distinct().order_by(AMPDSProtocol.card_number).all()
        
        return jsonify({
            'card_numbers': [c[0] for c in cards],
            'count': len(cards)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in get_ampds_cards: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@ampds_api.route('/api/ampds/priorities', methods=['GET'])
@login_required
@role_required('VIEW_DASHBOARD')
@rate_limit(limit=30, period=60)
def get_ampds_priorities():
    """Get a list of all unique AMPDS priorities."""
    try:
        priorities = db.session.query(AMPDSProtocol.priority).distinct().order_by(AMPDSProtocol.priority).all()
        
        return jsonify({
            'priorities': [p[0] for p in priorities],
            'count': len(priorities)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in get_ampds_priorities: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@ampds_api.route('/api/ampds/import', methods=['POST'])
@login_required
@role_required('ADMIN')
@csrf.exempt
@rate_limit(limit=5, period=300)  # Stricter rate limit for imports
def import_ampds_protocols():
    """Import AMPDS protocols from a CSV file."""
    try:
        file_storage = request.files.get('file')
        if not file_storage:
            return jsonify({'error': 'No file part in the request'}), 400
        if not getattr(file_storage, 'filename', None):
            return jsonify({'error': 'No file selected'}), 400
        if not str(file_storage.filename).lower().endswith('.csv'):
            return jsonify({'error': 'Only CSV files are allowed'}), 400

        # Import protocols using the FileStorage stream
        success_count, error_count, errors = AMPDSProtocol.import_from_csv(file_storage)
        
        # Log activity
        log_activity(
            action='import ampds protocols',
            details={'category': 'ampds', 'success_count': success_count, 'error_count': error_count},
            user_id=current_user.id,
            resource_type='ampds_protocols'
        )
        
        return jsonify({
            'success_count': success_count,
            'error_count': error_count,
            'errors': errors[:20] if errors else []  # Limit number of errors returned
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in import_ampds_protocols: {str(e)}", exc_info=True)
        return jsonify({'error': 'An unexpected error occurred', 'message': str(e)}), 500

@ampds_api.route('/api/ampds/export', methods=['GET'])
@login_required
@role_required('ADMIN')
@rate_limit(limit=5, period=300)  # Stricter rate limit for exports
def export_ampds_protocols():
    """Export all AMPDS protocols to a CSV file."""
    try:
        # Get all protocols
        protocols = AMPDSProtocol.query.order_by(AMPDSProtocol.card_number, AMPDSProtocol.category).all()
        
        # Prepare CSV output
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write headers
        writer.writerow([
            'unique_id', 'category', 'card_number', 'priority', 
            'subcategory', 'dispatch_advice', 'prearrival_pdf'
        ])
        
        # Write data
        for protocol in protocols:
            writer.writerow([
                protocol.unique_id,
                protocol.category,
                protocol.card_number,
                protocol.priority,
                protocol.subcategory,
                protocol.dispatch_advice,
                protocol.prearrival_pdf
            ])
        
        # Prepare response
        output.seek(0)
        date_str = datetime.now().strftime('%Y%m%d')
        
        # Log activity
        log_activity(
            action='export ampds protocols',
            details={'category': 'ampds'},
            user_id=current_user.id,
            resource_type='ampds_protocols'
        )
        
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            attachment_filename=f'ampds_protocols_{date_str}.csv'
        )
        
    except Exception as e:
        current_app.logger.error(f"Error in export_ampds_protocols: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@ampds_api.route('/api/ampds/category/<category>', methods=['GET'])
@login_required
@role_required('VIEW_DASHBOARD')
@rate_limit(limit=30, period=60)
def get_protocols_by_category(category):
    """Get all AMPDS protocols for a specific category."""
    try:
        protocols = AMPDSProtocol.query.filter_by(category=category).order_by(AMPDSProtocol.card_number).all()
        
        if not protocols:
            return jsonify({
                'category': category,
                'protocols': [],
                'count': 0
            })
        
        return jsonify({
            'category': category,
            'protocols': [p.to_dict() for p in protocols],
            'count': len(protocols)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in get_protocols_by_category: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@ampds_api.route('/api/ampds/card/<card_number>', methods=['GET'])
@login_required
@role_required('VIEW_DASHBOARD')
@rate_limit(limit=30, period=60)
def get_protocols_by_card(card_number):
    """Get all AMPDS protocols for a specific card number."""
    try:
        protocols = AMPDSProtocol.query.filter_by(card_number=card_number).order_by(AMPDSProtocol.category).all()
        
        if not protocols:
            return jsonify({
                'card_number': card_number,
                'protocols': [],
                'count': 0
            })
        
        return jsonify({
            'card_number': card_number,
            'protocols': [p.to_dict() for p in protocols],
            'count': len(protocols)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in get_protocols_by_card: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@ampds_api.route('/api/incidents/<int:incident_id>/set_ampds', methods=['POST'])
@login_required
@role_required('UPDATE_INCIDENTS')
@csrf.exempt
@rate_limit(limit=20, period=60)
def set_incident_ampds_protocol(incident_id):
    """Set the AMPDS protocol for an incident."""
    try:
        # Validate request
        schema = {
            'type': 'object',
            'required': ['protocol_id'],
            'properties': {
                'protocol_id': {'type': 'string'}
            }
        }
        
        data = request.get_json()
        validation_result = validate_request_json(data, schema)
        
        if validation_result:
            return jsonify({'error': validation_result}), 400
        
        # Get incident
        incident = Incident.query.get(incident_id)
        if not incident:
            return jsonify({'error': 'Incident not found'}), 404
        
        # Get protocol
        protocol_id = data['protocol_id']
        protocol = AMPDSProtocol.query.filter_by(unique_id=protocol_id).first()
        if not protocol:
            return jsonify({'error': 'AMPDS protocol not found'}), 404
        
        # Set protocol
        incident.set_ampds_protocol(protocol, current_user.id)
        
        # Log activity
        log_activity(
            category='incident',
            action='update_ampds',
            user_id=current_user.id,
            resource_type='incident',
            resource_id=str(incident.id),
            details=json.dumps({'protocol_id': protocol_id})
        )
        
        return jsonify({
            'message': 'AMPDS protocol set successfully',
            'incident': {
                'id': incident.id,
                'incident_number': incident.incident_number,
                'ampds_code': incident.ampds_code,
                'ampds_data': incident.get_ampds_data()
            }
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in set_incident_ampds_protocol: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@ampds_api.route('/api/incidents/<int:incident_id>/clear_ampds', methods=['POST'])
@login_required
@role_required('UPDATE_INCIDENTS')
@csrf.exempt
@rate_limit(limit=20, period=60)
def clear_incident_ampds_protocol(incident_id):
    """Clear the AMPDS protocol from an incident."""
    try:
        # Get incident
        incident = Incident.query.get(incident_id)
        if not incident:
            return jsonify({'error': 'Incident not found'}), 404
        
        # Check if there's a protocol to clear
        if not incident.ampds_code:
            return jsonify({'message': 'No AMPDS protocol set for this incident'}), 200
        
        # Store old value for logging
        old_ampds_code = incident.ampds_code
        
        # Clear protocol
        incident.ampds_code = None
        incident.ampds_data = None
        
        # Add log entry
        incident.add_log_entry(
            f"AMPDS protocol {old_ampds_code} removed by {current_user.username}",
            current_user.id,
            type="info"
        )
        
        db.session.commit()
        
        # Log activity
        log_activity(
            category='incident',
            action='clear_ampds',
            user_id=current_user.id,
            resource_type='incident',
            resource_id=str(incident.id),
            details=json.dumps({'previous_protocol_id': old_ampds_code})
        )
        
        return jsonify({
            'message': 'AMPDS protocol cleared successfully',
            'incident': {
                'id': incident.id,
                'incident_number': incident.incident_number
            }
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in clear_incident_ampds_protocol: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

@ampds_api.route('/api/incidents/with_ampds', methods=['GET'])
@login_required
@role_required('VIEW_INCIDENTS')
@rate_limit(limit=20, period=60)
def get_incidents_with_ampds():
    """Get a list of incidents that have AMPDS protocols assigned."""
    try:
        # Parse query parameters
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        protocol_id = request.args.get('protocol_id')
        
        # Build query
        query = Incident.query.filter(Incident.ampds_code.isnot(None))
        
        # Filter by specific protocol if requested
        if protocol_id:
            query = query.filter(Incident.ampds_code == protocol_id)
        
        # Order by newest first
        query = query.order_by(desc(Incident.created_at))
        
        # Paginate results
        incidents_pagination = query.paginate(page=page, per_page=per_page)
        
        # Prepare response
        incidents = []
        for incident in incidents_pagination.items:
            inc_dict = {
                'id': incident.id,
                'incident_number': incident.incident_number,
                'ampds_code': incident.ampds_code,
                'ampds_data': incident.get_ampds_data(),
                'status': incident.status,
                'created_at': incident.created_at.isoformat() if incident.created_at else None
            }
            incidents.append(inc_dict)
        
        return jsonify({
            'incidents': incidents,
            'total': incidents_pagination.total,
            'pages': incidents_pagination.pages,
            'current_page': page
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in get_incidents_with_ampds: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500
