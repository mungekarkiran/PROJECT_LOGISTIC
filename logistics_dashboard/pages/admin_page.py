import streamlit as st
import pandas as pd
from database import get_connection

BLUE  = "#1565C0"
GREEN = "#2E7D32"
DARK  = "#0D47A1"


def render():
    st.markdown(f"<h1 style='color:{DARK};'>🛡️ Admin Dashboard</h1>",
                unsafe_allow_html=True)
    st.caption("System overview — users, models, and purchase-order audit.")

    conn = get_connection()
    users = pd.read_sql_query(
        "SELECT id, username, email, role, created_at FROM users ORDER BY id", conn)
    conn.close()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Users", len(users))
    c2.metric("Admins",    int((users["role"] == "Admin").sum()))
    c3.metric("Operators", int((users["role"] == "Operator").sum()))
    c4.metric("Planners",  int((users["role"] == "Planner").sum()))

    st.divider()
    st.subheader("👥 Registered Users")
    st.dataframe(users, use_container_width=True)

    # ---------------- Model Health ----------------
    st.divider()
    st.subheader("🤖 Model Health")
    try:
        conn = get_connection()
        mm = pd.read_sql_query(
            "SELECT model_name, version, metric_name, metric_value, trained_at "
            "FROM model_metrics ORDER BY trained_at DESC LIMIT 20", conn)
        conn.close()
    except Exception as e:
        mm = pd.DataFrame()
        st.info(f"Model metrics not available ({e}).")

    if mm.empty:
        st.info(
            "No models trained yet. Run `notebooks/eta_model_training.ipynb` "
            "and `notebooks/demand_prophet.ipynb`."
        )
    else:
        mm["metric_value"] = mm["metric_value"].round(3)
        st.dataframe(mm, use_container_width=True)
        latest = (mm.sort_values("trained_at")
                    .groupby(["model_name", "metric_name"], as_index=False)
                    .last())
        pivot = latest.pivot(index="model_name", columns="metric_name",
                             values="metric_value")
        st.markdown("**Latest metrics per model**")
        st.dataframe(pivot, use_container_width=True)

    # ---------------- Data Volume ----------------
    st.divider()
    st.subheader("📦 Data Volume")
    try:
        conn = get_connection()
        counts = {t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
                  for t in ["warehouses", "carriers", "vehicles", "shipments",
                            "skus", "sales_history", "inventory",
                            "demand_forecast", "purchase_orders"]}
        conn.close()
        dc1, dc2, dc3 = st.columns(3)
        dc1.metric("Shipments",     f"{counts['shipments']:,}")
        dc2.metric("Sales rows",    f"{counts['sales_history']:,}")
        dc3.metric("Forecast rows", f"{counts['demand_forecast']:,}")
        st.dataframe(pd.DataFrame([counts]).T.rename(columns={0: "rows"}),
                     use_container_width=True)
    except Exception as e:
        st.info(f"Data volume stats not available ({e}).")

    # ---------------- Purchase Orders audit ----------------
    st.divider()
    st.subheader("🛒 Purchase Orders — audit")
    try:
        conn = get_connection()
        po = pd.read_sql_query("""
            SELECT po.po_no, po.status, po.qty_ordered, po.total_inr,
                   po.created_at, po.approved_at,
                   s.sku_code, w.city AS warehouse_city,
                   u.username AS created_by
            FROM purchase_orders po
            JOIN skus s ON po.sku_id = s.id
            JOIN warehouses w ON po.warehouse_id = w.id
            LEFT JOIN users u ON po.created_by_user_id = u.id
            ORDER BY po.created_at DESC LIMIT 50
        """, conn)
        conn.close()
        if po.empty:
            st.info("No purchase orders yet.")
        else:
            st.metric("Total PO value", f"₹{po['total_inr'].sum():,.0f}")
            st.dataframe(po, use_container_width=True)
    except Exception as e:
        st.info(f"PO audit not available ({e}).")

    st.divider()
    st.subheader("🚀 Coming Soon")
    st.info(
        "• Shipment ↔ SKU traceability (`shipment_items` table)\n\n"
        "• Live inventory decrement when shipments are dispatched\n\n"
        "• Vehicle maintenance RUL model (Step 4)\n\n"
        "• Warehouse SOP chatbot with RAG"
    )
