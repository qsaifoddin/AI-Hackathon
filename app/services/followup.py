import sqlite3
from datetime import datetime, timedelta
from app.db.database import get_connection
from app.services.audit import log_action, get_config
from app.services.notification import NotificationService

class FollowupService:
    @staticmethod
    def generate_copilot_message(customer_name, case_number):
        """
        Simulated Copilot Studio content generation.
        Returns a personalized, professional customer email.
        """
        return f"Hello {customer_name},\n\n" \
               f"We are following up regarding your HP support case {case_number}.\n" \
               f"Please let us know if you were able to complete the requested troubleshooting steps or if " \
               f"you require additional assistance from our engineering team.\n\n" \
               f"If you have resolved the issue, you can reply directly to close this request.\n\n" \
               f"Regards,\n" \
               f"HP Support Agent Copilot"

    @staticmethod
    def initiate_followup(case_id, changed_by="System"):
        conn = get_connection()
        cursor = conn.cursor()

        # Get case info
        cursor.execute("""
            SELECT c.case_number, c.customer_id, c.engineer_id, cust.name as customer_name, cust.email as customer_email
            FROM cases c
            JOIN customers cust ON c.customer_id = cust.customer_id
            WHERE c.case_id = ?
        """, (case_id,))
        case_row = cursor.fetchone()

        if not case_row:
            conn.close()
            return None

        # Check if follow-up record already exists for this case
        cursor.execute("""
            SELECT * FROM case_followups 
            WHERE case_id = ? AND status NOT IN ('Customer Responded', 'Cancelled')
            ORDER BY followup_number DESC LIMIT 1
        """, (case_id,))
        existing_followup = cursor.fetchone()
        existing_followup_dict = dict(existing_followup) if existing_followup else None

        now = datetime.now()
        first_wait = int(get_config('FirstFollowupHours', '48'))
        scheduled_dt = (now + timedelta(hours=first_wait)).strftime("%Y-%m-%d %H:%M:%S")

        # Set Case properties
        cursor.execute("UPDATE cases SET awaiting_customer = 1, status = 'Awaiting Customer' WHERE case_id = ?", (case_id,))
        
        # Commit and close first to prevent SQLite deadlock during notification dispatch
        conn.commit()
        conn.close()

        # Log case change notification (Scenario B)
        NotificationService.log_change_and_notify(
            case_id=case_id,
            change_type='STATUS_CHANGED',
            prev_value='Active',
            new_value='Awaiting Customer',
            changed_by=changed_by
        )

        # Reopen connection for inserting followup record
        conn = get_connection()
        cursor = conn.cursor()
        
        followup_id = None
        if not existing_followup_dict:
            # Create first follow-up record
            cursor.execute("""
                INSERT INTO case_followups (
                    case_id, case_number, customer_id, engineer_id, followup_number,
                    scheduled_datetime, status, response_received, escalated
                ) VALUES (?, ?, ?, ?, 1, ?, 'Scheduled', 0, 0)
            """, (case_id, case_row['case_number'], case_row['customer_id'], case_row['engineer_id'], scheduled_dt))
            followup_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            log_action(
                user=changed_by,
                action="Scheduled First Follow-up",
                case_id=case_id,
                automation="Customer Follow-up",
                new_value=f"Scheduled for {scheduled_dt}",
                result="Success"
            )
        else:
            followup_id = existing_followup_dict['followup_id']
            conn.close()

        return followup_id

    @staticmethod
    def simulate_time_elapsed_and_send(case_id, hours_elapsed=48):
        """
        Simulates the background scheduler running and sending a pending follow-up email.
        """
        conn = get_connection()
        cursor = conn.cursor()

        # Find Scheduled follow-up
        cursor.execute("""
            SELECT f.*, c.name as customer_name, cs.case_number 
            FROM case_followups f
            JOIN customers c ON f.customer_id = c.customer_id
            JOIN cases cs ON f.case_id = cs.case_id
            WHERE f.case_id = ? AND f.status = 'Scheduled'
            LIMIT 1
        """, (case_id,))
        
        followup = cursor.fetchone()
        if not followup:
            conn.close()
            return False

        followup_dict = dict(followup)
        now = datetime.now()
        sent_dt = now.strftime("%Y-%m-%d %H:%M:%S")

        # Update follow-up status to Sent
        cursor.execute("""
            UPDATE case_followups
            SET status = 'Sent', sent_datetime = ?
            WHERE followup_id = ?
        """, (sent_dt, followup_dict['followup_id']))
        
        conn.commit()
        conn.close()

        # Send simulated email containing Copilot body
        email_content = FollowupService.generate_copilot_message(followup_dict['customer_name'], followup_dict['case_number'])
        
        # Log to Audit Log
        log_action(
            user="System Automator",
            action=f"Dispatched Follow-up #{followup_dict['followup_number']} (Copilot Generated)",
            case_id=case_id,
            automation="Customer Follow-up",
            new_value=f"To: {followup_dict['customer_name']}\nMessage: {email_content[:100]}...",
            result="Success"
        )

        # Reopen to write next follow-up if applicable
        conn = get_connection()
        cursor = conn.cursor()
        
        max_followups = int(get_config('MaximumFollowups', '2'))
        if followup_dict['followup_number'] < max_followups:
            # Schedule the 2nd follow-up
            second_wait = int(get_config('SecondFollowupHours', '48'))
            next_sched = (now + timedelta(hours=second_wait)).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                INSERT INTO case_followups (
                    case_id, case_number, customer_id, engineer_id, followup_number,
                    scheduled_datetime, status, response_received, escalated
                ) VALUES (?, ?, ?, ?, ?, ?, 'Scheduled', 0, 0)
            """, (case_id, followup_dict['case_number'], followup_dict['customer_id'], followup_dict['engineer_id'],
                  followup_dict['followup_number'] + 1, next_sched))
            
            conn.commit()
            conn.close()
            
            log_action(
                user="System Automator",
                action="Scheduled Second Follow-up",
                case_id=case_id,
                automation="Customer Follow-up",
                new_value=f"Scheduled for {next_sched}",
                result="Success"
            )
        else:
            conn.close()

        return True

    @staticmethod
    def simulate_customer_reply(case_id, reply_text="Troubleshooting completed, it works!"):
        conn = get_connection()
        cursor = conn.cursor()

        # Find sent follow-up to mark customer responded
        cursor.execute("""
            SELECT * FROM case_followups
            WHERE case_id = ? AND status = 'Sent'
            ORDER BY followup_number DESC LIMIT 1
        """, (case_id,))
        
        followup = cursor.fetchone()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if followup:
            followup_dict = dict(followup)
            cursor.execute("""
                UPDATE case_followups
                SET status = 'Customer Responded', response_received = 1, response_datetime = ?
                WHERE followup_id = ?
            """, (now_str, followup_dict['followup_id']))
            
            # Re-activate Case in Dynamics
            cursor.execute("UPDATE cases SET status = 'Active', awaiting_customer = 0 WHERE case_id = ?", (case_id,))
            
            conn.commit()
            conn.close()
            
            NotificationService.log_change_and_notify(
                case_id=case_id,
                change_type='CUSTOMER_REPLIED',
                prev_value='Awaiting Customer',
                new_value=f"Active (Reply: '{reply_text}')",
                changed_by='Customer Portal'
            )
            
            log_action(
                user='Customer Portal',
                action='Customer Responded to Follow-up',
                case_id=case_id,
                automation='Customer Follow-up',
                new_value=f"Reply: {reply_text}",
                result='Success'
            )
            return True
            
        conn.close()
        return False

    @staticmethod
    def trigger_escalation(case_id):
        conn = get_connection()
        cursor = conn.cursor()

        # Get case info
        cursor.execute("SELECT case_number, priority FROM cases WHERE case_id = ?", (case_id,))
        case = cursor.fetchone()
        if not case:
            conn.close()
            return False

        case_dict = dict(case)

        # Set follow-up to Escalated
        cursor.execute("""
            UPDATE case_followups
            SET status = 'Escalated', escalated = 1
            WHERE case_id = ? AND status = 'Sent'
        """, (case_id,))

        # Escalate priority and update Case in Dynamics
        cursor.execute("""
            UPDATE cases 
            SET priority = 'Critical', status = 'Active', awaiting_customer = 0, crt = 'Critical' 
            WHERE case_id = ?
        """, (case_id,))
        
        conn.commit()
        conn.close()

        NotificationService.log_change_and_notify(
            case_id=case_id,
            change_type='PRIORITY_CHANGED',
            prev_value=case_dict['priority'],
            new_value='Critical (SLA Escalated)',
            changed_by='Escalation Engine'
        )

        log_action(
            user='System Automator',
            action='Escalated Case (No customer response)',
            case_id=case_id,
            automation='Customer Follow-up',
            new_value="Priority -> Critical | CRT -> Critical",
            result='Success'
        )
        return True
