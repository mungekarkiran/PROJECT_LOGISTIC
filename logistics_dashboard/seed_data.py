"""
Generates 3 years of realistic logistics dummy data.
- Writes CSVs to ./data_csv/
- Inserts into logistics.db (idempotent: wipes data tables first)
"""
import os, csv, random, math
from datetime import datetime, timedelta, date
from database import get_connection

random.seed(42)

CSV_DIR = "data_csv"
os.makedirs(CSV_DIR, exist_ok=True)

# ---- reference data (realistic Indian logistics network) ----
WAREHOUSES = [
    ("WH-Mumbai",   "Mumbai",    "Maharashtra", 19.0760, 72.8777),
    ("WH-Delhi",    "Delhi",     "Delhi",       28.7041, 77.1025),
    ("WH-Bengaluru","Bengaluru", "Karnataka",   12.9716, 77.5946),
    ("WH-Chennai",  "Chennai",   "Tamil Nadu",  13.0827, 80.2707),
    ("WH-Kolkata",  "Kolkata",   "West Bengal", 22.5726, 88.3639),
    ("WH-Hyderabad","Hyderabad", "Telangana",   17.3850, 78.4867),
    ("WH-Pune",     "Pune",      "Maharashtra", 18.5204, 73.8567),
    ("WH-Ahmedabad","Ahmedabad", "Gujarat",     23.0225, 72.5714),
    ("WH-Jaipur",   "Jaipur",    "Rajasthan",   26.9124, 75.7873),
    ("WH-Lucknow",  "Lucknow",   "Uttar Pradesh", 26.8467, 80.9462),
]

CARRIERS = [
    ("BlueDart Express",  0.93, 12.5),
    ("Delhivery",         0.89, 10.0),
    ("DTDC",              0.85,  9.5),
    ("Ekart Logistics",   0.90, 11.0),
    ("XpressBees",        0.87, 10.5),
    ("Gati KWE",          0.82,  8.5),
]

VEHICLE_MAKES = [
    ("Tata",     ["Ace", "407", "Prima"]),
    ("Ashok Leyland", ["Dost", "Boss", "Ecomet"]),
    ("Mahindra", ["Bolero Pickup", "Jeeto"]),
    ("Eicher",   ["Pro 1049", "Pro 2049"]),
]

PRIORITIES = ["Standard", "Express", "Priority"]   # weights applied below
PRIORITY_W = [0.65, 0.25, 0.10]

def haversine(lat1, lon1, lat2, lon2):
    """distance in km"""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl   = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return round(2 * R * math.asin(math.sqrt(a)), 1)

def write_csv(name, headers, rows):
    path = os.path.join(CSV_DIR, name)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)
    print(f"  ✓ {path} ({len(rows)} rows)")

def seed():
    conn = get_connection(); cur = conn.cursor()

    # ---- clean data tables (keep users) ----
    for t in ["shipments", "vehicles", "carriers", "warehouses", "model_metrics"]:
        cur.execute(f"DELETE FROM {t}")
    cur.execute("DELETE FROM sqlite_sequence WHERE name IN "
                "('shipments','vehicles','carriers','warehouses')")
    conn.commit()

    # ---- warehouses ----
    for w in WAREHOUSES:
        cur.execute("INSERT INTO warehouses (name, city, state, lat, lon) VALUES (?,?,?,?,?)", w)
    conn.commit()
    wh_rows = cur.execute("SELECT * FROM warehouses").fetchall()
    wh_by_id = {r["id"]: r for r in wh_rows}
    write_csv("warehouses.csv",
              ["id", "name", "city", "state", "lat", "lon"],
              [[r["id"], r["name"], r["city"], r["state"], r["lat"], r["lon"]] for r in wh_rows])

    # ---- carriers ----
    for c in CARRIERS:
        cur.execute("INSERT INTO carriers (name, reliability_score, base_rate_per_km) VALUES (?,?,?)", c)
    conn.commit()
    carrier_rows = cur.execute("SELECT * FROM carriers").fetchall()
    write_csv("carriers.csv",
              ["id", "name", "reliability_score", "base_rate_per_km"],
              [[r["id"], r["name"], r["reliability_score"], r["base_rate_per_km"]] for r in carrier_rows])

    # ---- vehicles ----
    veh_rows = []
    plate_ctr = 1
    for c in carrier_rows:
        for _ in range(random.randint(8, 12)):
            make, models = random.choice(VEHICLE_MAKES)
            model = random.choice(models)
            year  = random.randint(2015, 2023)
            mil   = random.randint(20_000, 180_000)
            last_service = (datetime.now() - timedelta(days=random.randint(5, 150))).date().isoformat()
            plate = f"MH{random.randint(10,99)}AB{plate_ctr:04d}"
            plate_ctr += 1
            cur.execute(
                "INSERT INTO vehicles (plate, carrier_id, make, model, year, mileage_km, last_service_date) "
                "VALUES (?,?,?,?,?,?,?)",
                (plate, c["id"], make, model, year, mil, last_service)
            )
            veh_rows.append((plate, c["id"], make, model, year, mil, last_service))
    conn.commit()
    all_vehicles = cur.execute("SELECT * FROM vehicles").fetchall()
    write_csv("vehicles.csv",
              ["id", "plate", "carrier_id", "make", "model", "year", "mileage_km", "last_service_date"],
              [[v["id"], v["plate"], v["carrier_id"], v["make"], v["model"],
                v["year"], v["mileage_km"], v["last_service_date"]] for v in all_vehicles])

    # ---- shipments: 3 YEARS, ~2 per day (≈2200 rows) ----
    print("  Generating 3 years of shipments...")
    today = date.today()
    start = today - timedelta(days=365 * 3)
    shipment_rows_csv = []
    ship_ctr = 1
    d = start
    while d <= today:
        # more shipments on weekdays, peak around month-end
        weekday_factor = 2 if d.weekday() < 5 else 1
        month_end_bonus = 1 if d.day >= 25 else 0
        n_today = random.randint(1, 3) + weekday_factor + month_end_bonus

        for _ in range(n_today):
            origin = random.choice(wh_by_id_values := list(wh_by_id.values()))
            dest   = random.choice([w for w in wh_by_id_values if w["id"] != origin["id"]])
            carrier = random.choice(carrier_rows)
            distance = haversine(origin["lat"], origin["lon"], dest["lat"], dest["lon"])
            weight = round(random.uniform(1, 500), 1)
            priority = random.choices(PRIORITIES, PRIORITY_W)[0]

            # promised lead time (hours) — distance/carrier/priority based
            base_hours = distance / 55.0                         # avg 55 km/h
            promise_hours = {
                "Priority": base_hours * 0.75,
                "Express":  base_hours * 1.0,
                "Standard": base_hours * 1.5,
            }[priority]
            promised_dt = datetime.combine(d, datetime.min.time()) + timedelta(hours=promise_hours + random.uniform(-2, 2))

            # actual delivery:
            #  - before today's cut-off: mostly delivered, delay likelihood by carrier + priority
            #  - shipment created in the last 4 days: still in pipeline
            days_ago = (today - d).days
            if days_ago > 4:
                # probability of on-time ≈ carrier reliability * priority factor
                p_on_time = carrier["reliability_score"] * (1.05 if priority != "Standard" else 1.0)
                p_on_time = min(0.98, p_on_time)
                if random.random() < p_on_time:
                    actual_dt = promised_dt + timedelta(minutes=random.randint(-180, 30))
                    status = "Delivered"
                else:
                    delay_h = random.randint(2, 48)
                    actual_dt = promised_dt + timedelta(hours=delay_h)
                    status = "Delivered" if days_ago > delay_h / 24 else "Delayed"
            else:
                actual_dt = None
                status = random.choice(["Created", "Picked Up", "In Transit", "Out for Delivery"])

            vehicle = random.choice([v for v in all_vehicles if v["carrier_id"] == carrier["id"]])
            tracking = f"SH{ship_ctr:06d}"
            ship_ctr += 1

            cur.execute("""
                INSERT INTO shipments
                (tracking_no, origin_wh_id, dest_wh_id, carrier_id, vehicle_id,
                 weight_kg, priority, created_at, promised_date, actual_delivery_date,
                 status, created_by_user_id, distance_km, eta_hours)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                tracking, origin["id"], dest["id"], carrier["id"], vehicle["id"],
                weight, priority, d.isoformat(), promised_dt.isoformat(),
                actual_dt.isoformat() if actual_dt else None,
                status, None, distance, round(promise_hours, 2)
            ))
            shipment_rows_csv.append([
                tracking, origin["id"], dest["id"], carrier["id"], vehicle["id"],
                weight, priority, d.isoformat(), promised_dt.isoformat(),
                actual_dt.isoformat() if actual_dt else "",
                status, distance, round(promise_hours, 2),
                d.weekday()
            ])
        d += timedelta(days=1)

    conn.commit()
    write_csv("shipments.csv",
              ["tracking_no", "origin_wh_id", "dest_wh_id", "carrier_id", "vehicle_id",
               "weight_kg", "priority", "created_at", "promised_date", "actual_delivery_date",
               "status", "distance_km", "eta_hours", "day_of_week"],
              shipment_rows_csv)

    # ---- final count ----
    for tbl in ["warehouses", "carriers", "vehicles", "shipments"]:
        n = cur.execute(f"SELECT COUNT(*) c FROM {tbl}").fetchone()["c"]
        print(f"  DB {tbl}: {n} rows")

    conn.close()
    print("\n✅ Seed complete. CSVs in ./data_csv/, DB rows inserted.")

if __name__ == "__main__":
    seed()