"""
Input validation utilities for the CAD system.

This module provides functions for validating user input to prevent injection attacks,
ensure data integrity, and improve security.
"""

import re
import json
from flask import request, jsonify
from functools import wraps
import jsonschema
from jsonschema import validate, ValidationError, Draft7Validator

# Common validation patterns
PATTERNS = {
    'email': r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$',
    'phone': r'^\+?[0-9]{10,15}$',
    'name': r'^[a-zA-Z0-9\s\-\'\.]{2,50}$',
    'username': r'^[a-zA-Z0-9_\-\.]{3,30}$',
    'password': r'^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d@$!%*#?&]{8,}$',
    'zipcode': r'^\d{5}(-\d{4})?$',
    'url': r'^(https?:\/\/)?([\da-z\.-]+)\.([a-z\.]{2,6})([\/\w \.-]*)*\/?$',
    'date': r'^\d{4}-\d{2}-\d{2}$',
    'time': r'^\d{2}:\d{2}(:\d{2})?$',
    'datetime': r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:\d{2})?$',
    'latitude': r'^[-+]?([1-8]?\d(\.\d+)?|90(\.0+)?)$',
    'longitude': r'^[-+]?(180(\.0+)?|((1[0-7]\d)|([1-9]?\d))(\.\d+)?)$',
    'alpha': r'^[a-zA-Z]+$',
    'alphanumeric': r'^[a-zA-Z0-9]+$',
    'numeric': r'^[0-9]+$',
    'integer': r'^[-+]?[0-9]+$',
    'float': r'^[-+]?[0-9]*\.?[0-9]+$',
    'hexcolor': r'^#?([a-fA-F0-9]{6}|[a-fA-F0-9]{3})$',
    'id': r'^[0-9]+$',
}

def validate_pattern(value, pattern_name=None, pattern=None, required=True):
    """
    Validate a value against a regex pattern.
    
    Args:
        value: The value to validate
        pattern_name: Name of the pattern from PATTERNS
        pattern: Custom regex pattern
        required: Whether the value is required
    
    Returns:
        (bool, str): Tuple of (is_valid, error_message)
    """
    if value is None or value == '':
        return (not required, "Field is required" if required else "")
    
    if pattern is None and pattern_name in PATTERNS:
        pattern = PATTERNS[pattern_name]
    
    if pattern and not re.match(pattern, str(value)):
        return (False, f"Invalid format for {pattern_name or 'field'}")
    
    return (True, "")

def validate_length(value, min_length=None, max_length=None, required=True):
    """
    Validate the length of a string.
    
    Args:
        value: The value to validate
        min_length: Minimum allowed length
        max_length: Maximum allowed length
        required: Whether the value is required
    
    Returns:
        (bool, str): Tuple of (is_valid, error_message)
    """
    if value is None or value == '':
        return (not required, "Field is required" if required else "")
    
    value_str = str(value)
    
    if min_length is not None and len(value_str) < min_length:
        return (False, f"Value is too short (minimum length: {min_length})")
    
    if max_length is not None and len(value_str) > max_length:
        return (False, f"Value is too long (maximum length: {max_length})")
    
    return (True, "")

def validate_range(value, min_value=None, max_value=None, required=True):
    """
    Validate that a numeric value is within a specified range.
    
    Args:
        value: The value to validate
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        required: Whether the value is required
    
    Returns:
        (bool, str): Tuple of (is_valid, error_message)
    """
    if value is None or value == '':
        return (not required, "Field is required" if required else "")
    
    try:
        numeric_value = float(value)
    except (ValueError, TypeError):
        return (False, "Value must be a number")
    
    if min_value is not None and numeric_value < min_value:
        return (False, f"Value is too small (minimum: {min_value})")
    
    if max_value is not None and numeric_value > max_value:
        return (False, f"Value is too large (maximum: {max_value})")
    
    return (True, "")

def validate_in_list(value, allowed_values, required=True):
    """
    Validate that a value is in a list of allowed values.
    
    Args:
        value: The value to validate
        allowed_values: List of allowed values
        required: Whether the value is required
    
    Returns:
        (bool, str): Tuple of (is_valid, error_message)
    """
    if value is None or value == '':
        return (not required, "Field is required" if required else "")
    
    if value not in allowed_values:
        return (False, f"Value must be one of: {', '.join(str(x) for x in allowed_values)}")
    
    return (True, "")

def sanitize_html(text):
    """
    Sanitize HTML content to prevent XSS attacks.
    
    Args:
        text: The text to sanitize
    
    Returns:
        str: Sanitized text
    """
    import bleach
    
    # Define allowed tags and attributes
    allowed_tags = ['a', 'abbr', 'acronym', 'b', 'blockquote', 'code', 'em', 'i', 'li', 'ol', 'p', 'strong', 'ul']
    allowed_attrs = {
        'a': ['href', 'title'],
        '*': ['class']
    }
    
    # Clean the text
    return bleach.clean(text, tags=allowed_tags, attributes=allowed_attrs, strip=True)

def validate_json_payload(schema):
    """
    Decorator to validate JSON payloads against a schema.
    
    Args:
        schema: Dictionary mapping field names to validation functions
    
    Returns:
        function: Decorated view function
    """
    def decorator(view_function):
        @wraps(view_function)
        def decorated_function(*args, **kwargs):
            # Only validate POST, PUT, PATCH methods
            if request.method not in ('POST', 'PUT', 'PATCH'):
                return view_function(*args, **kwargs)
            
            # Check if the request has JSON data
            if not request.is_json:
                return jsonify({
                    'success': False,
                    'message': 'Request must be JSON',
                    'errors': {'_general': 'Content-Type must be application/json'}
                }), 400
            
            # Get JSON data
            try:
                data = request.get_json()
            except:
                return jsonify({
                    'success': False,
                    'message': 'Invalid JSON payload',
                    'errors': {'_general': 'Could not parse JSON data'}
                }), 400
            
            # Validate against schema
            errors = {}
            for field, validators in schema.items():
                if not isinstance(validators, list):
                    validators = [validators]
                
                field_value = data.get(field)
                
                for validator in validators:
                    is_valid, error_message = validator(field_value)
                    if not is_valid:
                        errors[field] = error_message
                        break
            
            if errors:
                return jsonify({
                    'success': False,
                    'message': 'Validation failed',
                    'errors': errors
                }), 400
            
            return view_function(*args, **kwargs)
        
        return decorated_function
    
    return decorator

def validate_coordinates(latitude, longitude):
    """
    Validate geographic coordinates (latitude and longitude).
    
    Args:
        latitude: Latitude value to validate (-90 to 90)
        longitude: Longitude value to validate (-180 to 180)
    
    Returns:
        bool: True if coordinates are valid, False otherwise
    """
    # Check latitude
    try:
        lat = float(latitude)
        if lat < -90 or lat > 90:
            return False
    except (ValueError, TypeError):
        return False
    
    # Check longitude
    try:
        lon = float(longitude)
        if lon < -180 or lon > 180:
            return False
    except (ValueError, TypeError):
        return False
    
    return True

# Helper function to create validators
def create_validator(field_name, **validation_params):
    """
    Create a validation function for a field.
    
    Args:
        field_name: Name of the field (for error messages)
        **validation_params: Validation parameters
    
    Returns:
        function: Validation function
    """
    def validator(value):
        # Required check
        required = validation_params.get('required', True)
        if (value is None or value == '') and required:
            return False, f"{field_name} is required"
        elif (value is None or value == '') and not required:
            return True, ""
        
        # Pattern validation
        pattern = validation_params.get('pattern')
        pattern_name = validation_params.get('pattern_name')
        if pattern or pattern_name:
            is_valid, error = validate_pattern(value, pattern_name, pattern, required=False)
            if not is_valid:
                return False, error
        
        # Length validation
        min_length = validation_params.get('min_length')
        max_length = validation_params.get('max_length')
        if min_length is not None or max_length is not None:
            is_valid, error = validate_length(value, min_length, max_length, required=False)
            if not is_valid:
                return False, error
        
        # Range validation
        min_value = validation_params.get('min_value')
        max_value = validation_params.get('max_value')
        if min_value is not None or max_value is not None:
            is_valid, error = validate_range(value, min_value, max_value, required=False)
            if not is_valid:
                return False, error
        
        # Allowed values validation
        allowed_values = validation_params.get('allowed_values')
        if allowed_values:
            is_valid, error = validate_in_list(value, allowed_values, required=False)
            if not is_valid:
                return False, error
        
        return True, ""
    
    return validator

# JSON Schema Validation
def validate_json_schema(schema):
    """
    Decorator to validate request JSON against a JSON schema.
    
    Args:
        schema (dict): JSON schema to validate against
    
    Returns:
        function: Decorated function
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Only validate POST, PUT, PATCH methods
            if request.method not in ('POST', 'PUT', 'PATCH'):
                return f(*args, **kwargs)
            
            # Check if the request has JSON data
            if not request.is_json:
                return jsonify({
                    'success': False,
                    'message': 'Request must be JSON',
                    'error': 'content_type_error'
                }), 415
                
            # Get JSON data
            try:
                data = request.get_json()
            except:
                return jsonify({
                    'success': False,
                    'message': 'Invalid JSON payload',
                    'error': 'json_parse_error'
                }), 400
                
            # Validate against schema
            try:
                validate(instance=data, schema=schema)
            except ValidationError as e:
                return jsonify({
                    'success': False,
                    'message': 'Validation failed',
                    'error': 'schema_validation_error',
                    'details': str(e)
                }), 400
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Advanced JSON Schema Validation with custom error formatting
def validate_json_schema_detailed(schema):
    """
    Decorator to validate request JSON against a JSON schema with detailed error messages.
    
    Args:
        schema (dict): JSON schema to validate against
    
    Returns:
        function: Decorated function
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Only validate POST, PUT, PATCH methods
            if request.method not in ('POST', 'PUT', 'PATCH'):
                return f(*args, **kwargs)
            
            # Check if the request has JSON data
            if not request.is_json:
                return jsonify({
                    'success': False,
                    'message': 'Request must be JSON',
                    'error': 'content_type_error'
                }), 415
                
            # Get JSON data
            try:
                data = request.get_json()
            except:
                return jsonify({
                    'success': False,
                    'message': 'Invalid JSON payload',
                    'error': 'json_parse_error'
                }), 400
            
            # Validate schema using Draft7Validator for more detailed errors
            validator = Draft7Validator(schema)
            errors = []
            
            for error in sorted(validator.iter_errors(data), key=str):
                path = '.'.join(str(p) for p in error.path) if error.path else 'root'
                errors.append({
                    'path': path,
                    'message': error.message,
                    'schema_path': '.'.join(str(p) for p in error.schema_path)
                })
                
            if errors:
                return jsonify({
                    'success': False,
                    'message': 'Validation failed',
                    'error': 'schema_validation_error',
                    'details': errors
                }), 400
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Standard JSON schemas for common objects
USER_SCHEMA = {
    "type": "object",
    "required": ["username", "email", "password", "first_name", "last_name"],
    "properties": {
        "username": {"type": "string", "minLength": 3, "maxLength": 30},
        "email": {"type": "string", "format": "email"},
        "password": {"type": "string", "minLength": 8},
        "first_name": {"type": "string", "minLength": 1, "maxLength": 50},
        "last_name": {"type": "string", "minLength": 1, "maxLength": 50},
        "role": {"type": "string", "enum": ["user", "dispatcher", "admin"]},
        "phone": {"type": "string", "pattern": "^\\+?[0-9]{10,15}$"}
    }
}

def validate_request_json(required_fields=None, optional_fields=None):
    """
    Decorator to validate that a request contains valid JSON with required fields.
    
    Args:
        required_fields (list): List of field names that must be present
        optional_fields (list): List of field names that may be present
        
    Returns:
        function: Decorated function
    """
    if required_fields is None:
        required_fields = []
    if optional_fields is None:
        optional_fields = []
        
    def decorator(view_function):
        @wraps(view_function)
        def decorated_function(*args, **kwargs):
            # Only validate POST, PUT, PATCH methods
            if request.method not in ('POST', 'PUT', 'PATCH'):
                return view_function(*args, **kwargs)
                
            # Check if the request has JSON data
            if not request.is_json:
                return jsonify({
                    'success': False,
                    'message': 'Request must be JSON',
                    'errors': {'_general': 'Content-Type must be application/json'}
                }), 400
                
            # Get JSON data
            try:
                data = request.get_json()
                if data is None:
                    raise ValueError("Empty JSON body")
            except Exception as e:
                return jsonify({
                    'success': False,
                    'message': 'Invalid JSON payload',
                    'errors': {'_general': f'Could not parse JSON data: {str(e)}'}
                }), 400
                
            # Check required fields
            errors = {}
            for field in required_fields:
                if field not in data or data[field] is None or data[field] == "":
                    errors[field] = f'Field "{field}" is required'
                    
            # If there are validation errors, return them
            if errors:
                return jsonify({
                    'success': False,
                    'message': 'Validation error',
                    'errors': errors
                }), 400
                
            # If we've passed validation, continue to the view function
            return view_function(*args, **kwargs)
            
        return decorated_function
    return decorator

def validate_date(date_str, format_str="%Y-%m-%d"):
    """
    Validate a date string against a specific format.
    
    Args:
        date_str (str): Date string to validate
        format_str (str): Expected date format (default: YYYY-MM-DD)
        
    Returns:
        tuple: (is_valid, error_message_or_datetime_object)
        If valid, returns (True, datetime object)
        If invalid, returns (False, error message)
    """
    from datetime import datetime
    
    if not date_str:
        return False, "Date cannot be empty"
        
    try:
        date_obj = datetime.strptime(date_str, format_str)
        return True, date_obj
    except ValueError:
        return False, f"Invalid date format. Expected format: {format_str}"

# System Settings Schema
SYSTEM_SETTINGS_SCHEMA = {
    "type": "object",
    "required": ["name", "value"],
    "properties": {
        "name": {"type": "string", "minLength": 1, "maxLength": 100},
        "value": {"type": ["string", "number", "boolean", "null"]},
        "description": {"type": "string"}
    },
    "additionalProperties": False
}

SCHEMAS = {
    'user': {
        'type': 'object',
        'required': ['username', 'email', 'password'],
        'properties': {
            'username': {
                'type': 'string',
                'minLength': 3,
                'maxLength': 30,
                'pattern': PATTERNS['username'][1:-1]  # Remove ^ and $
            },
            'email': {
                'type': 'string',
                'format': 'email',
                'pattern': PATTERNS['email'][1:-1]
            },
            'password': {
                'type': 'string',
                'minLength': 8,
                'pattern': PATTERNS['password'][1:-1]
            },
            'first_name': {
                'type': 'string',
                'maxLength': 50
            },
            'last_name': {
                'type': 'string',
                'maxLength': 50
            },
            'role_id': {
                'type': 'integer'
            }
        },
        'additionalProperties': False
    },
    'unit': {
        'type': 'object',
        'required': ['name', 'type_id'],
        'properties': {
            'name': {
                'type': 'string',
                'minLength': 1,
                'maxLength': 50
            },
            'type_id': {
                'type': 'integer'
            },
            'status': {
                'type': 'string',
                'enum': ['available', 'dispatched', 'on_scene', 'unavailable', 'out_of_service']
            },
            'location': {
                'type': 'object',
                'properties': {
                    'latitude': {
                        'type': 'number',
                        'minimum': -90,
                        'maximum': 90
                    },
                    'longitude': {
                        'type': 'number',
                        'minimum': -180,
                        'maximum': 180
                    }
                },
                'required': ['latitude', 'longitude']
            },
            'personnel': {
                'type': 'array',
                'items': {
                    'type': 'integer'
                }
            }
        },
        'additionalProperties': False
    },
    'incident': {
        'type': 'object',
        'required': ['type', 'priority', 'location'],
        'properties': {
            'type': {
                'type': 'string',
                'minLength': 1,
                'maxLength': 50
            },
            'priority': {
                'type': 'integer',
                'minimum': 1,
                'maximum': 5
            },
            'location': {
                'type': 'object',
                'properties': {
                    'address': {
                        'type': 'string',
                        'minLength': 1,
                        'maxLength': 200
                    },
                    'latitude': {
                        'type': 'number',
                        'minimum': -90,
                        'maximum': 90
                    },
                    'longitude': {
                        'type': 'number',
                        'minimum': -180,
                        'maximum': 180
                    }
                },
                'required': ['address']
            },
            'description': {
                'type': 'string',
                'maxLength': 500
            },
            'caller_info': {
                'type': 'object',
                'properties': {
                    'name': {
                        'type': 'string',
                        'maxLength': 100
                    },
                    'phone': {
                        'type': 'string',
                        'pattern': PATTERNS['phone'][1:-1]
                    }
                }
            }
        },
        'additionalProperties': False
    }
}
