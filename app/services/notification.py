import sqlite3
from datetime import datetime, timedelta
from app.db.database import get_connection
from app.services.audit import log_action

class NotificationService:
    @staticmethod
    def log_change_and_notify(case_id, change_type, prev_value, new_value, changed_by, channel='In-App'):
        conn = get_connection()
        cursor = conn.cursor()
        
        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")

        # Fetch case and owner info
        cursor.execute("""
            SELECT c.case_number, c.engineer_id, e.name as engineer_name
            FROM cases c
            LEFT JOIN engineers e ON c.engineer_id = e.engineer_id
            WHERE c.case_id = ?
        """, (case_id,))
        case_row = cursor.fetchone()
        
        if not case_row:
            conn.close()
            return
            
        case_number = case_row['case_number']
        engineer_id = case_row['engineer_id']
        
        # Deduplication / Batching logic:
        # Check if there is already a 'Pending' notification for this case and engineer
        # created in the last 30 seconds.
        time_limit = (now - timedelta(seconds=30)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            SELECT notification_id, change_type, previous_value, new_value 
            FROM case_change_notifications
            WHERE case_id = ? AND notification_status = 'Pending' AND changed_datetime >= ?
            LIMIT 1
        """, (case_id, time_limit))
        
        pending_row = cursor.fetchone()
        
        if pending_row:
            # Grouping occurred!
            notif_id = pending_row['notification_id']
            merged_change_type = f"{pending_row['change_type']} | {change_type}"
            merged_prev = f"{pending_row['previous_value']} | {prev_value}"
            merged_new = f"{pending_row['new_value']} | {new_value}"
            
            cursor.execute("""
                UPDATE case_change_notifications
                SET change_type = ?, previous_value = ?, new_value = ?, changed_datetime = ?, changed_by = ?
                WHERE notification_id = ?
            """, (merged_change_type, merged_prev, merged_new, now_str, f"Grouped({changed_by})", notif_id))
            
            conn.commit()
            conn.close()
            
            log_action(
                user='System Automator',
                action="Grouped and deduplicated case change notification",
                case_id=case_id,
                automation='Case Update Notifications',
                new_value=f"Merged into Notif ID {notif_id}",
                result='Success'
            )
            return notif_id
        else:
            # Create new pending notification
            cursor.execute("""
                INSERT INTO case_change_notifications (
                    case_number, case_id, engineer_id, change_type, previous_value, new_value,
                    changed_by, changed_datetime, notification_channel, notification_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending')
            """, (case_number, case_id, engineer_id, change_type, prev_value, new_value, changed_by, now_str, channel))
            
            notif_id = cursor.lastrowid
            conn.commit()
            conn.close()
            return notif_id

    @staticmethod
    def process_and_send_pending():
        """
        Simulates the background worker (Power Automate schedule flow) that 
        flushes all 'Pending' notifications, generating mock dispatches to Teams, Outlook, and In-app.
        """
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT n.notification_id, n.case_number, n.change_type, n.previous_value, n.new_value, 
                   n.changed_by, n.notification_channel, e.name as engineer_name, e.email as engineer_email
            FROM case_change_notifications n
            LEFT JOIN engineers e ON n.engineer_id = e.engineer_id
            WHERE n.notification_status = 'Pending'
        """)
        
        pending_notifications = [dict(r) for r in cursor.fetchall()]
        conn.close() # Close immediately to prevent database locking during nested writes
        
        sent_count = 0
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        for notif in pending_notifications:
            notif_id = notif['notification_id']
            channel = notif['notification_channel']
            eng_name = notif['engineer_name']
            eng_email = notif['engineer_email']
            
            # Format visual details
            change_details = []
            types = notif['change_type'].split(" | ")
            prevs = str(notif['previous_value']).split(" | ")
            news = str(notif['new_value']).split(" | ")
            
            for t, p, n in zip(types, prevs, news):
                change_details.append(f"- **{t}**: '{p}' → '{n}'")
            
            details_str = "\n".join(change_details)
            
            # Update status in a separate short-lived connection
            conn_write = get_connection()
            cursor_write = conn_write.cursor()
            cursor_write.execute("""
                UPDATE case_change_notifications
                SET notification_status = 'Sent', notification_sent_datetime = ?
                WHERE notification_id = ?
            """, (now_str, notif_id))
            conn_write.commit()
            conn_write.close()
            
            log_action(
                user='System Automator',
                action=f"Dispatched notification via {channel}",
                case_id=None,
                automation='Case Update Notifications',
                new_value=f"Channel: {channel} | Sent to: {eng_email or 'Owner'}",
                result='Success'
            )
            
            sent_count += 1
            
        return sent_count

    @staticmethod
    def get_unread_notifications(engineer_id=None):
        conn = get_connection()
        cursor = conn.cursor()
        if engineer_id:
            cursor.execute("""
                SELECT * FROM case_change_notifications 
                WHERE engineer_id = ? 
                ORDER BY changed_datetime DESC LIMIT 20
            """, (engineer_id,))
        else:
            cursor.execute("""
                SELECT * FROM case_change_notifications 
                ORDER BY changed_datetime DESC LIMIT 50
            """)
        rows = cursor.fetchall()
        conn.close()
        return rows
