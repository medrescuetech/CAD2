---
title: CAD Ecosystem Master Design and External Agency Reference
subtitle: CAD Main, CAD - Event and CAD - Call Taker
author: Alex Gillam
date: 8 August 2026
---

**Document status:** Expanded master design - build-planning baseline  
**Version:** 1.0

## 1. Executive summary

This document defines a three-application Computer-Aided Dispatch (CAD) ecosystem built around one shared operational record. It expands the November 2025 CAD build documentation using the supplied Ambulance Victoria, ESTA, NSW Ambulance, event-CAD, emergency incident coding, special-alert, major-incident, screen-profile and training material.

The ecosystem comprises:

1. **CAD - Call Taker:** the intake application. It receives calls or electronic referrals, captures and validates the initial information, identifies urgency and hazards, checks for possible duplicates and routes the case to CAD Main or an active CAD Event workspace.
2. **CAD - Event:** a dispatch application for a defined event, site or venue. It uses an event-specific location register, response areas, primary and secondary response posts, local units, event terminology and event-specific configuration. An Event case may be escalated or transferred to CAD Main without losing its identity or chronology.
3. **CAD Main:** the principal operational dispatch application. It manages general incidents, resources, multi-unit and major incidents, external-agency notifications, outcomes, closure, search, audit and reporting.

The three applications must use a **shared canonical data model and append-only chronology**. Every operational action must generate a chronology entry: creation, routing, opening, field edit, free-text addition, warning acknowledgement, code or priority change, unit assignment, dispatch, status change, operator handover, application transfer, escalation, deallocation, cancellation, outcome, reopening and closure. A later correction must not erase the original action; it creates a new corrective entry.

Fixed **incident and location GPS coordinates are in scope**. Operators may capture, validate, search, display and report incident latitude/longitude, and imported locations may include coordinates and map references. What remains excluded is live unit/vehicle GPS or AVL tracking, nearest-unit calculation and unit-location telemetry.

![Three-application CAD architecture](../work/architecture.png)

## 2. Design authority and source treatment

The supplied `CAD_System_Documentation_20251112_083352.txt` is the baseline for the prior build. This master design retains its useful concepts - incident creation, unit management, quick notes, live logs, daily logs, role-based access, pickup points, type-ahead locations, real-time synchronisation and PDF export - but replaces the earlier collection of JSON files with a transactional relational model suitable for three interlinked applications.

External-agency documents are used as design references, not as instructions to reproduce a specific agency's confidential workflow or obsolete product. Agency-specific codes and terminology must be configurable. Legacy user-interface details are retained only where they reveal an operational requirement.

### 2.1 Source contribution register

| Source | Primary contribution to this design | Treatment |
|---|---|---|
| CAD System Documentation, 12 Nov 2025 | Existing incident form, units, live log, daily log, permissions, shortcuts, web interface and autosave concepts | Baseline, revised into the shared-core architecture |
| AO2016 CAD BUILD 1 | Event-location import schema, venue identifier, map/grid reference, response areas, primary/secondary responders and active flags | Direct model for Event CAD location packs |
| ESTA-AV Interfaces Specification | Event identifiers, event statuses, event/unit/comment/supplementary-information message domains and reporting feeds | Reference only; useful field concepts retained without implementing legacy interfaces |
| APPENDIX IX CAD and EMD Incident Coding | Configurable medical dispatch-code hierarchy and non-medical incident-code examples | Importable code-set reference, not hard-coded clinical logic |
| Special Priority Patient / Special Situation CAD Alerts | Address validation, scoped alerts, urgent interim alerts, warning acknowledgement, expiry and review | Generalised safety/clinical/location alert subsystem |
| Manage Major Incidents Instructions for CAD | Multi-unit incident isolation, dedicated coordination view/channel, communications chronology and demobilisation | Major-incident workspace requirements |
| NSW Ambulance CAD variables | Master incident and response identifiers, operational timestamps, location, problem, priority and derived performance intervals | Reporting/data-dictionary reference |
| Noggin CAD Data Advice Paper | Read-only real-time operational export, event/unit subject areas and secure downstream integration | Future integration pattern; no live mapping dependency |
| Default CAD Profiles | Standardised screen/workstation views, state-wide visibility, unit/event groupings and role profiles | Configurable role-based layouts and saved views |
| CAD Glossary | Travel codes, resource statuses, event statuses, event types, operational roles and functional centres | Configurable terminology/reference dictionaries |
| CAD Users Guide | Event selection/update, transfers, chronology search, unit history, paging, dispatch warnings, operator changes and locking | Functional and usability requirements |
| CAD 7.9 screen layout | Legacy visual/layout reference | Low evidentiary value; no direct screen replication |
| CAD Training archive | Call-taking, dispatch, business rules, ProQA concepts, audit expectations and operator competency | Workflow and training/acceptance-test reference |

## 3. System boundary and principles

### 3.1 In scope

- Intake, structured information capture and routing.
- General and event-specific incident management.
- Event-specific imported locations and response rules.
- Unit/resource registration, availability and assignment.
- Multiple resources and multiple patients where required.
- Priorities, incident types, dispatch codes and configurable terminology.
- Warnings, alerts and acknowledgement.
- Immutable incident chronology and unit history.
- Operator ownership, transfer and handover.
- Event-to-Main escalation and cross-application transfer.
- Duplicate identification, linking and controlled cancellation as duplicate.
- Major-incident coordination workspace.
- Daily/shift operational log.
- Search, export, audit and operational/management reporting in CAD Main.
- Role-based permissions, application profiles and saved views.
- Import/export interfaces using versioned files or APIs.
- Optional inbound data feeds from PagerMon, weather services and other incident/information sources to be confirmed.
- Fixed incident/location coordinates and incident mapping.
- A Windows desktop application distributed as an EXE plus a secure remote web client.

### 3.2 Explicitly out of scope for this stage

- Live GPS/AVL unit or vehicle tracking.
- Nearest-resource calculation or automated routing.
- Turn-by-turn navigation.
- Direct integration with Triple Zero telephony, radio networks, pagers, ProQA, AMPDS APIs, hospitals or agency production systems unless separately approved.
- Clinical patient-care records or an electronic patient-care record replacement.
- Automated clinical decision-making.
- Billing.

### 3.3 Governing principles

- **One incident, one identity:** an incident is not duplicated merely because it moves between applications.
- **Many responses:** every unit assignment creates a separate response record linked to the incident.
- **Chronology is the audit spine:** current-state tables improve performance, but the chronology proves what happened.
- **Configuration over code:** priorities, statuses, incident codes, outcomes, views and event packs are configurable and versioned.
- **Corrections are additive:** no silent overwrites of operational history.
- **Operator attribution:** every human or system action records the acting identity and workstation/session.
- **Fast keyboard workflow:** tab order and shortcuts are first-class requirements.
- **Safe concurrency:** the system prevents conflicting edits without unnecessarily locking an incident for other viewers.
- **Minimum necessary information:** personal and alert data are visible only to authorised roles.

## 4. Logical architecture

All applications connect to a shared CAD Core through a versioned service layer. They may have different screens and permissions, but they do not maintain independent authoritative copies. The primary operator interface is a Windows desktop program packaged as an EXE. A secure browser-based remote client connects to the same API and provides the same features permitted by the user's role; "remote view" describes the access channel, not a read-only limitation.

### 4.1 Components

| Component | Responsibility |
|---|---|
| Windows desktop EXE | Primary installed client hosting CAD Main, CAD Event and/or Call Taker workspaces according to role |
| Remote web client | Secure browser access to all role-authorised CAD functions, including call taking, dispatch, chronology and reporting |
| CAD - Call Taker workspace | Rapid intake, validation, structured questions, duplicate suggestions, alert presentation and routing |
| CAD - Event workspace | Event work queue, event location picker, event units, assignments, local response rules and escalation |
| CAD Main workspace | General dispatch, broad resource management, major incidents, reporting, administration and audit |
| CAD Core API | Authentication, authorisation, commands, validation, transactions, concurrency and event publication |
| Primary relational database | Canonical operational state and append-only chronology |
| Real-time update service | Pushes authorised changes to connected clients |
| Reporting service | Read-optimised extracts, scheduled reports and data exports |
| Import service | Validates and versions event packs, code sets, units and reference data |
| Inbound feed gateway | Receives PagerMon, weather and other approved feeds; normalises, deduplicates and stages them before CAD action |
| Document service | Produces incident summaries, chronology exports and reports |
| Integration outbox | Reliably queues future outbound messages without coupling operational transactions to external systems |

### 4.2 Recommended implementation direction

The earlier plan used Bootstrap, JavaScript, WebSockets and JSON files. Retain real-time updates and a web interface for remote access, but make the installed Windows EXE the primary operations client and use:

- a supported SQL relational database (PostgreSQL or SQL Server recommended for multi-user deployment; SQLite only for a disposable single-machine prototype);
- a server-side API with transactions and optimistic concurrency;
- WebSocket or server-sent event updates;
- database migrations and seeded reference data;
- an append-only `chronology_entry` table;
- an outbox table for reliable real-time/integration events;
- separate operational and reporting queries.

### 4.3 Desktop EXE and remote web access

The desktop EXE and remote web client must share commands, validation, permissions and chronology behaviour through the same server API. Business rules must not be implemented only in the desktop client.

The Windows EXE should:

- install and update through a controlled signed package;
- provide the dense multi-panel CAD workspace, keyboard shortcuts, multi-monitor layouts and optional local notification sounds;
- cache only minimum non-authoritative UI state such as layout and recent reference lists;
- clearly show server connection, database/API version and degraded state;
- never write directly to the SQL database.

The remote web client should:

- provide all functions authorised for the logged-in role, not merely dashboards;
- use multi-factor authentication where exposed outside the trusted local network;
- enforce TLS, short sessions, device/session audit and configurable network restrictions;
- adapt to laptops and tablets while warning when the viewport is unsuitable for high-intensity dispatch;
- support dispatch, call-taking, escalation, chronology, reporting and administration where permissions allow;
- use the same conflict controls and live-update stream as the EXE.

## 5. Application responsibilities

### 5.1 CAD - Call Taker

Call Taker is designed for uninterrupted, high-speed intake. It must support multiple open intake cards per operator and allow dispatch to commence before all supplementary questioning is finished.

Core functions:

- Create intake from telephone, radio, walk-up, electronic message, scheduled request or another agency.
- Capture received time, answered time, source, caller/contact details, callback number, location, problem, patient/person details where relevant, hazards, other agencies and narrative.
- Toggle between a general address/location search and an active event's controlled venue-location list.
- Display location, person or special-situation alerts with scope and expiry.
- Search for possible duplicate open incidents using location, event workspace, callback number, key narrative terms and time window.
- Assign an initial incident type, problem category, code and priority; allow structured-questioning integration later.
- Save and continue questioning after routing.
- Route to CAD Main or a selected CAD Event workspace.
- Transfer intake ownership between call takers with a reason and acknowledgement.
- Add urgent messages to an already-routed incident.
- Mark abandoned, hoax, information-only, duplicate or cancelled intakes with controlled reasons.

Call Taker must not directly delete an intake or incident.

### 5.2 CAD - Event

Event CAD is an operational workspace instantiated from an event template. It is not a separate data silo.

Core functions:

- Activate an event with name, event code, venue/site, operating dates, timezone, command location, local terminology and responsible agency/provider.
- Import and version event locations, response areas, response posts, units, pickup points, incident types, quick notes and user access.
- Limit normal location selection to active records in the event pack while retaining a conspicuous **Not listed / confirm location** path.
- Show event cases in waiting, assigned, active, held and completed views.
- Recommend or highlight the configured primary and secondary responders for the selected location; recommendations remain advisory and require operator action.
- Assign, dispatch, reassign, deallocate and clear event units.
- Support medical, security, fire, rescue, welfare, lost person, logistics and other configurable event case types.
- Escalate an incident to CAD Main while preserving incident ID, case number, all call data, alerts, assignments and chronology.
- Continue to display an escalated incident in Event CAD as linked/read-only or shared-control according to the escalation mode.
- Produce event operational summaries; organisation-wide reporting remains a CAD Main responsibility.

### 5.3 CAD Main

Core functions:

- Receive routed Call Taker incidents and Event escalations.
- Create incidents directly when authorised.
- Manage general locations, pickup points, external destinations and broad resource pools.
- Manage multiple responses, backup resources, later transport legs and third-party resources.
- Support major-incident views, command roles, staging areas and dedicated communication groups.
- Record agency notifications and requested/acknowledged/arrived times.
- Maintain outcomes, closure validation, reopening and post-closure correction workflows.
- Search incidents, chronology, units, responses, contacts, warnings and audit events.
- Run operational, performance, quality, workload and event reports.
- Administer users, roles, permissions, code sets, statuses, event templates and retention settings.

## 6. End-to-end lifecycle

![Incident lifecycle](../work/lifecycle.png)

### 6.1 Intake and early dispatch

1. Call Taker creates an intake; the system records `intake_created` and the received/answered timestamps.
2. Every committed field change creates a chronology entry with field name and safe before/after representation.
3. The application validates location and presents applicable alerts.
4. Duplicate suggestions are shown but never automatically merge incidents.
5. The call taker selects CAD Main or an active Event workspace and routes the incident.
6. The destination queue receives the incident immediately. The call taker may continue to update information; those entries appear live in the same chronology.
7. An urgent update is visually and audibly distinguished until acknowledged by the destination operator.

### 6.2 Dispatch and response progression

Each unit assignment creates a `response` with its own response ID and timestamps. Recommended progression is configurable but should support:

`ASSIGNED -> ALERTED/DISPATCHED -> ACKNOWLEDGED -> EN_ROUTE -> ARRIVED_SCENE -> DEPARTED_SCENE/LOADED -> ARRIVED_DESTINATION -> CLEAR`

Non-transport and non-medical event workflows may skip irrelevant states. Status transition rules must validate sequence but allow authorised retrospective corrections with reasons.

### 6.3 Escalation from Event to Main

Escalation is a controlled state transition, not copy-and-close:

1. Event operator selects **Escalate to CAD Main**.
2. Operator records reason, urgency, requested ownership model and receiving queue.
3. The system validates that the incident is not already owned by Main.
4. A single transaction creates the routing/escalation record, updates incident ownership and appends chronology entries.
5. CAD Main receives a high-visibility notification containing event context, location, warnings, assignments and latest narrative.
6. A Main operator accepts ownership. Acceptance is timestamped.
7. Existing Event unit responses remain valid. Main may add external/general resources.
8. Event CAD retains visibility. Edit control is either shared or limited by the selected escalation mode.

Escalation modes:

- **Main lead / Event support:** Main owns incident decisions; Event retains local-unit control.
- **Full transfer:** Main owns all operational changes; Event is read-only.
- **Shared major incident:** both applications contribute within role-specific command scopes.

### 6.4 Closure and reopening

Closure requires:

- a controlled incident outcome;
- all responses clear, cancelled, deallocated or explicitly carried forward;
- outstanding urgent messages acknowledged;
- required response timestamps or an authorised missing-data reason;
- open operator transfers resolved;
- closure note and responsible operator.

Closed incidents are immutable in normal edit mode. Reopening creates `incident_reopened`, records reason and authorisation, and retains the original closure entry.

## 7. Canonical identifiers and relationships

| Identifier | Purpose |
|---|---|
| `incident_id` | Immutable globally unique internal identifier |
| `incident_number` | Human-operational reference, configurable display format |
| `intake_id` | A received call/contact; several intakes may relate to one incident |
| `response_id` | One unit/resource response to an incident; many per incident |
| `event_workspace_id` | Active event/site operating context |
| `location_id` | Canonical location or event-pack location |
| `chronology_id` | Immutable ordered audit entry |
| `operator_session_id` | Authenticated user/workstation session |
| `external_reference` | Reference supplied by another agency/system |

Incident numbers should be readable and unique but not carry irreplaceable meaning. Recommended format: `INC-YYYYMMDD-NNNN`, generated server-side using the operational timezone and a daily sequence. Event workspaces may display an alias such as `EVT-AO26-0123`; the internal `incident_id` remains unchanged.

## 8. Chronology and audit design

### 8.1 Non-negotiable chronology rules

- Chronology is append-only.
- Server time is authoritative; client time may be recorded separately.
- Entries use UTC internally and display the relevant operational timezone.
- Each entry records actor, session, application, workstation/client, action type, incident, optional response/unit, correlation ID and structured payload.
- Text changes are logged, including minor narrative amendments.
- Sensitive values are masked in general chronology views but retained in controlled audit data where legally appropriate.
- No chronology entry can be edited or deleted through the application.
- A correction references the entry being corrected.
- Automated actions identify the system actor and initiating human action.

### 8.2 Required action types

At minimum:

- intake created, answered, abandoned, routed, rerouted and linked;
- incident created, viewed in edit mode, saved, held, resumed, escalated, transferred, reopened and closed;
- field added, changed, cleared or corrected;
- narrative, remark, quick note, urgent message and situation report added;
- location selected, changed, unlisted location entered and location validated;
- alert presented, opened, acknowledged, no-match selected and overridden;
- incident type, problem, dispatch code, determinant and priority changed;
- duplicate suggested, linked, merged or cancelled as duplicate;
- unit recommended, assigned, dispatched, acknowledged, status changed, reassigned, deallocated and cleared;
- operator ownership offered, accepted, declined and handed over;
- agency notification requested, sent, acknowledged, arrived or cancelled;
- file/import/export/report created;
- permission/configuration/reference-data change;
- authentication, failed access and elevated action.

### 8.3 Chronology schema

`chronology_entry` should include:

- `id`, `incident_id`, `sequence_no`;
- `occurred_at_utc`, `recorded_at_utc`, `display_timezone`;
- `actor_user_id`, `operator_session_id`, `source_application`;
- `action_type`, `entity_type`, `entity_id`;
- `summary_text` for rapid display;
- `payload_json` for structured before/after values and metadata;
- `severity` (`routine`, `attention`, `urgent`, `warning`, `error`);
- `correlation_id` linking all entries from one transaction;
- `corrects_entry_id` where applicable;
- integrity metadata such as row hash and prior-entry hash if tamper evidence is required.

Location-coordinate changes must record the previous and new latitude/longitude, capture method, accuracy/precision where available, operator/source and reason.

## 9. Core data model

### 9.1 Principal entities

| Entity | Key content |
|---|---|
| Incident | identity, number, owning application/queue, workspace, type, problem, code, priority, status, location, summary, created/closed times |
| Intake | source, caller, callback, received/answered times, operator, raw and structured information, route state |
| Person/Patient | minimal operational identity/contact fields, role in incident, privacy controls |
| Location | name/address hierarchy, event venue, level/aisle/stand, grid/map refs, latitude/longitude, coordinate source/accuracy, aliases, notes, response area, active dates |
| Alert | scope, category, severity, instruction, start/expiry, approval and acknowledgement requirements |
| Unit | call sign/name, type, organisation, capability, home/assigned workspace, availability |
| Crew assignment | people assigned to a unit for a period |
| Response | incident-unit relationship, response role, priority, sequence, statuses/timestamps and outcome |
| Operator assignment | call-taking/dispatch ownership and transfer history |
| Agency involvement | agency, requested action, contact method, status and timestamps |
| Event workspace | event identity, site, dates, status, timezone, command structure and configuration version |
| Code set | incident/problem/determinant/priority/outcome/status definitions with effective dates |
| Chronology entry | immutable action record |
| Daily log entry | shift-wide operational record, optionally linked to incidents/units |
| Attachment | metadata, access classification, hash and link to controlled file storage |

### 9.2 Incident and response separation

The NSW variable reference and legacy CAD training distinguish a master incident from individual unit responses. This design adopts that distinction. A five-unit incident has one incident and five response records. A later transport leg may be another response or leg record; a genuinely separate occurrence must be a new incident linked by a relationship such as `related`, `same_event`, `secondary_incident` or `duplicate_of`.

## 10. Event CAD location packs

### 10.1 AO2016-derived import structure

The Australian Open workbook contains a location register and a grid-to-response mapping. The proposed generalised import schema is:

| Import field | Meaning | Requirement |
|---|---|---|
| `location_name` | Search/display name | Required |
| `location_key` | Stable source key | Required for updates; generate during first import if absent |
| `venue_id` | Event/site identifier such as AO2016 | Required |
| `level` | Floor, level or operational layer | Optional |
| `aisle` | Aisle/section | Optional |
| `stand_or_zone` | Stand, building, arena or zone | Optional |
| `map_reference` | Event map grid/reference | Optional |
| `alternate_reference` | Secondary map or radio reference | Optional |
| `other_details` | Access directions, landmarks or clarification | Optional |
| `response_area` | Operational area/sector | Optional but recommended |
| `primary_responder` | Default primary post/unit group | Optional |
| `secondary_responder` | Default backup post/unit group | Optional |
| `latitude`, `longitude` | Fixed location coordinates for selection, validation, map display and reporting | Optional but recommended where reliably known |
| `active` | Available for selection | Required, defaults true |

The AO grid sheet demonstrates rules in which a map grid resolves to an area and primary/secondary post. Event CAD should model this as a separate `event_response_rule` table rather than spreadsheet formulas.

### 10.2 Import behaviour

- Import into a staging area first.
- Validate headers, required fields, duplicate keys, invalid booleans and broken response-rule references.
- Produce preview counts: create, update, deactivate, unchanged and rejected.
- Do not remove a location referenced by prior incidents; mark it inactive.
- Version each approved import and allow rollback to the prior active configuration without rewriting historical incidents.
- Preserve the exact historical location label and details on each incident while retaining the canonical `location_id`.
- Support aliases and common misspellings.
- Flag placeholder values such as `***`, `Unknown`, `Confirm location` and `Not listed` for operator confirmation.
- Provide one or more intentionally broad fallback locations for each major venue area.

## 11. Incident classification, coding and priorities

### 11.1 Configurable hierarchy

The EMD coding appendix demonstrates a hierarchy of protocol number, complaint, determinant level and suffix (for example, complaint 29 for traffic/transport incidents and determinant descriptors for multiple victims, major incident, hazmat or entrapment). The system must store code sets as versioned reference data rather than embed them in application logic.

Suggested model:

- service domain: medical, fire, rescue, security, welfare, logistics, other;
- incident type;
- problem/chief complaint;
- dispatch code/determinant;
- locally mapped operational priority;
- recommended response profile;
- effective dates and source/version;
- display description and short description;
- flags such as multiple patients, hazard, police required, rescue required or major incident candidate.

### 11.2 Initial reference categories

The supplied medical references collectively cover abdominal pain, allergy/envenomation, animal attack, assault, back pain, breathing problems, burns/explosion, inhalation/hazmat, cardiac arrest/death, chest pain, choking, seizure, diabetic problems, drowning/diving, electrocution, eye injury, falls, headache, cardiac problems, environmental exposure, haemorrhage, machinery incident, overdose/poisoning, pregnancy/childbirth, psychiatric/behavioural/suicide, sick person, penetrating trauma, stroke, transport accident, traumatic injury, unconscious/fainting, unknown problem and interfacility/palliative transfer.

These categories are a reference dataset only. Any implementation of licensed medical dispatch protocols requires separate authority, content licensing, clinical governance and version control.

### 11.3 Priority model

Priority must be configuration-driven. The existing build's High/Medium/Low values are too coarse for interoperability, while legacy agency scales differ. Use:

- an internal ordered `priority_rank` for sorting;
- a configurable display code and label;
- response-mode attributes;
- target-time attributes used for reporting, not silent clinical promises;
- explicit reason and chronology entry for every upgrade/downgrade;
- optional approval rules for downgrade;
- an `urgent_update` flag independent of the overall priority.

## 12. Units, resources and responses

### 12.1 Unit master data

- call sign/display name;
- organisation/provider;
- unit type and capabilities/skill set;
- event workspace or general pool;
- active/inactive status;
- current availability status;
- crew assignment;
- pager/radio/contact identifiers where authorised;
- free-text operational restrictions and expiry;
- home post/base and current manually entered unit location (optional; no live unit GPS tracking).

### 12.2 Configurable unit statuses

The existing build and agency references provide a useful superset:

- available/in service;
- meal break/rest;
- patrol/standby/staging;
- out of service/unavailable;
- assigned/alerted;
- acknowledged;
- en route;
- arrived/on scene;
- on scene but available;
- loaded/departed scene;
- at medical centre/destination;
- returning/return to station;
- clear/in station.

Status codes must be mapped per operating context. A status transition applies to either the unit's overall availability, a specific response, or both; the data model must not confuse them.

### 12.3 Assignment types

- primary response;
- backup/support;
- later transport leg;
- command/supervision;
- staging;
- third-party provider;
- agency liaison;
- event post coverage.

Reassignment must retain the original response/assignment history and record reason. Deallocation returns the incident to the waiting queue only where no other active response remains and business rules allow it.

## 13. Alerts, warnings and special situations

### 13.1 Alert categories

- violence/aggression or scene safety;
- access hazard;
- clinical special requirement;
- infection/contamination;
- manual handling/complex patient;
- dangerous animal;
- environmental or site hazard;
- security restriction;
- event-specific instruction;
- information-only.

### 13.2 Alert scope

An alert must define whether it applies to:

- the exact address;
- a sub-location such as unit, floor, room or tenancy;
- a named person/patient;
- an event location;
- a temporary hazard zone;
- a combination of person and location.

This prevents an alert for one unit or person being incorrectly applied to every attendance at a shared address.

### 13.3 Alert workflow

- urgent interim alert with automatic expiry (the supplied special-situation procedure uses 28 days as an example);
- review/validation state;
- approved longer-term alert with review date;
- source and evidence metadata;
- operational instruction written in neutral, actionable language;
- presentation to Call Taker and dispatchers;
- mandatory open/acknowledge/no-match selection before dispatch where configured;
- acknowledgement and override in chronology;
- expiry, renewal, deactivation and audit.

Alerts must never silently prevent emergency action. They inform risk management and trigger the configured escalation/approval process.

## 14. Duplicate, linked and dependent incidents

Possible duplicate detection uses configurable matching signals and returns candidates with reasons. Operators may:

- keep separate;
- link as related;
- mark as dependent/sub-incident;
- merge intake information into one incident;
- cancel one as duplicate.

Merge requirements:

- preserve both original incident numbers and intake records;
- choose a surviving incident ID;
- move or relink responses only through a controlled transaction;
- append chronology to both incidents;
- never discard narrative, alerts or attachments;
- allow audit users to reconstruct the pre-merge state.

## 15. Major incidents

CAD Main must offer a major-incident workspace that can be activated without moving data to another system.

Required capabilities derived from the major-incident instructions and glossary:

- isolate one incident and its assigned units in a dedicated view;
- establish command roles such as Incident Controller/Commander, communications coordinator and liaison roles;
- define incident area, control point, staging area and functional centres as structured locations;
- establish a dedicated dispatch/coordination group or channel label;
- bulk-transfer selected units to the incident workspace while individually logging each assignment;
- prevent inappropriate recommendation/diversion of committed resources while allowing authorised override;
- record all communications with a source prefix/structured source field;
- create situation reports/wordbacks and escalation/resource requests;
- track pending related calls within the defined area;
- support additional-patient and casualty-count updates;
- demobilise in a controlled sequence, returning units to normal pools and verifying availability;
- retain a complete incident chronology and post-incident export.

## 16. Operator ownership, transfer and concurrency

### 16.1 Operator sessions

Operators must log in under their own account. Session records include login, logout, workstation, application, role profile and timeout. Changing operator requires explicit handover, never continued use of the previous operator's identity.

### 16.2 Ownership transfer

Call and incident ownership can be offered to another operator/queue. The transfer records:

- sender and recipient;
- offered, accepted or declined timestamps;
- reason and handover note;
- outstanding urgent items;
- originating and receiving application/queue.

Until acceptance, the sending operator retains responsibility unless an authorised forced transfer is used.

### 16.3 Concurrent editing

Use optimistic concurrency with a record version. When two users edit the same field, the second save receives a conflict comparison and must refresh, reapply or cancel. Quick notes, chronology entries and distinct response updates may append concurrently. Avoid the legacy behaviour of leaving an entire event locked in update mode.

## 17. User-interface design

### 17.1 Shared interaction pattern

- top bar: application, workspace, connection state, operator, role and clock;
- queue/grid area: waiting, active, held, assigned, closing and completed views;
- active incident area: key identity, location, problem, priority, warnings and ownership;
- unit/resource panel;
- chronology panel;
- clear save state, conflict state and offline/error state;
- keyboard-first field order and shortcuts;
- role-specific saved layouts.

### 17.2 Call Taker layout

Prioritise caller, callback, exact location, problem, hazards, event selection, priority and route controls. Separate caller wording from operator summary. Allow a structured-question panel to run beside the CAD card in a future integration.

### 17.3 Event layout

Prioritise event location search, response area, primary/secondary post recommendation, event units and open event-case grid. Show event name and configuration version prominently to prevent entry into the wrong workspace.

### 17.4 Main layout

Prioritise waiting and assigned queues, broad resource grid, major-incident tabs, warnings, operator assignment and reporting/search access.

### 17.5 Colours and accessibility

Colour reinforces status but never carries meaning alone. Use text labels/icons, keyboard focus, sufficient contrast, scalable text and screen-reader names. Priority, warnings and stale/unacknowledged updates must remain distinguishable for colour-vision deficiencies.

### 17.6 CAD Main visual design instructions

The supplied visual references show several generations of CAD interfaces. Their most valuable common feature is **simultaneous operational visibility**: dispatchers can see demand, resources, the active incident and immediate actions without navigating away. CAD Main should modernise this pattern without reducing the amount of operationally important information visible at once.

#### 17.6.1 Preferred desktop composition

Use a configurable multi-panel desktop designed primarily for 1920 x 1080 or larger displays and capable of spanning two monitors. The default single-monitor arrangement should contain:

- **Application and session bar:** CAD Main identity, operator name/ID, role, session, selected dispatch group, operational date/time, connection state, notifications and active major-incident mode.
- **Incident queue stack:** separate compact grids for new/pending, assigned/active, held/delayed and awaiting closure. Each grid shows only its most decision-relevant columns and displays its item count in the header.
- **Unit status monitor:** a persistent unit grid grouped or filtered by dispatch group, post, unit type, capability or status. It must remain visible while an incident is being edited.
- **Active incident card:** the selected incident's number, type, priority, exact location, caller/person, structured details, warnings, responsible operator and current responses.
- **Chronology/communications panel:** a high-density, scrollable log of calls, remarks, field edits, dispatch actions, unit statuses, agency messages and transfers. It must support quick filtering without hiding the unfiltered audit record.
- **Command strip:** a small set of context-sensitive operational actions positioned close to the incident and unit identifiers.
- **Working-status strip:** a persistent one-line summary of the incident currently in focus, including number, type, location, priority, assigned units and outstanding warning/urgent-message indicators.

The layout should support saved role profiles such as Main Dispatcher, Supervisor, Clinical Reviewer, Major Incident and Read-only Monitor. Panels may be resized, collapsed or moved, but the default profiles must be centrally managed so a user cannot accidentally hide safety-critical information.

#### 17.6.2 Queue and grid design

The dashboard reference demonstrates the value of stacked waiting, active and delayed lists beside the unit monitor. Adopt that information architecture with the following improvements:

- use restrained row heights and fixed headers so a meaningful number of incidents and units remain visible;
- keep incident number, priority, type, location, age/waiting time and assignment state visible without horizontal scrolling;
- allow user-defined secondary columns, but prevent removal of mandatory safety/identity columns;
- use a selected-row border and background in addition to colour;
- allow a queue to expand temporarily over adjacent panels, then return to its saved size;
- display queue ageing and overdue thresholds as text/icon states, not colour alone;
- permit sorting and filtering while clearly showing that a filter is active;
- provide a one-keystroke return to the centrally approved default view;
- preserve selection when live updates reorder a grid, unless the selected record closes or leaves the authorised scope.

#### 17.6.3 Active incident card

The close-up incident examples separate stable case facts from changing operational details. CAD Main should use the same distinction:

- **Identity header:** incident number, status, priority, type, owning queue and event workspace link.
- **Location block:** validated location, access details, response area, pickup/rendezvous point, latitude/longitude, map reference, coordinate source/accuracy and active warnings. An incident map may display the fixed incident location and other fixed reference locations.
- **Caller/person block:** caller, callback, subject/patient and privacy flags appropriate to the operator's permissions.
- **Problem/details block:** structured problem/code plus caller wording and operator summary, visually separated.
- **Response block:** each assigned unit, response role, current status, key timestamps and outstanding message/acknowledgement.
- **Agency block:** requested agencies, current state and timestamps.
- **Chronology block:** newest operational entries visible, with access to the full chronological view.

The compact event-display reference is suitable as a read-only or secondary-monitor view: incident facts on the left and unit history on the right. It should be available as **Incident Status View**, with print/export, but not used as the primary editing form.

#### 17.6.4 Unit monitor

The legacy unit-status references show the operational value of dense, status-coloured unit lists. The modern unit monitor should provide:

- call sign, provider, unit type/capability, crew indicator, current status, assigned incident and elapsed status time;
- configurable groups/tabs for general operations, event workspaces, posts, third-party resources and major incidents;
- clear differentiation between unit availability and response status;
- selection of one or several units for supported bulk actions, with individual chronology entries generated for every affected unit;
- a unit-history drawer showing logon, crew changes, assignments, statuses, incidents and corrections;
- stale-status and missed-acknowledgement indicators;
- no unit-location column implying live vehicle GPS. A manually entered post/staging/current-unit-location label may be shown where operationally maintained.

Black-background status monitors from older systems achieve high contrast but can be visually fatiguing and rely too heavily on colour. The default design should use a neutral light or dark theme with tested contrast and text status labels; an approved dark operations theme may be provided as an alternative.

#### 17.6.5 Command strip and close-up controls

The compact control-panel reference is useful because it places unit and incident identifiers immediately beside frequent commands. CAD Main should implement a modern equivalent as a context-sensitive action strip.

Primary actions should include:

- assign/dispatch;
- acknowledge;
- en route;
- arrive;
- clear;
- unit status;
- add note/remark;
- add response/support;
- reassign or deallocate;
- transfer/escalate;
- hold/resume;
- close/reopen where authorised;
- unit history, incident history and full chronology.

Controls must follow these rules:

- show the selected incident number and unit call sign directly in the strip;
- enable only valid actions for the current state;
- require a reason for destructive, exceptional or retrospective actions;
- place routine progression actions in a consistent left-to-right order;
- avoid a large wall of permanently visible buttons; less-common actions belong in a labelled **More actions** menu;
- support keyboard shortcuts and command search;
- provide immediate success/failure feedback without modal dialogs for routine updates;
- never use ambiguous abbreviations without accessible full labels/tooltips.

#### 17.6.6 Chronology presentation

The chronology should take cues from the references that keep radio/dispatch history continuously visible:

- default to oldest-to-newest for formal reconstruction, with an optional newest-first operational view;
- show time to seconds, action category, actor/source, related unit and concise message;
- visually distinguish urgent messages, warnings, unit progression, field corrections and system errors;
- allow filters for unit, operator, intake, response, agency and action category;
- keep a visible indication when filters are active;
- permit an operator to pin an important entry without changing chronology order;
- expand structured before/after information on demand;
- display corrections beside, and linked to, the original entry;
- support a full-height chronology view and a narrow live-log view.

#### 17.6.7 Incident mapping without unit tracking

The map-focused references remain useful for incident orientation. CAD Main may include an incident map panel that:

- plots the selected incident's fixed latitude/longitude;
- plots fixed venue locations, pickup points, rendezvous points, command posts, staging areas or hazards where configured;
- supports coordinate entry, map-pin correction and conversion between displayed coordinate formats;
- displays map/grid references and access notes;
- opens as a panel, pop-out window or optional second-monitor view;
- never displays live unit icons, nearest-unit suggestions, route lines or unit telemetry;
- makes the difference between an incident coordinate and any manually entered unit/post location explicit.

The default layout may replace or collapse the map when chronology or unit visibility is more valuable. Mapping must not be required to create or dispatch an incident.

#### 17.6.8 Visual density, themes and screen behaviour

CAD is a specialist operational tool, so normal consumer-app whitespace rules should not make it sparse. Aim for high information density with disciplined hierarchy:

- 12-14 px grid text at standard desktop scaling, with an accessible larger-density mode;
- compact but not clipped row heights;
- stable column alignment and tabular numerals for times;
- muted panel chrome, reserving strong colours for priority, warnings and exceptional states;
- no gradients, decorative imagery or animation unrelated to state change;
- resizable split panes with minimum safe sizes;
- full-screen and multi-monitor profiles;
- pop-out Incident Status View and Unit History View;
- clear focus indication and predictable tab order;
- no automatic pop-up that steals keyboard focus while the operator is entering a call.

#### 17.6.9 Design options to prototype

Prototype and usability-test three CAD Main arrangements before committing:

1. **Queue-led dashboard:** stacked incident queues on the left, unit monitor on the right, active incident and chronology in a lower drawer. Best for broad workload monitoring.
2. **Incident-led workstation:** active incident and chronology dominate the centre, with narrower queues and unit monitor on either side. Best for complex incident coordination.
3. **Dual-monitor operations profile:** monitor one contains queues and unit status; monitor two contains the active incident, responses, chronology and command strip. This is the preferred supervisor/major-incident arrangement.

Testing must measure time to recognise a new case, select the correct incident, identify available units, dispatch, record an urgent update, transfer ownership, reconstruct the last five actions and recover from an unintended filter or layout change.

## 18. Daily log

Retain the earlier daily-log concept but store entries in the database. Categories may include general, radio message, security, emergency, traffic, patrol, medical, administrative, report and incident.

Each entry records timestamp, operator, category, text and optional incident/unit/workspace link. Entries are append-only; corrections reference earlier entries. Logs are grouped by operational day and workspace, searchable and exportable.

## 19. Reporting in CAD Main

### 19.1 Source fields

The reporting model should expose:

- incident, intake and response identifiers;
- event workspace and external references;
- received, answered, created, routed, assigned, dispatched, acknowledged, en-route, scene-arrival, scene-departure, destination-arrival, clear and closed timestamps;
- incident location and response area;
- problem, type, code, priority and priority history;
- unit type, provider and response role;
- outcome, cancellation and closure reasons;
- alert and agency-notification indicators;
- operator/queue handling data;
- data-quality flags and corrections.

### 19.2 Derived intervals

Calculate rather than store as authoritative facts:

- call-processing time;
- route/queue delay;
- assignment delay;
- turnout time (assignment to en route);
- travel time (en route to scene);
- response time (defined start point to first appropriate arrival);
- scene time;
- transport time;
- destination turnaround/off-stretcher interval where captured;
- unit cycle time;
- incident cycle time;
- call-taker and dispatcher workload measures.

Every report must state its exact timestamp definitions and treatment of missing/corrected values.

### 19.3 Initial reports

- live operational snapshot;
- incidents by date, event, type, problem, priority and outcome;
- response counts and unit workload;
- response-time distribution and percentile reports;
- call-processing and dispatch-delay report;
- event workload by location/response area;
- cancellations, duplicates, deallocations and reopenings;
- priority upgrades/downgrades;
- alert acknowledgements and overrides;
- agency notifications;
- missing/invalid timestamp and data-quality report;
- operator transfer and ownership report;
- full incident chronology and unit history;
- daily/shift log export.

## 20. Interfaces and messages

The ESTA interface workbook demonstrates that event, unit, supplementary information, comments, hospital diversion and incident data often arrive as distinct message types. The new system should expose a consistent envelope:

- message ID and type;
- schema version;
- occurred and published timestamps;
- source system/application;
- actor/correlation ID;
- entity ID and incident ID where relevant;
- payload;
- security classification;
- retry/idempotency key.

### 20.1 Optional inbound feeds

An inbound feed must never bypass intake validation or silently create an operational incident. Each connector writes to a staged `feed_item` record and applies a configurable rule:

- information only;
- suggest a new Call Taker intake;
- automatically create an unverified intake in a nominated queue;
- attach an update to a matched incident;
- raise a notification/alert;
- update a reference condition such as weather.

Initial connector candidates are:

- **PagerMon:** pager/POCSAG messages received by webhook, polling or supported message forwarding; map sender/channel/capcode and message patterns to source profiles;
- **weather:** current observations, warnings and forecasts for configured sites/event workspaces;
- **other incident feeds:** agency alerts, site alarms, security systems, public-event systems or incident-management platforms, subject to later confirmation;
- **manual/API import:** authorised JSON, CSV or webhook submission for testing and low-volume partners.

Every feed item records source, source message ID, received time, source time, raw payload hash, parsed content, processing status, matched incident and operator/system action. Connectors require schema validation, authentication, rate limits, idempotency, duplicate suppression, quarantine for malformed data and a visible health state. Raw source content is retained according to configured privacy and retention rules.

Initial domain events:

- `IntakeCreated`, `IntakeUpdated`, `IncidentRouted`;
- `IncidentCreated`, `IncidentUpdated`, `PriorityChanged`, `IncidentEscalated`, `IncidentClosed`;
- `ResponseCreated`, `UnitAssigned`, `UnitStatusChanged`, `ResponseCleared`;
- `ChronologyAdded`, `UrgentMessageAdded`, `AlertAcknowledged`;
- `OperatorTransferOffered`, `OperatorTransferAccepted`;
- `EventPackActivated`, `ReferenceDataChanged`.

The Noggin reference supports a future read-only external operational feed. Implement it through the outbox/reporting layer, not direct database access. Incident KML/map output may be supported using fixed incident/location coordinates; it must not imply unit tracking.

## 21. Security and privacy

- Role-based access with least privilege.
- Separate permissions for view, create, update, dispatch, close, reopen, correct, report, export, administer and audit.
- Application/workspace scoping for Event CAD.
- Strong authentication and secure session timeout.
- Encryption in transit and at rest.
- CSRF protection, input validation and output encoding.
- Sensitive alert/person fields segregated from general operational narrative.
- Audit of access to sensitive alerts and exports.
- No hard-coded API keys; the placeholder AMPDS key in the prior plan must be removed.
- Configurable retention and legal hold.
- Backup, tested restore and disaster-recovery procedures.

### 21.1 Suggested roles

- Call Taker;
- Event Dispatcher;
- Main Dispatcher;
- Supervisor/Duty Manager;
- Clinical/Operational Reviewer;
- Event Administrator;
- System Administrator;
- Report Analyst;
- Audit/Read Only.

## 22. Reliability and operational behaviour

- All commands are transactional.
- Autosave must not create noisy duplicate chronology entries; coalesce uncommitted keystrokes and log the committed text update.
- Critical commands return explicit success/failure and remain retry-safe.
- Real-time update failure shows a prominent degraded-state banner.
- Clients reconnect and replay missed updates from a sequence cursor.
- Offline creation is not supported initially unless a separate conflict-safe design is approved.
- Database backups and restoration are tested.
- System health, queue lag, errors, failed logins and integration retries are monitored.
- Operational data remain usable when the reporting service is unavailable.

## 23. Migration from the November 2025 build

| Existing concept | Target treatment |
|---|---|
| `incidents.json` | Migrate to incident/intake/response relational tables |
| `units.json` | Unit master and unit-status history |
| `users.json` | Managed identity/role records; passwords never migrated as plain values |
| `pickup_points.json` | General/event locations and pickup-point types |
| `daily_logs.json` or text logs | Daily log entries with operator attribution |
| AMPDS category/subcategory JSON | Versioned external code-set import, subject to licensing/governance |
| medical assessments JSON | Separate structured assessment/intake module; not chronology-only text |
| locations JSON | Canonical locations plus aliases and event-pack versions |
| 30-second autosave | Shorter debounced save with server versioning and deliberate chronology coalescing |
| closed incidents non-editable | Retain; use controlled reopen/correction workflow |
| WebSockets | Retain for authorised real-time updates |
| PDF export | Retain and extend to chronology and formal incident summary |

## 24. Build sequence

### Phase 1 - Shared core and Main minimum viable product

- Authentication, roles and sessions.
- Relational schema, migrations and reference data.
- Windows desktop EXE shell, signed packaging and connection management.
- Secure remote web client foundation using the same API.
- Incident, intake, unit, response and chronology APIs.
- Main waiting/active queues, incident card, assignment and status progression.
- Search, daily log and basic incident/chronology export.
- Fixed incident coordinates and basic incident map; no live unit GPS/AVL.

### Phase 2 - Call Taker

- Rapid intake card and keyboard flow.
- Routing, ownership transfer and urgent updates.
- Location/alert presentation.
- Duplicate suggestions and controlled linking.
- Concurrent call-taking and dispatch updates.

### Phase 3 - Event CAD

- Event workspace lifecycle.
- Location-pack import/validation/versioning.
- Response-area and primary/secondary responder rules.
- Event queues, units and local configuration.
- Event-to-Main escalation and shared visibility.

### Phase 4 - Reporting and operational maturity

- Reporting warehouse/views and data-quality reporting.
- Major-incident workspace.
- Advanced audit, alert governance and saved layouts.
- Supported imports/exports and integration outbox.
- PagerMon proof-of-concept connector and generic inbound-feed gateway.
- Weather feed for configured sites/workspaces, subject to provider selection.

### Phase 5 - Optional future capabilities

- Approved medical-dispatch integration.
- Pager/radio/telephony integration.
- External incident-management feed.
- Expanded mapping and, only after a separate design review, live unit GPS/AVL.

## 25. Acceptance criteria

The first production-capable release must demonstrate:

1. One incident can be created in Call Taker, routed to Event, escalated to Main and closed without changing internal identity or losing chronology.
2. Every field update, narrative update, unit action and operator transfer appears once in chronological order with actor and timestamp.
3. Two users can add distinct updates concurrently; conflicting edits are detected and never silently overwrite.
4. An AO-style location pack can be staged, validated, previewed, activated and versioned.
5. A location resolves to event response area and suggested primary/secondary responders.
6. A Not Listed/Confirm Location path is available and conspicuous.
7. Multiple unit responses have independent IDs, statuses and timestamps.
8. Alerts are correctly scoped, displayed and acknowledged, including no-match/override.
9. Closed incidents cannot be normally edited; authorised correction/reopen remains auditable.
10. CAD Main reports use documented timestamp definitions and identify missing data.
11. Role restrictions prevent unauthorised viewing, dispatch, export, correction and administration.
12. Incident latitude/longitude can be captured, changed with audit, displayed and reported while the system operates without live unit GPS/AVL.
13. The Windows EXE and remote web client apply identical permissions, validation and chronology rules.
14. A test inbound PagerMon-style message can be staged, deduplicated, reviewed and routed without bypassing operator control.

## 26. Decisions confirmed by this master design

- Three user-facing applications, one shared CAD Core.
- CAD Main is the principal system and reporting authority.
- CAD Event uses controlled, versioned location packs and operates within a defined site/event.
- CAD Call Taker routes incidents to Main or Event and may continue adding information after routing.
- Event incidents can escalate to Main without copying or losing identity.
- Every operational action is chronologised.
- Incident and response records are separate.
- External-agency codes, statuses and terminology are configurable references.
- Fixed incident/location GPS coordinates and incident maps are in scope; live unit/vehicle GPS/AVL is not.
- The production design uses an SQL database, a primary Windows EXE and a secure full-feature remote web client.
- Optional PagerMon, weather and other inbound feeds use a staged, auditable feed gateway.

## 27. Open design decisions before implementation

- Preferred server technology and supported deployment platform.
- PostgreSQL production deployment versus a smaller prototype path.
- Exact incident-number display formats for Main and Event.
- Which roles may share edit control after Event-to-Main escalation.
- Local priority scale and response modes.
- Initial unit/status/outcome dictionaries.
- Whether Call Taker includes structured medical questioning in the first release or only an integration boundary.
- Exact retention periods and privacy classification.
- Whether event packs are Excel, CSV or both; a canonical CSV template is recommended.
- Reporting output formats and scheduled distribution.
- High-availability and disaster-recovery targets.

## Appendix A - Recommended controlled dictionaries

Maintain versioned dictionaries for incident types, problem categories, dispatch codes, priorities, incident statuses, unit statuses, response roles, response outcomes, cancellation reasons, closure outcomes, agency types, alert categories, alert severities, location types, response areas, unit types, capabilities, daily-log types and chronology action types.

## Appendix B - Example incident statuses

`NEW`, `PENDING`, `HELD`, `ASSIGNED`, `ACTIVE`, `AWAITING_CLOSURE`, `CLOSED`, `CANCELLED`, `DUPLICATE_CANCELLED` and `SCHEDULED` provide a practical starting set based on the prior build and interface references. Statuses such as `BROADCAST_HELD`, `STATION_ALERT` or `DEPENDENT` should be enabled only when the operating model needs them.

## Appendix C - Example outcomes

Configurable outcomes may include transported, treated/not transported, service not required before arrival, response not required after arrival, patient/person not found, referred, resolved on scene, handed to another agency, false alarm, cancelled, duplicate, information only and other. Legacy acronyms may be mapped for import but should not be the only displayed explanation.

## Appendix D - Source caveats

- Several agency documents are legacy material and may no longer represent current policy or production systems.
- Some references describe licensed clinical-dispatch products or agency-specific codes. Their inclusion here defines a data/configuration capability, not permission to reproduce proprietary content.
- The ESTA interface workbook contains useful data-domain examples but is not required for the initial three-application build.
- The CAD 7.9 layout file provided little extractable textual content; it is treated only as a visual legacy reference.
- Fixed incident/location latitude and longitude are operational fields and may be mapped. No live unit GPS/AVL, automatic routing or nearest-unit function is authorised by this design.
