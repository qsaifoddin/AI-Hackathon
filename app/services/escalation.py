import sqlite3
from datetime import datetime
from app.db.database import get_connection
from app.services.audit import log_action
from app.services.notification import NotificationService

class EscalationService:
    @staticmethod
    def escalate_case(case_id, target_tier="Tier 2", reason="Complex hardware failure", requested_by="Alex Carter"):
        """
        L2/L3 Case Escalation Engine.
        Reassigns case to specialized queues (e.g. Critical Software & OS or Enterprise Server Priority),
        bumps priority/CRT status to Critical, logs audit trail, and dispatches real-time notification cards.
        """
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT case_number, priority, ats, crt, queue_id FROM cases WHERE case_id = ?", (case_id,))
        case_row = cursor.fetchone()

        if not case_row:
            conn.close()
            return {"success": False, "error": "Case not found"}

        case = dict(case_row)
        old_ats = case['ats']
        old_priority = case['priority']

        # Determine target queue based on tier
        if target_tier in ["Tier 3", "L3"]:
            target_queue_name = "Enterprise Server Priority"
            new_ats = "Tier 3"
            new_crt = "Critical"
            new_priority = "Critical"
        else:
            target_queue_name = "Critical Software & OS"
            new_ats = "Tier 2"
            new_crt = "Elevated"
            new_priority = "High" if old_priority != "Critical" else "Critical"

        cursor.execute("SELECT queue_id FROM queues WHERE name = ?", (target_queue_name,))
        q_row = cursor.fetchone()
        new_queue_id = q_row[0] if q_row else 4

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Update Case in Dataverse
        cursor.execute("""
            UPDATE cases
            SET ats = ?, crt = ?, priority = ?, queue_id = ?, l2_pending = 1, modified_date = ?
            WHERE case_id = ?
        """, (new_ats, new_crt, new_priority, new_queue_id, now_str, case_id))

        conn.commit()
        conn.close()

        # Log change notification to owner/team via NotificationService
        NotificationService.log_change_and_notify(
            case_id=case_id,
            change_type=f"ESCALATED_{new_ats.replace(' ', '_').upper()}",
            prev_value=f"ATS: {old_ats} | Priority: {old_priority}",
            new_value=f"ATS: {new_ats} | Queue: {target_queue_name} | Reason: {reason}",
            changed_by=requested_by,
            channel="Teams"
        )

        log_action(
            user=requested_by,
            action=f"Escalated Case to {new_ats}",
            case_id=case_id,
            automation="L2/L3 Escalation Engine",
            new_value=f"Target Queue: {target_queue_name} | Reason: {reason}",
            result="Success"
        )

        return {
            "success": True,
            "case_id": case_id,
            "case_number": case['case_number'],
            "new_ats": new_ats,
            "new_crt": new_crt,
            "new_priority": new_priority,
            "assigned_queue": target_queue_name,
            "escalation_reason": reason,
            "escalated_at": now_str
        }
