import sqlite3
from datetime import datetime
from app.db.database import get_connection

def log_action(user, action, case_id=None, automation=None, old_value=None, new_value=None, result='Success', error=None):
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute("""
        INSERT INTO audit_logs (timestamp, user, automation, case_id, action, old_value, new_value, result, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (now_str, user, automation, case_id, action, str(old_value) if old_value is not None else None, 
          str(new_value) if new_value is not None else None, result, error))
    
    conn.commit()
    conn.close()

def get_config(key, default=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT config_value FROM configurations WHERE config_key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0]
    return default

def set_config(key, value):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO configurations (config_key, config_value, description)
        VALUES (?, ?, 'Dynamic configuration key')
        ON CONFLICT(config_key) DO UPDATE SET config_value = excluded.config_value
    """, (key, value))
    conn.commit()
    conn.close()
    log_action('Administrator', f"Updated config '{key}' to '{value}'", result='Success')

def get_all_configs():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT config_key, config_value, description FROM configurations")
    rows = cursor.fetchall()
    conn.close()
    return {row['config_key']: {'value': row['config_value'], 'description': row['description']} for row in rows}
