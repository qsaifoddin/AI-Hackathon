import sqlite3
from datetime import datetime, timedelta
from app.db.database import get_connection
from app.services.audit import log_action

class CallbackService:
    @staticmethod
    def get_upcoming_callbacks(engineer_id=None):
        conn = get_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT c.*, cs.case_number, cust.name as customer_name, cust.phone as customer_phone
            FROM callbacks c
            JOIN cases cs ON c.case_id = cs.case_id
            JOIN customers cust ON c.customer_id = cust.customer_id
            WHERE c.status = 'Scheduled'
        """
        params = []
        if engineer_id:
            query += " AND c.engineer_id = ?"
            params.append(engineer_id)
            
        query += " ORDER BY c.callback_datetime ASC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        return rows

    @staticmethod
    def get_callback_metrics(engineer_id=None):
        conn = get_connection()
        cursor = conn.cursor()
        
        query = "SELECT status, callback_datetime, actual_callback_datetime FROM callbacks"
        params = []
        if engineer_id:
            query += " WHERE engineer_id = ?"
            params.append(engineer_id)
            
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        total_due = len(rows)
        completed = 0
        missed = 0
        on_time = 0
        delays = []

        for row in rows:
            status = row['status']
            cb_dt_str = row['callback_datetime']
            act_dt_str = row['actual_callback_datetime']

            if status == 'Completed':
                completed += 1
                if cb_dt_str and act_dt_str:
                    cb_dt = datetime.strptime(cb_dt_str, "%Y-%m-%d %H:%M:%S")
                    act_dt = datetime.strptime(act_dt_str, "%Y-%m-%d %H:%M:%S")
                    delay = (act_dt - cb_dt).total_seconds() / 60.0
                    delays.append(max(0, delay))
                    if delay <= 10:  # 10 minute grace period
                        on_time += 1
            elif status == 'Missed':
                missed += 1
            elif status == 'Scheduled':
                cb_dt = datetime.strptime(cb_dt_str, "%Y-%m-%d %H:%M:%S")
                if cb_dt < datetime.now():
                    missed += 1
                else:
                    # Not missed yet, just scheduled
                    pass

        on_time_pct = (on_time / completed * 100.0) if completed > 0 else 100.0
        avg_delay = (sum(delays) / len(delays)) if delays else 0.0

        return {
            "cbc_due": total_due,
            "cbc_completed": completed,
            "cbc_missed": missed,
            "cbc_on_time_pct": round(on_time_pct, 1),
            "avg_callback_delay_min": round(avg_delay, 1)
        }

    @staticmethod
    def InitiateCall(callback_id, status_sequence_step):
        """
        Returns the simulated state of the outbound call based on the UI request.
        States: 'Ready', 'Dialing', 'Ringing', 'Connected', 'No Answer', 'Failed', 'Completed'
        """
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT c.*, cs.case_number, cust.name as customer_name
            FROM callbacks c
            JOIN cases cs ON c.case_id = cs.case_id
            JOIN customers cust ON c.customer_id = cust.customer_id
            WHERE c.callback_id = ?
        """, (callback_id,))
        cb = cursor.fetchone()
        
        if not cb:
            conn.close()
            return 'Failed'

        cb_dict = dict(cb)
        conn.close()

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        case_id = cb_dict['case_id']

        if status_sequence_step == 'Dialing':
            log_action('Alex Carter', f"Outbound callback initiated to {cb_dict['customer_name']}", case_id=case_id)
        elif status_sequence_step == 'Connected':
            log_action('System Voice Gate', "Outbound callback connected", case_id=case_id)
        elif status_sequence_step == 'Completed':
            # Complete the callback record and resolve case
            conn_write = get_connection()
            cursor_write = conn_write.cursor()
            cursor_write.execute("""
                UPDATE callbacks
                SET status = 'Completed', actual_callback_datetime = ?, call_duration = '3m 45s', 
                    call_outcome = 'Discussed troubleshooting. Customer verified resolution.'
                WHERE callback_id = ?
            """, (now_str, callback_id))
            
            cursor_write.execute("""
                UPDATE cases
                SET status = 'Resolved', resolution_date = ?, modified_date = ?, sla_status = 'Met'
                WHERE case_id = ?
            """, (now_str, now_str, case_id))
            conn_write.commit()
            conn_write.close()

            log_action('System Voice Gate', "Outbound callback completed. Call duration: 3m 45s", case_id=case_id)
            log_action('Alex Carter', "Resolved Case via Callback", case_id=case_id, automation='CBC Alerts & Autodial', new_value="Status: Resolved")
        elif status_sequence_step == 'No Answer':
            # Missed callback
            conn_write = get_connection()
            cursor_write = conn_write.cursor()
            cursor_write.execute("""
                UPDATE callbacks
                SET status = 'Missed', actual_callback_datetime = ?, call_outcome = 'Voicemail left - customer did not pick up.'
                WHERE callback_id = ?
            """, (now_str, callback_id))
            conn_write.commit()
            conn_write.close()
            
            log_action('Alex Carter', "Callback missed - Customer did not answer", case_id=case_id, automation='CBC Alerts & Autodial')
            
        return status_sequence_step
