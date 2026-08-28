# CAD System API Documentation

## Overview

This document provides detailed information about the CAD System API endpoints, authentication requirements, and response formats. The API enables integration with external systems and programmatic access to incident data, location services, and other CAD System features.

## Authentication

### API Keys

All API requests require authentication using API keys. API keys can be generated and managed from the Admin panel.

To authenticate, include the API key in the request header:

```
Authorization: Bearer YOUR_API_KEY
```

### Rate Limiting

To ensure system stability and security, API requests are rate-limited. Default limits are:
- 100 requests per minute per API key
- 5,000 requests per day per API key

## Common Response Formats

All API responses are returned in JSON format with the following structure:

### Success Response

```json
{
  "status": "success",
  "data": {
    // Response data here
  }
}
```

### Error Response

```json
{
  "status": "error",
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable error message"
  }
}
```

## Common Status Codes

- `200 OK`: Request was successful
- `201 Created`: Resource was successfully created
- `400 Bad Request`: Invalid request parameters
- `401 Unauthorized`: Missing or invalid API key
- `403 Forbidden`: API key doesn't have required permissions
- `404 Not Found`: Resource not found
- `429 Too Many Requests`: Rate limit exceeded
- `500 Internal Server Error`: Server error

## Endpoints

### Incidents

#### GET /api/incidents

Retrieves a list of incidents with optional filtering.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| status | string | No | Filter by incident status (e.g., "active", "closed") |
| priority | string | No | Filter by priority (e.g., "high", "medium", "low") |
| from_date | string | No | ISO 8601 date format (e.g., "2023-01-01T00:00:00Z") |
| to_date | string | No | ISO 8601 date format (e.g., "2023-01-31T23:59:59Z") |
| page | integer | No | Page number for pagination (default: 1) |
| per_page | integer | No | Results per page (default: 20, max: 100) |

**Response:**

```json
{
  "status": "success",
  "data": {
    "incidents": [
      {
        "id": 1,
        "case_number": "INC-2023-0001",
        "incident_type": {
          "id": 1,
          "name": "Medical Emergency"
        },
        "location": "123 Main St, Example City",
        "coordinates": {
          "latitude": -20.7256,
          "longitude": 116.8464
        },
        "status": "Active",
        "priority": "High",
        "created_at": "2023-01-15T08:30:00Z",
        "updated_at": "2023-01-15T09:15:00Z"
      }
    ],
    "total": 150,
    "page": 1,
    "per_page": 20,
    "pages": 8
  }
}
```

#### GET /api/incidents/{id}

Retrieves details for a specific incident.

**Response:**

```json
{
  "status": "success",
  "data": {
    "incident": {
      "id": 1,
      "case_number": "INC-2023-0001",
      "incident_type": {
        "id": 1,
        "name": "Medical Emergency"
      },
      "location": "123 Main St, Example City",
      "coordinates": {
        "latitude": -20.7256,
        "longitude": 116.8464
      },
      "status": "Active",
      "priority": "High",
      "created_at": "2023-01-15T08:30:00Z",
      "updated_at": "2023-01-15T09:15:00Z",
      "notes": [
        {
          "id": 1,
          "content": "Patient experiencing chest pain",
          "created_at": "2023-01-15T08:32:00Z",
          "created_by": "john.doe"
        }
      ],
      "resources_assigned": [
        {
          "id": 1,
          "name": "Ambulance 1",
          "type": "Ambulance",
          "status": "En Route"
        }
      ]
    }
  }
}
```

#### POST /api/incidents

Creates a new incident.

**Request:**

```json
{
  "incident_type_id": 1,
  "location": "123 Main St, Example City",
  "coordinates": {
    "latitude": -20.7256,
    "longitude": 116.8464
  },
  "priority": "High",
  "description": "Patient experiencing chest pain"
}
```

**Response:**

```json
{
  "status": "success",
  "data": {
    "incident": {
      "id": 1,
      "case_number": "INC-2023-0001",
      "incident_type": {
        "id": 1,
        "name": "Medical Emergency"
      },
      "location": "123 Main St, Example City",
      "coordinates": {
        "latitude": -20.7256,
        "longitude": 116.8464
      },
      "status": "Active",
      "priority": "High",
      "created_at": "2023-01-15T08:30:00Z",
      "updated_at": "2023-01-15T08:30:00Z"
    }
  }
}
```

#### PUT /api/incidents/{id}

Updates an existing incident.

**Request:**

```json
{
  "status": "Closed",
  "resolution": "Patient transported to hospital"
}
```

**Response:**

```json
{
  "status": "success",
  "data": {
    "incident": {
      "id": 1,
      "case_number": "INC-2023-0001",
      "status": "Closed",
      "updated_at": "2023-01-15T10:45:00Z"
    }
  }
}
```

### Resources

#### GET /api/resources

Retrieves a list of available resources with optional filtering.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| type | string | No | Filter by resource type (e.g., "ambulance", "police") |
| status | string | No | Filter by status (e.g., "available", "busy") |
| page | integer | No | Page number for pagination (default: 1) |
| per_page | integer | No | Results per page (default: 20, max: 100) |

**Response:**

```json
{
  "status": "success",
  "data": {
    "resources": [
      {
        "id": 1,
        "name": "Ambulance 1",
        "type": "Ambulance",
        "status": "Available",
        "current_location": {
          "latitude": -20.7245,
          "longitude": 116.8470
        },
        "last_updated": "2023-01-15T08:25:00Z"
      }
    ],
    "total": 50,
    "page": 1,
    "per_page": 20,
    "pages": 3
  }
}
```

#### GET /api/resources/{id}

Retrieves details for a specific resource.

**Response:**

```json
{
  "status": "success",
  "data": {
    "resource": {
      "id": 1,
      "name": "Ambulance 1",
      "type": "Ambulance",
      "status": "Available",
      "current_location": {
        "latitude": -20.7245,
        "longitude": 116.8470
      },
      "last_updated": "2023-01-15T08:25:00Z",
      "capabilities": [
        "Advanced Life Support",
        "Trauma Care"
      ],
      "current_assignment": null
    }
  }
}
```

### Location Services

#### GET /api/locations/search

Searches for locations based on keywords.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| query | string | Yes | Search query |
| limit | integer | No | Maximum number of results (default: 10, max: 50) |

**Response:**

```json
{
  "status": "success",
  "data": {
    "locations": [
      {
        "id": "loc-1",
        "name": "Central Hospital",
        "address": "123 Medical Dr, Example City",
        "coordinates": {
          "latitude": -20.7240,
          "longitude": 116.8450
        },
        "type": "Hospital"
      }
    ]
  }
}
```

#### GET /api/locations/nearby

Finds locations near specified coordinates.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| latitude | number | Yes | Latitude coordinate |
| longitude | number | Yes | Longitude coordinate |
| radius | number | No | Search radius in kilometers (default: 5, max: 50) |
| type | string | No | Filter by location type (e.g., "hospital", "police_station") |
| limit | integer | No | Maximum number of results (default: 10, max: 50) |

**Response:**

```json
{
  "status": "success",
  "data": {
    "locations": [
      {
        "id": "loc-1",
        "name": "Central Hospital",
        "address": "123 Medical Dr, Example City",
        "coordinates": {
          "latitude": -20.7240,
          "longitude": 116.8450
        },
        "type": "Hospital",
        "distance": 1.2
      }
    ]
  }
}
```

### AMPDS Integration

#### POST /api/ampds/dispatch

Receives AMPDS dispatch information and creates a corresponding incident.

**Request:**

```json
{
  "dispatch_id": "AMPDS-2023-0001",
  "call_time": "2023-01-15T08:30:00Z",
  "caller_info": {
    "phone": "555-123-4567",
    "name": "Jane Smith"
  },
  "location": {
    "address": "123 Main St, Example City",
    "coordinates": {
      "latitude": -20.7256,
      "longitude": 116.8464
    }
  },
  "chief_complaint": "Chest Pain",
  "determinant_code": "10-D-01",
  "priority": "High",
  "dispatch_code": "CHEST PAIN",
  "protocol_version": "v13.0"
}
```

**Response:**

```json
{
  "status": "success",
  "data": {
    "incident_id": 1,
    "case_number": "INC-2023-0001",
    "ampds_mapping": {
      "determinant_code": "10-D-01",
      "incident_type_id": 1,
      "priority": "High"
    },
    "status": "Active",
    "created_at": "2023-01-15T08:30:00Z"
  }
}
```

#### GET /api/ampds/codes

Retrieves the list of supported AMPDS codes and their mappings in the system.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| protocol_version | string | No | Filter by protocol version (e.g., "v13.0") |

**Response:**

```json
{
  "status": "success",
  "data": {
    "protocol_versions": ["v12.2", "v13.0"],
    "codes": [
      {
        "determinant_code": "10-D-01",
        "description": "Chest Pain - Not breathing at all",
        "incident_type_id": 1,
        "incident_type_name": "Medical Emergency - Critical",
        "priority": "High",
        "protocol_version": "v13.0"
      }
    ]
  }
}
```

### System Status

#### GET /api/system/status

Retrieves the current system status and operational metrics.

**Response:**

```json
{
  "status": "success",
  "data": {
    "system_status": "operational",
    "services": {
      "database": "operational",
      "websocket": "operational",
      "mapping": "operational",
      "ampds": "operational"
    },
    "metrics": {
      "active_incidents": 12,
      "incidents_today": 45,
      "resources_available": 18,
      "resources_assigned": 8,
      "average_response_time_minutes": 8.5
    },
    "server_time": "2023-01-15T12:30:00Z"
  }
}
```

## Webhooks

The CAD System supports webhook notifications for various events. Webhooks can be configured in the Admin panel.

### Event Types

- `incident.created`: Triggered when a new incident is created
- `incident.updated`: Triggered when an incident is updated
- `incident.closed`: Triggered when an incident is closed
- `resource.assigned`: Triggered when a resource is assigned to an incident
- `resource.status_changed`: Triggered when a resource's status changes

### Webhook Payload Example

```json
{
  "event": "incident.created",
  "timestamp": "2023-01-15T08:30:00Z",
  "data": {
    "incident": {
      "id": 1,
      "case_number": "INC-2023-0001",
      "incident_type": {
        "id": 1,
        "name": "Medical Emergency"
      },
      "status": "Active",
      "priority": "High"
    }
  }
}
```

## Error Codes

| Error Code | Description |
|------------|-------------|
| `AUTH_INVALID_KEY` | Invalid API key |
| `AUTH_EXPIRED_KEY` | Expired API key |
| `AUTH_INSUFFICIENT_PERMISSIONS` | Insufficient permissions for this operation |
| `RATE_LIMIT_EXCEEDED` | Rate limit exceeded |
| `RESOURCE_NOT_FOUND` | Requested resource not found |
| `VALIDATION_ERROR` | Input validation failed |
| `INTERNAL_ERROR` | Internal server error |

## Support

For API support, please contact the system administrator or open a support ticket through the CAD System interface.
