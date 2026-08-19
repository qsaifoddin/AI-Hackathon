import sqlite3
import qrcode
import io
from datetime import datetime
from app.db.database import get_connection
from app.services.audit import log_action, get_config

class EntitlementService:
    @staticmethod
    def is_service_healthy():
        # Check system config for service status simulation
        status = get_config('EntitlementServiceStatus', 'Online')
        return status == 'Online'

    @staticmethod
    def GetEntitlement(serial_number):
        if not EntitlementService.is_service_healthy():
            raise ConnectionError("Warranty Entitlement Service is currently offline. The request has been queued for retry.")
        
        # Simulated responses based on serial number patterns
        if serial_number.startswith("5CG"):
            return {
                "serial_number": serial_number,
                "status": "In Warranty (Base)",
                "expiry_date": "2027-04-15",
                "carepack_active": False,
                "product_name": "HP EliteBook 840 G10"
            }
        elif serial_number.startswith("8CC"):
            return {
                "serial_number": serial_number,
                "status": "Care Pack Active",
                "expiry_date": "2029-09-30",
                "carepack_active": True,
                "product_name": "HP ZBook Power G10"
            }
        else:
            return {
                "serial_number": serial_number,
                "status": "Out of Warranty",
                "expiry_date": "2025-01-10",
                "carepack_active": False,
                "product_name": "HP ProBook 450 G9"
            }

    @staticmethod
    def CreateExtensionRequest(case_id, serial_number, product_number, customer_id, request_type, current_status, requested_action, customer_contact):
        if not EntitlementService.is_service_healthy():
            raise ConnectionError("Warranty Entitlement Service is currently offline. The request has been queued for retry.")

        conn = get_connection()
        cursor = conn.cursor()
        
        req_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Insert request into database (Dataverse simulation)
        cursor.execute("""
            INSERT INTO warranty_requests (
                case_id, serial_number, product_number, customer_id, request_type,
                current_warranty_status, requested_action, customer_contact, request_date, request_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'New')
        """, (case_id, serial_number, product_number, customer_id, request_type, current_status, requested_action, customer_contact, req_date))
        
        request_id = cursor.lastrowid
        
        # Generate QR code pointing to mock Power Apps request page URL
        base_url = get_config('EntitlementBaseURL', 'https://apps.powerapps.com/play/e/default-entitlement-service')
        qr_url = f"{base_url}?requestId=WREQ-{request_id}&serial={serial_number}&action={request_type.replace(' ', '')}"
        
        cursor.execute("""
            UPDATE warranty_requests
            SET qr_code_url = ?, request_status = 'Submitted'
            WHERE request_id = ?
        """, (qr_url, request_id))
        
        conn.commit()
        conn.close()
        
        # Log to Audit Log
        log_action(
            user='System Automator',
            action=f"Created {request_type} request",
            case_id=case_id,
            automation='Warranty Automation',
            new_value=f"WREQ-{request_id} submitted",
            result='Success'
        )
        
        return {
            "request_id": f"WREQ-{request_id}",
            "qr_code_url": qr_url,
            "status": "Submitted"
        }

    @staticmethod
    def CreateTransferRequest(case_id, serial_number, product_number, customer_id, request_type, current_status, requested_action, customer_contact):
        # Transact similarly for prototype
        return EntitlementService.CreateExtensionRequest(
            case_id, serial_number, product_number, customer_id, request_type, current_status, requested_action, customer_contact
        )

    @staticmethod
    def GetRequestStatus(request_id_str):
        if not EntitlementService.is_service_healthy():
            raise ConnectionError("Warranty Entitlement Service is currently offline.")
            
        try:
            req_id = int(request_id_str.replace("WREQ-", ""))
        except ValueError:
            return {"status": "Not Found"}

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT request_status, request_date, request_type FROM warranty_requests WHERE request_id = ?", (req_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "request_id": request_id_str,
                "status": row['request_status'],
                "request_date": row['request_date'],
                "request_type": row['request_type']
            }
        return {"status": "Not Found"}

    @staticmethod
    def GenerateQRCodeImage(url):
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Save to memory bytes
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        return img_byte_arr.getvalue()
