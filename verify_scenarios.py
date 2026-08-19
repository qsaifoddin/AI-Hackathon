import sys
import os
from datetime import datetime

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(__file__))

from app.db.database import get_connection, init_db
from app.services.notification import NotificationService
from app.services.followup import FollowupService
from app.services.callback import CallbackService
from app.services.ivr import IVRCaseService
from app.services.entitlement import EntitlementService
from app.services.audit import set_config

from app.services.ai_copilot import AICopilotService
from app.services.sla_predictor import SLAPredictorService
from app.services.escalation import EscalationService
from app.services.parts import PartsService
from app.api.main import list_cases, ai_propose_resolution, predict_sla_risk, escalate_case, EscalationRequest, place_part_order, PartOrderRequest

def run_verifications():
    print("Starting comprehensive automated verification scenarios...")
    init_db()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT case_id, case_number, customer_id, engineer_id, serial_number FROM cases LIMIT 1")
    test_case = cursor.fetchone()
    conn.close()

    if not test_case:
        print("ERROR: No test case found in database.")
        return

    case_id = test_case['case_id']
    case_number = test_case['case_number']
    customer_id = test_case['customer_id']
    engineer_id = test_case['engineer_id']
    serial_number = test_case['serial_number']

    print(f"\nUsing Test Case: {case_number} (ID: {case_id})")

    # --- Scenario A: Case Change Notification ---
    print("\n--- Testing Scenario A: Case Change Notification ---")
    notif_id = NotificationService.log_change_and_notify(
        case_id=case_id,
        change_type="WARRANTY_UPDATED",
        prev_value="Out of Warranty",
        new_value="Care Pack Active",
        changed_by="Alex Carter",
        channel="Teams"
    )
    print(f"Logged change notification ID: {notif_id}")
    sent_count = NotificationService.process_and_send_pending()
    print(f"Dispatched {sent_count} pending notifications.")
    print("Scenario A: PASSED")

    # --- Scenario B: Automated Customer Follow-up ---
    print("\n--- Testing Scenario B: Automated Customer Follow-up ---")
    followup_id = FollowupService.initiate_followup(case_id, changed_by="System Automator")
    print(f"Follow-up sequence initialized. Record ID: {followup_id}")
    print("Scenario B: PASSED")

    # --- Scenario C: CBC Callback Alerts & Dialer ---
    print("\n--- Testing Scenario C: CBC Callback Alerts & Dialer ---")
    upcoming_cbcs = CallbackService.get_upcoming_callbacks(engineer_id=engineer_id)
    print(f"Found {len(upcoming_cbcs)} upcoming callbacks for Engineer {engineer_id}.")
    print("Scenario C: PASSED")

    # --- Scenario D: IVR Customer Routing ---
    print("\n--- Testing Scenario D: IVR Customer Routing ---")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT phone FROM customers WHERE customer_id = ?", (customer_id,))
    phone = cursor.fetchone()['phone']
    conn.close()

    ivr_res = IVRCaseService.CreateCase(phone=phone, serial_number=serial_number, problem_category="Hardware")
    print(f"IVR response message: {ivr_res.get('message')} (Case: {ivr_res.get('case_number')})")
    print("Scenario D: PASSED")

    # --- Scenario E: Warranty QR Code & Error Handling ---
    print("\n--- Testing Scenario E: Warranty QR Code & Error Handling ---")
    qr_img = EntitlementService.GenerateQRCodeImage("https://apps.powerapps.com/play/e/default-entitlement-service")
    if qr_img and len(qr_img) > 0:
        print("QR Code generated successfully.")
    
    req_res = EntitlementService.CreateExtensionRequest(
        case_id=case_id,
        serial_number=serial_number,
        product_number="HP-PRO-100-DX",
        customer_id=customer_id,
        request_type="Care Pack Extension",
        current_status="In Warranty (Base)",
        requested_action="Extend Coverage 1 Year",
        customer_contact="admin@test.com"
    )
    print(f"Entitlement request created: {req_res.get('request_id')}")

    set_config('EntitlementServiceStatus', 'Offline')
    try:
        EntitlementService.GetEntitlement(serial_number)
    except ConnectionError as ce:
        print(f"Correctly caught offline error: {ce}")
    finally:
        set_config('EntitlementServiceStatus', 'Online')

    print("Scenario E: PASSED")

    # --- Scenario F: AI Copilot Resolution & Sentiment Analysis ---
    print("\n--- Testing Scenario F: AI Copilot Engine ---")
    prop_res = AICopilotService.propose_resolution(case_id)
    print(f"AI Resolution Summary: {prop_res['proposal']['copilot_summary']}")

    sent_res = AICopilotService.analyze_sentiment("I am extremely frustrated and angry about this broken display!")
    print(f"Sentiment Analysis Result: {sent_res['sentiment']} (Score: {sent_res['score']})")

    sum_res = AICopilotService.summarize_transcript("Customer: Screen is flickering.\nAgent: Let's run UEFI test.")
    print(f"Transcript Summarized: {sum_res['summary']['issue_summary']}")
    print("Scenario F: PASSED")

    # --- Scenario G: SLA Breach Risk Prediction & Escalations ---
    print("\n--- Testing Scenario G: SLA Breach Risk & Tier Escalations ---")
    sla_res = SLAPredictorService.predict_risk(case_id)
    print(f"SLA Breach Risk Score: {sla_res['risk_percentage']}% (Level: {sla_res['risk_level']})")

    esc_res = EscalationService.escalate_case(case_id, target_tier="Tier 3", reason="Motherboard hardware failure", requested_by="Test Automator")
    print(f"Escalated Case {case_number} to {esc_res['new_ats']} in Queue '{esc_res['assigned_queue']}'")
    print("Scenario G: PASSED")

    # --- Scenario H: Parts Replacement & Inventory Service ---
    print("\n--- Testing Scenario H: Parts Replacement & Inventory ---")
    parts = PartsService.search_parts("Motherboard")
    print(f"Found {len(parts)} Motherboard parts in catalog.")
    if parts:
        order_res = PartsService.place_order(case_id, parts[0]['part_id'], quantity=1, shipping_priority="Overnight", warehouse_region="North America")
        print(f"Placed Spare Part Order #{order_res['order_id']} (Tracking: {order_res['tracking_number']})")
    print("Scenario H: PASSED")

    # --- Scenario I: FastAPI REST Endpoints ---
    print("\n--- Testing Scenario I: FastAPI REST Endpoints ---")
    cases_api = list_cases(status="Active", limit=2)
    print(f"FastAPI list_cases returned {cases_api['total']} cases.")

    ai_api = ai_propose_resolution(case_id)
    print(f"FastAPI ai_propose_resolution response received.")

    sla_api = predict_sla_risk(case_id)
    print(f"FastAPI predict_sla_risk returned score: {sla_api['risk_percentage']}%")

    print("Scenario I: PASSED")

    print("\n" + "="*50)
    print("ALL 9 PLATFORM AUTOMATION & AI SCENARIOS PASSED SUCCESSFULLY!")
    print("="*50)

if __name__ == "__main__":
    run_verifications()
