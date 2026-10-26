"""
Planner Dashboard — Step 3 (fixed empty tabs + attractive forecast visuals).

Key design rules that fix the "empty tab" bug:
  1. Warehouse dropdown only lists warehouses WITH forecast rows for the selected SKU.
  2. If the current (SKU, WH, horizon) combo is empty → fall back automatically
     to the first combo that HAS data (never show an empty chart).
  3. Every tab has an "empty state" card that names the exact command to fix it.
  4. The demand_prophet_example.pkl is loaded in Tab 2's "Why this forecast?" section,
     and its 3 decomposition components (trend / weekly / yearly) are rendered.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, date
from database import get_connection
import demand_model as dm

BLUE   = "#1565C0"
GREEN  = "#2E7D32"
DARK   = "#0D47A1"
RED    = "#C62828"
AMBER  = "#F9A825"
CYAN   = "#00838F"
GREY   = "#90A4AE"
BG     = "#F5F9FF"

HORIZON_OPTIONS = {"7-day (reorder trigger)": 7,
                   "30-day (default)":        30,
                   "60-day (procurement)":    60}


# ============================================================
# UI helpers
# ============================================================
def _hero(title, subtitle):
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, {BLUE} 0%, {GREEN} 100%);
        color: white; padding: 22px 28px; border-radius: 14px;
        box-shadow: 0 8px 22px rgba(21,101,192,0.22);
        margin-bottom: 16px;">
        <div style="font-size: 24px; font-weight: 800;">{title}</div>
        <div style="font-size: 14px; opacity: 0.92; margin-top: 4px;">{subtitle}</div>
    </div>
    """, unsafe_allow_html=True)


def _empty_state(icon, title, body, action_text=None):
    act = (f'<div style="margin-top: 16px; font-family: monospace; '
           f'background: #263238; color: #B0BEC5; padding: 10px 16px; '
           f'border-radius: 6px; display: inline-block;">{action_text}</div>'
           if action_text else '')
    st.markdown(f"""
    <div style="
        background: {BG}; border: 2px dashed {BLUE};
        padding: 40px 20px; border-radius: 12px; text-align: center;
        margin: 20px 0;">
        <div style="font-size: 52px; margin-bottom: 12px;">{icon}</div>
        <div style="font-size: 20px; font-weight: 700; color: {DARK};
                    margin-bottom: 8px;">{title}</div>
        <div style="font-size: 14px; color: #455A64; max-width: 700px;
                    margin: 0 auto; line-height: 1.6;">{body}</div>
        {act}
    </div>
    """, unsafe_allow_html=True)


def _kpi_card(col, label, value, icon="", color=BLUE, subtext=None):
    sub = (f'<div style="font-size:12px;color:{GREY};margin-top:4px;">{subtext}</div>'
           if subtext else "")
    col.markdown(f"""
    <div style="background:white; padding:16px 18px; border-radius:12px;
                border-left: 4px solid {color};
                box-shadow: 0 3px 10px rgba(21,101,192,0.08);">
        <div style="font-size:11px; color:{GREY}; text-transform:uppercase;
                    letter-spacing:1px;">{icon} {label}</div>
        <div style="font-size:26px; font-weight:800; color:{DARK};
                    margin-top:6px;">{value}</div>
        {sub}
    </div>
    """, unsafe_allow_html=True)


# ============================================================
# DB helpers
# ============================================================
def _insert_sales_upload(df, user_id):
    conn = get_connection(); cur = conn.cursor()
    sku_map = {r["sku_code"]: r["id"] for r in cur.execute("SELECT id, sku_code FROM skus")}
    wh_map  = {r["name"]:     r["id"] for r in cur.execute("SELECT id, name FROM warehouses")}
    rows, errors = [], []
    for i, r in df.iterrows():
        try:
            code = str(r["sku_code"]).strip()
            wh   = str(r["warehouse_name"]).strip()
            qty  = int(float(r["qty_sold"]))
            rev  = float(r["revenue_inr"])
            dt   = pd.to_datetime(r["date"]).date().isoformat()
        except Exception as e:
            errors.append(f"row {i+2}: {e}"); continue
        if code not in sku_map:
            cur.execute("INSERT INTO skus (sku_code, name, category, unit_cost, lead_time_days) "
                        "VALUES (?,?,?,?,?)",
                        (code, code, "Uploaded", rev / max(qty, 1), 7))
            sku_map[code] = cur.lastrowid
        if wh not in wh_map:
            errors.append(f"row {i+2}: unknown warehouse '{wh}'"); continue
        rows.append((dt, sku_map[code], wh_map[wh], qty, rev, "upload",
                     user_id, datetime.now().isoformat()))
    if not rows:
        conn.close()
        return 0, "No valid rows — " + "; ".join(errors[:3])
    cur.executemany(
        "INSERT INTO sales_history (date, sku_id, warehouse_id, qty_sold, revenue_inr, "
        "source, uploaded_by_user_id, uploaded_at) VALUES (?,?,?,?,?,?,?,?)", rows)
    conn.commit(); conn.close()
    msg = f"✅ Inserted **{len(rows)}** rows."
    if errors: msg += f" Skipped {len(errors)} bad rows (first: {errors[0]})."
    return len(rows), msg


def _generate_po_no():
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT MAX(id) m FROM purchase_orders")
    nxt = (cur.fetchone()["m"] or 0) + 1
    conn.close()
    return f"PO-{datetime.now().year}-{nxt:05d}"


def _create_po(sku_id, wh_id, qty, unit_cost, user_id):
    conn = get_connection(); cur = conn.cursor()
    po_no = _generate_po_no()
    cur.execute("""
        INSERT INTO purchase_orders
        (po_no, sku_id, warehouse_id, qty_ordered, unit_cost, total_inr,
         status, created_by_user_id, created_at)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (po_no, sku_id, wh_id, qty, unit_cost,
         round(qty * unit_cost, 2), "Draft", user_id, datetime.now().isoformat()))
    conn.commit(); conn.close()
    return po_no


def _update_po_status(po_no, status):
    conn = get_connection(); cur = conn.cursor()
    cur.execute("UPDATE purchase_orders SET status = ?, approved_at = ? WHERE po_no = ?",
                (status, datetime.now().isoformat() if status == "Approved" else None, po_no))
    conn.commit(); conn.close()


# ============================================================
# TAB 1 — UPLOAD
# ============================================================
def _tab_upload(user):
    _hero("📤 Upload Historical Sales",
          "Feed the model with your own data — forecast accuracy improves with more history.")

    st.info(
        "**Expected columns:** `date`, `sku_code`, `warehouse_name`, "
        "`qty_sold`, `revenue_inr`\n\n"
        "💡 Uploads are **appended** to existing seeded history."
    )

    template = ("date,sku_code,warehouse_name,qty_sold,revenue_inr\n"
                "2026-10-01,SKU-1001,WH-Mumbai,12,4560.00\n"
                "2026-10-02,SKU-1001,WH-Mumbai,9,3420.00\n")
    st.download_button("⬇️ Download CSV template", data=template.encode(),
                      file_name="sales_upload_template.csv", mime="text/csv")

    up = st.file_uploader("Choose a CSV file", type=["csv"], key="f_up_csv")
    if up is not None:
        try:
            raw = pd.read_csv(up)
        except Exception as e:
            st.error(f"Could not parse CSV: {e}"); return
        st.write(f"**Preview** — {len(raw):,} rows")
        st.dataframe(raw.head(10), use_container_width=True)

        required = {"date", "sku_code", "warehouse_name", "qty_sold", "revenue_inr"}
        missing = required - set(raw.columns)
        if missing:
            st.error(f"Missing columns: {missing}")
        else:
            if st.button("📥 Insert into database", use_container_width=True):
                n, msg = _insert_sales_upload(raw, user["id"])
                (st.success if n > 0 else st.error)(msg)
                if n > 0: st.rerun()

    st.divider()
    st.subheader("📜 Recent uploads")
    conn = get_connection()
    try:
        up_hist = pd.read_sql_query("""
            SELECT sh.uploaded_at, u.username, COUNT(*) AS rows_uploaded
            FROM sales_history sh
            LEFT JOIN users u ON sh.uploaded_by_user_id = u.id
            WHERE sh.source = 'upload'
            GROUP BY sh.uploaded_at, u.username
            ORDER BY sh.uploaded_at DESC LIMIT 20
        """, conn)
    finally:
        conn.close()
    if up_hist.empty:
        st.info("No manual uploads yet. Seeded data is used for the forecast.")
    else:
        st.dataframe(up_hist, use_container_width=True)


# ============================================================
# TAB 2 — FORECAST VS ACTUAL (the ML showcase)
# ============================================================
def _tab_forecast():
    _hero("📈 Demand Forecast vs Actual",
          "Prophet forecast with 80% confidence band + model decomposition "
          "(trend / weekly / yearly).")

    conn = get_connection()
    sku_list = pd.read_sql_query("""
        SELECT DISTINCT s.id, s.sku_code, s.name, s.category
        FROM skus s JOIN demand_forecast f ON f.sku_id = s.id
        ORDER BY s.sku_code
    """, conn)
    conn.close()

    if sku_list.empty:
        _empty_state(
            "🔮", "No forecasts in the database yet",
            "The `demand_forecast` table is empty. Open the notebook and run "
            "Cells 5 and 6 to train Prophet and store the predictions.",
            "jupyter notebook notebooks/demand_prophet.ipynb")
        return

    # ---------------- selectors ----------------
    c1, c2, c3 = st.columns([3, 2, 2])
    sku_sel = c1.selectbox(
        "🔍 SKU",
        sku_list["id"].tolist(),
        format_func=lambda i: (
            f"{sku_list.loc[sku_list.id==i,'sku_code'].iloc[0]} — "
            f"{sku_list.loc[sku_list.id==i,'name'].iloc[0][:35]}"
        ),
        key="fc_sku")

    # warehouses WITH forecasts for THIS sku — this is the empty-tab fix
    conn = get_connection()
    wh_list = pd.read_sql_query("""
        SELECT DISTINCT w.id, w.name, w.city,
               (SELECT COUNT(*) FROM demand_forecast
                WHERE sku_id = ? AND warehouse_id = w.id) AS fc_rows
        FROM warehouses w
        JOIN demand_forecast f ON f.warehouse_id = w.id
        WHERE f.sku_id = ?
        ORDER BY fc_rows DESC, w.name
    """, conn, params=(sku_sel, sku_sel))
    conn.close()

    if wh_list.empty:
        _empty_state(
            "🏭", "No forecast rows for this SKU",
            f"SKU id {sku_sel} exists but the notebook never produced a forecast "
            f"for it. Try another SKU, or re-run Cell 5 in the notebook.",
            "In notebook: Cell 5 → Run")
        return

    wh_sel = c2.selectbox(
        "🏭 Warehouse",
        wh_list["id"].tolist(),
        format_func=lambda i: (
            f"{wh_list.loc[wh_list.id==i,'name'].iloc[0]} "
            f"({wh_list.loc[wh_list.id==i,'city'].iloc[0]}) "
            f"— {int(wh_list.loc[wh_list.id==i,'fc_rows'].iloc[0])} rows"
        ),
        key="fc_wh")

    horizon_label = c3.selectbox(
        "⏱️ Horizon", list(HORIZON_OPTIONS.keys()), index=1, key="fc_horizon")
    horizon = HORIZON_OPTIONS[horizon_label]

    # ---------------- load data ----------------
    fc = dm.get_forecast(sku_sel, wh_sel, horizon)
    if fc.empty:
        # auto-fallback to any horizon that has data
        for alt_h in [7, 30, 60]:
            if alt_h == horizon:
                continue
            fc_alt = dm.get_forecast(sku_sel, wh_sel, alt_h)
            if not fc_alt.empty:
                st.info(
                    f"⚠️ No {horizon}-day rows for this combo. "
                    f"Showing **{alt_h}-day** instead.")
                fc = fc_alt
                horizon = alt_h
                break

    if fc.empty:
        _empty_state(
            "⚠️", "Forecast rows exist in DB but not for this combination",
            f"(SKU {sku_sel}, WH {wh_sel}) has no rows at any horizon. "
            f"This happens when Cell 5 in the notebook skipped this series "
            f"(too short / too sparse). Pick another combination.",
            "Try a different SKU or warehouse")
        return

    actuals = dm.get_actuals(sku_sel, wh_sel, days=180)
    fc["forecast_date"] = pd.to_datetime(fc["forecast_date"])

    # ---------------- KPI cards ----------------
    conn = get_connection()
    mm = pd.read_sql_query(
        "SELECT metric_name, metric_value FROM model_metrics "
        "WHERE model_name = 'demand_forecast' ORDER BY trained_at DESC LIMIT 4", conn)
    conn.close()

    mape_v = mm[mm.metric_name == "MAPE_pct"]["metric_value"]
    mae_v  = mm[mm.metric_name == "MAE"]["metric_value"]

    k1, k2, k3, k4 = st.columns(4)
    _kpi_card(k1, "Avg MAPE",
              f"{mape_v.iloc[0]:.2f}%" if not mape_v.empty else "—",
              icon="🎯", color=GREEN, subtext="lower is better")
    _kpi_card(k2, "Avg MAE",
              f"{mae_v.iloc[0]:.2f}" if not mae_v.empty else "—",
              icon="📏", color=CYAN, subtext="avg units off per day")
    _kpi_card(k3, f"{horizon}-day total",
              f"{fc['yhat'].sum():,.0f}",
              icon="📦", color=BLUE, subtext="predicted demand")
    _kpi_card(k4, "Avg daily",
              f"{fc['yhat'].mean():.1f}",
              icon="📊", color=AMBER, subtext="units per day")

    st.divider()

    # ---------------- Main forecast chart ----------------
    fig = go.Figure()

    # confidence band
    fig.add_trace(go.Scatter(
        x=pd.concat([fc["forecast_date"], fc["forecast_date"][::-1]]),
        y=pd.concat([fc["yhat_upper"], fc["yhat_lower"][::-1]]),
        fill="toself", fillcolor="rgba(46,125,50,0.18)",
        line=dict(color="rgba(255,255,255,0)"),
        hoverinfo="skip", name="80% confidence",
    ))

    # actuals
    fig.add_trace(go.Scatter(
        x=actuals["date"], y=actuals["y"],
        name="Actual (last 180d)",
        line=dict(color=BLUE, width=2.5), mode="lines",
        hovertemplate="<b>%{x|%b %d}</b><br>Actual: %{y} units<extra></extra>",
    ))

    # forecast
    fig.add_trace(go.Scatter(
        x=fc["forecast_date"], y=fc["yhat"],
        name=f"Forecast ({horizon}d)",
        line=dict(color=GREEN, width=3, dash="dot"),
        mode="lines+markers", marker=dict(size=6),
        hovertemplate="<b>%{x|%b %d}</b><br>Forecast: %{y:.0f}<extra></extra>",
    ))

    fig.update_layout(
        height=460, hovermode="x unified",
        title=dict(
            text=(f"Demand: {sku_list.loc[sku_list.id==sku_sel,'sku_code'].iloc[0]} "
                  f"@ {wh_list.loc[wh_list.id==wh_sel,'city'].iloc[0]}"),
            font=dict(size=16, color=DARK)),
        xaxis=dict(title="Date", showgrid=True, gridcolor="#E0E0E0"),
        yaxis=dict(title="Units per day", showgrid=True, gridcolor="#E0E0E0"),
        plot_bgcolor=BG, paper_bgcolor="white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        margin=dict(t=60, b=40, l=40, r=20),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ---------------- "Why this forecast?" — PROOF OF ML ----------------
    st.subheader("🧠 Why this forecast? — Prophet decomposition")
    st.caption(
        "This section loads `models/demand_prophet_example.pkl` — the "
        "**actual trained Prophet model** — and shows the three components "
        "that make up every forecast: trend, weekly seasonality, and yearly seasonality."
    )

    em = dm.load_example_model()
    if em is None:
        _empty_state(
            "🧠", "Example Prophet model not found",
            "`models/demand_prophet_example.pkl` was not saved. Either Prophet "
            "isn't installed (SARIMA fallback was used) or Cell 8 didn't run.",
            "In notebook: Cell 8 → Run, then restart Streamlit")
    else:
        model = em["model"]
        st.success(
            f"✅ Loaded trained Prophet model "
            f"(sku_id={em['sku_id']}, warehouse_id={em['warehouse_id']})"
        )

        try:
            # 90-day future for visualization
            future = model.make_future_dataframe(periods=90, freq="D")
            fcst = model.predict(future)
            fcst["ds"] = pd.to_datetime(fcst["ds"])

            # ---- component availability check ----
            available = [c for c in ("trend", "weekly", "yearly", "yhat")
                         if c in fcst.columns]
            st.caption(f"Available components: {', '.join(available)}")

            col_a, col_b = st.columns(2)

            # ---- TREND ----
            if "trend" in fcst.columns:
                with col_a:
                    tr = go.Figure()
                    tr.add_trace(go.Scatter(
                        x=fcst["ds"], y=fcst["trend"],
                        line=dict(color=BLUE, width=2.5),
                        fill="tozeroy", fillcolor="rgba(21,101,192,0.10)",
                        name="Trend",
                    ))
                    tr.update_layout(
                        height=280, title="📈 Trend — long-term demand direction",
                        plot_bgcolor=BG, paper_bgcolor="white",
                        margin=dict(t=40, b=20, l=20, r=20),
                        xaxis=dict(showgrid=False),
                        yaxis=dict(showgrid=True, gridcolor="#E0E0E0"))
                    st.plotly_chart(tr, use_container_width=True)

            # ---- WEEKLY ----
            if "weekly" in fcst.columns:
                with col_b:
                    wk = fcst[["ds", "weekly"]].copy()
                    wk["dow"] = wk["ds"].dt.dayofweek
                    wk_avg = wk.groupby("dow")["weekly"].mean().reset_index()
                    wk_avg["day"] = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]

                    # colour bars by value (green = positive boost)
                    colors = [GREEN if v >= 0 else RED for v in wk_avg["weekly"]]
                    fig_wk = go.Figure(go.Bar(
                        x=wk_avg["day"], y=wk_avg["weekly"],
                        marker_color=colors,
                        text=[f"{v:+.1f}" for v in wk_avg["weekly"]],
                        textposition="outside",
                        hovertemplate="<b>%{x}</b><br>Effect: %{y:+.2f}<extra></extra>",
                    ))
                    fig_wk.update_layout(
                        height=280,
                        title="📅 Weekly — which days sell more",
                        plot_bgcolor=BG, paper_bgcolor="white",
                        margin=dict(t=40, b=20, l=20, r=20),
                        xaxis=dict(title=""),
                        yaxis=dict(title="Effect on units",
                                   showgrid=True, gridcolor="#E0E0E0"))
                    st.plotly_chart(fig_wk, use_container_width=True)

            # ---- YEARLY (full-width — this is where Diwali shows) ----
            if "yearly" in fcst.columns:
                yr = fcst[["ds", "yearly"]].copy()
                yr["month"] = yr["ds"].dt.month
                yr_avg = yr.groupby("month")["yearly"].mean().reset_index()
                month_names = ["Jan","Feb","Mar","Apr","May","Jun",
                               "Jul","Aug","Sep","Oct","Nov","Dec"]
                yr_avg["month_name"] = [month_names[int(m)-1] for m in yr_avg["month"]]

                fig_yr = go.Figure()
                fig_yr.add_trace(go.Scatter(
                    x=yr_avg["month_name"], y=yr_avg["yearly"],
                    mode="lines+markers+text",
                    line=dict(color=GREEN, width=3),
                    marker=dict(size=12, color=GREEN,
                                line=dict(width=2, color="white")),
                    fill="tozeroy", fillcolor="rgba(46,125,50,0.12)",
                    text=[f"{v:+.1f}" for v in yr_avg["yearly"]],
                    textposition="top center",
                    hovertemplate="<b>%{x}</b><br>Yearly effect: %{y:+.2f}<extra></extra>",
                ))
                fig_yr.update_layout(
                    height=320,
                    title="🗓️ Yearly seasonality — Diwali spike should show as + in Oct/Nov",
                    plot_bgcolor=BG, paper_bgcolor="white",
                    margin=dict(t=50, b=30, l=30, r=20),
                    xaxis=dict(title="Month"),
                    yaxis=dict(title="Effect on units",
                               showgrid=True, gridcolor="#E0E0E0"))
                st.plotly_chart(fig_yr, use_container_width=True)

            st.caption(
                "💡 **How to read this:** every forecast = trend + weekly + yearly + noise. "
                "If the Oct/Nov bars in the yearly chart are the tallest, "
                "the model **learned the Diwali spike** — that's real ML, "
                "not a hardcoded multiplier."
            )

        except Exception as e:
            st.error(f"Could not render decomposition: {e}")
            st.exception(e)


# ============================================================
# TAB 3 — SKU RISK & REORDER
# ============================================================
def _tab_risk(user):
    _hero("⚠️ SKU Risk & Reorder",
          "Forward-looking: which SKUs run out before the next delivery arrives?")

    hcol1, hcol2 = st.columns([3, 2])
    risk_horizon_label = hcol1.selectbox(
        "Reorder horizon", list(HORIZON_OPTIONS.keys()), index=1, key="risk_horizon")
    risk_horizon = HORIZON_OPTIONS[risk_horizon_label]

    try:
        rdf = dm.get_sku_risk_table(horizon_days=risk_horizon)
    except Exception as e:
        st.error(f"Could not compute risk table: {e}")
        return

    if rdf.empty:
        _empty_state(
            "⚠️", "Risk table is empty",
            "The `inventory` or `demand_forecast` table has no rows. Run "
            "`python seed_data_skus.py` first, then re-run the notebook.",
            "python seed_data_skus.py")
        return

    # ---------------- KPI cards ----------------
    n_critical  = int((rdf["risk"] == "🔴 Critical").sum())
    n_warning   = int((rdf["risk"] == "🟡 Warning").sum())
    n_overstock = int((rdf["risk"] == "🔵 Overstock").sum())
    total_value = float(rdf["reorder_value_inr"].sum())

    k1, k2, k3, k4 = st.columns(4)
    _kpi_card(k1, "Critical",  n_critical,  icon="🔴", color=RED,
              subtext="will stock out soon")
    _kpi_card(k2, "Warning",   n_warning,   icon="🟡", color=AMBER,
              subtext="reorder soon")
    _kpi_card(k3, "Overstock", n_overstock, icon="🔵", color=CYAN,
              subtext="excess capital tied up")
    _kpi_card(k4, "Total reorder", f"₹{total_value:,.0f}",
              icon="💰", color=GREEN, subtext="recommended spend")

    st.divider()

    # ---------------- heatmap ----------------
    st.subheader("🌡️ Stockout risk heatmap — days of stock remaining")
    st.caption("Red cells = will run out soon. Sorted by most urgent SKUs.")

    try:
        pivot = rdf.pivot_table(
            index="sku_code", columns="warehouse_city",
            values="days_of_stock", aggfunc="min")
        pivot["__m__"] = pivot.median(axis=1)
        pivot = pivot.sort_values("__m__").drop(columns="__m__").head(25)

        z = pivot.values
        z_capped = [[(v if pd.notna(v) and v < 120 else 120) for v in row]
                    for row in z]

        fig_hm = go.Figure(data=go.Heatmap(
            z=z_capped,
            x=pivot.columns.tolist(),
            y=pivot.index.tolist(),
            colorscale=[
                [0.0, RED], [0.15, "#EF5350"], [0.35, AMBER],
                [0.55, "#FFEB3B"], [0.8, "#81C784"], [1.0, GREEN],
            ],
            zmin=0, zmax=120,
            text=[[f"{v:.0f}d" if pd.notna(v) else "" for v in row] for row in z],
            texttemplate="%{text}",
            colorbar=dict(title="Days<br>of stock"),
            hovertemplate="<b>%{y}</b> @ <b>%{x}</b><br>"
                          "Days of stock: %{text}<extra></extra>",
        ))
        fig_hm.update_layout(
            height=520, margin=dict(t=20, b=20, l=20, r=20),
            plot_bgcolor=BG, xaxis=dict(title="Warehouse"),
            yaxis=dict(title="SKU", autorange="reversed"))
        st.plotly_chart(fig_hm, use_container_width=True)
    except Exception as e:
        st.info(f"Heatmap unavailable: {e}")

    st.divider()

    # ---------------- table ----------------
    st.subheader("📋 Detailed risk table")
    risk_filter = st.multiselect(
        "Filter by risk level",
        ["🔴 Critical", "🟡 Warning", "🔵 Overstock", "🟢 Healthy"],
        default=["🔴 Critical", "🟡 Warning"], key="risk_filter")

    rdf_filtered = rdf[rdf["risk"].isin(risk_filter)].copy()
    show_cols = ["sku_code", "sku_name", "category", "warehouse_city",
                 "qty_on_hand", "safety_stock", "avg_daily_forecast",
                 "days_of_stock", "forecast_demand", "recommended_reorder_qty",
                 "reorder_value_inr", "risk"]
    st.dataframe(
        rdf_filtered[show_cols].sort_values(["risk", "days_of_stock"]),
        use_container_width=True, height=380)

    # ---------------- PO generation ----------------
    st.divider()
    st.subheader("🛒 Create purchase orders")
    critical = rdf[(rdf["risk"] == "🔴 Critical")
                   & (rdf["recommended_reorder_qty"] > 0)]
    if critical.empty:
        st.success("✅ No critical SKUs need reorder right now.")
    else:
        st.write(f"**{len(critical)} critical SKUs** need reorder · "
                 f"Total recommended: **₹{critical['reorder_value_inr'].sum():,.0f}**")

        sel = st.multiselect(
            "Select SKUs to create POs for",
            (critical["sku_code"] + " · " + critical["sku_name"]
             + " · " + critical["warehouse_city"]).tolist(),
            default=(critical["sku_code"] + " · " + critical["sku_name"]
                     + " · " + critical["warehouse_city"]).tolist()[:3],
            key="risk_po_sel")

        if st.button("📝 Create Draft Purchase Orders", use_container_width=True):
            made = []
            for label in sel:
                parts = [p.strip() for p in label.split("·")]
                code, city = parts[0], parts[-1]
                row = critical[(critical["sku_code"] == code)
                               & (critical["warehouse_city"] == city)].iloc[0]
                made.append(_create_po(int(row["sku_id"]), int(row["warehouse_id"]),
                                       int(row["recommended_reorder_qty"]),
                                       float(row["unit_cost"]), user["id"]))
            st.success(f"✅ Created {len(made)} draft POs: {', '.join(made)}")
            st.rerun()

    st.download_button(
        "⬇️ Download full risk table (CSV)",
        data=rdf_filtered[show_cols].to_csv(index=False).encode(),
        file_name=f"sku_risk_{risk_horizon}d.csv", mime="text/csv")


# ============================================================
# TAB 4 — PURCHASE ORDERS
# ============================================================
def _tab_po():
    _hero("📋 Purchase Order Workflow",
          "Draft → Approved → Received. Every PO is tracked with its creator.")

    conn = get_connection()
    po_df = pd.read_sql_query("""
        SELECT po.po_no, po.status, po.qty_ordered, po.unit_cost, po.total_inr,
               po.created_at, po.approved_at,
               s.sku_code, s.name AS sku_name,
               w.city AS warehouse_city,
               u.username AS created_by
        FROM purchase_orders po
        JOIN skus s ON po.sku_id = s.id
        JOIN warehouses w ON po.warehouse_id = w.id
        LEFT JOIN users u ON po.created_by_user_id = u.id
        ORDER BY po.created_at DESC
    """, conn)
    conn.close()

    if po_df.empty:
        _empty_state(
            "📋", "No purchase orders yet",
            "Go to the **SKU Risk & Reorder** tab, filter for 🔴 Critical SKUs, "
            "and click **Create Draft Purchase Orders**. They'll appear here "
            "for approval and receipt.",
            "→ Open the '⚠️ SKU Risk & Reorder' tab")
        return

    status_counts = po_df["status"].value_counts()
    k1, k2, k3, k4 = st.columns(4)
    _kpi_card(k1, "Draft",    int(status_counts.get("Draft", 0)),
              icon="✏️", color=AMBER)
    _kpi_card(k2, "Approved", int(status_counts.get("Approved", 0)),
              icon="✅", color=BLUE)
    _kpi_card(k3, "Received", int(status_counts.get("Received", 0)),
              icon="📦", color=GREEN)
    _kpi_card(k4, "Total value", f"₹{po_df['total_inr'].sum():,.0f}",
              icon="💰", color=CYAN)

    st.divider()

    # ---- kanban ----
    st.subheader("🗂️ Workflow board")
    kanban_cols = st.columns(3)
    status_color = {"Draft": AMBER, "Approved": BLUE, "Received": GREEN}
    status_icon  = {"Draft": "✏️", "Approved": "✅", "Received": "📦"}

    for col, status in zip(kanban_cols, ["Draft", "Approved", "Received"]):
        bucket = po_df[po_df["status"] == status]
        with col:
            st.markdown(
                f"<div style='background:{status_color[status]}20; "
                f"border-top:4px solid {status_color[status]}; "
                f"padding:10px 14px; border-radius:8px; margin-bottom:10px;'>"
                f"<b>{status_icon[status]} {status}</b> "
                f"<span style='float:right;background:{status_color[status]};"
                f"color:white;padding:2px 10px;border-radius:12px;"
                f"font-size:12px;'>{len(bucket)}</span></div>",
                unsafe_allow_html=True)
            if bucket.empty:
                st.caption("— none —")
            else:
                for _, r in bucket.head(8).iterrows():
                    st.markdown(
                        f"<div style='background:white; padding:10px 12px; "
                        f"border-radius:8px; box-shadow:0 2px 6px rgba(0,0,0,0.06);"
                        f"margin-bottom:8px; font-size:12px;'>"
                        f"<b>{r['po_no']}</b><br>"
                        f"{r['sku_code']} @ {r['warehouse_city']}<br>"
                        f"Qty {r['qty_ordered']} · ₹{r['total_inr']:,.0f}<br>"
                        f"<span style='color:{GREY};'>by {r['created_by'] or '—'}</span>"
                        f"</div>",
                        unsafe_allow_html=True)

    st.divider()
    st.subheader("📄 Full PO list")
    status_pick = st.multiselect(
        "Filter", ["Draft", "Approved", "Received", "Cancelled"],
        default=["Draft", "Approved", "Received"], key="po_status_filter")
    show = po_df[po_df["status"].isin(status_pick)]
    st.dataframe(show, use_container_width=True, height=320)

    st.subheader("🔄 Advance a purchase order")
    if show.empty:
        st.info("No POs in the selected statuses.")
        return
    po_sel = st.selectbox("PO no.", show["po_no"].tolist(), key="po_sel")
    row = show[show["po_no"] == po_sel].iloc[0]

    st.markdown(f"""
    <div style='background:{BG}; border-left:4px solid {BLUE};
                padding:14px 18px; border-radius:8px; margin-bottom:12px;'>
        <b style='color:{DARK}; font-size:16px;'>{row['po_no']}</b>
        &nbsp;·&nbsp;
        <span style='color:{status_color.get(row["status"], GREY)};
                     font-weight:600;'>{row['status']}</span>
        <div style='margin-top:8px; font-size:13px; color:#455A64;'>
            {row['sku_code']} — {row['sku_name']} &nbsp;·&nbsp;
            {row['warehouse_city']} &nbsp;·&nbsp;
            Qty <b>{row['qty_ordered']}</b> &nbsp;·&nbsp;
            Total <b>₹{row['total_inr']:,.2f}</b>
        </div>
    </div>
    """, unsafe_allow_html=True)

    next_status = {"Draft": "Approved", "Approved": "Received"}.get(row["status"])
    if next_status is None:
        st.info("This PO is in a terminal state.")
    else:
        col_a, col_b = st.columns([2, 1])
        if col_a.button(f"➡️ Advance to '{next_status}'", use_container_width=True):
            _update_po_status(po_sel, next_status)
            st.success(f"✅ {po_sel} → {next_status}")
            st.rerun()
        if col_b.button("❌ Cancel", use_container_width=True):
            _update_po_status(po_sel, "Cancelled")
            st.rerun()


# ============================================================
# MAIN
# ============================================================
def render():
    st.markdown(f"<h1 style='color:{DARK}; margin-bottom:4px;'>"
                f"📈 Planner Dashboard</h1>", unsafe_allow_html=True)
    st.caption("Demand forecast · Inventory risk · Purchase-order workflow")

    user = st.session_state["user"]

    conn = get_connection()
    kpi = conn.execute("""
        SELECT
          (SELECT COUNT(*) FROM skus)                                    AS n_skus,
          (SELECT COUNT(*) FROM sales_history)                           AS n_sales,
          (SELECT COUNT(*) FROM demand_forecast)                         AS n_fc,
          (SELECT COUNT(DISTINCT warehouse_id) FROM demand_forecast)     AS n_wh_fc,
          (SELECT COUNT(*) FROM purchase_orders WHERE status='Draft')    AS n_draft
    """).fetchone()
    conn.close()

    k1, k2, k3, k4 = st.columns(4)
    _kpi_card(k1, "Active SKUs",    f"{kpi['n_skus']:,}",
              icon="🏷️", color=BLUE)
    _kpi_card(k2, "Forecast rows",  f"{kpi['n_fc']:,}",
              icon="🔮", color=GREEN, subtext=f"across {kpi['n_wh_fc']} warehouses")
    _kpi_card(k3, "Sales rows",     f"{kpi['n_sales']:,}",
              icon="📊", color=CYAN)
    _kpi_card(k4, "Draft POs",      f"{kpi['n_draft']:,}",
              icon="🛒", color=AMBER)

    st.divider()

    tab_up, tab_fc, tab_risk, tab_po = st.tabs([
        "📤 Upload Sales Data", "📈 Forecast vs Actual",
        "⚠️ SKU Risk & Reorder", "📋 Purchase Orders"])

    with tab_up:   _tab_upload(user)
    with tab_fc:   _tab_forecast()
    with tab_risk: _tab_risk(user)
    with tab_po:   _tab_po()