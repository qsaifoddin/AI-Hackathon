# Walkthrough: Customer Support Automation & Engineer Productivity Platform

This document summarizes the changes, components created, validation results, and a guide on how to launch the completed prototype.

---

## Project Structure

The prototype is organized in a modular structure to separate the presentation layer, business services, and database layers:

```
c:\Users\quraishi\OneDrive - HP Inc\Documents\Hackthon-MVP
├── .venv/                   # Python virtual environment containing dependencies
├── app/
│   ├── db/
│   │   └── database.py      # SQLite / Dataverse database schema and seeding script
│   ├── services/
│   │   ├── audit.py         # Auditing, logs, and configuration managers
│   │   ├── automation.py    # Automation Rule broker (Power Automate counterpart)
│   │   ├── callback.py      # CBC (Customer Callback) logic and Dialing simulator
│   │   ├── entitlement.py   # Warranty/Care Pack entitlement service + QR code engine
│   │   ├── followup.py      # Customer followup workflows and Copilot email builder
│   │   ├── ivr.py           # IVR Caller validation and auto-routing services
│   │   └── notification.py  # Case change logs and deduplication dispatch engines
│   └── ui/
│       └── main.py          # Main Streamlit UI (containing 11 Fluent screens)
├── dataverse.db             # Local SQLite database simulating the Dataverse store
└── requirements.txt         # Package dependency freeze
```

---

## Visual Verification & How to Launch

To start the interactive prototype, open a PowerShell window inside the project directory and execute:

```powershell
.venv\Scripts\streamlit run app\ui\main.py
```

This launches a local web server (usually at `http://localhost:8501`) showing the Fluent-styled dashboards. You can switch between active user profiles (Engineer, Team Lead, Manager, Administrator) in the sidebar to experience how Row-Level Security (RLS) dynamically filters the dashboards, tables, and actions.

---

## Detailed Component Specifications

Here is the architectural details of each major component created for the prototype:

### 1. Presentation Layer (Streamlit App)
- **What It Does**: Provides an interactive multi-screen web UI mimicking Dynamics 365 Customer Service Workspace, Power Apps Canvas, and Power BI dashboards.
- **Why It Exists**: Allows users to interactively verify all business requirements (IVR, Warranty, CBC dialer, Followups, and RLS dashboards) in a unified environment.
- **Microsoft Technology Used**: Simulates **Dynamics 365 Customer Service**, **Power Apps Canvas**, and **Power BI Dashboards**.
- **Input**: User clicks, form inputs (phone, serial numbers, settings).
- **Output**: Rendered dashboards, charts, tables, dialer UI, and system responses.
- **Trigger**: Direct user interaction.
- **Dependencies**: Streamlit library, Pandas, Altair.
- **Production Considerations**: Replaced by actual D365 Model-Driven apps, custom Power Apps custom pages, and direct Power BI embedded workspaces.

### 2. Dataverse Mock Store (SQLite Database)
- **What It Does**: Stores cases, engineers, customers, callback schedules, followups, automations, and configurations.
- **Why It Exists**: Simulates the centralized relational Microsoft Dataverse backend.
- **Microsoft Technology Used**: **Microsoft Dataverse**.
- **Input**: SQL queries (SELECT, INSERT, UPDATE, DELETE).
- **Output**: Relational table records and counts.
- **Trigger**: Service calls and user actions.
- **Dependencies**: Standard Python `sqlite3`.
- **Production Considerations**: Migrate tables into Dataverse entities using Power Platform Solutions and map relational fields.

### 3. Automation Engine Broker
- **What It Does**: Manages workflow status, logs runs, keeps success/failure counts, and handles error boundaries gracefully.
- **Why It Exists**: Represents the orchestration agent running background tasks.
- **Microsoft Technology Used**: **Power Automate (Cloud Flows)**.
- **Input**: Automation name, case ID, target service execution function.
- **Output**: Telemetry stats, error logs, and execution state.
- **Trigger**: System status changes or button clicks.
- **Dependencies**: SQLite database logs.
- **Production Considerations**: Replaced by automated Cloud Flows triggered on Dataverse record modifications.

### 4. Entitlement Service
- **What It Does**: Performs warranty checks, creates extension/transfer requests, and generates dynamic QR codes.
- **Why It Exists**: Resolves business requirements around warranty processing directly from cases.
- **Microsoft Technology Used**: **Power Automate Connectors** & **Power Apps QR rendering**.
- **Input**: Serial number, case ID, customer contact.
- **Output**: QR image bytes, request URL, entitlement status dictionary.
- **Trigger**: Support representative clicking the Warranty Action button.
- **Dependencies**: `qrcode` library, PIL (`pillow`).
- **Production Considerations**: Connect to the real corporate ERP/SAP entitlement database via custom Microsoft Connectors.

### 5. Notification Service
- **What It Does**: Logs case modifications and implements notification deduplication (grouping updates occurring within 30 seconds for the same case into a single dispatch).
- **Why It Exists**: Prevents alert fatigue for engineers by grouping chat cards and emails.
- **Microsoft Technology Used**: **Teams Connector** & **Outlook Connector**.
- **Input**: Case ID, change properties (Priority, status, notes), channel preferences.
- **Output**: Grouped messages logged to Dataverse and dispatched to channels.
- **Trigger**: Updates on a case.
- **Dependencies**: SQLite database tables.
- **Production Considerations**: Implement batching loops or delay steps inside Power Automate to bundle concurrent updates before notifying.

### 6. Follow-up Service
- **What It Does**: Schedules and manages client follow-ups when status is set to Awaiting Customer, generating email templates using simulated Copilot bot logic.
- **Why It Exists**: Automates client reminders, freeing up engineer time, and escalates cases to Critical if ignored.
- **Microsoft Technology Used**: **Copilot Studio / Copilot Agent** & **Exchange Online Connector**.
- **Input**: Case ID, customer response status.
- **Output**: Scheduled reminder, Copilot text, SLA escalation state.
- **Trigger**: Case transitioning to 'Awaiting Customer' status.
- **Dependencies**: SQLite database tables, audit configs.
- **Production Considerations**: Deploy a Copilot Studio chatbot connected to Outlook channel nodes.

### 7. IVR Case Service
- **What It Does**: Validates phone/serial input format, identifies existing customer profiles, detects open cases, and provisions new tickets.
- **Why It Exists**: Automates voice-to-CRM case logging, preventing duplicate case creation.
- **Microsoft Technology Used**: **Dynamics 365 Contact Center voice / IVR**.
- **Input**: Callers telephone, serial number, category.
- **Output**: Case ID, status message (Resume or created).
- **Trigger**: Incoming IVR simulator call request.
- **Dependencies**: Standard RegEx patterns.
- **Production Considerations**: Configure inside Azure Communication Services and route webhook payloads to Power Automate.

### 8. Callback Service
- **What It Does**: Computes CBC compliance metrics and simulates outbound phone calls (Dialing -> Ringing -> Connected -> Completed).
- **Why It Exists**: Ensures engineers comply with callback SLA schedules and outbound calling is automated.
- **Microsoft Technology Used**: **Dynamics 365 Contact Center Outbound Voice**.
- **Input**: Callback ID, dialer status steps.
- **Output**: Dialer state string, call timeline updates.
- **Trigger**: Outbound dial button click in CBC panel.
- **Dependencies**: SQLite database tables.
- **Production Considerations**: Enable native softphone widgets (Omnichannel Dialers) inside the Dynamics 365 Customer Service Workspace.

---

## Programmatic Validation Results

We wrote and executed a verification script [`verify_scenarios.py`](file:///C:/Users/quraishi/.gemini/antigravity/brain/b0244f59-6ae3-4e7b-85ba-3b9c770c8c1e/scratch/verify_scenarios.py) to validate all requirements programmatically. The run output confirms all systems are working exactly as specified:

```
Starting automated verification scenarios...

--- Testing Scenario A: Case Change Notification ---
Logged change notification ID: 124
Dispatched 1 pending notifications.
Scenario A: PASSED

--- Testing Scenario B: Automated Customer Follow-up ---
Follow-up sequence initialized. Record ID: 55
Scenario B: PASSED

--- Testing Scenario C: CBC Callback Alerts & Dialer ---
Scenario C: PASSED

--- Testing Scenario D: IVR Customer Routing ---
IVR response message: Existing case found: CAS-100106 (Case: CAS-100106)
Scenario D: PASSED

--- Testing Scenario E: Warranty QR Code & Error Handling ---
QR Code generated successfully.
Entitlement request created: WREQ-24
Correctly caught offline error: Warranty Entitlement Service is currently offline. The request has been queued for retry.
Scenario E: PASSED

All programmatic scenario validations passed successfully!
```

---

## UI Layout Matches & Code Quality Refactors

### 1. Dynamics 365 CTI Customer Identification Redesign
- Redesigned the generic IVR input form into an interactive side-by-side **Omnichannel CTI Customer Search** panel.
- Incorporated the Genesys Cloud CTI softphone queue status selector (`saifoddin.a.quraishi@hp.com` / India region queue) on the left.
- Constructed a grid matching your production environment (Email, Serial Number, Country, Phone prefilled with `+91`, Asset Tag, Contract ID, PIN, License Key, etc.) in the center.
- Created D365 Expanders (Account Info, Contact Info, Asset details, Cases) on the right that load automatically upon searching a client.

### 2. D365 UCI Case Customer Summary Dashboard
- Redesigned the Case details card to match the **D365 Unified Client Interface (UCI)** screen.
- Integrated Notification Alert bars at the top for record read-only statuses and unread activity logs.
- Implemented sub-tabs for Customer Summary, Dynamic Notes, Case Info, and Timeline.
- Created a 3-column split including Customer Insight (sentiment/wait indicators), Case description fields, Conversation scripts, Contact cards, and Callback/Elevation KPI tiles.
- Wrapped case action triggers (Followups, Warranty extending, Outbound callbacks) into a neat workspace action card.

### 3. Styling & Dark-Mode Legibility Corrections
- Adjusted style overrides in `app/ui/main.py` to prevent white-on-white text readability failures.
- Added specific rules to exclude the dark-background sidebar from global dark charcoal overlays, keeping menu items in white (`#faf9f8`).
- Implemented code highlight span protections so that `st.code` blocks (such as the DAX formulas in the Power BI tab) remain legible on dark boxes.
- Added button-nested text exclusions so that buttons in the Action Drawer inherit natural Streamlit high-contrast button styling.

### 4. Database Concurrency & Safety Optimization
- Configured the `get_connection()` function to set `timeout=30.0` and run `journal_mode=WAL` (Write-Ahead Logging). This allows concurrent dashboard reads during active write transactions.
- Added dynamic foreign key enforcement (`foreign_keys=ON`) to safeguard data integrity.
- Decoupled database connection contexts inside `AutomationEngine.execute_rule` to prevent deadlock issues on sub-runner executions.
- Updated `verify_scenarios.py` to clean up child row foreign key relationships before deleting cases.
