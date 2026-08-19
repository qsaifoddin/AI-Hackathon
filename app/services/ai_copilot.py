import sqlite3
from datetime import datetime
from app.db.database import get_connection
from app.services.audit import log_action

class AICopilotService:
    @staticmethod
    def propose_resolution(case_id):
        """
        AI Copilot Case Resolution Generator.
        Analyzes case issue category, priority, warranty status, and description
        to generate step-by-step diagnostic actions, recommended spare parts, and KB article references.
        """
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.*, cust.name as customer_name, cust.preferred_language
            FROM cases c
            JOIN customers cust ON c.customer_id = cust.customer_id
            WHERE c.case_id = ?
        """, (case_id,))
        case_row = cursor.fetchone()
        conn.close()

        if not case_row:
            return {"success": False, "error": "Case not found"}

        case = dict(case_row)
        cat = case['issue_category']
        prio = case['priority']
        warr = case['warranty_status']

        # Diagnostic steps generator based on domain rules & issue category
        if cat == 'Hardware':
            steps = [
                "Run HP PC Hardware Diagnostics UEFI (F2 at boot) to execute System Fast Test.",
                "Inspect physical connections and verify power LED diagnostic error codes.",
                "Check BIOS version and update to latest HP firmware release via HP Support Assistant.",
                "If component error (e.g. 24-digit failure code) is generated, dispatch replacement hardware."
            ]
            kb_articles = ["KB-88210: HP Diagnostic Error Codes", "KB-94211: System Board Replacement Protocol"]
            suggested_part = "HP-PRT-MB-840" if "840" in case.get('product_number', '') else "HP-PRT-BAT-6cell"
        elif cat == 'Software':
            steps = [
                "Verify OS build version and check for conflicting third-party driver updates.",
                "Run HP Image Assistant to restore factory-validated HP driver bundle.",
                "Clear temporary application caches and execute System File Checker (sfc /scannow).",
                "Reinstall HP Client Security Suite and reboot target endpoint."
            ]
            kb_articles = ["KB-77102: HP Image Assistant Rollout", "KB-33019: Driver Conflict Resolution"]
            suggested_part = "None (Software Resolution)"
        elif cat == 'Network':
            steps = [
                "Verify Wi-Fi 6E module status in Windows Device Manager (Check for Error Code 10/43).",
                "Reset TCP/IP stack (`netsh int ip reset`) and flush DNS cache (`ipconfig /flushdns`).",
                "Update WLAN controller driver to release v22.190 or higher.",
                "Test connection against corporate RADIUS / Enterprise WPA3 network."
            ]
            kb_articles = ["KB-55012: Wi-Fi 6E Roaming Optimization", "KB-11092: Enterprise WPA3 Configuration"]
            suggested_part = "HP-PRT-WIFI-6E"
        elif cat == 'Installation':
            steps = [
                "Review deployment log in `%windir%\\Panther\\unattend.xml` for unattended setup faults.",
                "Validate target drive partitioning (GPT / UEFI mode check).",
                "Apply HP Smart Array / NVMe storage controller inf drivers during WinPE setup phase."
            ]
            kb_articles = ["KB-40112: WinPE Driver Injection Guide"]
            suggested_part = "HP-PRT-SSD-1TB"
        else:
            steps = [
                "Verify billing entitlement and contract serial mapping in HP Care Pack portal.",
                "Confirm active Care Pack registration and invoice line item matching.",
                "Issue updated warranty coverage certificate to customer contact."
            ]
            kb_articles = ["KB-10022: Care Pack Entitlement Verification"]
            suggested_part = "None (Billing Action)"

        confidence_score = 94.5 if prio in ['Critical', 'High'] else 88.0

        proposal = {
            "case_number": case['case_number'],
            "issue_category": cat,
            "priority": prio,
            "warranty_status": warr,
            "copilot_summary": f"Recommended resolution plan for {cat} issue on serial {case['serial_number']} (Confidence: {confidence_score}%).",
            "diagnostic_steps": steps,
            "kb_articles": kb_articles,
            "recommended_part": suggested_part,
            "estimated_resolution_mins": 35 if cat == 'Software' else 60,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        log_action(
            user="HP AI Copilot Engine",
            action="Generated AI Case Resolution Proposal",
            case_id=case_id,
            automation="AI Copilot Engine",
            new_value=f"Category: {cat} | Confidence: {confidence_score}%",
            result="Success"
        )

        return {"success": True, "proposal": proposal}

    @staticmethod
    def analyze_sentiment(text_content):
        """
        Analyzes customer notes, chat text, or call transcripts.
        Returns sentiment score (0-100), classification rating, and risk indicators.
        """
        if not text_content:
            return {"sentiment": "Neutral", "score": 50, "churn_risk": "Low", "triggers": []}

        lower_text = text_content.lower()
        frustrated_keywords = ['frustrated', 'unacceptable', 'escalate', 'legal', 'broken', 'angry', 'terrible', 'useless', 'delayed', 'worst', 'failed', 'refund', 'manager']
        positive_keywords = ['thank', 'thanks', 'great', 'excellent', 'helpful', 'resolved', 'awesome', 'good', 'happy', 'quick', 'solved']

        found_frustrated = [w for w in frustrated_keywords if w in lower_text]
        found_positive = [w for w in positive_keywords if w in lower_text]

        if len(found_frustrated) >= 2 or 'escalate' in lower_text or 'legal' in lower_text or 'unacceptable' in lower_text:
            sentiment = "At-Risk / High Churn"
            score = max(10, 30 - len(found_frustrated) * 10)
            churn_risk = "High"
        elif len(found_frustrated) == 1:
            sentiment = "Frustrated"
            score = 40
            churn_risk = "Medium"
        elif len(found_positive) > len(found_frustrated):
            sentiment = "Positive"
            score = min(95, 70 + len(found_positive) * 8)
            churn_risk = "Low"
        else:
            sentiment = "Neutral"
            score = 55
            churn_risk = "Low"

        return {
            "sentiment": sentiment,
            "score": score,
            "churn_risk": churn_risk,
            "triggers": found_frustrated if found_frustrated else (found_positive if found_positive else ["Standard Inquiry"])
        }

    @staticmethod
    def summarize_transcript(transcript_text):
        """
        Summarizes raw call/chat transcripts into structured CRM case notes.
        """
        if not transcript_text or len(transcript_text.strip()) == 0:
            return {"success": False, "error": "Transcript empty"}

        sentiment_info = AICopilotService.analyze_sentiment(transcript_text)

        # Extract main points (heuristics simulation for demo)
        lines = [l.strip() for l in transcript_text.split("\n") if l.strip()]

        summary = {
            "issue_summary": lines[0] if lines else "Customer called regarding technical support issue.",
            "sentiment": sentiment_info['sentiment'],
            "churn_risk": sentiment_info['churn_risk'],
            "sentiment_score": sentiment_info['score'],
            "key_discussion_points": [
                "Customer reported intermittent system behavior.",
                "Engineer performed initial hardware diagnostic check.",
                "Agreed on next steps for follow-up or hardware replacement."
            ],
            "recommended_next_action": "Schedule CBC Callback or order replacement spare part." if sentiment_info['churn_risk'] != 'High' else "Escalate case immediately to Senior L2 Engineer.",
            "summarized_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        return {"success": True, "summary": summary}
