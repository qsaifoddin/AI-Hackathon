import sqlite3
from datetime import datetime, timedelta
from app.db.database import get_connection
from app.services.audit import log_action

class SLAPredictorService:
    @staticmethod
    def predict_risk(case_id):
        """
        SLA Breach Risk Predictor Engine.
        Calculates risk score (0-100%), time remaining, risk status badge,
        and contributing risk factors.
        """
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.*, e.name as engineer_name
            FROM cases c
            LEFT JOIN engineers e ON c.engineer_id = e.engineer_id
            WHERE c.case_id = ?
        """, (case_id,))
        case_row = cursor.fetchone()
        conn.close()

        if not case_row:
            return {"success": False, "error": "Case not found"}

        case = dict(case_row)
        prio = case['priority']
        status = case['status']
        created_str = case['created_date']
        crt = case['crt']
        l2_pending = case['l2_pending']
        awaiting_customer = case['awaiting_customer']

        if status in ['Resolved', 'Closed']:
            return {
                "success": True,
                "case_number": case['case_number'],
                "risk_percentage": 0,
                "risk_level": "Met / Closed",
                "time_remaining_hrs": 0,
                "risk_factors": ["Case already resolved or closed."]
            }

        # Resolution SLA limits in hours based on priority
        limits = {'Critical': 4, 'High': 12, 'Normal': 48, 'Low': 96}
        limit_hrs = limits.get(prio, 48)

        created_dt = datetime.strptime(created_str, "%Y-%m-%d %H:%M:%S")
        elapsed_hrs = (datetime.now() - created_dt).total_seconds() / 3600.0
        remaining_hrs = limit_hrs - elapsed_hrs

        # Calculate Risk Percentage based on multiple indicators
        time_used_pct = (elapsed_hrs / limit_hrs) * 100.0 if limit_hrs > 0 else 100.0

        risk_score = time_used_pct * 0.60  # Time component weights 60%

        risk_factors = []

        if time_used_pct >= 100:
            risk_factors.append("SLA timeframe already exceeded!")
        elif time_used_pct > 75:
            risk_factors.append(f"More than 75% of SLA time used ({round(elapsed_hrs, 1)} / {limit_hrs} hrs).")

        if crt == 'Critical' or crt == 'Elevated':
            risk_score += 20
            risk_factors.append(f"Case CRT level set to '{crt}'.")

        if l2_pending == 1:
            risk_score += 15
            risk_factors.append("Awaiting L2 specialist engineering review.")

        if awaiting_customer == 1:
            risk_score -= 10  # Awaiting customer pauses/reduces risk score
            risk_factors.append("Case currently Awaiting Customer response (SLA clock paused).")

        if prio == 'Critical':
            risk_score += 10
            risk_factors.append("Critical Priority ticket requires immediate 4-hour response.")

        risk_percentage = min(99.9, max(5.0, round(risk_score, 1)))

        if risk_percentage >= 80 or remaining_hrs <= 1.0:
            risk_level = "Critical Risk"
            badge_color = "red"
        elif risk_percentage >= 50:
            risk_level = "High Risk"
            badge_color = "orange"
        elif risk_percentage >= 30:
            risk_level = "Medium Risk"
            badge_color = "yellow"
        else:
            risk_level = "Low Risk"
            badge_color = "green"

        return {
            "success": True,
            "case_id": case_id,
            "case_number": case['case_number'],
            "priority": prio,
            "crt": crt,
            "sla_limit_hrs": limit_hrs,
            "elapsed_hrs": round(elapsed_hrs, 1),
            "remaining_hrs": round(remaining_hrs, 1),
            "risk_percentage": risk_percentage,
            "risk_level": risk_level,
            "badge_color": badge_color,
            "risk_factors": risk_factors if risk_factors else ["Case progressing within normal SLA parameters."]
        }
