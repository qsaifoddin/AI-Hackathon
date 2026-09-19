import os
import sys

# Ensure root directory is on python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Auto-initialize database schema on startup
from app.db.database import init_db, get_connection
init_db()

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from app.db.database import get_connection
from app.services.ai_copilot import AICopilotService
from app.services.sla_predictor import SLAPredictorService
from app.services.escalation import EscalationService
from app.services.parts import PartsService
from app.services.ivr import IVRCaseService
from app.services.entitlement import EntitlementService
from app.services.followup import FollowupService
from app.services.callback import CallbackService
from app.services.notification import NotificationService
from app.services.audit import log_action

app = FastAPI(
    title="HP Support Automation & Dataverse REST API",
    description="Production-grade API endpoints exposing Dataverse mock records, AI Copilot services, SLA breach risk prediction, L2/L3 escalations, parts tracking, and Power Automate webhooks.",
    version="2.0.0"
)

# Pydantic Schemas
class IVRCallRequest(BaseModel):
    phone: str
    serial_number: str
    problem_category: Optional[str] = "Hardware"
    customer_name: Optional[str] = None

class EscalationRequest(BaseModel):
    target_tier: str = "Tier 2"
    reason: str = "Complex hardware fault requiring L2 escalation"
    requested_by: str = "Power Automate Agent"

class PartOrderRequest(BaseModel):
    case_id: int
    part_id: int
    quantity: int = 1
    shipping_priority: str = "Express"
    warehouse_region: str = "North America"
    requested_by: str = "D365 Engineer"

class WebhookCaseUpdateRequest(BaseModel):
    case_number: str
    updated_field: str
    old_value: str
    new_value: str
    source_system: str = "Power Automate Cloud Flow"

# 1. System Health
@app.get("/api/v1/health")
def get_health():
    return {
        "status": "Online",
        "service": "HP Support Automation & Dataverse REST API",
        "timestamp": datetime.now().isoformat(),
        "database_connected": True
    }

# 2. Case Management Endpoints
@app.get("/api/v1/cases")
def list_cases(status: Optional[str] = None, priority: Optional[str] = None, limit: int = 50):
    conn = get_connection()
    cursor = conn.cursor()
    sql = "SELECT c.*, cust.name as customer_name, e.name as engineer_name FROM cases c JOIN customers cust ON c.customer_id = cust.customer_id LEFT JOIN engineers e ON c.engineer_id = e.engineer_id WHERE 1=1"
    params = []
    if status:
        sql += " AND c.status = ?"
        params.append(status)
    if priority:
        sql += " AND c.priority = ?"
        params.append(priority)
    sql += " ORDER BY c.case_id DESC LIMIT ?"
    params.append(limit)

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()
    return {"total": len(rows), "cases": [dict(r) for r in rows]}

@app.get("/api/v1/cases/{case_id}")
def get_case_details(case_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT c.*, cust.name as customer_name, cust.email as customer_email, e.name as engineer_name FROM cases c JOIN customers cust ON c.customer_id = cust.customer_id LEFT JOIN engineers e ON c.engineer_id = e.engineer_id WHERE c.case_id = ?", (case_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")
    return dict(row)

# 3. AI Copilot Endpoints
@app.post("/api/v1/cases/{case_id}/ai-propose-resolution")
def ai_propose_resolution(case_id: int):
    result = AICopilotService.propose_resolution(case_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result

@app.post("/api/v1/ai/summarize-transcript")
def ai_summarize_transcript(transcript: str):
    result = AICopilotService.summarize_transcript(transcript)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result

# 4. SLA Breach Risk Prediction Endpoint
@app.post("/api/v1/cases/{case_id}/predict-sla-risk")
def predict_sla_risk(case_id: int):
    result = SLAPredictorService.predict_risk(case_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result

# 5. L2/L3 Escalation Endpoint
@app.post("/api/v1/cases/{case_id}/escalate")
def escalate_case(case_id: int, req: EscalationRequest):
    result = EscalationService.escalate_case(case_id, req.target_tier, req.reason, req.requested_by)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result

# 6. Parts Inventory & Ordering Endpoints
@app.get("/api/v1/parts/catalog")
def search_parts_catalog(query: Optional[str] = None, category: Optional[str] = "All"):
    return {"parts": PartsService.search_parts(query, category)}

@app.post("/api/v1/parts/order")
def place_part_order(req: PartOrderRequest):
    result = PartsService.place_order(req.case_id, req.part_id, req.quantity, req.shipping_priority, req.warehouse_region, req.requested_by)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result

@app.get("/api/v1/cases/{case_id}/parts-orders")
def get_case_parts_orders(case_id: int):
    return {"orders": PartsService.get_case_orders(case_id)}

# 7. IVR Call Intake Endpoint
@app.post("/api/v1/ivr/incoming-call")
def ivr_incoming_call(req: IVRCallRequest):
    return IVRCaseService.CreateCase(req.phone, req.serial_number, req.problem_category, req.customer_name)

# 8. Power Automate Inbound Webhook
@app.post("/api/v1/webhooks/power-automate/case-update")
def power_automate_webhook(req: WebhookCaseUpdateRequest):
    log_action(
        user=req.source_system,
        action=f"Power Automate Webhook: {req.updated_field} updated",
        case_id=None,
        automation="Power Automate Cloud Flow",
        new_value=f"Case: {req.case_number} | {req.old_value} -> {req.new_value}",
        result="Success"
    )
    return {
        "status": "Received & Processed",
        "webhook_id": f"WH-PA-{datetime.now().strftime('%M%S%f')[:8]}",
        "case_number": req.case_number,
        "processed_at": datetime.now().isoformat()
    }
