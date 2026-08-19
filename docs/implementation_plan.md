# Implementation Plan - Customer Support Automation & Engineer Productivity Platform

This plan outlines the architecture, data model, and implementation steps to build the enterprise-grade prototype. The solution simulates a Microsoft-native stack (Dynamics 365, Dataverse, Power Apps, Power Automate, Power BI, Teams, Outlook, and Contact Center voice).

We will implement this prototype as an interactive **Streamlit web application** running on a mock **SQLite database** (representing Microsoft Dataverse). This lets us build an interactive, data-driven prototype with working screens, real-time logging, and dynamic security role filtering.

---

## Solution Architecture & Design

```mermaid
graph TD
    subgraph UI Layer (Power Apps / Power BI / D365 Simulator)
        ED[Executive Dashboard]
        EngD[Engineer Dashboard]
        CD[Case Details & Actions]
        WC[Warranty & Care Pack Screen]
        CBCC[CBC Callback Center]
        FC[Follow-up Center]
        IVR[IVR Phone Simulator]
        AC[Automation Control Center]
        ADMIN[Admin Settings & Audit Log]
    end

    subgraph Security Layer
        Identity[User & Role Switcher: Engineer, Team Lead, Manager, Admin]
        RLS[Row-Level Security Filter]
    end

    subgraph Service & Automation Layer (Power Automate Mock)
        AE[Automation Engine]
        NS[Case Change Notifications]
        FS[Automated Customer Follow-up]
        CS[CBC Call Service & Dialer]
        ES[Entitlement Service]
        IS[IVR Case Creation Service]
    end

    subgraph Data Layer (Dataverse Mock)
        DB[(SQLite / Dataverse Tables)]
    end

    %% Routing
    Identity --> RLS
    RLS --> UI_Data[Filtered Views]
    ED & EngD & CD & WC & CBCC & FC & IVR & AC & ADMIN --> UI_Data
    UI_Data <--> AE
    AE <--> DB
    NS & FS & CS & ES & IS <--> DB
```

---

## Data Model (Dataverse Mock)

We will create the following logical entities in a SQLite database:

| Entity Name | Description | Key Fields |
| :--- | :--- | :--- |
| **Case** | Core ticket entity | `CaseID`, `CaseNumber`, `CustomerID`, `SerialNumber`, `ProductNumber`, `EngineerID`, `QueueID`, `Status` (New, Active, Awaiting Customer, Resolved, Closed), `Priority` (Critical, High, Normal, Low), `ATS`, `CRT`, `WarrantyStatus`, `QuoteStatus`, `AwaitingCustomer`, `L2Pending`, `CBCDateTime`, `Source` (Web, Email, Portal, IVR) |
| **Customer** | Account/Contact information | `CustomerID`, `Name`, `Phone`, `Email`, `PreferredLanguage` |
| **Engineer** | D365 users | `EngineerID`, `Name`, `Email`, `TeamID`, `Role` (Engineer, Team Lead, Manager, Admin) |
| **WarrantyRequest** | Extension/transfer tracking | `RequestID`, `CaseID`, `SerialNumber`, `ProductNumber`, `CustomerID`, `RequestType` (Warranty Extension, Care Pack Extension, Warranty Transfer, Care Pack Transfer), `CurrentStatus`, `RequestedAction`, `RequestDate`, `RequestStatus` (New, Submitted, Under Review, Approved, Rejected, Completed), `QRCodeURL` |
| **CaseChangeNotification** | Notification audit and queue | `NotificationID`, `CaseID`, `EngineerID`, `ChangeType` (ATS_CHANGED, STATUS_CHANGED, etc.), `PreviousValue`, `NewValue`, `NotificationChannel` (Teams, Outlook, In-App), `NotificationStatus` (Pending, Sent), `SentDateTime` |
| **CaseFollowup** | Automation follow-up records | `FollowupID`, `CaseID`, `CaseNumber`, `CustomerID`, `EngineerID`, `FollowupNumber`, `ScheduledDateTime`, `SentDateTime`, `ResponseReceived` (Yes/No), `Status` (Scheduled, Sent, Customer Responded, No Response, Escalated, Cancelled) |
| **Callback** | CBC (Customer Callback) records | `CallbackID`, `CaseID`, `CaseNumber`, `CustomerID`, `EngineerID`, `CallbackDateTime`, `ReminderDateTime`, `Status` (Scheduled, Completed, Missed, Call Initiated), `ActualCallbackDateTime` |
| **Automation** | Automation rule configurations | `AutomationID`, `Name`, `Description`, `Trigger`, `Condition`, `Action`, `Status` (Enabled/Disabled), `LastRun`, `SuccessCount`, `FailCount`, `ErrorMessage` |
| **AuditLog** | Comprehensive system audits | `LogID`, `Timestamp`, `User`, `Automation`, `CaseID`, `Action`, `OldValue`, `NewValue`, `Result`, `Error` |
| **Configuration** | Settings for the system | `ConfigKey`, `ConfigValue`, `Description` |

---

## Power BI Data Model (Star Schema representation)

The prototype will include a "Power BI Analytics" tab showing a visual layout of the Star Schema along with actual working charts generated from the SQLite dataset.

- **Fact Tables**:
  - `FactCases` (Case details, SLA, resolution times)
  - `FactCallbacks` (Callbacks scheduled, delays, SLA compliance)
  - `FactFollowups` (Follow-up counts, response times)
  - `FactNotifications` (Notification volumes, channels, delivery latency)
- **Dimension Tables**:
  - `DimEngineer` (Profile, Team, Role)
  - `DimCustomer` (Name, Location, Language)
  - `DimDate` (Calendar dates, DayOfWeek, Month)
  - `DimQueue` (D365 Queue assignments)
  - `DimIssueCategory` (Product categories)
- **Calculated Measures**:
  - `Open Cases = COUNTROWS(FILTER(FactCases, FactCases[Status] <> "Closed"))`
  - `SLA % = DIVIDE(COUNTROWS(FILTER(FactCases, FactCases[SLAStatus] = "Met")), COUNTROWS(FactCases)) * 100`
  - `Average Case Age = AVERAGE(FactCases[AgeInDays])`
  - `CBC Compliance % = DIVIDE(COUNTROWS(FILTER(FactCallbacks, FactCallbacks[Status] = "Completed" AND FactCallbacks[DelayMinutes] <= 0)), COUNTROWS(FactCallbacks)) * 100`

---

## Screen Mapping

We will provide side-by-side tabs in the Streamlit app to represent the requested screens:

1. **Executive Dashboard**: Corporate KPIs (Open cases, SLA%, CBC Today, Aging metrics) with interactive charts.
2. **Engineer Dashboard**: Personalized case lists, pending CBCs, cases awaiting customer, and critical SLA timers.
3. **Case Details**: In-depth case record view. Features action buttons: *Initiate Follow-up, Trigger Warranty Request, Schedule CBC, Add L2 Activity, Create Case Note, Escalate Case*.
4. **Case Automation Center**: Controls to Enable/Disable automations. Displays real-time run counters (Success/Failure) and "Last Run" times.
5. **Warranty Request Center**: Custom Power App mockup to request extensions/transfers, input settings, and render a generated QR code pointing to a simulated endpoint.
6. **CBC Callback Center**: Real-time callback tracking with a "Call Customer" simulator, dialing status indicator (Dialing, Connected, Ringing), and case history logging.
7. **Customer Follow-up Center**: Lists cases waiting for responses and displays simulated Copilot Studio follow-up templates.
8. **IVR Simulator**: Simulates a customer calling the Dynamics Contact Center voice IVR. Input phone/serial to either resume an existing case or auto-create a new one.
9. **Administration Center**: Configurations (follow-up intervals, SLA thresholds, API URLs) and the **Audit Log Viewer**.
10. **Integration Readiness Matrix**: Shows what is real vs. mocked, specifying Microsoft technologies needed to go production-grade.

---

## Security Model (Row-Level Security)

A global user selector in the Streamlit sidebar will let you log in as:
1. **Engineer (e.g., Alex Carter)**: Can only see their assigned cases/metrics. Cannot view manager controls.
2. **Team Lead (e.g., Sarah Jenkins)**: Can view team cases, metrics, and trigger escalations.
3. **Manager (e.g., Robert Vance)**: Can view all team cases, full dashboards, and automation performance.
4. **Administrator (e.g., Admin User)**: Can access and edit configurations, view audit logs, and toggle automations.

---

## Verification & Demo Scenarios Plan

We will verify the prototype using the following scenario runs in the UI:
- **Scenario A (Case Change)**: Update a case property (e.g. Warranty Status). Verify notification record and Audit log is created.
- **Scenario B (Follow-up)**: Transition a case to "Awaiting Customer". Verify that the Follow-up Engine schedules a message.
- **Scenario C (CBC)**: Schedule a callback. Verify that a 30-minute reminder triggers and the "Call Customer" dialer updates the case timeline.
- **Scenario D (IVR)**: Call the IVR simulator with an existing phone/serial. Verify that it locates the existing case and updates it.
- **Scenario E (Warranty)**: Create a warranty extension. Verify that the Entitlement Service generates the QR code and logs the status.
- **Scenario F & G (Security)**: Toggle between "Engineer" and "Manager" roles. Verify that the dashboards dynamically filter data.

---

## Implementation Steps

1. **Step 1**: Install requirements (`streamlit`, `pandas`, `qrcode`, `pillow` or similar).
2. **Step 2**: Create `app/db/database.py` with schema and seed 100 cases, 20 engineers, 30 customers, 50 callbacks, etc.
3. **Step 3**: Create services for Entitlement, Notifications, Follow-up, IVR, and Callback.
4. **Step 4**: Create `app/services/automation.py` containing the trigger checking loops and logs.
5. **Step 5**: Write `app/ui/main.py` implementing the UI layout, dashboards, and role filters.
6. **Step 6**: Test and verify scenarios using the built-in browser/testing script.
