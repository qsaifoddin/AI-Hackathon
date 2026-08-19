import sqlite3
import random
from datetime import datetime
from app.db.database import get_connection
from app.services.audit import log_action

class PartsService:
    @staticmethod
    def search_parts(query=None, category=None):
        """
        Searches available HP spare parts across regional warehouses.
        """
        conn = get_connection()
        cursor = conn.cursor()
        sql = "SELECT * FROM parts_catalog WHERE 1=1"
        params = []

        if query:
            sql += " AND (part_number LIKE ? OR name LIKE ? OR compatible_products LIKE ?)"
            q_pat = f"%{query}%"
            params.extend([q_pat, q_pat, q_pat])

        if category and category != 'All':
            sql += " AND category = ?"
            params.append(category)

        sql += " ORDER BY name ASC"

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def get_parts_summary():
        """
        Aggregates regional stock levels for Power BI visual analytics.
        """
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT category, SUM(stock_na) as na_total, SUM(stock_emea) as emea_total, SUM(stock_apac) as apac_total, COUNT(*) as part_count
            FROM parts_catalog
            GROUP BY category
        """)
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def place_order(case_id, part_id, quantity=1, shipping_priority="Express", warehouse_region="North America", requested_by="Alex Carter"):
        """
        Reserves spare part, deducts inventory, creates a shipment tracking order record, and logs audit details.
        """
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM parts_catalog WHERE part_id = ?", (part_id,))
        part_row = cursor.fetchone()
        if not part_row:
            conn.close()
            return {"success": False, "error": "Part not found in catalog"}

        part = dict(part_row)

        # Check regional inventory
        region_column = {'North America': 'stock_na', 'EMEA': 'stock_emea', 'APAC': 'stock_apac'}.get(warehouse_region, 'stock_na')
        current_stock = part[region_column]

        if current_stock < quantity:
            conn.close()
            return {"success": False, "error": f"Insufficient stock in {warehouse_region} warehouse. Current stock: {current_stock} units."}

        # Deduct stock
        new_stock = current_stock - quantity
        cursor.execute(f"UPDATE parts_catalog SET {region_column} = ? WHERE part_id = ?", (new_stock, part_id))

        tracking_no = f"1Z999999{random.randint(10000000, 99999999)}"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
            INSERT INTO parts_orders (
                case_id, part_id, quantity, shipping_priority, warehouse_region, status, tracking_number, order_date
            ) VALUES (?, ?, ?, ?, ?, 'Approved', ?, ?)
        """, (case_id, part_id, quantity, shipping_priority, warehouse_region, tracking_no, now_str))

        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        log_action(
            user=requested_by,
            action=f"Placed Spare Part Order #{order_id}",
            case_id=case_id,
            automation="Parts Replacement Service",
            new_value=f"Part: {part['part_number']} ({part['name']}) | Tracking: {tracking_no} | Region: {warehouse_region}",
            result="Success"
        )

        return {
            "success": True,
            "order_id": order_id,
            "part_number": part['part_number'],
            "part_name": part['name'],
            "warehouse_region": warehouse_region,
            "shipping_priority": shipping_priority,
            "tracking_number": tracking_no,
            "status": "Approved",
            "ordered_at": now_str
        }

    @staticmethod
    def get_case_orders(case_id):
        """
        Retrieves all parts dispatch orders for a specific support case.
        """
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT o.*, p.part_number, p.name as part_name, p.category, p.price_usd
            FROM parts_orders o
            JOIN parts_catalog p ON o.part_id = p.part_id
            WHERE o.case_id = ?
            ORDER BY o.order_date DESC
        """, (case_id,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]
