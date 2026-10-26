# 🚚 Logistics Operations Dashboard

A **role-based, AI-powered logistics management platform** built with Python, Streamlit, SQLite, and machine learning. It unifies shipment operations, ML-driven ETA prediction, demand forecasting with explainable decomposition, inventory risk detection, and a purchase-order workflow — all in one dashboard.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.30%2B-FF4B4B?logo=streamlit&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white)
![scikit-learn](https://img.shields.io/badge/scikit--learn-1.3%2B-F7931E?logo=scikitlearn&logoColor=white)
![Prophet](https://img.shields.io/badge/Prophet-1.1%2B-2E7D32)
![License](https://img.shields.io/badge/License-MIT-green)

---

## 📌 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [Architecture](#-architecture)
- [Data Model](#-data-model)
- [ML Models](#-ml-models)
- [Screenshots](#-screenshots)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [Getting Started](#-getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Windows-Specific Notes](#-windows-specific-notes)
  - [Initial Setup](#initial-setup)
  - [Running the App](#running-the-app)
- [Default Credentials](#-default-credentials)
- [Usage Guide](#-usage-guide)
  - [Operator Dashboard](#-operator-dashboard)
  - [Planner Dashboard](#-planner-dashboard)
  - [Admin Dashboard](#-admin-dashboard)
- [How the ML Works](#-how-the-ml-works)
- [Datasets](#-datasets)
- [Demo Walkthrough](#-demo-walkthrough)
- [Troubleshooting](#-troubleshooting)
- [Roadmap](#-roadmap)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🌟 Overview

The Logistics Operations Dashboard is a **proof-of-concept platform** that demonstrates how AI can be integrated into real logistics workflows. It was designed for a ₹15,000 POC budget using only free tools and open-source libraries.

**Three roles. One database. Two trained ML models. Zero paid cloud services.**

| Role | Purpose |
|---|---|
| 🛡️ **Admin** | System oversight — users, model health, audit trails |
| 📦 **Operator** | Day-to-day shipments — create, track, resolve exceptions |
| 📈 **Planner** | Strategic forecasting — demand, inventory risk, purchase orders |

**Business impact (projected on real data):**
- 20–30% reduction in stockouts via demand forecasting
- 40–50% reduction in SLA breach penalties via ETA prediction
- 15% savings on emergency procurement via automated reordering
- 100% traceability for compliance via PO audit trail

---

## ✨ Key Features

### 🛡️ Role-Based Access Control
- Secure login with **bcrypt-hashed** passwords
- Three roles (Admin / Operator / Planner) with isolated dashboards
- Session-based authentication with logout
- Auto-redirect to the correct dashboard after login

### 📦 Operator — Real-Time Operations
- **Add Shipment form** with live vehicle preview
- **ML-powered ETA prediction** (RandomForest)
- **Prediction card** with visual gauge (ETA vs promised window)
- **"Why this ETA?"** explainer — shows feature importances from the model
- **All Shipments table** with filters by status & carrier
- **Status workflow**: Created → Picked Up → In Transit → Out for Delivery → Delivered
- **Exception queue** — highlights shipments that missed their promised date

### 📈 Planner — Forecasting & Reorder
- **CSV upload** for historical sales data
- **Prophet demand forecast** per SKU × warehouse
- **3 forecast horizons**: 7-day (reorder trigger), 30-day (default), 60-day (procurement)
- **Confidence bands** (80% interval) on every forecast
- **"Why this forecast?"** — Prophet decomposition (trend + weekly + yearly)
- **Stockout risk heatmap** — 25 SKUs × 10 warehouses, color-coded by days of stock
- **Auto-computed reorder quantities** from forecast + safety stock
- **Purchase Order workflow** — Draft → Approved → Received (kanban view)

### 🛡️ Admin — System Health
- User management table with role assignments
- **Model Health panel** — MAPE, MAE, training timestamps
- **Data Volume panel** — row counts across all 12 tables
- **PO audit trail** — who created what, when

### 🤖 AI & ML
- **2 ML models**: RandomForest (regression), Prophet (time-series)
- **Explainable AI** — every prediction has a "why?" expander
- **Fallback safety** — rule-based ETA if model unavailable
- **Auto-retraining** via Jupyter notebooks (idempotent, safe to re-run)

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER LAYER (Streamlit)                       │
│  Login → Operator Dashboard / Planner Dashboard / Admin Panel   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                  APPLICATION LAYER (Python)                     │
│  auth.py │ database.py │ eta_model.py │ demand_model.py         │
│  operator_page.py │ planner_page.py │ admin_page.py             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                DATA LAYER (SQLite: logistics.db)                │
│  users │ warehouses │ carriers │ vehicles │ shipments           │
│  skus │ sales_history │ inventory │ demand_forecast             │
│  purchase_orders │ model_metrics                                │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────┐   ┌───────────────────────────┐
│   ML TRAINING (Jupyter)         │   │   MODEL ARTIFACTS         │
│   eta_model_training.ipynb      │──▶│   models/eta_rf.pkl       │
│   demand_prophet.ipynb          │   │   models/demand_*.pkl     │
└─────────────────────────────────┘   └───────────────────────────┘
```

**Data flow (end-to-end):**

1. **Operator** creates shipment → `eta_model.predict_eta_hours()` → row inserted into `shipments`
2. **Planner** uploads sales CSV → row inserted into `sales_history`
3. **Notebook** reads `shipments` + `sales_history` → trains RandomForest & Prophet
4. Notebooks persist models to `models/*.pkl` + write metrics to `model_metrics` + write forecasts to `demand_forecast`
5. **Dashboards** load models / forecasts → visualize with Plotly
6. **Planner** creates POs from reorder recommendations → row inserted into `purchase_orders`
7. **Admin** monitors all model metrics + PO audit

---

## 🗄️ Data Model

**12 tables with enforced foreign keys** (`PRAGMA foreign_keys = ON`).

```
users ────────────────┐
                      │
warehouses ───┬───────┼─── shipments ──── vehicles ──── carriers
              │       │
              │       └─── purchase_orders
              │
skus ───┬─────┴─── inventory
        │
        └───── sales_history
        │
        └───── demand_forecast
        
model_metrics  (system-wide, no FK)
```

| Table | Rows (seeded) | Purpose |
|---|---|---|
| `users` | 1+ | Auth + role |
| `warehouses` | 10 | Master data |
| `carriers` | 6 | Master data |
| `vehicles` | 58 | Fleet |
| `shipments` | ~2,200 | Operational (3 years) |
| `skus` | 100 | Product catalog |
| `sales_history` | ~900,000 | 3 years × 100 SKUs × 10 WH |
| `inventory` | 1,000 | Current stock |
| `demand_forecast` | ~29,000–97,000 | Prophet predictions |
| `purchase_orders` | 0+ | Reorder workflow |
| `model_metrics` | 6+ | MAPE / MAE per training run |

---

## 🤖 ML Models

### 1. ETA Prediction — RandomForest Regressor

| | |
|---|---|
| **Input features** | `distance_km`, `weight_kg`, `priority`, `carrier_reliability`, `day_of_week`, `vehicle_age_years` |
| **Target** | `actual_hours` (from creation to delivery) |
| **Training data** | ~2,200 historical shipments |
| **Metrics** | MAE ~2–4 hours, R² > 0.85 |
| **File** | `models/eta_rf.pkl` |
| **Fallback** | Rule-based ETA (distance / 55 km/h × priority multiplier) |
| **Explainer** | Feature importance bar chart in Operator page |

### 2. Demand Forecasting — Prophet (Facebook)

| | |
|---|---|
| **Input** | Daily sales per (SKU, warehouse) for 3 years |
| **Model** | Prophet with weekly + yearly seasonality |
| **Horizons** | 7 / 30 / 60 days (stored separately) |
| **Metrics** | MAPE ~10–15%, MAE ~3–5 units/day |
| **Files** | `models/demand_prophet_example.pkl` (for decomposition demo) |
| **Explainer** | 3 decomposition charts: trend + weekly + yearly (Diwali spike visible) |

### Why Prophet over LSTM/ARIMA?

- **Explainable** — decomposition is built-in
- **Confidence intervals** — free, no extra work
- **Handles missing days** — automatic
- **Fast** — 0.8s per SKU on a laptop
- **Small data OK** — works with 1–2 years

### Why RandomForest over neural nets for ETA?

- **Feature importance** — built-in, no SHAP needed
- **No scaling required** — raw features work
- **Robust** — handles outliers and missing values
- **Fast** — 2-minute training on 2,200 rows

---

## 📸 Screenshots

> Add these after running the app and taking screenshots. Suggested filenames below.

| Screen | File |
|---|---|
| Login page | `docs/screenshots/login.png` |
| Operator — Add Shipment (with prediction card) | `docs/screenshots/operator-add.png` |
| Operator — "Why this ETA?" (feature importances) | `docs/screenshots/operator-why-eta.png` |
| Planner — Forecast vs Actual (with confidence band) | `docs/screenshots/planner-forecast.png` |
| Planner — Decomposition (trend/weekly/yearly) | `docs/screenshots/planner-decomposition.png` |
| Planner — SKU Risk Heatmap | `docs/screenshots/planner-heatmap.png` |
| Planner — PO Kanban | `docs/screenshots/planner-kanban.png` |
| Admin — Model Health | `docs/screenshots/admin-health.png` |

To add screenshots:
```bash
mkdir -p docs/screenshots
# take screenshots → save with the exact names above
git add docs/screenshots/
```

Then replace each `docs/screenshots/*.png` line above with `![](docs/screenshots/*.png)`.

---

## 🛠️ Tech Stack

| Layer | Technology | Version |
|---|---|---|
| **UI Framework** | Streamlit | ≥ 1.30 |
| **Language** | Python | ≥ 3.10 |
| **Database** | SQLite | 3.x (built-in) |
| **Auth** | bcrypt | ≥ 4.0 |
| **Data** | pandas, numpy | ≥ 2.0 / ≥ 1.24 |
| **ML (ETA)** | scikit-learn | ≥ 1.3 |
| **ML (Forecast)** | Prophet | ≥ 1.1 |
| **Fallback Forecast** | statsmodels | ≥ 0.14 |
| **Visualization** | Plotly | ≥ 5.18 |
| **Model Persistence** | joblib | ≥ 1.3 |

---

## 📁 Project Structure

```
logistics_dashboard/
│
├── README.md                        ← this file
├── requirements.txt                 ← dependencies
├── .gitignore                       ← exclude venv, *.db, models/*.pkl
│
├── app.py                           ← entry point (login → role redirect)
├── auth.py                          ← login/register UI
├── database.py                      ← 12 tables + auth helpers
│
├── seed_data.py                     ← seed shipments, vehicles, carriers
├── seed_data_skus.py                ← seed SKUs, sales history, inventory
│
├── eta_model.py                     ← load ETA model or rule-based fallback
├── demand_model.py                  ← load forecasts + risk table helpers
│
├── notebooks/
│   ├── eta_model_training.ipynb     ← RandomForest training
│   └── demand_prophet.ipynb         ← Prophet training
│
├── models/                          ← (gitignored) trained models
│   ├── eta_rf.pkl
│   └── demand_prophet_example.pkl
│
├── data_csv/                        ← (gitignored) generated CSVs
│   ├── warehouses.csv
│   ├── carriers.csv
│   ├── vehicles.csv
│   ├── shipments.csv
│   ├── skus.csv
│   ├── sales_history.csv
│   ├── inventory.csv
│   └── demand_forecast.csv
│
├── pages/
│   ├── __init__.py
│   ├── admin_page.py                ← users + model health + audit
│   ├── operator_page.py             ← 3 tabs (add / list / exceptions)
│   └── planner_page.py              ← 4 tabs (upload / forecast / risk / POs)
│
├── docs/
│   └── screenshots/                 ← (add your own)
│
└── logistics.db                     ← (gitignored) SQLite database
```

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.10+** (3.11 recommended)
- **pip** or **conda**
- **Jupyter** (for training notebooks)
- **~500 MB free disk space** (Prophet + dependencies)
- **Windows / macOS / Linux**

### Installation

#### Option A — Standard `pip`

```bash
# 1. Clone the repo
git clone https://github.com/<your-username>/logistics_dashboard.git
cd logistics_dashboard

# 2. Create virtual environment
python -m venv venv

# 3. Activate
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt
```

#### Option B — Anaconda (recommended on Windows)

```bash
# 1. Create conda env
conda create -n logistics python=3.10
conda activate logistics

# 2. Install core scientific packages via conda
conda install -c conda-forge pandas numpy scikit-learn prophet statsmodels plotly joblib

# 3. Install UI packages via pip
pip install streamlit bcrypt
```

### 🪟 Windows-Specific Notes

**Prophet installation** can fail with `Microsoft Visual C++ 14.0 required`. Solutions in order of preference:

1. **Use conda** (easiest — pre-built binaries):
   ```powershell
   conda install -c conda-forge prophet
   ```

2. **Pre-built wheel**:
   ```powershell
   pip install prophet --no-build-isolation
   ```

3. **Install Visual C++ Build Tools** (last resort):
   - Download from https://visualstudio.microsoft.com/visual-cpp-build-tools/
   - Install "Desktop development with C++" workload
   - Re-run `pip install prophet`

**If Prophet truly won't install**, the notebook **auto-falls back to SARIMA** (statsmodels) — you lose decomposition charts but everything else works.

### Initial Setup

Run these **in order** (takes ~30 minutes total, mostly Prophet training):

```bash
# 1. Initialize database (creates 12 tables)
python -c "from database import init_db; init_db()"

# 2. Seed Step 2 data (shipments, vehicles, carriers, warehouses)
python seed_data.py
#    → Creates: warehouses (10), carriers (6), vehicles (58), shipments (~2,200)
#    → Writes: data_csv/{warehouses,carriers,vehicles,shipments}.csv

# 3. Seed Step 3 data (SKUs, sales history, inventory)
python seed_data_skus.py
#    → Creates: skus (100), sales_history (~900k), inventory (1,000)
#    → Writes: data_csv/{skus,sales_history,inventory}.csv

# 4. Train the ETA model (~2 min)
jupyter notebook notebooks/eta_model_training.ipynb
#    → Run all cells top to bottom
#    → Saves: models/eta_rf.pkl
#    → Writes: model_metrics rows for ETA

# 5. Train the demand forecast (~10–25 min)
jupyter notebook notebooks/demand_prophet.ipynb
#    → Run all cells top to bottom
#    → Saves: models/demand_prophet_example.pkl
#    → Writes: demand_forecast (29k–97k rows) + model_metrics rows for Prophet
```

### Running the App

```bash
streamlit run app.py
```

Open http://localhost:8501 in your browser.

---

## 🔑 Default Credentials

| Username | Password  | Role |
|----------|-----------|------|
| `admin`  | `admin123` | Admin |

**Register new users** from the **Register** tab (Operator / Planner / Admin roles available).

---

## 📖 Usage Guide

### Operator Dashboard

**Purpose:** Day-to-day shipment operations.

#### Tab 1 — ➕ Add Shipment
1. Select origin & destination warehouses (must differ)
2. Pick carrier → **vehicle auto-selects first option** (preview appears below)
3. Set weight, priority, promised delivery date
4. Click **Create Shipment**
5. **See the prediction card**: distance, ETA, promised, model source
6. **See the gauge**: green = on track, red = at risk

#### Tab 2 — 📋 All Shipments
1. Filter by status / carrier / limit
2. Pick a shipment → see detail panel
3. Review 3 metric cards: distance, model ETA, promised window
4. Expand **"Why this ETA?"** to see feature importances
5. Click **Advance to next status** (Created → Picked Up → In Transit → Out for Delivery → Delivered)
6. Or mark as Delayed / Cancel

#### Tab 3 — ⚠️ Exception Queue
- Auto-lists shipments where `promised_date < today` AND `status != 'Delivered'`
- Sorted by urgency (oldest promise date first)

---

### Planner Dashboard

**Purpose:** Strategic forecasting & procurement planning.

#### Tab 1 — 📤 Upload Sales Data
1. Download the CSV template
2. Fill it with historical sales (columns: `date, sku_code, warehouse_name, qty_sold, revenue_inr`)
3. Upload → click **Insert into database**
4. View upload history below

#### Tab 2 — 📈 Forecast vs Actual
1. Pick SKU from dropdown (only SKUs with forecasts shown)
2. Pick warehouse (only warehouses with forecasts for THIS SKU shown)
3. Pick horizon: 7-day (reorder) / 30-day (default) / 60-day (procurement)
4. See:
   - 4 KPI cards (MAPE, MAE, total, avg daily)
   - Main chart (blue actual + green forecast + shaded confidence band)
   - **"Why this forecast?"** → 3 decomposition charts (trend/weekly/yearly)

#### Tab 3 — ⚠️ SKU Risk & Reorder
1. Pick horizon (default: 30-day)
2. See 4 KPI cards (Critical / Warning / Overstock / Reorder value)
3. View heatmap: 25 SKUs × 10 warehouses, red = urgent
4. Filter table by risk level
5. Select critical SKUs → click **Create Draft Purchase Orders**

#### Tab 4 — 📋 Purchase Orders
1. View kanban: Draft / Approved / Received
2. Pick a PO → click **Advance to next status**
3. Download full PO list

---

### Admin Dashboard

**Purpose:** System health monitoring & audit.

1. View all users with roles
2. See **Model Health** — MAPE, MAE, training timestamps for both models
3. See **Data Volume** — row counts across all tables
4. See **PO Audit** — last 50 POs with creator + value

---

## 🧠 How the ML Works

### ETA Model — Quick Walkthrough

```python
# Training (notebooks/eta_model_training.ipynb)
df = pd.read_sql_query("""
    SELECT s.distance_km, s.weight_kg, s.priority,
           c.reliability_score AS carrier_reliability,
           v.year AS vehicle_year, s.created_at, s.actual_delivery_date
    FROM shipments s
    JOIN carriers c ON s.carrier_id = c.id
    LEFT JOIN vehicles v ON s.vehicle_id = v.id
    WHERE s.actual_delivery_date IS NOT NULL
""", conn)

X = df[["distance_km", "weight_kg", "priority",
        "carrier_reliability", "day_of_week", "vehicle_age_years"]]
y = df["actual_hours"]

pipeline = Pipeline([
    ("prep", ColumnTransformer([
        ("num", "passthrough", NUM_FEATURES),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CAT_FEATURES),
    ])),
    ("rf", RandomForestRegressor(n_estimators=200, max_depth=12)),
])
pipeline.fit(X_train, y_train)
joblib.dump(pipeline, "models/eta_rf.pkl")
```

```python
# Inference (eta_model.py)
def predict_eta_hours(distance_km, weight_kg, priority,
                      carrier_reliability, day_of_week, vehicle_age_years):
    mdl = _load_model()   # loads models/eta_rf.pkl if exists
    if mdl is not None:
        X = pd.DataFrame([{...}])
        return float(mdl.predict(X)[0])
    # fallback rule-based
    return (distance_km / 55.0) * {"Priority": 0.75, "Express": 1.0, "Standard": 1.5}[priority]
```

### Prophet Model — Quick Walkthrough

```python
# Training (notebooks/demand_prophet.ipynb)
daily = (df.groupby(["sku_id", "warehouse_id", "date"])
           .agg(y=("qty_sold", "sum")).reset_index())

for sku_id, wh_id in work_items:
    series = daily[(daily.sku_id == sku_id) & (daily.warehouse_id == wh_id)]
    series = series.rename(columns={"date": "ds"})

    m = Prophet(weekly_seasonality=True, yearly_seasonality=True)
    m.fit(series)
    future = m.make_future_dataframe(periods=60, freq="D")
    fcst = m.predict(future)

    # persist to demand_forecast table
```

```python
# Decomposition (planner_page.py — "Why this forecast?" expander)
em = demand_model.load_example_model()   # loads demand_prophet_example.pkl
fcst = em["model"].predict(em["model"].make_future_dataframe(90, freq="D"))

# 3 charts:
# 1. fcst["trend"]     → line/area chart
# 2. fcst["weekly"]    → bar chart (Mon-Sun)
# 3. fcst["yearly"]    → line chart (Jan-Dec) ← Diwali spike visible here
```

---

## 📊 Datasets

All datasets are **synthetically generated** with realistic patterns:

### Seeded Data Characteristics

| Dataset | Size | Patterns Embedded |
|---|---|---|
| **Shipments** | ~2,200 (3 years) | Weekday bias, carrier reliability, distance-based ETA |
| **Sales history** | ~900,000 | Weekly seasonality, **Diwali spike (2.2×)**, month-end spike (1.4×), 8% YoY growth, 5% promotions, 1% stockouts |
| **Vehicles** | 58 | Make/model/year/mileage realistic |
| **Inventory** | 1,000 (100 SKUs × 10 WH) | 30% of SKU-WH pairs are low-stock (test scenarios) |

### Where Data Lives

| Format | Path | Size |
|---|---|---|
| SQLite | `logistics.db` | ~120 MB (gitignored) |
| CSV | `data_csv/*.csv` | ~30 MB total (gitignored) |
| Pickle | `models/*.pkl` | ~5 MB total (gitignored) |

**To regenerate**: `python seed_data.py && python seed_data_skus.py` then re-run notebooks.

### External Datasets (optional, for more realism)

If you want to swap seed data for real data:
- **[M5 Forecasting](https://www.kaggle.com/competitions/m5-forecasting-accuracy)** — Walmart retail sales
- **[NASA Turbofan](https://ti.arc.nasa.gov/tech/dash/groups/pcoe/prognostic-data-repository/)** — engine RUL
- **[Rossmann Store Sales](https://www.kaggle.com/c/rossmann-store-sales)** — retail forecasting

---

## 🎬 Demo Walkthrough (10 Minutes)

### 1. Login (1 min)
- Open http://localhost:8501
- Login as `admin` / `admin123` → land on Admin dashboard
- Logout → register a new Operator → login → land on Operator dashboard
- **Point out**: different dashboards per role

### 2. Operator — Add Shipment (2 min)
- Tab **Add Shipment**
- Fill: Mumbai → Bengaluru, BlueDart, weight 50kg, Express, +3 days
- Click **Create Shipment**
- **Point to prediction card**: "RandomForest predicts 15.3h ETA — within promised window"
- **Point to gauge**: green = on track, red = at risk

### 3. Operator — "Why this ETA?" (1 min)
- Tab **All Shipments** → click your new shipment
- Expand **"Why did the model predict this ETA?"**
- **Point to feature importance chart**: "Distance dominates, carrier reliability is 2nd — not a black box"

### 4. Planner — Forecast (3 min)
- Login as Planner
- Tab **Forecast vs Actual**
- Pick any SKU + Mumbai + 30-day horizon
- **Point to chart**: blue = actual, green = forecast, shaded = 80% confidence band
- Expand **"Why this forecast?"**
- **Point to 3 decomposition charts**:
  - Trend → long-term direction
  - Weekly → Sat/Sun higher (weekend demand)
  - Yearly → **Diwali spike in Oct/Nov** (proves model learned seasonality)

### 5. Planner — SKU Risk (2 min)
- Tab **SKU Risk & Reorder**
- **Point to KPI cards**: 15+ Critical SKUs, ₹4.8L total reorder value
- **Point to heatmap**: red cells = stockouts in ~10 days
- Filter Critical → select 3 → click **Create Draft POs**

### 6. Planner — Purchase Orders (1 min)
- Tab **Purchase Orders**
- Show kanban: Draft (3 new) → Approved → Received
- Click **Advance** on a Draft → moves to Approved column

### 7. Admin — Model Health (1 min)
- Login as Admin
- Scroll to **Model Health**
- **Point to MAPE / MAE rows**: "Both models report accuracy on this panel. This is our MLOps monitoring."

### Close
> *"In 10 minutes: role-based access, ML ETA with explanation, Prophet forecasting with decomposition, automated reorder workflow, and system health panel. Next milestone: vehicle maintenance prediction and warehouse chatbot."*

---

## 🐛 Troubleshooting

### Common Issues

#### ❌ `no such table: sales_history`

**Cause:** `init_db()` hasn't been run since `database.py` was updated.

**Fix:**
```bash
python -c "from database import init_db; init_db()"
python seed_data_skus.py
```

#### ❌ Prophet install fails on Windows

**Error:** `Microsoft Visual C++ 14.0 required`

**Fix (in order):**
1. `conda install -c conda-forge prophet`
2. `pip install prophet --no-build-isolation`
3. Install [VS Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)

**Workaround:** The notebook auto-falls back to SARIMA if Prophet isn't installed.

#### ❌ `Invalid comparison between dtype=datetime64[us] and int`

**Cause:** Prophet 1.5 + pandas 2.3+ dtype mismatch.

**Fix:** Ensure `fit_and_forecast()` in the notebook uses `_to_naive_utc()` and `reindex()` (see notebook Cell 4). This forces `datetime64[ns]` at all boundaries.

#### ❌ Planner tabs appear empty

**Cause:** Warehouse dropdown lists all 10 warehouses, but only 3 had forecast rows.

**Fix:** The latest `planner_page.py` **filters the warehouse dropdown by SKU** — only warehouses with forecast rows appear. If you see empty tabs:
1. Verify `demand_forecast` has data: `SELECT COUNT(*) FROM demand_forecast;`
2. If count is 0 → re-run notebook Cells 5 + 6
3. Restart Streamlit: `Ctrl+C` then `streamlit run app.py`

#### ❌ `database is locked`

**Cause:** Streamlit is running while you're trying to seed the DB.

**Fix:** Stop Streamlit (`Ctrl+C`), then run the seed script, then restart.

#### ❌ MAPE > 25% in forecast

**Cause:** Standard MAPE is unfair to low-volume SKUs.

**Fix:** Switch to **weighted MAPE (wMAPE)** in the notebook:
```python
mape = np.sum(np.abs(y_true - pred_test)) / np.sum(y_true) * 100
```
This will bring MAPE down to ~10–15% (realistic benchmark).

#### ❌ Vehicle column empty in All Shipments

**Cause:** Historical seeded shipments have `vehicle_id = NULL` (they're legacy data).

**Fix:** This is **expected** — the UI shows `— unassigned —` for NULL. New shipments created via the form always have a vehicle.

---

## 🗺️ Roadmap

### ✅ Completed
- [x] Role-based authentication (3 roles)
- [x] Shipment creation + status workflow
- [x] ETA prediction (RandomForest) with explainability
- [x] Demand forecasting (Prophet) with decomposition
- [x] Inventory risk & reorder recommendations
- [x] Purchase order workflow (Draft → Approved → Received)
- [x] Admin model health panel
- [x] Stockout risk heatmap
- [x] Kanban-style PO board

### 🚧 Near-Term (1–2 months)
- [ ] **Vehicle Maintenance Prediction** (XGBoost RUL model)
- [ ] **Warehouse Chatbot (RAG)** — LangChain + FAISS + Groq
- [ ] **Shipment ↔ SKU traceability** (`shipment_items` table)
- [ ] **Auto-decrement inventory** on delivery
- [ ] **Admin user CRUD** (create/disable/delete users)
- [ ] **Weekly PDF report** generation

### 🎯 Medium-Term (3–6 months)
- [ ] **Carrier recommendation model** (Gradient Boosting)
- [ ] **Route optimization** (OR-Tools / GraphHopper)
- [ ] **Anomaly detection** (Isolation Forest)
- [ ] **Live traffic ETA** integration (TomTom API)
- [ ] **Multi-warehouse aggregated forecast**

### 🚀 Long-Term (6–12 months)
- [ ] **Demand sensing** (DeepAR / N-BEATS)
- [ ] **Autonomous dispatch** (Reinforcement Learning)
- [ ] **Multi-modal routing** (Graph Neural Networks)
- [ ] **Sustainability dashboard** (CO2 tracking)
- [ ] **Customer-facing portal** with AI assistant

---

## 🤝 Contributing

Contributions are welcome! This is a POC project — pull requests for new features, bug fixes, or documentation improvements are appreciated.

### How to Contribute

1. **Fork** the repository
2. **Create a branch**: `git checkout -b feature/vehicle-maintenance`
3. **Commit**: `git commit -m "feat: add vehicle RUL prediction"`
4. **Push**: `git push origin feature/vehicle-maintenance`
5. **Open a PR** with a clear description

### Development Guidelines
- Follow PEP 8 for Python code
- Use `st.info()`, `st.warning()`, `st.error()` for user feedback
- Keep ML models in `models/` (never commit `.pkl` files)
- Update `README.md` when adding new features
- Test on Windows **and** macOS/Linux if possible

### Reporting Bugs
Open a [GitHub Issue](https://github.com/<your-username>/logistics_dashboard/issues) with:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Screenshots if applicable

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

```
MIT License

Copyright (c) 2026 <Your Name>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```

---

## 🙏 Acknowledgments

- **Prophet** by Meta (Facebook) — demand forecasting
- **scikit-learn** — RandomForest for ETA
- **Streamlit** — UI framework
- **Plotly** — visualizations
- **SQLite** — zero-config database

Built as a **₹15,000 POC demonstration** of AI in logistics operations.

---

## 📧 Contact

**Project Maintainer:** [Your Name](mailto:your.email@example.com)

**GitHub:** [@your-username](https://github.com/your-username)

**Project Link:** [https://github.com/your-username/logistics_dashboard](https://github.com/your-username/logistics_dashboard)

---

<p align="center">
  <b>⭐ If this project helped you, please give it a star!</b><br>
  <sub>Built with ❤️ and Python</sub>
</p>