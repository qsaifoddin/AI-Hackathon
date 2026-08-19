import sys
import os

# Add project root to python path to resolve 'app' package correctly when run via Streamlit
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import streamlit as st
import pandas as pd
import sqlite3
import io
import time
from datetime import datetime, timedelta

# Import services
from app.db.database import get_connection, DB_PATH
from app.services.audit import log_action, get_config, set_config, get_all_configs
from app.services.entitlement import EntitlementService
from app.services.notification import NotificationService
from app.services.followup import FollowupService
from app.services.ivr import IVRCaseService
from app.services.callback import CallbackService
from app.services.automation import AutomationEngine

# Page settings
st.set_page_config(
    page_title="HP Support Automation & Engineer Productivity Hub",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Fluent UI Styling
st.markdown("""
<style>
    /* Main body background and text */
    .stApp {
        background-color: #f3f2f1;
        color: #323130 !important;
        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    }
    
    /* Force text color for basic markdown elements to maintain contrast */
    .stApp p, .stApp li, .stApp td, .stApp th, .stApp h4, .stApp h5, .stApp h6 {
        color: #323130 !important;
    }
    
    /* Exclude code block spans from dark text override so code blocks remain readable */
    .stApp code span, .stApp pre span {
        color: inherit !important;
    }
    
    /* Protect button text elements from dark text override, letting them inherit high-contrast button styling */
    .stApp button p, .stApp button span, .stApp button div, .stApp button label {
        color: inherit !important;
    }
    
    /* Restore text color for sidebar elements to be legible on dark sidebar background */
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] div,
    section[data-testid="stSidebar"] li {
        color: #faf9f8 !important;
    }
    
    /* Standard Card containers */
    .fluent-card {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 4px;
        border: 1px solid #e0e0e0;
        box-shadow: 0 1.6px 3.6px 0 rgba(0,0,0,0.132), 0 0.3px 0.9px 0 rgba(0,0,0,0.108);
        margin-bottom: 20px;
    }
    
    /* Title colors */
    h1, h2, h3 {
        color: #323130 !important;
        font-weight: 600 !important;
    }
    
    /* Custom status badges */
    .badge {
        padding: 4px 8px;
        border-radius: 2px;
        font-size: 12px;
        font-weight: bold;
        display: inline-block;
    }
    .badge-new { background-color: #c7e0f4; color: #0078d4; }
    .badge-active { background-color: #dff6dd; color: #107c41; }
    .badge-awaiting { background-color: #fde7e9; color: #a80000; }
    .badge-resolved { background-color: #f3f2f1; color: #323130; border: 1px dashed #a19f9d; }
    .badge-closed { background-color: #a19f9d; color: #ffffff; }

    .badge-critical { background-color: #fde7e9; color: #a80000; font-weight: 800; }
    .badge-high { background-color: #fed9cc; color: #d83b01; }
    .badge-normal { background-color: #fff4ce; color: #795600; }
    .badge-low { background-color: #dff6dd; color: #107c41; }
</style>
""", unsafe_allow_html=True)

# Helper: Fetch list of Engineers and Customers for selectors
def fetch_engineers():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, role, email, team_id FROM engineers")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def fetch_customers():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM customers")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# Global state / caches
engineers = fetch_engineers()
customers = fetch_customers()

# --------------------------------------------------------------------------------
# SIDEBAR / IDENTITY & SECURITY ROLE CONCEPT (ENTRA ID)
# --------------------------------------------------------------------------------
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/a/ad/HP_logo_2012.svg", width=60)
st.sidebar.markdown("### Support Automation Hub")

st.sidebar.subheader("🔒 Microsoft Entra ID Identity")
selected_user_name = st.sidebar.selectbox(
    "Active Profile",
    options=[e['name'] for e in engineers] + ["Admin User"]
)

# Resolve active profile details
if selected_user_name == "Admin Portal" or selected_user_name == "Admin User":
    active_role = "Administrator"
    active_email = "admin.portal@hpsupport.com"
    active_team = "IT Operations"
    active_engineer_id = 999
else:
    active_eng = [e for e in engineers if e['name'] == selected_user_name][0]
    active_role = active_eng['role']
    active_email = active_eng['email']
    active_team = active_eng['team_id']
    
    # Retrieve DB ID
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT engineer_id FROM engineers WHERE name = ?", (selected_user_name,))
    row = cursor.fetchone()
    conn.close()
    active_engineer_id = row[0] if row else 1

st.sidebar.markdown(f"**Role:** `{active_role}`")
st.sidebar.markdown(f"**Team:** `{active_team}`")
st.sidebar.markdown(f"**Email:** `{active_email}`")

st.sidebar.markdown("---")

# Navigation Menu
nav_selection = st.sidebar.radio(
    "Dynamics Navigation",
    options=[
        "Executive Dashboard",
        "Engineer Dashboard",
        "Case Details & Actions",
        "Case Automation Center",
        "Warranty Request Hub",
        "CBC Callback Center",
        "Follow-up Center",
        "CTI Customer Search (D365 CC)",
        "Administration Panel",
        "Integration Readiness",
        "Power BI Data Model"
    ]
)

st.sidebar.markdown("---")
st.sidebar.caption("System Location: HP Dataverse Cluster (Mocked)")

# RLS Query Generator Utility
def rls_where_clause(table_prefix="cases"):
    """
    Simulates Row-Level Security policies.
    - Engineer: can only view their own cases.
    - Team Lead: can view cases of engineers in their team.
    - Manager / Admin: can view all cases.
    """
    pfx = f"{table_prefix}." if table_prefix else ""
    if active_role == 'Engineer':
        return f" AND {pfx}engineer_id = {active_engineer_id}"
    elif active_role == 'Team Lead':
        return f" AND {pfx}engineer_id IN (SELECT engineer_id FROM engineers WHERE team_id = '{active_team}')"
    return "" # No limits for Manager and Administrator

# Flush pending notifications on page refresh (simulating background trigger)
NotificationService.process_and_send_pending()

# --------------------------------------------------------------------------------
# SCREEN 1: EXECUTIVE DASHBOARD
# --------------------------------------------------------------------------------
if nav_selection == "Executive Dashboard":
    st.title("📊 Executive Support Operations Dashboard")
    st.markdown("Managerial view into HP customer support cases, SLAs, and callback queues.")
    
    # Apply RLS check
    if active_role == 'Engineer':
        st.warning("⚠️ Access Restricted: Engineers do not have permission to view global Executive dashboards. Content is filtered to your active profile.")
    
    # Fetch Data
    conn = get_connection()
    cursor = conn.cursor()
    
    # SLA Math
    cursor.execute(f"SELECT COUNT(*) FROM cases WHERE 1=1 {rls_where_clause()}")
    total_cases = cursor.fetchone()[0]
    
    cursor.execute(f"SELECT COUNT(*) FROM cases WHERE status NOT IN ('Resolved', 'Closed') {rls_where_clause()}")
    open_cases = cursor.fetchone()[0]
    
    cursor.execute(f"SELECT COUNT(*) FROM cases WHERE sla_status = 'Breached' {rls_where_clause()}")
    breached_sla = cursor.fetchone()[0]
    
    cursor.execute(f"SELECT COUNT(*) FROM cases WHERE status = 'Awaiting Customer' {rls_where_clause()}")
    awaiting_cust = cursor.fetchone()[0]
    
    # Calculate cases > 5 days old
    five_days_ago = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(f"SELECT COUNT(*) FROM cases WHERE status NOT IN ('Resolved', 'Closed') AND created_date <= ? {rls_where_clause()}", (five_days_ago,))
    aging_5_days = cursor.fetchone()[0]

    # CBC Today
    today_start = datetime.now().replace(hour=0, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S")
    today_end = datetime.now().replace(hour=23, minute=59, second=59).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(f"SELECT COUNT(*) FROM callbacks WHERE status = 'Scheduled' AND callback_datetime BETWEEN ? AND ? {rls_where_clause('callbacks')}", (today_start, today_end))
    cbc_today = cursor.fetchone()[0]

    # SLA met count
    cursor.execute(f"SELECT COUNT(*) FROM cases WHERE sla_status = 'Met' {rls_where_clause()}")
    sla_met = cursor.fetchone()[0]
    sla_pct = round((sla_met / (total_cases - open_cases) * 100), 1) if (total_cases - open_cases) > 0 else 98.4

    conn.close()

    # KPI Layout
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.metric("Total Cases", total_cases)
    with col2:
        st.metric("Open Cases", open_cases)
    with col3:
        st.metric("SLA Compliance %", f"{sla_pct}%", delta="0.2%")
    with col4:
        st.metric("CBCs Due Today", cbc_today)
    with col5:
        st.metric("Awaiting Customer", awaiting_cust)
    with col6:
        st.metric("Aging Cases (>5d)", aging_5_days, delta=f"{aging_5_days}", delta_color="inverse")

    # Display Charts
    st.markdown("---")
    c1, c2 = st.columns(2)
    
    # Query case volumes
    conn = get_connection()
    df_priority = pd.read_sql_query(f"SELECT priority, COUNT(*) as count FROM cases WHERE 1=1 {rls_where_clause()} GROUP BY priority", conn)
    df_status = pd.read_sql_query(f"SELECT status, COUNT(*) as count FROM cases WHERE 1=1 {rls_where_clause()} GROUP BY status", conn)
    df_category = pd.read_sql_query(f"SELECT issue_category, COUNT(*) as count FROM cases WHERE 1=1 {rls_where_clause()} GROUP BY issue_category", conn)
    conn.close()
    
    with c1:
        st.markdown("<div class='fluent-card'><h3>Cases by Priority</h3>", unsafe_allow_html=True)
        st.bar_chart(df_priority.set_index('priority'))
        st.markdown("</div>", unsafe_allow_html=True)

    with c2:
        st.markdown("<div class='fluent-card'><h3>Cases by Status</h3>", unsafe_allow_html=True)
        st.bar_chart(df_status.set_index('status'))
        st.markdown("</div>", unsafe_allow_html=True)
        
    c3, c4 = st.columns(2)
    with c3:
        st.markdown("<div class='fluent-card'><h3>Case Volumes by Category</h3>", unsafe_allow_html=True)
        st.bar_chart(df_category.set_index('issue_category'))
        st.markdown("</div>", unsafe_allow_html=True)
        
    with c4:
        st.markdown("<div class='fluent-card'><h3>Operational Analytics Trends</h3>", unsafe_allow_html=True)
        # Mocking an SLA trend line
        sla_data = pd.DataFrame({
            'Week': ['Wk 30', 'Wk 31', 'Wk 32', 'Wk 33', 'Wk 34'],
            'SLA %': [95.4, 96.1, 95.8, 97.2, sla_pct]
        })
        st.line_chart(sla_data.set_index('Week'))
        st.markdown("</div>", unsafe_allow_html=True)

# --------------------------------------------------------------------------------
# SCREEN 2: ENGINEER DASHBOARD
# --------------------------------------------------------------------------------
elif nav_selection == "Engineer Dashboard":
    st.title("💻 Personal Engineer Workspace")
    st.markdown(f"Logged in as: **{selected_user_name}** | Team: **{active_team}**")

    # Fetch Engineer Metrics
    conn = get_connection()
    cursor = conn.cursor()
    
    # Force queries to belong to selected engineer
    cursor.execute("SELECT COUNT(*) FROM cases WHERE engineer_id = ?", (active_engineer_id,))
    total_assigned = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM cases WHERE engineer_id = ? AND status NOT IN ('Resolved', 'Closed')", (active_engineer_id,))
    my_open = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM cases WHERE engineer_id = ? AND status = 'Awaiting Customer'", (active_engineer_id,))
    my_awaiting = cursor.fetchone()[0]

    # SLA met count
    cursor.execute("SELECT COUNT(*) FROM cases WHERE engineer_id = ? AND sla_status = 'Met'", (active_engineer_id,))
    my_sla_met = cursor.fetchone()[0]
    my_sla_pct = round((my_sla_met / (total_assigned - my_open) * 100), 1) if (total_assigned - my_open) > 0 else 96.2

    # CBC Upcoming
    cursor.execute("SELECT COUNT(*) FROM callbacks WHERE engineer_id = ? AND status = 'Scheduled'", (active_engineer_id,))
    my_cbc = cursor.fetchone()[0]
    
    # Aging
    five_days_ago = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("SELECT COUNT(*) FROM cases WHERE engineer_id = ? AND status NOT IN ('Resolved', 'Closed') AND created_date <= ?", (active_engineer_id, five_days_ago))
    my_aging = cursor.fetchone()[0]

    conn.close()

    # KPI Layout
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("My Open Cases", my_open)
    with col2:
        st.metric("My SLA %", f"{my_sla_pct}%")
    with col3:
        st.metric("My Scheduled CBCs", my_cbc)
    with col4:
        st.metric("Cases Awaiting Cust.", my_awaiting)
    with col5:
        st.metric("My Aging Cases (>5d)", my_aging)

    st.markdown("---")
    st.subheader("⚠️ Cases Requiring Attention")
    
    # Fetch cases requiring attention (SLA breached or Critical/High priority)
    conn = get_connection()
    query = """
        SELECT c.case_id, c.case_number, cust.name as customer_name, c.priority, c.status, c.created_date, c.sla_status, c.cbc_datetime
        FROM cases c
        JOIN customers cust ON c.customer_id = cust.customer_id
        WHERE c.engineer_id = ? AND c.status NOT IN ('Resolved', 'Closed')
        AND (c.priority IN ('Critical', 'High') OR c.sla_status = 'Breached')
        ORDER BY c.priority DESC, c.created_date ASC
    """
    df_attention = pd.read_sql_query(query, conn, params=(active_engineer_id,))
    conn.close()

    if not df_attention.empty:
        st.dataframe(df_attention, use_container_width=True)
    else:
        st.success("🎉 Excellent! You have no critical or breached open cases.")

    st.markdown("### All My Assigned Open Cases")
    conn = get_connection()
    query_all = """
        SELECT c.case_id, c.case_number, cust.name as customer_name, c.serial_number, c.priority, c.status, c.created_date, c.sla_status
        FROM cases c
        JOIN customers cust ON c.customer_id = cust.customer_id
        WHERE c.engineer_id = ? AND c.status NOT IN ('Resolved', 'Closed')
        ORDER BY c.created_date DESC
    """
    df_all_my = pd.read_sql_query(query_all, conn, params=(active_engineer_id,))
    conn.close()
    
    st.dataframe(df_all_my, use_container_width=True)

# --------------------------------------------------------------------------------
# SCREEN 3: CASE DETAILS & ACTIONS
# --------------------------------------------------------------------------------
elif nav_selection == "Case Details & Actions":
    st.title("🎫 Dynamics 365 Case Details Card")
    
    # Query cases list based on RLS
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT c.case_id, c.case_number, cust.name as customer_name 
        FROM cases c
        JOIN customers cust ON c.customer_id = cust.customer_id
        WHERE 1=1 {rls_where_clause('c')}
        ORDER BY c.case_number DESC
    """)
    case_options = [f"{row['case_number']} - {row['customer_name']}" for row in cursor.fetchall()]
    conn.close()

    if not case_options:
        st.warning("No cases match your security filtering policies.")
    else:
        selected_case_str = st.selectbox("Select Case File", case_options)
        selected_case_num = selected_case_str.split(" - ")[0]

        # Fetch detailed case record
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.*, cust.name as customer_name, cust.phone as customer_phone, cust.email as customer_email, e.name as engineer_name
            FROM cases c
            JOIN customers cust ON c.customer_id = cust.customer_id
            LEFT JOIN engineers e ON c.engineer_id = e.engineer_id
            WHERE c.case_number = ?
        """, (selected_case_num,))
        c_details = dict(cursor.fetchone())
        
        # Also fetch case history/notifications logs
        cursor.execute("SELECT * FROM case_change_notifications WHERE case_id = ? ORDER BY changed_datetime DESC", (c_details['case_id'],))
        history_rows = [dict(r) for r in cursor.fetchall()]
        
        # Fetch followups
        cursor.execute("SELECT * FROM case_followups WHERE case_id = ? ORDER BY followup_number DESC", (c_details['case_id'],))
        followup_rows = [dict(r) for r in cursor.fetchall()]

        # Fetch callbacks
        cursor.execute("SELECT * FROM callbacks WHERE case_id = ? ORDER BY callback_datetime DESC", (c_details['case_id'],))
        callback_rows = [dict(r) for r in cursor.fetchall()]

        conn.close()

        # Display Grid Layout
        # D365 Notification Bar Alert Mock
        unread_notifs_count = len([h for h in history_rows if h['notification_status'] == 'Pending'])
        if c_details['status'] in ['Resolved', 'Closed']:
            st.markdown("""
            <div style="background-color: #f3f2f1; border-left: 4px solid #a19f9d; padding: 10px 15px; margin-bottom: 15px; font-size: 13px; color: #323130;">
                ℹ️ Read-only: This record's status is Resolved/Closed.
            </div>
            """, unsafe_allow_html=True)
        elif unread_notifs_count > 0:
            st.markdown(f"""
            <div style="background-color: #fff4ce; border-left: 4px solid #795600; padding: 10px 15px; margin-bottom: 15px; font-size: 13px; color: #323130;">
                🔔 You have {unread_notifs_count} unread change notification(s). Check the Timeline tab below.
            </div>
            """, unsafe_allow_html=True)

        # Main D365 UCI Tab Structure
        tab_summary, tab_dynamic_notes, tab_case_info, tab_timeline = st.tabs([
            "Customer Summary", "Dynamic Notes", "Case Information", "Timeline & History Logs"
        ])

        with tab_summary:
            # 3-Column D365 Layout Grid
            col_left, col_middle, col_right = st.columns(3)

            # --- LEFT COLUMN: INSIGHTS & SUMMARIES ---
            with col_left:
                st.markdown("""
                <div class="fluent-card" style="margin-bottom: 15px; padding: 15px;">
                    <h5 style="margin: 0 0 10px 0; color: #323130;">Customer Insight</h5>
                    <div style="display: flex; justify-content: space-around; text-align: center;">
                        <div>
                            <div style="font-size: 22px;">😐</div>
                            <div style="font-size: 11px; font-weight:bold; color: #323130;">Neutral</div>
                            <div style="font-size: 9px; color: #605e5c;">Previous Sentiment</div>
                        </div>
                        <div style="border-left: 1px solid #e0e0e0; height: 35px;"></div>
                        <div>
                            <div style="font-size: 18px; font-weight: bold; color: #323130;">N/A</div>
                            <div style="font-size: 11px; font-weight:bold; color: #323130;">Waiting Time</div>
                            <div style="font-size: 9px; color: #605e5c;">(In Mins)</div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                with st.expander("📝 Case Summary", expanded=True):
                    st.markdown(f"**Issue Description:** Identified hardware failures on notebook diagnostics. Serial number `{c_details['serial_number']}` matching model `{c_details['product_number']}`.")
                    st.markdown(f"**Conversation Channel:** `{c_details['source']}`")

                with st.expander("💬 Conversation Summary", expanded=True):
                    st.markdown(f"""
                    - *Agent Saifoddin:* Hello! Thanks for contacting HP Support. How can I help you?
                    - *Customer:* My laptop screen is flickering after the last Windows update.
                    - *Agent Saifoddin:* I see. Let's run hardware diagnostics.
                    """)

                with st.expander("🎫 Case Details Info", expanded=True):
                    st.markdown(f"""
                    **Assigned Engineer:** {c_details['engineer_name']}  
                    **ATS Tier:** {c_details['ats']}  
                    **CRT Level:** {c_details['crt']}  
                    **Warranty:** {c_details['warranty_status']}  
                    **Quote Status:** {c_details['quote_status']}
                    """)

            # --- MIDDLE COLUMN: METRIC TILES & CONTACT CARD ---
            with col_middle:
                # Cases, Asset Orders, Customer Orders Tiles
                st.markdown("""
                <div style="background-color: white; border: 1px solid #e0e0e0; border-radius: 4px; padding: 12px; display: flex; justify-content: space-around; text-align: center; margin-bottom: 15px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                    <div>
                        <div style="font-size: 18px; font-weight: bold; color: #0078d4;">4</div>
                        <div style="font-size: 10px; color: #605e5c;">Cases</div>
                    </div>
                    <div style="border-left: 1px solid #e0e0e0; height: 30px;"></div>
                    <div>
                        <div style="font-size: 18px; font-weight: bold; color: #323130;">0</div>
                        <div style="font-size: 10px; color: #605e5c;">Asset Orders</div>
                    </div>
                    <div style="border-left: 1px solid #e0e0e0; height: 30px;"></div>
                    <div>
                        <div style="font-size: 18px; font-weight: bold; color: #323130;">0</div>
                        <div style="font-size: 10px; color: #605e5c;">Customer Orders</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                st.markdown(f"""
                <div class="fluent-card" style="padding: 15px;">
                    <h5 style="margin: 0 0 10px 0; color: #323130;">Contact</h5>
                    <table style="width: 100%; border-collapse: collapse; font-size: 12px; text-align: left;">
                        <tr style="border-bottom: 1px solid #f3f2f1;">
                            <td style="padding: 6px 0; font-weight: bold; color: #605e5c;">Customer Account:</td>
                            <td style="padding: 6px 0; color: #0078d4; font-weight:bold;">{c_details['customer_name']}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #f3f2f1;">
                            <td style="padding: 6px 0; font-weight: bold; color: #605e5c;">Contact:</td>
                            <td style="padding: 6px 0; color: #0078d4; font-weight:bold;">{c_details['customer_name']}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #f3f2f1;">
                            <td style="padding: 6px 0; font-weight: bold; color: #605e5c;">Salutation:</td>
                            <td style="padding: 6px 0;">Mr.</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #f3f2f1;">
                            <td style="padding: 6px 0; font-weight: bold; color: #605e5c;">Contact Type:</td>
                            <td style="padding: 6px 0;">Individual</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #f3f2f1;">
                            <td style="padding: 6px 0; font-weight: bold; color: #605e5c;">Phone Number:</td>
                            <td style="padding: 6px 0; font-weight:bold;">{c_details['customer_phone']}</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 0; font-weight: bold; color: #605e5c;">Email Address:</td>
                            <td style="padding: 6px 0; word-break: break-all;">{c_details['customer_email']}</td>
                        </tr>
                    </table>
                </div>
                """, unsafe_allow_html=True)

            # --- RIGHT COLUMN: CALL STATISTICS, ACTION LISTS, AND TRIGGERS ---
            with col_right:
                # Callbacks, Elevations, Complaints Tiles
                st.markdown("""
                <div style="background-color: white; border: 1px solid #e0e0e0; border-radius: 4px; padding: 12px; display: flex; justify-content: space-around; text-align: center; margin-bottom: 15px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                    <div>
                        <div style="font-size: 16px; font-weight: bold; color: #323130;">N/A</div>
                        <div style="font-size: 9px; color: #605e5c;">Scheduled Callbacks</div>
                    </div>
                    <div style="border-left: 1px solid #e0e0e0; height: 30px;"></div>
                    <div>
                        <div style="font-size: 16px; font-weight: bold; color: #323130;">0</div>
                        <div style="font-size: 9px; color: #605e5c;">Elevations</div>
                    </div>
                    <div style="border-left: 1px solid #e0e0e0; height: 30px;"></div>
                    <div>
                        <div style="font-size: 16px; font-weight: bold; color: #323130;">0</div>
                        <div style="font-size: 9px; color: #605e5c;">Complaints</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Action List Container
                st.markdown("""
                <div class="fluent-card" style="margin-bottom: 15px; padding: 15px;">
                    <h5 style="margin: 0 0 10px 0; color: #323130;">Action List</h5>
                    <table style="width: 100%; font-size: 11px; text-align: left; border-collapse: collapse;">
                        <tr style="background-color: #faf9f8; font-weight: bold; border-bottom: 1px solid #e0e0e0;">
                            <th style="padding: 5px;">Action Type</th>
                            <th style="padding: 5px;">Action Required</th>
                            <th style="padding: 5px; text-align:center;">Action Status</th>
                        </tr>
                        <tr style="border-bottom: 1px solid #f3f2f1;">
                            <td style="padding: 6px 5px; color: #d83b01;">🔴 Fraud Check Status</td>
                            <td style="padding: 6px 5px; color: #0078d4; font-weight:bold;">Run Security Check</td>
                            <td style="padding: 6px 5px; text-align:center;">[ ]</td>
                        </tr>
                        <tr>
                            <td style="padding: 6px 5px; color: #107c41;">⚙️ Sales Offer</td>
                            <td style="padding: 6px 5px; color: #0078d4; font-weight:bold;">Check Sales Offer</td>
                            <td style="padding: 6px 5px; text-align:center;">[ ]</td>
                        </tr>
                    </table>
                </div>
                """, unsafe_allow_html=True)

                # Order Management
                st.markdown("""
                <div class="fluent-card" style="margin-bottom: 15px; padding: 15px; display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: 12px; font-weight: bold; color: #323130;">Order Management (0)</span>
                    <button style="background-color: #0078d4; color: white; border: none; padding: 4px 10px; border-radius: 2px; font-size: 11px;">Get Recommendations</button>
                </div>
                """, unsafe_allow_html=True)

                # Workspace Operational Actions Trigger Container
                with st.container(border=True):
                    st.caption("⚡ Workspace Operational Actions")
                    
                    # 1. Trigger Follow-up
                    if st.button("🔔 Initiate Customer Follow-up", key="uci_followup_btn", use_container_width=True):
                        success, msg = AutomationEngine.execute_rule(
                            name="Customer Follow-up",
                            case_id=c_details['case_id'],
                            runner_func=FollowupService.initiate_followup,
                            changed_by=selected_user_name
                        )
                        if success:
                            st.success("Awaiting customer workflow triggered. Follow-up scheduled.")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"Failed: {msg}")

                    # 2. Warranty Extension
                    if st.button("🛡️ Warranty/Care Pack Request", key="uci_warranty_btn", use_container_width=True):
                        st.session_state['warranty_case_number'] = c_details['case_number']
                        st.session_state['warranty_serial'] = c_details['serial_number']
                        st.session_state['warranty_product'] = c_details['product_number']
                        st.session_state['warranty_contact'] = c_details['customer_email']
                        st.session_state['warranty_status_cur'] = c_details['warranty_status']
                        st.session_state['navigate_to'] = "Warranty Request Hub"
                        st.rerun()

                    # 3. Schedule Callback
                    with st.expander("📅 Schedule CBC Callback", expanded=False):
                        cbc_date = st.date_input("Callback Date", value=datetime.today() + timedelta(days=1), key="uci_cbc_date")
                        cbc_time = st.time_input("Callback Time", key="uci_cbc_time")
                        if st.button("Save Callback", key="uci_cbc_save", use_container_width=True):
                            dt_str = datetime.combine(cbc_date, cbc_time).strftime("%Y-%m-%d %H:%M:%S")
                            rem_dt_str = (datetime.combine(cbc_date, cbc_time) - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
                            
                            conn_cb = get_connection()
                            cursor_cb = conn_cb.cursor()
                            cursor_cb.execute("""
                                INSERT INTO callbacks (case_id, case_number, customer_id, engineer_id, callback_datetime, reminder_datetime, status)
                                VALUES (?, ?, ?, ?, ?, ?, 'Scheduled')
                            """, (c_details['case_id'], c_details['case_number'], c_details['customer_id'], c_details['engineer_id'], dt_str, rem_dt_str))
                            
                            cursor_cb.execute("UPDATE cases SET cbc_datetime = ? WHERE case_id = ?", (dt_str, c_details['case_id']))
                            conn_cb.commit()
                            conn_cb.close()
                            
                            log_action(selected_user_name, f"Scheduled customer callback for {dt_str}", case_id=c_details['case_id'])
                            st.success("Callback scheduled successfully!")
                            time.sleep(1)
                            st.rerun()

                    # 4. Notify Owner
                    if st.button("✉️ Notify Assigned Engineer", key="uci_notify_btn", use_container_width=True):
                        notif_id = NotificationService.log_change_and_notify(
                            case_id=c_details['case_id'],
                            change_type='CASE_NOTE_ADDED',
                            prev_value='None',
                            new_value='Manual notification ping',
                            changed_by=selected_user_name
                        )
                        st.success(f"Notification added. ID: {notif_id}")

                    # 5. Escalate Case
                    if st.button("🚨 Escalate to Critical SLA", key="uci_escalate_btn", use_container_width=True):
                        conn_esc = get_connection()
                        cursor_esc = conn_esc.cursor()
                        cursor_esc.execute("UPDATE cases SET priority = 'Critical', crt = 'Critical' WHERE case_id = ?", (c_details['case_id'],))
                        conn_esc.commit()
                        conn_esc.close()
                        
                        NotificationService.log_change_and_notify(
                            case_id=c_details['case_id'],
                            change_type='PRIORITY_CHANGED',
                            prev_value=c_details['priority'],
                            new_value='Critical',
                            changed_by=selected_user_name
                        )
                        st.warning("Case priority escalated to Critical!")
                        time.sleep(1)
                        st.rerun()

                    # 6. L2 Activity Pending
                    l2_label = "Remove L2 Activity pending" if c_details['l2_pending'] == 1 else "Flag L2 Activity pending"
                    if st.button(l2_label, key="uci_l2_btn", use_container_width=True):
                        new_l2 = 0 if c_details['l2_pending'] == 1 else 1
                        conn_l2 = get_connection()
                        cursor_l2 = conn_l2.cursor()
                        cursor_l2.execute("UPDATE cases SET l2_pending = ? WHERE case_id = ?", (new_l2, c_details['case_id']))
                        conn_l2.commit()
                        conn_l2.close()
                        
                        NotificationService.log_change_and_notify(
                            case_id=c_details['case_id'],
                            change_type='L2_ACTIVITY_ADDED',
                            prev_value=str(c_details['l2_pending']),
                            new_value=str(new_l2),
                            changed_by=selected_user_name
                        )
                        st.success("L2 status updated.")
                        time.sleep(1)
                        st.rerun()

        # Render sub-tab content for non-summary details
        with tab_dynamic_notes:
            with st.form("uci_notes_form"):
                note_txt = st.text_area("Add dynamic note transcript", key="uci_note_area")
                note_btn = st.form_submit_button("Add Note to Case")
            if note_btn:
                log_action(selected_user_name, f"Added Note: {note_txt}", case_id=c_details['case_id'])
                NotificationService.log_change_and_notify(
                    case_id=c_details['case_id'],
                    change_type='CASE_NOTE_ADDED',
                    prev_value='None',
                    new_value=note_txt[:30] + '...',
                    changed_by=selected_user_name
                )
                st.success("Note logged successfully.")
                time.sleep(1)
                st.rerun()

        with tab_case_info:
            st.subheader("📋 Static Case Fields")
            st.json(c_details)

        with tab_timeline:
            st.subheader("📜 System Audit History & Logs")
            
            # Sub-tabs for detailed timeline
            tab_logs, tab_f_hist, tab_cb_hist = st.tabs(["Audits", "Follow-ups", "Callbacks"])
            
            with tab_logs:
                if history_rows:
                    for h in history_rows:
                        st.markdown(f"**[{h['changed_datetime']}]** {h['changed_by']} - **{h['change_type']}**: `{h['previous_value']}` ➔ `{h['new_value']}` | *Channel: {h['notification_channel']}*")
                else:
                    st.info("No modifications recorded.")
                    
            with tab_f_hist:
                if followup_rows:
                    for f in followup_rows:
                        st.markdown(f"**Follow-up #{f['followup_number']}** | Status: `{f['status']}` | Scheduled: {f['scheduled_datetime']} | Sent: {f['sent_datetime'] or 'Pending'} | Response: {'Yes' if f['response_received'] == 1 else 'No'}")
                else:
                    st.info("No automated follow-ups scheduled.")

            with tab_cb_hist:
                if callback_rows:
                    for cb in callback_rows:
                        st.markdown(f"📅 **Callback committed for {cb['callback_datetime']}** | Status: `{cb['status']}` | Outcome: *{cb['call_outcome'] or 'None'}*")
                else:
                    st.info("No customer callbacks scheduled.")

# --------------------------------------------------------------------------------
# SCREEN 4: CASE AUTOMATION CENTER
# --------------------------------------------------------------------------------
elif nav_selection == "Case Automation Center":
    st.title("🤖 Microsoft Power Automate Automation Hub")
    st.markdown("Monitor and toggle active Power Automate flows and workflow metrics in Dataverse.")

    # Fetch automations
    autos = AutomationEngine.get_all_automations()

    # RLS/Permission check: only Managers and Admins can toggle
    can_toggle = active_role in ['Manager', 'Administrator']

    for a in autos:
        # Determine status styling
        status_color = "#107c41" if a['status'] == 'Enabled' else "#a19f9d"
        
        st.markdown(f"""
        <div style='background-color: #ffffff; padding: 20px; border-radius: 4px; border-left: 5px solid {status_color}; box-shadow: 0 1px 3px rgba(0,0,0,0.12); margin-bottom: 15px;'>
            <div style='display: flex; justify-content: space-between;'>
                <h3>{a['name']}</h3>
                <span class='badge' style='background-color: {status_color}22; color: {status_color}; border: 1px solid {status_color};'>{a['status']}</span>
            </div>
            <p style='color: #605e5c;'>{a['description']}</p>
            <div style='display: flex; gap: 30px; font-size: 14px; color: #323130;'>
                <span><b>Trigger:</b> {a['trigger']}</span>
                <span><b>Success Runs:</b> {a['success_count']}</span>
                <span><b>Failed Runs:</b> {a['fail_count']}</span>
                <span><b>Last Run:</b> {a['last_run'] or 'Never'}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        if can_toggle:
            toggle_label = "Disable Workflow" if a['status'] == 'Enabled' else "Enable Workflow"
            if st.button(toggle_label, key=f"tg_{a['automation_id']}"):
                AutomationEngine.toggle_automation(a['automation_id'], enable=(a['status'] == 'Disabled'))
                st.rerun()
        
        # Display errors if any
        if a['error_message']:
            st.error(f"⚠️ Last Run Error: {a['error_message']}")

    # Automation Health chart
    st.markdown("### Run Analytics Health Indicator")
    health_data = pd.DataFrame({
        'Automation': [a['name'] for a in autos],
        'Success Runs': [a['success_count'] for a in autos],
        'Failed Runs': [a['fail_count'] for a in autos]
    })
    st.bar_chart(health_data.set_index('Automation'))

# --------------------------------------------------------------------------------
# SCREEN 5: WARRANTY REQUEST HUB
# --------------------------------------------------------------------------------
elif nav_selection == "Warranty Request Hub":
    st.title("🛡️ Warranty & Care Pack Request Center")
    st.markdown("Power Apps request page simulation. Generates QR codes and secure request endpoints.")

    # Retrieve pre-filled session values from Case Details redirection
    case_num_init = st.session_state.get('warranty_case_number', '')
    serial_init = st.session_state.get('warranty_serial', '')
    prod_init = st.session_state.get('warranty_product', '')
    contact_init = st.session_state.get('warranty_contact', '')
    status_cur_init = st.session_state.get('warranty_status_cur', 'Out of Warranty')

    with st.form("warranty_request_form"):
        col1, col2 = st.columns(2)
        with col1:
            case_no = st.text_input("Case Number", value=case_num_init)
            serial_no = st.text_input("Serial Number", value=serial_init)
            prod_no = st.text_input("Product Number", value=prod_init)
            cust_contact = st.text_input("Customer Contact (Email/Phone)", value=contact_init)
        
        with col2:
            req_type = st.selectbox(
                "Request Type",
                options=["Warranty Extension", "Care Pack Extension", "Warranty Transfer", "Care Pack Transfer"]
            )
            curr_status = st.text_input("Current Warranty Status", value=status_cur_init)
            req_action = st.selectbox(
                "Requested Action",
                options=["Extend Coverage 1 Year", "Extend Coverage 2 Years", "Transfer Ownership", "Upgrade to Care Pack Pro"]
            )

        submit_btn = st.form_submit_button("Generate Entitlement Link & QR Code")

    if submit_btn:
        # Check database for Case ID matching case number
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT case_id, customer_id FROM cases WHERE case_number = ?", (case_no,))
        case_row = cursor.fetchone()
        conn.close()
        
        if not case_row:
            st.error("❌ Invalid Case Number. Case record must exist in Dataverse to generate request.")
        else:
            case_id = case_row['case_id']
            customer_id = case_row['customer_id']
            
            try:
                # Call service logic
                req_result = EntitlementService.CreateExtensionRequest(
                    case_id=case_id,
                    serial_number=serial_no,
                    product_number=prod_no,
                    customer_id=customer_id,
                    request_type=req_type,
                    current_status=curr_status,
                    requested_action=req_action,
                    customer_contact=cust_contact
                )
                
                st.success(f"✅ Success! Generated Request ID: **{req_result['request_id']}**")
                
                # Show QR Code
                qr_bytes = EntitlementService.GenerateQRCodeImage(req_result['qr_code_url'])
                
                col_qr, col_info = st.columns([1, 2])
                with col_qr:
                    st.image(qr_bytes, caption="Scan to access Power Apps Request form", width=250)
                with col_info:
                    st.markdown(f"**Secure Portal URL:**")
                    st.code(req_result['qr_code_url'])
                    st.markdown("""
                    **Scenario E flow simulation:**
                    - In production, scanning the QR launches a canvas Power App for the Customer.
                    - Once approved by customer/system, Dataverse updates case warranty entitlement instantly.
                    """)
                    
            except Exception as e:
                # Graceful Error Handling (Scenario E/Error Requirement)
                st.error("⚠️ System Offline Warning")
                st.error(str(e))
                # Insert queued retry log
                log_action(
                    user='System Automator',
                    action=f"Queued warranty request for retry ({req_type})",
                    case_id=case_id,
                    automation='Warranty Automation',
                    result='Queued',
                    error=str(e)
                )

    # Show active warranty requests
    st.markdown("---")
    st.subheader("📋 Active Warranty Requests (Dataverse)")
    conn = get_connection()
    query = """
        SELECT wr.request_id, c.case_number, wr.serial_number, wr.request_type, wr.request_status, wr.request_date
        FROM warranty_requests wr
        LEFT JOIN cases c ON wr.case_id = c.case_id
        ORDER BY wr.request_date DESC
    """
    df_wr = pd.read_sql_query(query, conn)
    conn.close()
    st.dataframe(df_wr, use_container_width=True)

# --------------------------------------------------------------------------------
# SCREEN 6: CBC CALLBACK CENTER
# --------------------------------------------------------------------------------
elif nav_selection == "CBC Callback Center":
    st.title("📞 Customer Callback (CBC) & Autodial Center")
    st.markdown("Assigned callbacks. Outbound dialer integration with Dynamics 365 voice concepts.")

    # Show metrics
    metrics = CallbackService.get_callback_metrics(engineer_id=(active_engineer_id if active_role == 'Engineer' else None))
    
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Total Callbacks", metrics['cbc_due'])
    with col2:
        st.metric("Completed On-Time", metrics['cbc_completed'])
    with col3:
        st.metric("Missed Commitments", metrics['cbc_missed'], delta_color="inverse")
    with col4:
        st.metric("On-Time SLA %", f"{metrics['cbc_on_time_pct']}%")
    with col5:
        st.metric("Avg Callback Delay", f"{metrics['avg_callback_delay_min']} min")

    st.markdown("---")
    
    # Fetch list of active callbacks to Dial
    up_callbacks = CallbackService.get_upcoming_callbacks(engineer_id=(active_engineer_id if active_role == 'Engineer' else None))
    
    if not up_callbacks:
        st.success("No scheduled callbacks found.")
    else:
        st.subheader("☎️ Call Outbound Dialer Launcher")
        cb_options = {f"Callback ID: {r['callback_id']} - Case {r['case_number']} ({r['customer_name']})": r for r in up_callbacks}
        selected_cb_key = st.selectbox("Select Scheduled Call to Dial", options=list(cb_options.keys()))
        selected_cb = cb_options[selected_cb_key]

        # Dialer Simulator UI
        st.markdown(f"""
        <div class='fluent-card' style='max-width: 500px; margin: auto;'>
            <h4 style='margin:0;'>Outbound Phone Panel</h4>
            <div style='text-align: center; padding: 20px 0;'>
                <h2 style='margin:0;'>{selected_cb['customer_name']}</h2>
                <p style='color: #0078d4; font-size:18px;'>{selected_cb['customer_phone']}</p>
                <p style='font-size:14px; color: #605e5c;'>Scheduled Commit: {selected_cb['callback_datetime']}</p>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Dial sequence state machine
        if 'dial_state' not in st.session_state:
            st.session_state['dial_state'] = 'Ready'
            st.session_state['dial_cb_id'] = None

        if st.session_state['dial_cb_id'] != selected_cb['callback_id']:
            st.session_state['dial_state'] = 'Ready'
            st.session_state['dial_cb_id'] = selected_cb['callback_id']

        dial_state = st.session_state['dial_state']
        
        # Color based on state
        state_colors = {
            'Ready': '#a19f9d',
            'Dialing': '#ffaa00',
            'Ringing': '#0078d4',
            'Connected': '#107c41',
            'No Answer': '#a80000',
            'Failed': '#a80000',
            'Completed': '#323130'
        }
        
        st.markdown(f"<div style='text-align: center; margin-bottom: 20px;'><span class='badge' style='background-color: {state_colors[dial_state]}22; color: {state_colors[dial_state]}; font-size: 20px; padding: 10px 20px; border: 2px solid {state_colors[dial_state]};'>{dial_state}</span></div>", unsafe_allow_html=True)

        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
            if st.button("📞 CALL CUSTOMER", use_container_width=True, disabled=(dial_state != 'Ready')):
                st.session_state['dial_state'] = 'Dialing'
                CallbackService.InitiateCall(selected_cb['callback_id'], 'Dialing')
                st.rerun()
        with col_b2:
            if st.button("🔔 Simulate Ringing", use_container_width=True, disabled=(dial_state != 'Dialing')):
                st.session_state['dial_state'] = 'Ringing'
                st.rerun()
            if st.button("🤝 Sim Answer / Connect", use_container_width=True, disabled=(dial_state != 'Ringing')):
                st.session_state['dial_state'] = 'Connected'
                CallbackService.InitiateCall(selected_cb['callback_id'], 'Connected')
                st.rerun()
        with col_b3:
            if st.button("❌ Terminate & Complete", use_container_width=True, disabled=(dial_state != 'Connected')):
                st.session_state['dial_state'] = 'Completed'
                CallbackService.InitiateCall(selected_cb['callback_id'], 'Completed')
                st.rerun()
            if st.button("🔇 Customer No Answer", use_container_width=True, disabled=(dial_state not in ['Dialing', 'Ringing'])):
                st.session_state['dial_state'] = 'No Answer'
                CallbackService.InitiateCall(selected_cb['callback_id'], 'No Answer')
                st.rerun()

        if dial_state == 'Completed':
            st.success("✅ Callback completed. Case resolved and updated in Dataverse timeline.")
            if st.button("Reset Dialer"):
                st.session_state['dial_state'] = 'Ready'
                st.rerun()

# --------------------------------------------------------------------------------
# SCREEN 7: FOLLOW-UP CENTER
# --------------------------------------------------------------------------------
elif nav_selection == "Follow-up Center":
    st.title("✉️ Customer Follow-up Manager")
    st.markdown("Monitor automated follow-up intervals, active sequences, and Copilot messages.")

    # Show configuration thresholds
    f_hours = get_config('FirstFollowupHours', '48')
    s_hours = get_config('SecondFollowupHours', '48')
    max_f = get_config('MaximumFollowups', '2')

    st.info(f"⚙️ Active follow-up policy: Wait **{f_hours}h** for 1st follow-up, **{s_hours}h** for 2nd. Max retry limits: **{max_f}** before escalation.")

    # Retrieve all follow-up files
    conn = get_connection()
    df_f = pd.read_sql_query("""
        SELECT cf.followup_id, cf.case_id, cf.case_number, cf.followup_number, 
               cf.scheduled_datetime, cf.sent_datetime, cf.response_received, 
               cf.response_datetime, cf.status, cf.escalated,
               cust.name as customer_name, cust.email as customer_email
        FROM case_followups cf
        JOIN customers cust ON cf.customer_id = cust.customer_id
        ORDER BY cf.scheduled_datetime DESC
    """, conn)
    conn.close()

    # Split into statuses
    col_sc, col_se, col_cr, col_es = st.columns(4)
    with col_sc:
        st.subheader("📅 Scheduled")
        st.dataframe(df_f[df_f['status'] == 'Scheduled'][['case_number', 'customer_name', 'followup_number']], use_container_width=True)
    with col_se:
        st.subheader("🚀 Sent")
        st.dataframe(df_f[df_f['status'] == 'Sent'][['case_number', 'customer_name', 'sent_datetime']], use_container_width=True)
    with col_cr:
        st.subheader("💬 Responded")
        st.dataframe(df_f[df_f['status'] == 'Customer Responded'][['case_number', 'customer_name', 'response_datetime']], use_container_width=True)
    with col_es:
        st.subheader("🚨 Escalated")
        st.dataframe(df_f[df_f['status'] == 'Escalated'][['case_number', 'customer_name']], use_container_width=True)

    # Simulation Controls for Demo Scenario B
    st.markdown("---")
    st.subheader("🛠️ Demo Follow-up Simulation Tools")
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT cf.*, c.case_number, cust.name as customer_name FROM case_followups cf JOIN cases c ON cf.case_id = c.case_id JOIN customers cust ON cf.customer_id = cust.customer_id WHERE cf.status IN ('Scheduled', 'Sent')")
    sched_list = [f"Followup ID {r['followup_id']} - Case {r['case_number']} (Num {r['followup_number']}) - Status: {r['status']}" for r in cursor.fetchall()]
    conn.close()

    if sched_list:
        selected_sim_f = st.selectbox("Select Follow-up to trigger", sched_list)
        f_id = int(selected_sim_f.split("Followup ID ")[1].split(" - ")[0])
        f_status = selected_sim_f.split("Status: ")[1]

        c_sim1, c_sim2 = st.columns(2)
        with c_sim1:
            if f_status == 'Scheduled':
                if st.button("🚀 Force Dispatch Follow-up email", use_container_width=True):
                    # Find case id
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT case_id FROM case_followups WHERE followup_id = ?", (f_id,))
                    c_id = cursor.fetchone()[0]
                    conn.close()
                    
                    FollowupService.simulate_time_elapsed_and_send(c_id)
                    st.success("Follow-up email dispatched via Copilot Agent!")
                    time.sleep(1)
                    st.rerun()
            elif f_status == 'Sent':
                if st.button("💬 Simulate Customer Response", use_container_width=True):
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT case_id FROM case_followups WHERE followup_id = ?", (f_id,))
                    c_id = cursor.fetchone()[0]
                    conn.close()
                    
                    FollowupService.simulate_customer_reply(c_id, "We did the bios restart. Issue resolved!")
                    st.success("Customer reply received. Case moved back to Active status in D365.")
                    time.sleep(1)
                    st.rerun()
        with c_sim2:
            if f_status == 'Sent':
                if st.button("🚨 Simulate SLA Breach (Auto Escalate)", use_container_width=True):
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT case_id FROM case_followups WHERE followup_id = ?", (f_id,))
                    c_id = cursor.fetchone()[0]
                    conn.close()
                    
                    FollowupService.trigger_escalation(c_id)
                    st.warning("Customer ignored notifications. Automated escalation rules triggered in D365.")
                    time.sleep(1)
                    st.rerun()
    else:
        st.info("No active followups in Scheduled or Sent state.")

# --------------------------------------------------------------------------------
# SCREEN 8: IVR SIMULATOR
# --------------------------------------------------------------------------------
elif nav_selection == "CTI Customer Search (D365 CC)":
    st.title("📞 Omnichannel Workspace - CTI Customer Identification")
    st.markdown("Integrates the Genesys CTI toolbar, D365 search grid, and account details pane side-by-side.")

    # Split workspace into 3 columns matching the D365 layout
    col_cti, col_search, col_acc = st.columns([1, 2.2, 0.8])

    with col_cti:
        st.markdown("""
        <div class="fluent-card" style="padding: 15px; margin-bottom: 10px;">
            <h4 style="margin: 0 0 5px 0; color: #323130;">Genesys Cloud CTI</h4>
            <span style="font-size: 11px; color: #605e5c; display:block; margin-bottom: 10px;">CTI Connector - India</span>
            <div style="background-color: #faf9f8; border: 1px solid #e0e0e0; padding: 10px; border-radius: 4px; margin-bottom: 10px;">
                <strong style="font-size: 13px; display:block; color: #323130;">Saifoddin A Quraishi</strong>
                <span style="font-size: 11px; color: #605e5c; display:block; word-break: break-all;">saifoddin.a.quraishi@hp.com</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        status_choice = st.selectbox(
            "Agent Queue Status",
            options=["On Queue", "Available", "Busy", "Away", "Break", "Log Out"],
            index=1,
            key="cti_status_select"
        )
        
        if status_choice == "Available":
            st.markdown("🟢 **Available** (On Queue)")
        elif status_choice == "On Queue":
            st.markdown("⚪ **On Queue**")
        else:
            st.markdown(f"🔴 **{status_choice}**")

        st.markdown("---")
        st.subheader("📞 Call Controls")
        
        # Phone call dial input
        dial_number = st.text_input("Enter Phone Number to Dial/Simulate Call", value="+15550192834")
        
        if st.button("Simulate Incoming Call Hook", use_container_width=True):
            st.session_state['cti_dial_phone'] = dial_number
            # Prefill the search grid with this phone number
            st.session_state['search_phone_val'] = dial_number
            # Fetch customer automatically
            cust = IVRCaseService.FindCustomer(dial_number)
            if cust:
                st.session_state['cti_active_customer'] = cust['customer_id']
                st.session_state['search_email_val'] = cust['email']
                st.session_state['search_company_val'] = cust['name']
                st.success(f"Incoming call detected from {cust['name']}!")
                time.sleep(0.5)
                st.rerun()
            else:
                st.warning("Incoming call from unknown number. Enter details in search grid.")
                st.session_state['cti_active_customer'] = None
                st.rerun()

    with col_search:
        # Title bar for Customer Information card
        st.markdown("""
        <div style="background-color: #0078d4; padding: 12px 20px; border-radius: 4px 4px 0 0; margin-bottom: 0px;">
            <strong style="color: white; font-size: 16px;">Customer Information</strong>
        </div>
        """, unsafe_allow_html=True)
        
        # Initialize text inputs values
        email_val = st.session_state.get('search_email_val', '')
        phone_val = st.session_state.get('search_phone_val', '+91 ')
        company_val = st.session_state.get('search_company_val', '')
        serial_val = st.session_state.get('search_serial_val', '5CG12345AB') # prefilled default matching seeded serial
        
        with st.container(border=True):
            # Row 1: Email | Serial Number | Country
            r1_c1, r1_c2, r1_c3 = st.columns(3)
            with r1_c1:
                search_email = st.text_input("EMAIL", value=email_val, key="cti_search_email")
            with r1_c2:
                search_serial = st.text_input("SERIAL NUMBER", value=serial_val, key="cti_search_serial")
            with r1_c3:
                search_country = st.selectbox("COUNTRY", options=["India", "United States", "United Kingdom", "Germany", "Singapore"], index=0, key="cti_search_country")
                
            # Row 2: Company | Zip/Postal | City
            r2_c1, r2_c2, r2_c3 = st.columns(3)
            with r2_c1:
                search_company = st.text_input("COMPANY", value=company_val, key="cti_search_company")
            with r2_c2:
                search_zip = st.text_input("ZIP/POSTAL", value="560001", key="cti_search_zip")
            with r2_c3:
                search_city = st.text_input("CITY", value="Bangalore", key="cti_search_city")
                
            # Row 3: Phone | Asset Tag | Contract ID
            r3_c1, r3_c2, r3_c3 = st.columns(3)
            with r3_c1:
                search_phone = st.text_input("PHONE", value=phone_val, key="cti_search_phone")
            with r3_c2:
                search_asset = st.text_input("ASSET TAG", value="AST-990821", key="cti_search_asset")
            with r3_c3:
                search_contract = st.text_input("CONTRACT ID", value="CON-8829", key="cti_search_contract")
                
            # Row 4: Transaction Type | Transaction ID | Opsi
            r4_c1, r4_c2, r4_c3 = st.columns(3)
            with r4_c1:
                search_tx_type = st.selectbox("TRANSACTION TYPE", options=["Case", "Call Inquiry", "Escalation", "Repair Request"], index=0, key="cti_search_tx")
            with r4_c2:
                search_tx_id = st.text_input("TRANSACTION ID", value="TX-10023", key="cti_search_tx_id")
            with r4_c3:
                search_opsi = st.text_input("OPSI", value="OPSI-992", key="cti_search_opsi")
                
            # Row 5: License Key | Pin
            r5_c1, r5_c2, r5_c3 = st.columns(3)
            with r5_c1:
                search_license = st.text_input("LICENSE KEY", value="LIC-9988-2234", key="cti_search_lic")
            with r5_c2:
                search_pin = st.text_input("PIN", value="1234", key="cti_search_pin")
            with r5_c3:
                st.write("") # Spacer

            # Action Buttons
            f_col1, f_col2, f_col3 = st.columns([1, 1, 1])
            with f_col1:
                if st.button("Clear all", key="cti_clear_btn", use_container_width=True):
                    # Clear session state cache
                    for key in ['search_email_val', 'search_phone_val', 'search_company_val', 'search_serial_val', 'cti_active_customer', 'cti_ivr_case_result']:
                        if key in st.session_state:
                            del st.session_state[key]
                    st.rerun()
            with f_col2:
                if st.button("Create Case", key="cti_create_case_btn", type="secondary", use_container_width=True):
                    if not search_phone or search_phone == "+91 ":
                        st.error("Phone number required to create case.")
                    else:
                        # Auto-create case using IVR routing service
                        res = IVRCaseService.CreateCase(
                            phone=search_phone,
                            serial_number=search_serial,
                            problem_category="Hardware",
                            customer_name=search_company if search_company else "Workspace Caller"
                        )
                        st.session_state['cti_ivr_case_result'] = res
                        st.rerun()
            with f_col3:
                if st.button("Search", key="cti_search_btn", type="primary", use_container_width=True):
                    # Lookup in DB by Phone or Email
                    cust = None
                    if search_phone and search_phone != "+91 ":
                        cust = IVRCaseService.FindCustomer(search_phone)
                    if not cust and search_email:
                        conn = get_connection()
                        cursor = conn.cursor()
                        cursor.execute("SELECT * FROM customers WHERE email = ?", (search_email,))
                        row = cursor.fetchone()
                        conn.close()
                        if row:
                            cust = dict(row)
                            
                    if cust:
                        st.session_state['cti_active_customer'] = cust['customer_id']
                        st.session_state['search_email_val'] = cust['email']
                        st.session_state['search_phone_val'] = cust['phone']
                        st.session_state['search_company_val'] = cust['name']
                        st.success(f"Customer identified: {cust['name']}")
                    else:
                        st.error("No customer records found matching phone/email.")
                        st.session_state['cti_active_customer'] = None
                    st.rerun()

        # Display Case creation results inside the center container if triggered
        if 'cti_ivr_case_result' in st.session_state:
            res = st.session_state['cti_ivr_case_result']
            st.markdown("---")
            st.subheader("📋 Case Action Outcomes")
            if res.get('existing_case_found', False):
                st.warning(f"⚠️ Existing case found: **{res['case_number']}**")
                st.markdown(f"**Customer:** {res['customer_name']}")
                
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("🔗 Continue / Resume Existing Case", key="cti_resume_case"):
                        st.session_state['warranty_case_number'] = res['case_number']
                        del st.session_state['cti_ivr_case_result']
                        st.session_state['navigate_to'] = "Case Details & Actions"
                        st.rerun()
                with c2:
                    if st.button("➕ Force Create New Case anyway", key="cti_force_create"):
                        # Bypass and insert
                        conn = get_connection()
                        cursor = conn.cursor()
                        cursor.execute("SELECT customer_id FROM customers WHERE name = ?", (res['customer_name'],))
                        customer_id = cursor.fetchone()[0]
                        cursor.execute("SELECT COUNT(*) FROM cases")
                        case_count = cursor.fetchone()[0]
                        new_case_number = f"CAS-{100001 + case_count}"
                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        cursor.execute("""
                            INSERT INTO cases (case_number, customer_id, serial_number, product_number, engineer_id, queue_id, status, priority, issue_category, created_date, modified_date, source)
                            VALUES (?, ?, ?, 'HP-PRO-MOCK-IVR', 1, 1, 'New', 'Normal', 'Hardware', ?, ?, 'IVR')
                        """, (new_case_number, customer_id, search_serial, now_str, now_str))
                        case_id = cursor.lastrowid
                        conn.commit()
                        conn.close()
                        
                        log_action('CTI Agent', f"Force created new case {new_case_number} despite existing open case", case_id=case_id)
                        st.success(f"Generated new Case file: **{new_case_number}**!")
                        del st.session_state['cti_ivr_case_result']
                        st.rerun()
            else:
                st.success(f"✅ Success! Routed Customer Profile: **{res['customer_name']}**")
                st.success(f"Case Auto-provisioned: **{res['case_number']}**")
                if st.button("Open Case details", key="cti_open_new_case"):
                    del st.session_state['cti_ivr_case_result']
                    st.session_state['navigate_to'] = "Case Details & Actions"
                    st.rerun()

# --------------------------------------------------------------------------------
# SCREEN 9: ADMINISTRATION PANEL
# --------------------------------------------------------------------------------
elif nav_selection == "Administration Panel":
    st.title("⚙️ System Administration Console")
    
    # RLS/Admin Role restriction check
    if active_role != "Administrator":
        st.error("🔒 Security Restriction: Only users with the Administrator role can modify system settings or access audit logs.")
    else:
        st.subheader("🔧 Core Platform Settings")
        configs = get_all_configs()
        
        with st.form("admin_settings_form"):
            col1, col2 = st.columns(2)
            with col1:
                f_hours = st.text_input("First Follow-up Interval (Hours)", value=configs['FirstFollowupHours']['value'])
                s_hours = st.text_input("Second Follow-up Interval (Hours)", value=configs['SecondFollowupHours']['value'])
                max_f = st.text_input("Maximum Follow-up Retries", value=configs['MaximumFollowups']['value'])
            with col2:
                cbc_rem = st.text_input("CBC Reminder Lead Time (Minutes)", value=configs['CBCLeadTimeMinutes']['value'])
                ent_url = st.text_input("Entitlement Base URL", value=configs['EntitlementBaseURL']['value'])
                ent_status = st.selectbox("Simulated Entitlement Service Status", options=["Online", "Offline"])

            save_settings = st.form_submit_button("Commit Changes to Dataverse")

        if save_settings:
            set_config('FirstFollowupHours', f_hours)
            set_config('SecondFollowupHours', s_hours)
            set_config('MaximumFollowups', max_f)
            set_config('CBCLeadTimeMinutes', cbc_rem)
            set_config('EntitlementBaseURL', ent_url)
            set_config('EntitlementServiceStatus', ent_status)
            st.success("Configuration updated successfully.")
            st.rerun()

        # Audit Log viewer
        st.markdown("---")
        st.subheader("📜 System Audit Logs")
        
        conn = get_connection()
        df_audit = pd.read_sql_query("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 100", conn)
        conn.close()
        
        st.dataframe(df_audit, use_container_width=True)

# --------------------------------------------------------------------------------
# SCREEN 10: INTEGRATION READINESS
# --------------------------------------------------------------------------------
elif nav_selection == "Integration Readiness":
    st.title("⚡ Integration Readiness Matrix")
    st.markdown("Review the technical readiness mapping for moving this prototype to enterprise production.")
    
    readiness_data = [
        {"Integration Name": "Dynamics Case Management", "Current Status": "Connected / Mocked", "Technology": "Dataverse Web API", "API Required": "Dataverse REST SDK", "Production Ready": "Yes (Requires Env mapping)"},
        {"Integration Name": "Warranty Entitlement API", "Current Status": "Mocked Service", "Technology": "EntitlementService Class", "API Required": "REST / SOAP Partner API", "Production Ready": "No (Requires API Endpoint)"},
        {"Integration Name": "IVR Case Creation", "Current Status": "Simulated Voice Handshake", "Technology": "Dynamics CC Voice Integration", "API Required": "Azure Communication Services Webhook", "Production Ready": "No (Requires CC voice config)"},
        {"Integration Name": "Outbound Dialing", "Current Status": "Simulated call status widget", "Technology": "Contact Center Telephony", "API Required": "Outbound SIP / WebRTC Dialer", "Production Ready": "No (Telephony carrier setup)"},
        {"Integration Name": "Teams Notifications", "Current Status": "Simulated dispatch logging", "Technology": "Power Automate Teams Connector", "API Required": "Microsoft Teams Graph Webhook", "Production Ready": "Yes (Needs Connector install)"},
        {"Integration Name": "Outlook Email Notifications", "Current Status": "Simulated dispatch logging", "Technology": "Power Automate Outlook Connector", "API Required": "Office 365 Mail API", "Production Ready": "Yes (Needs standard client auth)"}
    ]
    st.dataframe(pd.DataFrame(readiness_data), use_container_width=True)

# --------------------------------------------------------------------------------
# SCREEN 11: POWER BI DATA MODEL
# --------------------------------------------------------------------------------
elif nav_selection == "Power BI Data Model":
    st.title("📊 Power BI Star-Schema & Measures Representation")
    st.markdown("Detailed breakdown of the Data Warehouse architecture supporting the analytics layer.")

    st.markdown("""
    ### Star-Schema Architectural Layout
    
    ```mermaid
    erDiagram
        FactCases }|--|| DimEngineer : "assigned_to"
        FactCases }|--|| DimCustomer : "customer_of"
        FactCases }|--|| DimDate : "created_on"
        FactCases }|--|| DimQueue : "routed_to"
        
        FactCallbacks }|--|| DimEngineer : "executed_by"
        FactCallbacks }|--|| DimCustomer : "associated_with"
        
        FactFollowups }|--|| DimCustomer : "sent_to"
        FactFollowups }|--|| DimEngineer : "monitored_by"
        
        FactNotifications }|--|| DimEngineer : "received_by"
    ```
    """)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
        #### Fact Tables
        
        1. **FactCases**
           - CaseKey (FK)
           - CustomerKey (FK)
           - EngineerKey (FK)
           - DateKey (FK)
           - QueueKey (FK)
           - Priority
           - AgeInDays
           - ResolutionTimeMinutes
           - SLAStatus (Met/Breached)
           
        2. **FactCallbacks**
           - CallbackKey (FK)
           - CaseKey (FK)
           - CustomerKey (FK)
           - EngineerKey (FK)
           - CallbackDelayMinutes
           - Status (Completed/Missed)
        """)
    with c2:
        st.markdown("""
        #### Dimension Tables
        
        1. **DimEngineer**
           - EngineerKey (PK)
           - EngineerName
           - Email
           - Team
           - SecurityRole
           
        2. **DimCustomer**
           - CustomerKey (PK)
           - CustomerName
           - Telephone
           - Email
           - PreferredLanguage
        """)

    st.markdown("---")
    st.subheader("📐 Key DAX Measures defined in Power BI Desktop file")
    
    st.code("""
    -- 1. SLA Met Percentage
    SLA Met % = 
    DIVIDE(
        CALCULATE(COUNTROWS(FactCases), FactCases[SLAStatus] = "Met"),
        COUNTROWS(FactCases),
        0
    ) * 100
    """, language="sql")
    
    st.code("""
    -- 2. Average Delay in Callback Commitment
    Average Callback Delay = 
    AVERAGE(FactCallbacks[CallbackDelayMinutes])
    """, language="sql")

    st.code("""
    -- 3. Number of Cases Reopened
    Reopened Cases Count = 
    CALCULATE(
        COUNTROWS(FactCases), 
        FactCases[AwaitingCustomer] = 0, 
        FactCases[PreviousStatus] = "Awaiting Customer"
    )
    """, language="sql")

# Handle navigation changes pushed by session state
if 'navigate_to' in st.session_state:
    target = st.session_state['navigate_to']
    del st.session_state['navigate_to']
    # Update navigation widget choice and reload (handled by streamlit query parameters or simple state check next load)
    # Streamlit query params can be used, but simple session rerun does the trick:
    st.info(f"Navigating to {target}. Please select it in the sidebar.")
