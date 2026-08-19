import sqlite3
from datetime import datetime
from app.db.database import get_connection
from app.services.audit import log_action

class AutomationEngine:
    @staticmethod
    def get_all_automations():
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM automations")
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def toggle_automation(automation_id, enable=True):
        conn = get_connection()
        cursor = conn.cursor()
        new_status = 'Enabled' if enable else 'Disabled'
        cursor.execute("UPDATE automations SET status = ? WHERE automation_id = ?", (new_status, automation_id))
        conn.commit()
        
        # Get name for logging
        cursor.execute("SELECT name FROM automations WHERE automation_id = ?", (automation_id,))
        row = cursor.fetchone()
        name = row[0] if row else "Unknown"
        conn.close()
        
        log_action('Administrator', f"Toggled automation '{name}' to {new_status}", result='Success')

    @staticmethod
    def execute_rule(name, case_id, runner_func, *args, **kwargs):
        """
        Executes a rule wrapped in audit logs and updates success/failure counters.
        """
        conn = get_connection()
        cursor = conn.cursor()
        
        # Check if enabled
        cursor.execute("SELECT status, success_count, fail_count FROM automations WHERE name = ?", (name,))
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            return False, "Automation rule not found"
            
        status = row['status']
        success_count = row['success_count']
        fail_count = row['fail_count']
        conn.close()  # Release lock immediately before running sub-logic
        
        if status == 'Disabled':
            return False, f"Automation '{name}' is currently disabled."

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            # Execute actual logic (running connection-free)
            result_data = runner_func(case_id, *args, **kwargs)
            
            # Increment success in a new transaction block
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE automations
                SET success_count = ?, last_run = ?, error_message = NULL
                WHERE name = ?
            """, (success_count + 1, now_str, name))
            conn.commit()
            conn.close()
            return True, result_data
        except Exception as e:
            err_msg = str(e)
            
            # Increment failure in a new transaction block
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE automations
                SET fail_count = ?, last_run = ?, error_message = ?
                WHERE name = ?
            """, (fail_count + 1, now_str, err_msg, name))
            conn.commit()
            conn.close()
            
            log_action(
                user='System Automator',
                action=f"Automation '{name}' failed",
                case_id=case_id,
                automation=name,
                result='Failed',
                error=err_msg
            )
            return False, err_msg
