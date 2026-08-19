import sqlite3
import random
import re
from datetime import datetime
from app.db.database import get_connection
from app.services.audit import log_action, get_config

class IVRCaseService:
    @staticmethod
    def validate_serial(serial_number):
        # Realistic serial validation (8-10 alphanumeric characters)
        if not serial_number:
            return False, "Serial number cannot be empty."
        clean_serial = serial_number.strip().upper()
        if not re.match(r'^[A-Z0-9]{8,10}$', clean_serial):
            return False, "Serial format invalid. Must be 8 to 10 alphanumeric characters (e.g. 5CG12345AB)."
        return True, clean_serial

    @staticmethod
    def validate_phone(phone_number):
        # Validates basic format (at least 10 digits)
        if not phone_number:
            return False, "Phone number cannot be empty."
        clean_phone = re.sub(r'[\s\-\(\)\+]', '', phone_number)
        if not clean_phone.isdigit() or len(clean_phone) < 10:
            return False, "Phone format invalid. Must contain at least 10 digits."
        return True, phone_number.strip()

    @staticmethod
    def FindCustomer(phone_number):
        conn = get_connection()
        cursor = conn.cursor()
        
        # Strip characters for broad match
        clean_phone = "%" + re.sub(r'[\s\-\(\)\+]', '', phone_number)[-10:]
        
        cursor.execute("SELECT * FROM customers WHERE phone LIKE ?", (clean_phone,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def FindExistingCase(customer_id, serial_number):
        conn = get_connection()
        cursor = conn.cursor()
        
        # Look for open cases (not Resolved/Closed) with matching serial
        cursor.execute("""
            SELECT * FROM cases 
            WHERE customer_id = ? AND serial_number = ? AND status NOT IN ('Resolved', 'Closed')
            ORDER BY created_date DESC LIMIT 1
        """, (customer_id, serial_number))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def CreateCase(phone, serial_number, problem_category, customer_name=None, preferred_language='English'):
        # Validate inputs
        phone_ok, phone_val = IVRCaseService.validate_phone(phone)
        if not phone_ok:
            return {"success": False, "error": phone_val}
            
        serial_ok, serial_val = IVRCaseService.validate_serial(serial_number)
        if not serial_ok:
            return {"success": False, "error": serial_val}

        conn = get_connection()
        cursor = conn.cursor()

        # 1. Identify or Create Customer
        customer = IVRCaseService.FindCustomer(phone_val)
        if customer:
            customer_id = customer['customer_id']
            cust_name = customer['name']
        else:
            # Create new customer profile
            c_name = customer_name if customer_name else f"Caller ({phone_val[-4:]})"
            c_email = f"caller_{phone_val[-4:]}@mock-ivr.com"
            cursor.execute("""
                INSERT INTO customers (name, phone, email, preferred_language)
                VALUES (?, ?, ?, ?)
            """, (c_name, phone_val, c_email, preferred_language))
            customer_id = cursor.lastrowid
            cust_name = c_name
            log_action('IVR AI Agent', f"Registered new customer: {cust_name}", result='Success')

        # 2. Check for existing open cases
        existing_case = IVRCaseService.FindExistingCase(customer_id, serial_val)
        if existing_case:
            conn.close()
            return {
                "success": True,
                "existing_case_found": True,
                "case_number": existing_case['case_number'],
                "case_id": existing_case['case_id'],
                "customer_name": cust_name,
                "message": f"Existing case found: {existing_case['case_number']}"
            }

        # 3. Resolve Queue and Engineer
        default_queue_name = get_config('DefaultQueue', 'General Hardware Queue')
        cursor.execute("SELECT queue_id FROM queues WHERE name = ?", (default_queue_name,))
        q_row = cursor.fetchone()
        queue_id = q_row[0] if q_row else 1

        # Select a random engineer
        cursor.execute("SELECT engineer_id FROM engineers WHERE role = 'Engineer'")
        engs = [row[0] for row in cursor.fetchall()]
        engineer_id = random.choice(engs) if engs else 1

        # 4. Generate new Case Number
        cursor.execute("SELECT COUNT(*) FROM cases")
        case_count = cursor.fetchone()[0]
        new_case_number = f"CAS-{100001 + case_count}"
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 5. Insert Case
        cursor.execute("""
            INSERT INTO cases (
                case_number, customer_id, serial_number, product_number, engineer_id, queue_id,
                status, priority, issue_category, created_date, modified_date, source,
                warranty_status, sla_status
            ) VALUES (?, ?, ?, ?, ?, ?, 'New', 'Normal', ?, ?, ?, 'IVR', 'In Warranty (Base)', 'In Progress')
        """, (new_case_number, customer_id, serial_val, "HP-PRO-MOCK-IVR", engineer_id, queue_id,
              problem_category, now_str, now_str))
        
        case_id = cursor.lastrowid
        conn.commit()
        conn.close()

        log_action(
            user='IVR AI Agent',
            action="Created new Case via IVR Call",
            case_id=case_id,
            automation='IVR Case Creation',
            new_value=f"Case {new_case_number} created and assigned to Queue ID {queue_id}",
            result='Success'
        )

        return {
            "success": True,
            "existing_case_found": False,
            "case_number": new_case_number,
            "case_id": case_id,
            "customer_name": cust_name,
            "message": "New case created successfully."
        }
