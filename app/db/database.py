import sqlite3
import os
import random
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "dataverse.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
    except Exception:
        pass
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")

    # 1. Customers Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS customers (
        customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT NOT NULL,
        email TEXT NOT NULL,
        preferred_language TEXT NOT NULL DEFAULT 'English'
    );
    """)

    # 2. Engineers Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS engineers (
        engineer_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        team_id TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('Engineer', 'Team Lead', 'Manager', 'Administrator'))
    );
    """)

    # 3. Queues Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS queues (
        queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT
    );
    """)

    # 4. Cases Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cases (
        case_id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_number TEXT UNIQUE NOT NULL,
        customer_id INTEGER NOT NULL,
        serial_number TEXT NOT NULL,
        product_number TEXT NOT NULL,
        engineer_id INTEGER,
        queue_id INTEGER,
        status TEXT NOT NULL CHECK(status IN ('New', 'Active', 'Awaiting Customer', 'Resolved', 'Closed')),
        priority TEXT NOT NULL CHECK(priority IN ('Critical', 'High', 'Normal', 'Low')),
        issue_category TEXT NOT NULL CHECK(issue_category IN ('Hardware', 'Software', 'Network', 'Billing', 'Installation')),
        created_date TEXT NOT NULL,
        modified_date TEXT NOT NULL,
        closed_date TEXT,
        sla_status TEXT NOT NULL DEFAULT 'In Progress' CHECK(sla_status IN ('In Progress', 'Met', 'Breached')),
        first_response_date TEXT,
        resolution_date TEXT,
        ats TEXT NOT NULL DEFAULT 'Tier 1',
        crt TEXT NOT NULL DEFAULT 'Normal',
        warranty_status TEXT NOT NULL DEFAULT 'Out of Warranty',
        quote_status TEXT NOT NULL DEFAULT 'Not Required',
        awaiting_customer INTEGER DEFAULT 0 CHECK(awaiting_customer IN (0, 1)),
        l2_pending INTEGER DEFAULT 0 CHECK(l2_pending IN (0, 1)),
        cbc_datetime TEXT,
        source TEXT NOT NULL DEFAULT 'Web',
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
        FOREIGN KEY (engineer_id) REFERENCES engineers(engineer_id),
        FOREIGN KEY (queue_id) REFERENCES queues(queue_id)
    );
    """)

    # 5. WarrantyRequests Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS warranty_requests (
        request_id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id INTEGER,
        serial_number TEXT NOT NULL,
        product_number TEXT NOT NULL,
        customer_id INTEGER NOT NULL,
        request_type TEXT NOT NULL CHECK(request_type IN ('Warranty Extension', 'Care Pack Extension', 'Warranty Transfer', 'Care Pack Transfer')),
        current_warranty_status TEXT NOT NULL,
        requested_action TEXT NOT NULL,
        customer_contact TEXT NOT NULL,
        request_date TEXT NOT NULL,
        request_status TEXT NOT NULL CHECK(request_status IN ('New', 'Submitted', 'Under Review', 'Approved', 'Rejected', 'Completed')),
        qr_code_url TEXT,
        FOREIGN KEY (case_id) REFERENCES cases(case_id),
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
    );
    """)

    # 6. CaseChangeNotifications Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS case_change_notifications (
        notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_number TEXT NOT NULL,
        case_id INTEGER NOT NULL,
        engineer_id INTEGER,
        change_type TEXT NOT NULL,
        previous_value TEXT,
        new_value TEXT,
        changed_by TEXT NOT NULL,
        changed_datetime TEXT NOT NULL,
        notification_channel TEXT NOT NULL,
        notification_status TEXT NOT NULL CHECK(notification_status IN ('Pending', 'Sent')),
        notification_sent_datetime TEXT,
        FOREIGN KEY (case_id) REFERENCES cases(case_id),
        FOREIGN KEY (engineer_id) REFERENCES engineers(engineer_id)
    );
    """)

    # 7. CaseFollowups Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS case_followups (
        followup_id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id INTEGER NOT NULL,
        case_number TEXT NOT NULL,
        customer_id INTEGER NOT NULL,
        engineer_id INTEGER,
        followup_number INTEGER NOT NULL,
        scheduled_datetime TEXT NOT NULL,
        sent_datetime TEXT,
        response_received INTEGER DEFAULT 0 CHECK(response_received IN (0, 1)),
        response_datetime TEXT,
        status TEXT NOT NULL CHECK(status IN ('Scheduled', 'Sent', 'Customer Responded', 'No Response', 'Escalated', 'Cancelled')),
        escalated INTEGER DEFAULT 0 CHECK(escalated IN (0, 1)),
        FOREIGN KEY (case_id) REFERENCES cases(case_id),
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
        FOREIGN KEY (engineer_id) REFERENCES engineers(engineer_id)
    );
    """)

    # 8. Callbacks (CBC) Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS callbacks (
        callback_id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id INTEGER NOT NULL,
        case_number TEXT NOT NULL,
        customer_id INTEGER NOT NULL,
        engineer_id INTEGER NOT NULL,
        callback_datetime TEXT NOT NULL,
        reminder_datetime TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('Scheduled', 'Completed', 'Missed', 'Call Initiated')),
        actual_callback_datetime TEXT,
        call_duration TEXT,
        call_outcome TEXT,
        FOREIGN KEY (case_id) REFERENCES cases(case_id),
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
        FOREIGN KEY (engineer_id) REFERENCES engineers(engineer_id)
    );
    """)

    # 9. Automations Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS automations (
        automation_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        description TEXT,
        trigger TEXT NOT NULL,
        condition TEXT,
        action TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Enabled' CHECK(status IN ('Enabled', 'Disabled')),
        last_run TEXT,
        success_count INTEGER DEFAULT 0,
        fail_count INTEGER DEFAULT 0,
        error_message TEXT
    );
    """)

    # 10. AuditLogs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        user TEXT NOT NULL,
        automation TEXT,
        case_id INTEGER,
        action TEXT NOT NULL,
        old_value TEXT,
        new_value TEXT,
        result TEXT NOT NULL,
        error TEXT,
        FOREIGN KEY (case_id) REFERENCES cases(case_id)
    );
    """)

    # 11. Configurations Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS configurations (
        config_key TEXT PRIMARY KEY,
        config_value TEXT NOT NULL,
        description TEXT
    );
    """)

    conn.commit()
    seed_data(conn)
    conn.close()

def seed_data(conn):
    cursor = conn.cursor()

    # Check if we already have data
    cursor.execute("SELECT COUNT(*) FROM customers")
    if cursor.fetchone()[0] > 0:
        return # Database already seeded

    # Seed Configurations
    configs = [
        ('FirstFollowupHours', '48', 'Hours to wait before first customer follow-up'),
        ('SecondFollowupHours', '48', 'Hours to wait before second customer follow-up'),
        ('MaximumFollowups', '2', 'Max follow-ups before escalations'),
        ('CBCLeadTimeMinutes', '30', 'Lead time in minutes for callback reminders'),
        ('EntitlementBaseURL', 'https://apps.powerapps.com/play/e/default-entitlement-service', 'Base URL for entitlement checks'),
        ('DefaultQueue', 'General Hardware Queue', 'Fallback queue for IVR cases'),
        ('SLAThresholdHours', '24', 'SLA resolution time limit in hours')
    ]
    cursor.executemany("INSERT INTO configurations (config_key, config_value, description) VALUES (?, ?, ?)", configs)

    # Seed Automations
    automations = [
        ('Customer Follow-up', 'Triggers automatically when case status is Awaiting Customer. Schedules follow-up emails at configured intervals and escalates to ownership if ignored.', 'Case status set to Awaiting Customer', 'awaiting_customer = 1 AND status = "Awaiting Customer"', 'Schedule / Send Follow-up & escalate', 'Enabled', None, 124, 0, None),
        ('Case Update Notifications', 'Monitors Case changes (Priority, Ownership, CRT, ATS) and dispatches real-time cards to Teams, Outlook, and In-App centres. Groups/deduplicates close notifications.', 'Case modified', 'Any field changed', 'Send grouped notification to Owner', 'Enabled', None, 452, 2, None),
        ('CBC Alerts & Autodial', 'Triggers alerts 30 minutes before callback time and displays call launcher at callback due time. Direct dial capability via simulated voice integration.', 'Current time matches reminder_datetime or callback_datetime', 'status = "Scheduled"', 'Trigger alert / enable Call Customer button', 'Enabled', None, 310, 0, None),
        ('IVR Case Creation', 'Processes customer phone/serial calls from IVR and either maps to existing open cases or creates a new case using automated queues.', 'Incoming voice call webhook', 'Caller authenticates', 'Validate caller and auto-assign case', 'Enabled', None, 88, 1, None),
        ('Warranty Automation', 'Generates Care Pack/Warranty request links and QR codes from D365 and updates entitled status on customer approval.', 'Case actions request', 'Support representative clicks Extend/Transfer', 'Generate QR and route request flow', 'Enabled', None, 45, 0, None)
    ]
    cursor.executemany("INSERT INTO automations (name, description, trigger, condition, action, status, last_run, success_count, fail_count, error_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", automations)

    # Seed Queues
    queues = [
        ('Commercial Notebook L1', 'L1 triage for corporate laptops'),
        ('Enterprise Server Priority', 'High-priority server infrastructure queue'),
        ('General Hardware Queue', 'Fallback queue for basic hardware issues'),
        ('Critical Software & OS', 'L2 OS and firmware diagnostics'),
        ('Billing & Warranties Queue', 'Warranty entitlement and invoice disputes')
    ]
    cursor.executemany("INSERT INTO queues (name, description) VALUES (?, ?)", queues)

    # Seed 20 Engineers
    engineers_data = [
        ('Alex Carter', 'alex.carter@hpsupport.com', 'Team Alpha', 'Engineer'),
        ('Sarah Jenkins', 'sarah.jenkins@hpsupport.com', 'Team Alpha', 'Team Lead'),
        ('Robert Vance', 'robert.vance@hpsupport.com', 'Support Division', 'Manager'),
        ('Admin User', 'admin.portal@hpsupport.com', 'IT Operations', 'Administrator'),
        ('John Doe', 'john.doe@hpsupport.com', 'Team Alpha', 'Engineer'),
        ('Jane Smith', 'jane.smith@hpsupport.com', 'Team Alpha', 'Engineer'),
        ('David Miller', 'david.miller@hpsupport.com', 'Team Beta', 'Engineer'),
        ('Emily Davis', 'emily.davis@hpsupport.com', 'Team Beta', 'Engineer'),
        ('Michael Brown', 'michael.brown@hpsupport.com', 'Team Beta', 'Team Lead'),
        ('Jessica Wilson', 'jessica.wilson@hpsupport.com', 'Team Gamma', 'Engineer'),
        ('James Jones', 'james.jones@hpsupport.com', 'Team Gamma', 'Engineer'),
        ('Linda Taylor', 'linda.taylor@hpsupport.com', 'Team Gamma', 'Team Lead'),
        ('Robert Thomas', 'robert.thomas@hpsupport.com', 'Team Delta', 'Engineer'),
        ('Patricia Anderson', 'patricia.anderson@hpsupport.com', 'Team Delta', 'Engineer'),
        ('William Jackson', 'william.jackson@hpsupport.com', 'Team Delta', 'Team Lead'),
        ('Barbara White', 'barbara.white@hpsupport.com', 'Support Division', 'Manager'),
        ('Richard Harris', 'richard.harris@hpsupport.com', 'Team Alpha', 'Engineer'),
        ('Susan Martin', 'susan.martin@hpsupport.com', 'Team Alpha', 'Engineer'),
        ('Charles Thompson', 'charles.thompson@hpsupport.com', 'Team Beta', 'Engineer'),
        ('Mary Garcia', 'mary.garcia@hpsupport.com', 'Team Beta', 'Engineer')
    ]
    cursor.executemany("INSERT INTO engineers (name, email, team_id, role) VALUES (?, ?, ?, ?)", engineers_data)

    # Seed 30 Customers
    customers_data = [
        ('Acme Corporation', '+15550192834', 'it@acme.com', 'English'),
        ('Globex Corporation', '+15550187263', 'support@globex.com', 'English'),
        ('Initech LLC', '+15550143890', 'peter@initech.com', 'English'),
        ('Umbrella Corp', '+15550122908', 'facility@umbrella.com', 'English'),
        ('Hooli Inc', '+15550133492', 'richard@hooli.com', 'English'),
        ('Stark Industries', '+15550199999', 'pepper@stark.com', 'English'),
        ('Wayne Enterprises', '+15550123232', 'lucius@wayne.com', 'English'),
        ('Tyrell Corp', '+15550119820', 'deckard@tyrell.com', 'English'),
        ('Cyberdyne Systems', '+15550192029', 'miles@cyberdyne.com', 'English'),
        ('Soylent Co', '+15550188822', 'thorn@soylent.com', 'Spanish'),
        ('Virtucon Group', '+15550137788', 'evil@virtucon.com', 'English'),
        ('Dunder Mifflin', '+15550100420', 'mscott@dundermifflin.com', 'English'),
        ('Aperture Science', '+15550144321', 'cave@aperture.com', 'English'),
        ('Black Mesa', '+15550198765', 'gfreeman@blackmesa.com', 'English'),
        ('Veer Towers LLC', '+15550111222', 'info@veer.com', 'Spanish'),
        ('Abstergo Ind.', '+15550155523', 'desmond@abstergo.com', 'French'),
        ('Vandelay Industries', '+15550112345', 'george@vandelay.com', 'English'),
        ('Pennypacker LLC', '+15550199887', 'kramer@pennypacker.com', 'English'),
        ('Kruger Industrial', '+15550133221', 'kruger@kruger.com', 'German'),
        ('Prestige Worldwide', '+15550124680', 'brennan@prestige.com', 'English'),
        ('Reynholm Industries', '+15550192837', 'douglas@reynholm.com', 'English'),
        ('Massive Dynamic', '+15550123984', 'wishop@massivedynamic.com', 'English'),
        ('Madrigal Electromotive', '+15550100998', 'lydia@madrigal.com', 'German'),
        ('Los Pollos Hermanos', '+15550177665', 'gus@lph.com', 'Spanish'),
        ('Bluth Company', '+15550132145', 'michael@bluthco.com', 'English'),
        ('Saturdays LLC', '+15550177723', 'sales@saturdays.com', 'English'),
        ('Genco Olive Oil', '+15550111111', 'vito@genco.com', 'Italian'),
        ('Sterling Cooper', '+15550133333', 'don@sterling.com', 'English'),
        ('Wonka Factory', '+15550101010', 'charlie@wonka.com', 'English'),
        ('Sledge Hammer Inc', '+15550155500', 'hammer@sledge.com', 'English')
    ]
    cursor.executemany("INSERT INTO customers (name, phone, email, preferred_language) VALUES (?, ?, ?, ?)", customers_data)

    # Prepare data collections for references
    cursor.execute("SELECT customer_id FROM customers")
    cust_ids = [row[0] for row in cursor.fetchall()]
    
    cursor.execute("SELECT engineer_id FROM engineers WHERE role != 'Administrator'")
    eng_ids = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT queue_id FROM queues")
    q_ids = [row[0] for row in cursor.fetchall()]

    categories = ['Hardware', 'Software', 'Network', 'Billing', 'Installation']
    priorities = ['Critical', 'High', 'Normal', 'Low']
    statuses = ['New', 'Active', 'Awaiting Customer', 'Resolved', 'Closed']
    ats_levels = ['Tier 1', 'Tier 2', 'Tier 3']
    crt_levels = ['Normal', 'Elevated', 'Critical']
    warranties = ['In Warranty (Base)', 'Care Pack Active', 'Out of Warranty']

    serial_prefixes = ['5CG', '8CC', 'CN']

    # Seeding 100 cases
    now = datetime.now()
    cases_created = []

    for i in range(1, 105):
        case_number = f"CAS-{100000 + i}"
        customer_id = random.choice(cust_ids)
        serial_number = f"{random.choice(serial_prefixes)}{random.randint(10000, 99999)}{random.choice(['AB', 'XY', 'CD'])}"
        product_number = f"HP-PRO-{random.randint(100, 999)}-{random.choice(['DX', 'MX', 'LN'])}"
        engineer_id = random.choice(eng_ids)
        queue_id = random.choice(q_ids)
        priority = random.choices(priorities, weights=[10, 25, 45, 20])[0]
        status = random.choices(statuses, weights=[15, 40, 25, 10, 10])[0]
        issue_category = random.choice(categories)

        # Dates seeding
        created_days_ago = random.randint(1, 28)
        created_dt = now - timedelta(days=created_days_ago, hours=random.randint(0, 23))
        
        modified_dt = created_dt + timedelta(hours=random.randint(1, 48))
        if modified_dt > now:
            modified_dt = now

        closed_dt = None
        resolution_date = None
        if status in ['Resolved', 'Closed']:
            resolved_days_after = random.randint(1, 7)
            res_dt = created_dt + timedelta(days=resolved_days_after, hours=random.randint(0, 10))
            if res_dt > now:
                res_dt = now
            resolution_date = res_dt.strftime("%Y-%m-%d %H:%M:%S")
            if status == 'Closed':
                closed_dt = (res_dt + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")

        first_resp_dt = None
        if random.random() > 0.1: # 90% have first response
            first_resp_dt = (created_dt + timedelta(minutes=random.randint(15, 240))).strftime("%Y-%m-%d %H:%M:%S")

        # SLA calculation
        # Let's say Critical is 4hr resolution, High is 12hr, Normal is 48hr, Low is 96hr.
        # Check if breached
        sla_status = 'In Progress'
        if status in ['Resolved', 'Closed'] and resolution_date:
            res_time = datetime.strptime(resolution_date, "%Y-%m-%d %H:%M:%S")
            duration_hrs = (res_time - created_dt).total_seconds() / 3600
            limit_hrs = {'Critical': 4, 'High': 12, 'Normal': 48, 'Low': 96}[priority]
            sla_status = 'Met' if duration_hrs <= limit_hrs else 'Breached'
        elif status not in ['Resolved', 'Closed']:
            duration_hrs = (now - created_dt).total_seconds() / 3600
            limit_hrs = {'Critical': 4, 'High': 12, 'Normal': 48, 'Low': 96}[priority]
            if duration_hrs > limit_hrs:
                sla_status = 'Breached'

        ats = random.choices(ats_levels, weights=[60, 30, 10])[0]
        crt = random.choices(crt_levels, weights=[70, 20, 10])[0]
        warranty_status = random.choice(warranties)
        quote_status = 'Approved' if random.random() > 0.7 else 'Not Required'
        awaiting_customer = 1 if status == 'Awaiting Customer' else 0
        l2_pending = 1 if (status == 'Active' and random.random() > 0.8) else 0

        cbc_dt = None
        if status in ['New', 'Active', 'Awaiting Customer'] and random.random() > 0.4:
            # Add upcoming or past CBC
            cbc_days_offset = random.randint(-2, 3)
            cbc_dt = (now + timedelta(days=cbc_days_offset, hours=random.randint(-4, 4))).strftime("%Y-%m-%d %H:%M:%S")

        source = random.choice(['Web', 'Email', 'Portal', 'IVR'])

        cursor.execute("""
            INSERT INTO cases (
                case_number, customer_id, serial_number, product_number, engineer_id, queue_id,
                status, priority, issue_category, created_date, modified_date, closed_date,
                sla_status, first_response_date, resolution_date, ats, crt, warranty_status,
                quote_status, awaiting_customer, l2_pending, cbc_datetime, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            case_number, customer_id, serial_number, product_number, engineer_id, queue_id,
            status, priority, issue_category, created_dt.strftime("%Y-%m-%d %H:%M:%S"),
            modified_dt.strftime("%Y-%m-%d %H:%M:%S"), closed_dt, sla_status, first_resp_dt,
            resolution_date, ats, crt, warranty_status, quote_status, awaiting_customer,
            l2_pending, cbc_dt, source
        ))
        
        case_id = cursor.lastrowid
        cases_created.append({
            'case_id': case_id,
            'case_number': case_number,
            'customer_id': customer_id,
            'engineer_id': engineer_id,
            'created_date': created_dt,
            'status': status,
            'cbc_datetime': cbc_dt
        })

    # Seed 50 Callbacks (CBC)
    cbc_count = 0
    for c in cases_created:
        if cbc_count >= 50:
            break
        if c['cbc_datetime']:
            cbc_dt_parsed = datetime.strptime(c['cbc_datetime'], "%Y-%m-%d %H:%M:%S")
            rem_dt = (cbc_dt_parsed - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
            
            # Status determination
            cbc_status = 'Scheduled'
            actual_dt = None
            duration = None
            outcome = None
            if cbc_dt_parsed < now:
                cbc_status = random.choice(['Completed', 'Missed'])
                if cbc_status == 'Completed':
                    actual_dt = (cbc_dt_parsed + timedelta(minutes=random.randint(-5, 15))).strftime("%Y-%m-%d %H:%M:%S")
                    duration = f"{random.randint(2, 15)}m {random.randint(0, 59)}s"
                    outcome = "Resolved customer inquiry"
                else:
                    outcome = "Customer unavailable - Voicemail left"
            
            cursor.execute("""
                INSERT INTO callbacks (
                    case_id, case_number, customer_id, engineer_id, callback_datetime,
                    reminder_datetime, status, actual_callback_datetime, call_duration, call_outcome
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                c['case_id'], c['case_number'], c['customer_id'], c['engineer_id'],
                c['cbc_datetime'], rem_dt, cbc_status, actual_dt, duration, outcome
            ))
            cbc_count += 1

    # Fill remaining callbacks if needed
    while cbc_count < 50:
        c = random.choice(cases_created)
        cbc_dt = (now + timedelta(days=random.randint(-5, 5), hours=random.randint(-6, 6)))
        rem_dt = (cbc_dt - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
        cbc_status = 'Scheduled' if cbc_dt > now else random.choice(['Completed', 'Missed'])
        
        cursor.execute("""
            INSERT INTO callbacks (
                case_id, case_number, customer_id, engineer_id, callback_datetime,
                reminder_datetime, status, actual_callback_datetime, call_duration, call_outcome
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            c['case_id'], c['case_number'], c['customer_id'], c['engineer_id'],
            cbc_dt.strftime("%Y-%m-%d %H:%M:%S"), rem_dt, cbc_status, None, None, None
        ))
        cbc_count += 1

    # Seed 50 CaseFollowups
    followup_count = 0
    for c in cases_created:
        if followup_count >= 50:
            break
        if c['status'] == 'Awaiting Customer' or random.random() > 0.7:
            f_num = random.randint(1, 2)
            sched_dt = (c['created_date'] + timedelta(days=f_num * 2)).strftime("%Y-%m-%d %H:%M:%S")
            
            f_status = 'Scheduled'
            sent_dt = None
            resp_received = 0
            resp_dt = None
            escalated = 0

            sched_dt_parsed = datetime.strptime(sched_dt, "%Y-%m-%d %H:%M:%S")
            if sched_dt_parsed < now:
                f_status = random.choices(
                    ['Sent', 'Customer Responded', 'No Response', 'Escalated'],
                    weights=[15, 50, 20, 15]
                )[0]
                sent_dt = (sched_dt_parsed + timedelta(minutes=random.randint(5, 30))).strftime("%Y-%m-%d %H:%M:%S")
                if f_status == 'Customer Responded':
                    resp_received = 1
                    resp_dt = (sched_dt_parsed + timedelta(hours=random.randint(1, 36))).strftime("%Y-%m-%d %H:%M:%S")
                elif f_status == 'Escalated':
                    escalated = 1

            cursor.execute("""
                INSERT INTO case_followups (
                    case_id, case_number, customer_id, engineer_id, followup_number,
                    scheduled_datetime, sent_datetime, response_received, response_datetime,
                    status, escalated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                c['case_id'], c['case_number'], c['customer_id'], c['engineer_id'],
                f_num, sched_dt, sent_dt, resp_received, resp_dt, f_status, escalated
            ))
            followup_count += 1

    # Seed 20 Warranty Requests
    hw_cases = [c for c in cases_created if c['status'] in ['Active', 'Resolved']]
    warranty_count = 0
    req_types = ['Warranty Extension', 'Care Pack Extension', 'Warranty Transfer', 'Care Pack Transfer']
    statuses_w = ['New', 'Submitted', 'Under Review', 'Approved', 'Rejected', 'Completed']

    for c in hw_cases:
        if warranty_count >= 20:
            break
        
        cursor.execute("SELECT serial_number, product_number, customer_id FROM cases WHERE case_id = ?", (c['case_id'],))
        row = cursor.fetchone()
        if not row:
            continue
        
        serial_no, prod_no, cust_id = row[0], row[1], row[2]
        
        req_type = random.choice(req_types)
        w_status = random.choice(statuses_w)
        req_date = (c['created_date'] + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        qr_code = f"https://apps.powerapps.com/play/e/default-entitlement-service?requestId=WREQ-880{warranty_count}&serial={serial_no}"

        cursor.execute("""
            INSERT INTO warranty_requests (
                case_id, serial_number, product_number, customer_id, request_type,
                current_warranty_status, requested_action, customer_contact, request_date,
                request_status, qr_code_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            c['case_id'], serial_no, prod_no, cust_id, req_type,
            'In Warranty (Base)', 'Extend Coverage 2 Years', 'IT Admin', req_date, w_status, qr_code
        ))
        warranty_count += 1

    # Seed 100+ Case Change Notifications
    change_types = ['ATS_CHANGED', 'CRT_CHANGED', 'WARRANTY_UPDATED', 'QUOTE_APPROVED', 'L2_ACTIVITY_ADDED', 'CASE_NOTE_ADDED', 'PRIORITY_CHANGED', 'STATUS_CHANGED', 'OWNER_CHANGED', 'CUSTOMER_REPLIED']
    channels = ['Teams', 'Outlook', 'In-App']
    
    for i in range(110):
        c = random.choice(cases_created)
        chg_type = random.choice(change_types)
        prev_val, new_val = "Old Value", "New Value"
        if chg_type == 'STATUS_CHANGED':
            prev_val = 'New'
            new_val = 'Active'
        elif chg_type == 'PRIORITY_CHANGED':
            prev_val = 'Normal'
            new_val = 'High'
        elif chg_type == 'OWNER_CHANGED':
            prev_val = 'Unassigned'
            new_val = 'Alex Carter'

        chg_dt = (c['created_date'] + timedelta(hours=random.randint(1, 48)))
        if chg_dt > now:
            chg_dt = now

        sent_dt = None
        n_status = 'Pending'
        if chg_dt < now - timedelta(minutes=10):
            n_status = 'Sent'
            sent_dt = (chg_dt + timedelta(seconds=random.randint(5, 60))).strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
            INSERT INTO case_change_notifications (
                case_number, case_id, engineer_id, change_type, previous_value, new_value,
                changed_by, changed_datetime, notification_channel, notification_status, notification_sent_datetime
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            c['case_number'], c['case_id'], c['engineer_id'], chg_type, prev_val, new_val,
            'System Automator', chg_dt.strftime("%Y-%m-%d %H:%M:%S"), random.choice(channels),
            n_status, sent_dt
        ))

    # Seed some Audit logs
    for i in range(75):
        c = random.choice(cases_created)
        log_time = (c['created_date'] + timedelta(minutes=random.randint(10, 1440))).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO audit_logs (
                timestamp, user, automation, case_id, action, old_value, new_value, result
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            log_time, 'System Service', 'Customer Follow-up', c['case_id'],
            'Follow-up scheduled', 'None', 'Scheduled 1st Followup', 'Success'
        ))

    conn.commit()

if __name__ == "__main__":
    init_db()
    print("Database schema initialized and sample data seeded successfully in", DB_PATH)
