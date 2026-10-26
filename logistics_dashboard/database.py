import sqlite3
import bcrypt
from datetime import datetime

DB_PATH = "logistics.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db():
    """Create all tables (idempotent) and seed a default admin."""
    conn = get_connection()
    cur = conn.cursor()

    # ==========================================================
    # STEP 2 TABLES (unchanged)
    # ==========================================================
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('Admin','Operator','Planner')),
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS warehouses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            city TEXT NOT NULL,
            state TEXT NOT NULL,
            lat REAL NOT NULL,
            lon REAL NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS carriers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            reliability_score REAL NOT NULL,
            base_rate_per_km REAL NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plate TEXT UNIQUE NOT NULL,
            carrier_id INTEGER NOT NULL,
            make TEXT,
            model TEXT,
            year INTEGER,
            mileage_km INTEGER NOT NULL,
            last_service_date TEXT NOT NULL,
            FOREIGN KEY (carrier_id) REFERENCES carriers(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS shipments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tracking_no TEXT UNIQUE NOT NULL,
            origin_wh_id INTEGER NOT NULL,
            dest_wh_id INTEGER NOT NULL,
            carrier_id INTEGER NOT NULL,
            vehicle_id INTEGER,
            weight_kg REAL NOT NULL,
            priority TEXT NOT NULL CHECK(priority IN ('Standard','Express','Priority')),
            created_at TEXT NOT NULL,
            promised_date TEXT NOT NULL,
            actual_delivery_date TEXT,
            status TEXT NOT NULL CHECK(status IN ('Created','Picked Up','In Transit','Out for Delivery','Delivered','Delayed','Cancelled')),
            created_by_user_id INTEGER,
            distance_km REAL,
            eta_hours REAL,
            FOREIGN KEY (origin_wh_id) REFERENCES warehouses(id),
            FOREIGN KEY (dest_wh_id)   REFERENCES warehouses(id),
            FOREIGN KEY (carrier_id)   REFERENCES carriers(id),
            FOREIGN KEY (vehicle_id)   REFERENCES vehicles(id),
            FOREIGN KEY (created_by_user_id) REFERENCES users(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS model_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_name TEXT NOT NULL,
            version TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            metric_value REAL NOT NULL,
            trained_at TEXT NOT NULL,
            notes TEXT
        )
    """)

    # ==========================================================
    # STEP 3 — NEW TABLES
    # ==========================================================
    cur.execute("""
        CREATE TABLE IF NOT EXISTS skus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku_code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            unit_cost REAL NOT NULL,
            lead_time_days INTEGER NOT NULL DEFAULT 7,
            is_active INTEGER NOT NULL DEFAULT 1
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sales_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            sku_id INTEGER NOT NULL,
            warehouse_id INTEGER NOT NULL,
            qty_sold INTEGER NOT NULL,
            revenue_inr REAL NOT NULL,
            source TEXT DEFAULT 'seed',
            uploaded_by_user_id INTEGER,
            uploaded_at TEXT,
            FOREIGN KEY (sku_id) REFERENCES skus(id),
            FOREIGN KEY (warehouse_id) REFERENCES warehouses(id),
            FOREIGN KEY (uploaded_by_user_id) REFERENCES users(id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sales_sku_date ON sales_history(sku_id, date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sales_wh_date  ON sales_history(warehouse_id, date)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku_id INTEGER NOT NULL,
            warehouse_id INTEGER NOT NULL,
            qty_on_hand INTEGER NOT NULL,
            safety_stock INTEGER NOT NULL,
            reorder_point INTEGER NOT NULL,
            last_updated TEXT NOT NULL,
            UNIQUE(sku_id, warehouse_id),
            FOREIGN KEY (sku_id) REFERENCES skus(id),
            FOREIGN KEY (warehouse_id) REFERENCES warehouses(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS demand_forecast (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku_id INTEGER NOT NULL,
            warehouse_id INTEGER NOT NULL,
            forecast_date TEXT NOT NULL,
            horizon_days INTEGER NOT NULL,
            yhat REAL NOT NULL,
            yhat_lower REAL,
            yhat_upper REAL,
            model_version TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            FOREIGN KEY (sku_id) REFERENCES skus(id),
            FOREIGN KEY (warehouse_id) REFERENCES warehouses(id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fc_sku_date ON demand_forecast(sku_id, forecast_date)")

    # ---------- NEW: purchase orders (reorder workflow) ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS purchase_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_no TEXT UNIQUE NOT NULL,
            sku_id INTEGER NOT NULL,
            warehouse_id INTEGER NOT NULL,
            qty_ordered INTEGER NOT NULL,
            unit_cost REAL NOT NULL,
            total_inr REAL NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('Draft','Approved','Received','Cancelled')),
            created_by_user_id INTEGER,
            created_at TEXT NOT NULL,
            approved_at TEXT,
            notes TEXT,
            FOREIGN KEY (sku_id) REFERENCES skus(id),
            FOREIGN KEY (warehouse_id) REFERENCES warehouses(id),
            FOREIGN KEY (created_by_user_id) REFERENCES users(id)
        )
    """)

    # ==========================================================
    # Seed default admin (unchanged)
    # ==========================================================
    cur.execute("SELECT COUNT(*) as c FROM users WHERE role='Admin'")
    if cur.fetchone()["c"] == 0:
        hashed = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode()
        cur.execute(
            "INSERT INTO users (username, email, password_hash, role, created_at) "
            "VALUES (?,?,?,?,?)",
            ("admin", "admin@logistics.local", hashed, "Admin", datetime.now().isoformat()),
        )

    conn.commit()
    conn.close()


# ---------- auth helpers (unchanged) ----------
def hash_password(p):
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def verify_password(p, h):
    try:
        return bcrypt.checkpw(p.encode(), h.encode())
    except Exception:
        return False


def create_user(username, email, password, role):
    conn = get_connection(); cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users (username, email, password_hash, role, created_at) "
            "VALUES (?,?,?,?,?)",
            (username, email, hash_password(password), role, datetime.now().isoformat()),
        )
        conn.commit()
        return True, "Registration successful! Please log in."
    except sqlite3.IntegrityError as e:
        s = str(e)
        if "username" in s:
            return False, "Username already exists."
        if "email" in s:
            return False, "Email already registered."
        return False, "Registration failed."
    finally:
        conn.close()


def authenticate(username, password):
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cur.fetchone(); conn.close()
    if row is None:
        return None, "User not found."
    if not verify_password(password, row["password_hash"]):
        return None, "Incorrect password."
    return {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"],
        "role": row["role"],
    }, None