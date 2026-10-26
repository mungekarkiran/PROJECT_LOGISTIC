"""
Operator Dashboard — fixed & visually enhanced.

Fixes vs previous version:
  * carrier & vehicle selectboxes now have STABLE keys  → no more NULL vehicle_id
  * vehicle dropdown defaults to FIRST vehicle (never None)
  * vehicle is REQUIRED on submit (prevents future "invisible vehicle" bugs)
  * vehicle preview card shown under the dropdown BEFORE submit
  * prediction card (gradient) shown AFTER submit with distance / ETA / model used
  * plotly gauge compares predicted ETA vs promised window (green/red)
  * All Shipments table now includes vehicle_model and shows "— unassigned —" for NULLs
  * Shipment detail panel shows 3 metric cards + "Why this ETA?" expander
    with LIVE feature importances pulled from the loaded RandomForest
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, date, timedelta
from database import get_connection
from eta_model import predict_eta_hours, model_available, _load_model, haversine

BLUE  = "#1565C0"
GREEN = "#2E7D32"
DARK  = "#0D47A1"
RED   = "#C62828"

STATUS_FLOW = ["Created", "Picked Up", "In Transit", "Out for Delivery", "Delivered"]


# ---------- helpers ----------
def _next_status(current: str):
    if current in ("Delivered", "Cancelled", "Delayed"):
        return None
    i = STATUS_FLOW.index(current)
    return STATUS_FLOW[i + 1] if i + 1 < len(STATUS_FLOW) else None


def _load_refs():
    conn = get_connection()
    whs      = pd.read_sql_query("SELECT * FROM warehouses ORDER BY city", conn)
    carriers = pd.read_sql_query("SELECT * FROM carriers  ORDER BY name", conn)
    vehicles = pd.read_sql_query("SELECT * FROM vehicles  ORDER BY plate", conn)
    conn.close()
    return whs, carriers, vehicles


def _insert_shipment(tracking_no, origin_id, dest_id, carrier_id, vehicle_id,
                     weight, priority, promised_date, distance_km, eta_hours, user_id):
    conn = get_connection(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO shipments
        (tracking_no, origin_wh_id, dest_wh_id, carrier_id, vehicle_id,
         weight_kg, priority, created_at, promised_date, status,
         created_by_user_id, distance_km, eta_hours)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        tracking_no, origin_id, dest_id, carrier_id, vehicle_id,
        weight, priority, datetime.now().isoformat(), promised_date,
        "Created", user_id, distance_km, eta_hours
    ))
    conn.commit(); conn.close()


def _update_status(tracking_no, new_status):
    conn = get_connection(); cur = conn.cursor()
    cur.execute(
        "UPDATE shipments SET status = ?, actual_delivery_date = ? WHERE tracking_no = ?",
        (new_status,
         datetime.now().isoformat() if new_status == "Delivered" else None,
         tracking_no),
    )
    conn.commit(); conn.close()


def _generate_tracking():
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT MAX(id) m FROM shipments")
    nxt = (cur.fetchone()["m"] or 0) + 1
    conn.close()
    return f"SH{nxt:06d}"


# ---------- main render ----------
def render():
    st.markdown(f"<h1 style='color:{DARK};'>📦 Operator Dashboard</h1>", unsafe_allow_html=True)
    st.caption("Add shipments, track them, update statuses in real time.")

    user = st.session_state["user"]
    whs, carriers, vehicles = _load_refs()

    # ---------- KPI strip ----------
    conn = get_connection()
    kpi = pd.read_sql_query("""
        SELECT
            SUM(status IN ('Created','Picked Up','In Transit','Out for Delivery')) AS active,
            SUM(status = 'Delivered')                                              AS delivered,
            SUM(status = 'Delayed')                                                AS delayed,
            SUM(CASE WHEN actual_delivery_date IS NOT NULL
                     AND actual_delivery_date <= promised_date THEN 1 ELSE 0 END)  AS on_time,
            SUM(actual_delivery_date IS NOT NULL)                                  AS completed
        FROM shipments
    """, conn).iloc[0]
    conn.close()

    otd = (kpi["on_time"] / kpi["completed"] * 100) if kpi["completed"] else 0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active Shipments", int(kpi["active"] or 0))
    c2.metric("Delivered",        int(kpi["delivered"] or 0))
    c3.metric("Delayed",          int(kpi["delayed"] or 0))
    c4.metric("On-Time %",        f"{otd:.1f}%")

    st.divider()

    tab_add, tab_list, tab_exceptions = st.tabs(
        ["➕ Add Shipment", "📋 All Shipments", "⚠️ Exception Queue"]
    )

    # ================================================================
    # TAB 1 — ADD SHIPMENT
    # ================================================================
    with tab_add:
        with st.form("add_shipment_form", clear_on_submit=True):
            st.subheader("New Shipment")
            col1, col2 = st.columns(2)

            with col1:
                origin = st.selectbox(
                    "Origin Warehouse",
                    whs["id"].tolist(),
                    format_func=lambda i: (
                        f"{whs.loc[whs.id == i, 'name'].iloc[0]} "
                        f"({whs.loc[whs.id == i, 'city'].iloc[0]})"
                    ),
                    key="f_origin",
                )
                dest = st.selectbox(
                    "Destination Warehouse",
                    whs["id"].tolist(),
                    index=min(1, len(whs) - 1),
                    format_func=lambda i: (
                        f"{whs.loc[whs.id == i, 'name'].iloc[0]} "
                        f"({whs.loc[whs.id == i, 'city'].iloc[0]})"
                    ),
                    key="f_dest",
                )
                weight = st.number_input("Weight (kg)", 1.0, 2000.0, 50.0, 1.0,
                                         key="f_weight")
                priority = st.selectbox(
                    "Priority",
                    ["Standard", "Express", "Priority"],
                    key="f_priority",
                )

            with col2:
                carrier = st.selectbox(
                    "Carrier",
                    carriers["id"].tolist(),
                    format_func=lambda i: carriers.loc[carriers.id == i, "name"].iloc[0],
                    key="f_carrier",           # ← STABLE KEY (bug fix #1)
                )
                carrier_vehicles = vehicles[vehicles["carrier_id"] == carrier]
                if carrier_vehicles.empty:
                    st.warning("No vehicles registered for this carrier.")
                    vehicle = None
                else:
                    vehicle = st.selectbox(
                        "Vehicle",
                        carrier_vehicles["id"].tolist(),   # ← no None default
                        format_func=lambda v: (
                            f"{vehicles.loc[vehicles.id == v, 'plate'].iloc[0]} — "
                            f"{vehicles.loc[vehicles.id == v, 'model'].iloc[0]} "
                            f"({vehicles.loc[vehicles.id == v, 'mileage_km'].iloc[0]:,} km)"
                        ),
                        key=f"f_vehicle_{carrier}",        # ← per-carrier key
                    )
                promised_date = st.date_input(
                    "Promised Delivery Date",
                    value=date.today() + timedelta(days=3),
                    key="f_promised",
                )

            # ---- vehicle preview card (visible BEFORE submit) ----
            if vehicle is not None:
                vrow = vehicles[vehicles.id == vehicle].iloc[0]
                st.info(
                    f"🚚 **{vrow['plate']}** — {vrow['make']} {vrow['model']} "
                    f"({vrow['year']})\n\n"
                    f"Mileage: **{vrow['mileage_km']:,} km** · "
                    f"Last service: **{vrow['last_service_date'][:10]}**"
                )

            submitted = st.form_submit_button("🚀 Create Shipment",
                                              use_container_width=True)

        # ---- handle submit ----
        if submitted:
            if origin == dest:
                st.error("Origin and destination must be different.")
            elif vehicle is None:
                st.error("No vehicle available for this carrier — pick another carrier.")
            else:
                o = whs[whs.id == origin].iloc[0]
                d = whs[whs.id == dest].iloc[0]
                distance = haversine(o["lat"], o["lon"], d["lat"], d["lon"])

                carrier_row = carriers[carriers.id == carrier].iloc[0]
                vrow = vehicles[vehicles.id == vehicle].iloc[0]
                vehicle_age = max(0, date.today().year - int(vrow["year"] or date.today().year))

                eta = predict_eta_hours(
                    distance_km=float(distance),
                    weight_kg=float(weight),
                    priority=priority,
                    carrier_reliability=float(carrier_row["reliability_score"]),
                    day_of_week=date.today().weekday(),
                    vehicle_age_years=vehicle_age,
                )

                tracking = _generate_tracking()
                _insert_shipment(
                    tracking, int(origin), int(dest), int(carrier), int(vehicle),
                    float(weight), priority, promised_date.isoformat(),
                    float(distance), float(eta), user["id"],
                )

                src_label = ("🤖 RandomForest ML model" if model_available()
                             else "📐 Rule-based fallback")

                # ============ PREDICTION CARD ============
                st.markdown(f"""
                <div style="
                    background: linear-gradient(135deg, {BLUE} 0%, {GREEN} 100%);
                    color: white; padding: 22px 26px; border-radius: 14px;
                    box-shadow: 0 8px 22px rgba(21,101,192,0.25);
                    margin: 8px 0 18px 0;">
                    <div style="font-size:13px; opacity:0.85; letter-spacing:1.5px;
                                text-transform:uppercase;">✅ Shipment Created</div>
                    <div style="font-size:30px; font-weight:800; margin:4px 0;">
                        {tracking}
                    </div>
                    <div style="font-size:14px; opacity:0.92;">
                        {o['city']} → {d['city']} &nbsp;·&nbsp;
                        {weight:.0f} kg &nbsp;·&nbsp; {priority} &nbsp;·&nbsp;
                        {carrier_row['name']}
                    </div>
                    <hr style="border-color:rgba(255,255,255,0.25); margin:16px 0;">
                    <div style="display:flex; gap:28px; flex-wrap:wrap;">
                        <div>
                            <div style="font-size:11px; opacity:0.8;">DISTANCE</div>
                            <div style="font-size:22px; font-weight:700;">{distance:.0f} km</div>
                        </div>
                        <div>
                            <div style="font-size:11px; opacity:0.8;">PREDICTED ETA</div>
                            <div style="font-size:22px; font-weight:700;">{eta:.1f} h</div>
                        </div>
                        <div>
                            <div style="font-size:11px; opacity:0.8;">PROMISED</div>
                            <div style="font-size:22px; font-weight:700;">{promised_date.isoformat()}</div>
                        </div>
                        <div>
                            <div style="font-size:11px; opacity:0.8;">MODEL</div>
                            <div style="font-size:15px; font-weight:600; margin-top:6px;">{src_label}</div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # ---- gauge: predicted ETA vs promised ----
                promised_hours = (datetime.combine(promised_date, datetime.min.time())
                                  - datetime.now()).total_seconds() / 3600
                promised_hours = max(promised_hours, 0.1)

                bar_color = BLUE if eta <= promised_hours else RED
                fig = go.Figure(go.Indicator(
                    mode="gauge+number+delta",
                    value=eta,
                    delta={"reference": promised_hours, "suffix": " h",
                           "increasing": {"color": RED},
                           "decreasing": {"color": GREEN}},
                    number={"suffix": " h", "font": {"size": 42, "color": BLUE}},
                    title={"text": "Predicted ETA vs Promised Window",
                           "font": {"size": 16, "color": DARK}},
                    gauge={
                        "axis": {"range": [0, max(promised_hours * 1.3, eta * 1.3, 1)]},
                        "bar": {"color": bar_color},
                        "threshold": {
                            "line": {"color": GREEN, "width": 4},
                            "thickness": 0.85,
                            "value": promised_hours,
                        },
                    },
                ))
                fig.update_layout(height=300,
                                  margin=dict(t=50, b=0, l=20, r=20),
                                  paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig, use_container_width=True)

                if eta <= promised_hours:
                    st.success("🟢 On track — predicted ETA fits inside the promised window.")
                else:
                    st.warning(
                        f"🔴 At risk — model predicts **{eta - promised_hours:.1f} h longer** "
                        f"than promised."
                    )

                if st.button("📋 View this shipment in All Shipments"):
                    st.session_state["focus_tracking"] = tracking
                    st.rerun()

        st.caption(
            "💡 ETA is predicted by the trained RandomForest model if "
            "`models/eta_rf.pkl` exists; otherwise a rule-based fallback is used."
        )

    # ================================================================
    # TAB 2 — ALL SHIPMENTS
    # ================================================================
    with tab_list:
        col_f1, col_f2, col_f3 = st.columns([2, 2, 1])
        status_filter = col_f1.multiselect(
            "Filter by status",
            ["Created", "Picked Up", "In Transit", "Out for Delivery",
             "Delivered", "Delayed", "Cancelled"],
            default=["Created", "Picked Up", "In Transit", "Out for Delivery", "Delayed"],
            key="f_status_filter",
        )
        carrier_filter = col_f2.multiselect(
            "Filter by carrier",
            carriers["name"].tolist(),
            default=[],
            key="f_carrier_filter",
        )
        limit = col_f3.selectbox("Limit", [50, 100, 500, 2000], index=1,
                                 key="f_limit")

        conn = get_connection()
        q = """
            SELECT s.tracking_no, s.status, s.priority,
                   ow.city AS origin, dw.city AS destination,
                   c.name  AS carrier,
                   v.plate AS vehicle, v.model AS vehicle_model,
                   s.weight_kg, s.distance_km, s.eta_hours,
                   s.promised_date, s.actual_delivery_date, s.created_at
            FROM shipments s
            JOIN warehouses ow ON s.origin_wh_id = ow.id
            JOIN warehouses dw ON s.dest_wh_id   = dw.id
            JOIN carriers c    ON s.carrier_id   = c.id
            LEFT JOIN vehicles v ON s.vehicle_id = v.id
            ORDER BY s.created_at DESC
            LIMIT ?
        """
        df = pd.read_sql_query(q, conn, params=(limit,))
        conn.close()

        if status_filter:
            df = df[df["status"].isin(status_filter)]
        if carrier_filter:
            df = df[df["carrier"].isin(carrier_filter)]

        df_display = df.copy()
        df_display["vehicle"] = df_display["vehicle"].fillna("— unassigned —")
        df_display["vehicle_model"] = df_display["vehicle_model"].fillna("")

        st.dataframe(df_display, use_container_width=True, height=420)

        st.subheader("🔄 Shipment Detail & Status Update")
        if df.empty:
            st.info("No shipments match the filter.")
            return  # nothing more to render for this tab

        default_idx = 0
        focus = st.session_state.get("focus_tracking")
        if focus and focus in df["tracking_no"].values:
            default_idx = int(df.index[df["tracking_no"] == focus][0])

        pick = st.selectbox(
            "Pick a shipment (tracking no.)",
            df["tracking_no"].tolist(),
            index=default_idx,
            key="f_pick_shipment",
        )
        row = df[df["tracking_no"] == pick].iloc[0]

        # ---- info card ----
        veh_txt = row["vehicle"] if pd.notna(row["vehicle"]) else "— unassigned —"
        veh_model = row["vehicle_model"] if pd.notna(row["vehicle_model"]) else ""
        st.markdown(f"""
        <div style="
            background:#F5F9FF; border-left:5px solid {BLUE};
            padding:14px 18px; border-radius:10px; margin-bottom:12px;">
            <b style="color:{DARK}; font-size:16px;">{pick}</b>
            &nbsp;—&nbsp;
            <span style="color:{GREEN}; font-weight:600;">{row['status']}</span>
            <div style="font-size:13px; color:#455A64; margin-top:6px;">
                {row['origin']} → {row['destination']} ·
                {row['carrier']} ·
                🚚 {veh_txt} {veh_model} ·
                {row['weight_kg']:.0f} kg · {row['priority']}
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ---- promised window (hours from creation to promise) ----
        promised_hours = None
        try:
            promised_dt = pd.to_datetime(row["promised_date"])
            created_dt  = pd.to_datetime(row["created_at"])
            promised_hours = (promised_dt - created_dt).total_seconds() / 3600
        except Exception:
            pass

        e1, e2, e3 = st.columns(3)
        e1.metric("📏 Distance", f"{row['distance_km']:.0f} km")
        delta_txt = None
        if promised_hours is not None and row["eta_hours"] is not None:
            delta_txt = f"{row['eta_hours'] - promised_hours:+.1f} h vs promised"
        e2.metric("🤖 Model ETA",
                  f"{row['eta_hours']:.1f} h" if pd.notna(row["eta_hours"]) else "—",
                  delta=delta_txt,
                  delta_color="inverse")
        if promised_hours is not None:
            e3.metric("📅 Promised Window", f"{promised_hours:.1f} h")

        # ---- "Why this ETA?" expander ----
        with st.expander("🔍 Why did the model predict this ETA?"):
            if model_available():
                try:
                    pipeline = _load_model()
                    rf  = pipeline.named_steps["rf"]
                    ohe = pipeline.named_steps["prep"].named_transformers_["cat"]
                    cat_names = ohe.get_feature_names_out(["priority"]).tolist()
                    names = ["distance_km", "weight_kg", "carrier_reliability",
                             "day_of_week", "vehicle_age_years"] + cat_names
                    importances = pd.Series(rf.feature_importances_,
                                            index=names).sort_values()

                    fig2 = px.bar(
                        importances,
                        orientation="h",
                        labels={"value": "Importance", "index": "Feature"},
                        color=importances.values,
                        color_continuous_scale=[[0, "#E3F2FD"], [1, BLUE]],
                        title="Feature importances — how the model decided",
                    )
                    fig2.update_layout(
                        showlegend=False,
                        coloraxis_showscale=False,
                        height=300,
                        margin=dict(t=40, b=20, l=10, r=10),
                        paper_bgcolor="rgba(0,0,0,0)",
                    )
                    st.plotly_chart(fig2, use_container_width=True)
                except Exception as e:
                    st.warning(f"Could not load feature importances: {e}")
            else:
                st.info(
                    "Model not trained yet — ETA was computed with a rule-based "
                    "fallback. Run `notebooks/eta_model_training.ipynb` to train it."
                )

            st.caption(
                "Features fed to the model: distance, weight, priority, "
                "carrier reliability score, weekday of creation, vehicle age. "
                "The model is a RandomForestRegressor trained on ~3 years of shipments."
            )

        # ---- status update controls ----
        col_a, col_b = st.columns([2, 1])
        nxt = _next_status(row["status"])
        if nxt is None:
            col_b.info("No further status step.")
        else:
            if col_b.button(f"➡️ Advance to '{nxt}'", use_container_width=True,
                            key=f"adv_{pick}"):
                _update_status(pick, nxt)
                st.success(f"{pick} → {nxt}")
                st.rerun()

        col_c, col_d = st.columns(2)
        if row["status"] not in ("Delivered", "Cancelled", "Delayed"):
            if col_c.button("⏰ Mark as Delayed", key=f"dly_{pick}"):
                _update_status(pick, "Delayed"); st.rerun()
            if col_d.button("❌ Cancel Shipment", key=f"cnl_{pick}"):
                _update_status(pick, "Cancelled"); st.rerun()

    # ================================================================
    # TAB 3 — EXCEPTION QUEUE
    # ================================================================
    with tab_exceptions:
        conn = get_connection()
        today_iso = date.today().isoformat()
        dfx = pd.read_sql_query("""
            SELECT s.tracking_no, s.status, s.priority, s.promised_date, s.eta_hours,
                   ow.city AS origin, dw.city AS destination, c.name AS carrier,
                   v.plate AS vehicle
            FROM shipments s
            JOIN warehouses ow ON s.origin_wh_id = ow.id
            JOIN warehouses dw ON s.dest_wh_id   = dw.id
            JOIN carriers c    ON s.carrier_id   = c.id
            LEFT JOIN vehicles v ON s.vehicle_id = v.id
            WHERE s.status IN ('Created','Picked Up','In Transit','Out for Delivery','Delayed')
              AND substr(s.promised_date,1,10) <= ?
            ORDER BY s.promised_date ASC
        """, conn, params=(today_iso,))
        conn.close()

        if dfx.empty:
            st.success("🎉 No exceptions right now.")
        else:
            dfx["vehicle"] = dfx["vehicle"].fillna("— unassigned —")
            st.warning(
                f"⚠️ **{len(dfx)} shipments** have breached their promised date "
                f"or are at risk:"
            )
            st.dataframe(dfx, use_container_width=True, height=420)