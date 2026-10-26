"""
Generates 100 SKUs × 10 warehouses × 3 years of realistic daily sales.
Embeds weekly, monthly, yearly (Diwali) seasonality + growth + promotions.

Writes CSVs to ./data_csv/ AND inserts into logistics.db.
Idempotent: wipes skus / sales_history / inventory before reseeding.
"""
import os
import csv
import random
import math
from datetime import date, timedelta
from database import get_connection

random.seed(7)

CSV_DIR = "data_csv"
os.makedirs(CSV_DIR, exist_ok=True)

# ---- 6 categories, 100 SKUs total ----
CATEGORIES = {
    "Electronics":  ["Wireless Earbuds", "USB-C Cable", "Power Bank", "Bluetooth Speaker",
                     "Smart Watch", "Webcam HD", "Keyboard Mechanical", "Mouse Wireless",
                     "HDMI Adapter", "Phone Case"],
    "Grocery":      ["Basmati Rice 5kg", "Sunflower Oil 1L", "Wheat Flour 10kg", "Toor Dal 1kg",
                     "Tea Powder 500g", "Sugar 5kg", "Salt 1kg", "Coffee Instant 200g",
                     "Biscuits Pack", "Masala Mix"],
    "Apparel":      ["Cotton T-Shirt", "Denim Jeans", "Sports Shoes", "Formal Shirt",
                     "Winter Jacket", "Sports Socks", "Cap", "Leather Belt",
                     "Silk Scarf", "Raincoat"],
    "Home Care":    ["Detergent 2kg", "Dish Soap 500ml", "Floor Cleaner 1L", "Glass Cleaner",
                     "Toilet Cleaner", "Air Freshener", "Mop Set", "Broom",
                     "Trash Bags 30ct", "Aluminum Foil"],
    "Personal Care":["Shampoo 400ml", "Toothpaste 200g", "Body Lotion 400ml", "Face Wash",
                     "Deodorant", "Razor Pack", "Soap Bar", "Sunscreen SPF50",
                     "Hair Oil 200ml", "Hand Sanitizer"],
    "Stationery":   ["A4 Notebook", "Ball Pen Pack", "Highlighter Set", "Stapler",
                     "Calculator", "Sticky Notes", "File Folder", "Sketch Pens",
                     "Geometry Box", "Marker Set"],
}

def gen_skus():
    skus = []
    code_n = 1001
    for cat, names in CATEGORIES.items():
        # 16-17 SKUs per category → 100 total
        per_cat = math.ceil(100 / len(CATEGORIES))
        for i, base in enumerate(names * (per_cat // len(names) + 1)):
            if len(skus) >= 100:
                break
            sku_code = f"SKU-{code_n}"
            name = f"{base} ({cat[:3]}-{i+1})"
            unit_cost = {
                "Electronics":   round(random.uniform(400, 3500), 2),
                "Grocery":       round(random.uniform(40, 900), 2),
                "Apparel":       round(random.uniform(250, 1800), 2),
                "Home Care":     round(random.uniform(80, 600), 2),
                "Personal Care": round(random.uniform(60, 700), 2),
                "Stationery":    round(random.uniform(20, 400), 2),
            }[cat]
            lead_time = random.choice([3, 5, 7, 10, 14])
            skus.append({
                "sku_code": sku_code,
                "name": name,
                "category": cat,
                "unit_cost": unit_cost,
                "lead_time_days": lead_time,
                "is_active": 1,
            })
            code_n += 1
    return skus


def write_csv(name, headers, rows):
    path = os.path.join(CSV_DIR, name)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)
    print(f"  ✓ {path} ({len(rows)} rows)")


def is_diwali_window(d: date) -> bool:
    """Approximate Diwali season: Oct 15 – Nov 15."""
    return (d.month == 10 and d.day >= 15) or (d.month == 11 and d.day <= 15)


def seed():
    conn = get_connection(); cur = conn.cursor()

    # ---- clean new tables only ----
    for t in ["purchase_orders", "demand_forecast", "inventory",
              "sales_history", "skus"]:
        cur.execute(f"DELETE FROM {t}")
        cur.execute(f"DELETE FROM sqlite_sequence WHERE name = ?", (t,))
    conn.commit()

    # ---- fetch existing warehouses ----
    whs = [dict(r) for r in cur.execute(
        "SELECT id, name, city FROM warehouses ORDER BY id").fetchall()]
    if not whs:
        print("❌ No warehouses found. Run `python seed_data.py` first.")
        conn.close(); return
    print(f"Found {len(whs)} warehouses (reusing Step 2 data).")

    # ---- SKUs ----
    skus = gen_skus()
    for s in skus:
        cur.execute(
            "INSERT INTO skus (sku_code, name, category, unit_cost, lead_time_days, is_active) "
            "VALUES (?,?,?,?,?,?)",
            (s["sku_code"], s["name"], s["category"],
             s["unit_cost"], s["lead_time_days"], s["is_active"]),
        )
    conn.commit()
    sku_rows = cur.execute("SELECT * FROM skus ORDER BY id").fetchall()
    write_csv(
        "skus.csv",
        ["id", "sku_code", "name", "category", "unit_cost", "lead_time_days", "is_active"],
        [[r["id"], r["sku_code"], r["name"], r["category"],
          r["unit_cost"], r["lead_time_days"], r["is_active"]] for r in sku_rows],
    )

    # ---- warehouse weight (Mumbai/Delhi bigger) ----
    wh_weight = {}
    for w in whs:
        if w["city"] in ("Mumbai", "Delhi"):
            wh_weight[w["id"]] = 2.0
        elif w["city"] in ("Bengaluru", "Chennai", "Kolkata", "Hyderabad", "Pune"):
            wh_weight[w["id"]] = 1.3
        else:
            wh_weight[w["id"]] = 0.9

    # ---- 3 years of daily sales ----
    today = date.today()
    start = today - timedelta(days=365 * 3)
    days = (today - start).days
    print(f"Generating {len(sku_rows)} SKUs × {days} days × {len(whs)} warehouses "
          f"(≈ {len(sku_rows) * len(whs) * days:,} potential rows)...")

    # per-SKU base demand
    sku_base = {}
    sku_volatility = {}
    for r in sku_rows:
        cat_factor = {
            "Electronics": 6, "Grocery": 40, "Apparel": 12,
            "Home Care": 20, "Personal Care": 25, "Stationery": 15,
        }[r["category"]]
        sku_base[r["id"]] = round(random.uniform(0.6, 1.6) * cat_factor, 1)
        sku_volatility[r["id"]] = random.uniform(0.15, 0.35)

    history_rows = []
    n_days_since_start = 0
    d = start
    while d <= today:
        dow_factor = 1.3 if d.weekday() >= 5 else 1.0
        month_end_factor = 1.4 if d.day >= 28 else 1.0
        diwali_factor = 2.2 if is_diwali_window(d) else 1.0
        year_growth = 1.0 + 0.08 * (n_days_since_start / 365.0)
        promo = random.random() < 0.05
        promo_factor = 1.5 if promo else 1.0

        # stockout: whole day no stock for ~1% of the time (per warehouse cluster)
        cluster_stockout = random.random() < 0.01

        for sku in sku_rows:
            base = sku_base[sku["id"]] * year_growth
            vol = sku_volatility[sku["id"]]
            for w in whs:
                if cluster_stockout:
                    continue
                lam = (base
                       * wh_weight[w["id"]]
                       * dow_factor
                       * month_end_factor
                       * diwali_factor
                       * promo_factor)
                # Poisson-like count with multiplicative noise
                noise = max(0.0, random.gauss(1.0, vol))
                qty = int(round(lam * noise))
                if qty <= 0:
                    continue
                revenue = round(qty * sku["unit_cost"] * random.uniform(1.05, 1.20), 2)
                history_rows.append((
                    d.isoformat(), sku["id"], w["id"], qty, revenue, "seed"
                ))
        d += timedelta(days=1)
        n_days_since_start += 1
        if n_days_since_start % 200 == 0:
            print(f"    ... {n_days_since_start} days processed, "
                  f"{len(history_rows):,} rows so far")

    print(f"Inserting {len(history_rows):,} sales rows into DB...")
    cur.executemany(
        "INSERT INTO sales_history (date, sku_id, warehouse_id, qty_sold, revenue_inr, source) "
        "VALUES (?,?,?,?,?,?)",
        history_rows,
    )
    conn.commit()
    print("  ✓ DB sales_history populated")

    # limit CSV to keep file size reasonable (~15 MB target)
    write_csv(
        "sales_history.csv",
        ["date", "sku_id", "warehouse_id", "qty_sold", "revenue_inr", "source"],
        history_rows[:150000],
    )
    if len(history_rows) > 150000:
        print(f"  (CSV truncated to 150,000 rows — full data is in SQLite)")

    # ---- inventory (current state) ----
    print("Generating current inventory snapshot...")
    inv_rows = []
    for sku in sku_rows:
        for w in whs:
            recent_avg = (cur.execute(
                "SELECT AVG(qty_sold) a FROM sales_history "
                "WHERE sku_id = ? AND warehouse_id = ? "
                "AND date >= date('now', '-30 day')",
                (sku["id"], w["id"]),
            ).fetchone()["a"] or 0)
            lead = sku["lead_time_days"]
            safety_stock = max(5, int(round(recent_avg * lead * 0.5)))
            reorder_point = max(10, int(round(recent_avg * lead * 1.2)))
            # simulate ~30% of SKUs being low on stock, rest healthy
            if random.random() < 0.30:
                on_hand = int(recent_avg * random.uniform(1, lead * 0.8))
            else:
                on_hand = int(recent_avg * random.uniform(lead * 1.3, lead * 4))
            inv_rows.append((
                sku["id"], w["id"], max(0, on_hand),
                safety_stock, reorder_point, today.isoformat(),
            ))
    cur.executemany(
        "INSERT INTO inventory (sku_id, warehouse_id, qty_on_hand, safety_stock, "
        "reorder_point, last_updated) VALUES (?,?,?,?,?,?)",
        inv_rows,
    )
    conn.commit()
    write_csv(
        "inventory.csv",
        ["sku_id", "warehouse_id", "qty_on_hand", "safety_stock",
         "reorder_point", "last_updated"],
        inv_rows,
    )

    # ---- summary ----
    print("\n📊 Final counts:")
    for t in ["skus", "sales_history", "inventory"]:
        n = cur.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
        print(f"  {t:18s}: {n:>8,}")
    conn.close()
    print("\n✅ Seed complete. Next: run notebooks/demand_prophet.ipynb")


if __name__ == "__main__":
    seed()