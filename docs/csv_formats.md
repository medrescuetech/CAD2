# CSV Import/Export Format Documentation

All CSV files must follow these general rules:
1. First row contains column headers (will be skipped during import)
2. All text values should be in UTF-8 encoding
3. Empty cells should be left blank, not filled with spaces or special characters
4. Boolean values should be 'true' or 'false' (case insensitive)

## Locations CSV Format
```csv
latitude,longitude,name
-20.7256,116.8464,Port Hedland
-31.9523,115.8613,Perth
```
- **latitude**: Decimal number between -90 and 90 (up to 10 decimal places)
- **longitude**: Decimal number between -180 and 180 (up to 10 decimal places)
- **name**: Text value for the location name (can include numbers)

## Users CSV Format
```csv
username,email,first_name,last_name,role,active
jsmith,john.smith@example.com,John,Smith,user,true
awhite,alice.white@example.com,Alice,White,admin,true
```
- **username**: Unique identifier for the user (alphanumeric)
- **email**: Valid email address
- **first_name**: User's first name
- **last_name**: User's last name
- **role**: Either 'admin' or 'user' (case insensitive)
- **active**: Boolean (true/false)

Note: 
1. When importing users, a default password 'cadsystem' will be set and must be changed on first login.
2. Role permissions are managed separately through the roles system in the admin interface.
3. Setting a user as 'admin' grants them access to the admin interface and all associated permissions.

## Units CSV Format

The following fields are required for unit imports:

- **unit_number**: Unique identifier for the unit (alphanumeric)
- **unit_type**: One of:
  - paramedic
  - critical care
  - fast attack
  - tanker
  - pumper
  - buggy
  - bike
- **station**: Station or base location of the unit
- **status**: Current status (available, dispatched, enroute, onscene, returning)
- **active**: Boolean (true/false)

Example:
```csv
unit_number,unit_type,station,status,active
PARA1,paramedic,Station 1,available,true
CC1,critical care,Station 2,available,true
FA1,fast attack,Station 3,available,true
TANK1,tanker,Station 4,available,true
PUMP1,pumper,Station 5,available,true
BUG1,buggy,Station 6,available,true
BIKE1,bike,Station 7,available,true
```

## AMPDS CSV Format
```csv
unique_id,category,card_number,priority,subcategory,dispatch_advice,prearrival_pdf
1,Abdominal Pain,A01,1,Severe Pain,Dispatch ALS,A01.pdf
2,Allergies,A02,2,Mild Reaction,Dispatch BLS,A02.pdf
```
- **unique_id**: Unique identifier (not shown in UI)
- **category**: Primary complaint category
- **card_number**: Protocol card reference
- **priority**: Response priority level
- **subcategory**: Specific condition subcategory
- **dispatch_advice**: Recommended response
- **prearrival_pdf**: Filename of pre-arrival instructions PDF

## Error Handling
During import:
1. Invalid rows will be skipped and logged
2. Valid rows will still be processed
3. A summary of successful imports and errors will be provided
4. Database transactions ensure all-or-nothing updates

## Export Format
Exports will follow the same format as imports, including the header row. All fields will be properly escaped and quoted as needed.
