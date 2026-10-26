"""Helpers to load forecasts / example Prophet model for the dashboard."""
import os
import sqlite3
import pandas as pd
import joblib

DB_PATH = "logistics.db"
EXAMPLE_MODEL_PATH = os.path.join("models", "demand_prophet_example.pkl")

_example = None


def example_model_available() -> bool:
    return os.path.exists(EXAMPLE_MODEL_PATH)


def load_example_model():
    """Returns dict {model, sku_id, warehouse_id} or None."""
    global _example
    if _example is None and example_model_available():
        _example = joblib.load(EXAMPLE_MODEL_PATH)
    return _example


def get_forecast(sku_id: int, warehouse_id: int, horizon_days: int) -> pd.DataFrame:
    """Return forecast rows for one series."""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT forecast_date, yhat, yhat_lower, yhat_upper, horizon_days "
        "FROM demand_forecast "
        "WHERE sku_id = ? AND warehouse_id = ? AND horizon_days = ? "
        "ORDER BY forecast_date",
        conn, params=(sku_id, warehouse_id, horizon_days),
    )
    conn.close()
    return df


def get_actuals(sku_id: int, warehouse_id: int, days: int = 180) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT date, SUM(qty_sold) AS y FROM sales_history "
        "WHERE sku_id = ? AND warehouse_id = ? "
        "AND date >= date('now', ?) "
        "GROUP BY date ORDER BY date",
        conn, params=(sku_id, warehouse_id, f"-{days} day"),
    )
    conn.close()
    df["date"] = pd.to_datetime(df["date"])
    return df


def get_sku_risk_table(horizon_days: int = 30) -> pd.DataFrame:
    """
    Compute SKU × warehouse risk: current stock, forecast demand, days-of-stock,
    recommended reorder. Uses demand_forecast for the chosen horizon.
    """
    conn = sqlite3.connect(DB_PATH)
    q = """
    SELECT
        s.id           AS sku_id,
        s.sku_code, s.name AS sku_name, s.category,
        s.unit_cost, s.lead_time_days,
        w.id           AS warehouse_id,
        w.city         AS warehouse_city,
        i.qty_on_hand, i.safety_stock, i.reorder_point,
        COALESCE(recent.avg_daily, 0)   AS avg_daily_actual,
        COALESCE(fc.forecast_qty, 0)    AS forecast_demand
    FROM skus s
    CROSS JOIN warehouses w
    LEFT JOIN inventory i
           ON i.sku_id = s.id AND i.warehouse_id = w.id
    LEFT JOIN (
        SELECT sku_id, warehouse_id, AVG(qty_sold) AS avg_daily
        FROM sales_history
        WHERE date >= date('now', '-30 day')
        GROUP BY sku_id, warehouse_id
    ) recent ON recent.sku_id = s.id AND recent.warehouse_id = w.id
    LEFT JOIN (
        SELECT sku_id, warehouse_id, SUM(yhat) AS forecast_qty
        FROM demand_forecast
        WHERE horizon_days = ?
        GROUP BY sku_id, warehouse_id
    ) fc ON fc.sku_id = s.id AND fc.warehouse_id = w.id
    WHERE i.qty_on_hand IS NOT NULL
    """
    df = pd.read_sql_query(q, conn, params=(horizon_days,))
    conn.close()

    df["avg_daily_actual"] = df["avg_daily_actual"].fillna(0)
    df["forecast_demand"] = df["forecast_demand"].fillna(0)
    df["avg_daily_forecast"] = df["forecast_demand"] / max(horizon_days, 1)

    # days_of_stock based on forecast (more forward-looking than actual)
    daily_for_stock = df["avg_daily_forecast"].where(
        df["avg_daily_forecast"] > 0, df["avg_daily_actual"]
    )
    df["daily_rate"] = daily_for_stock.replace(0, 0.01)
    df["days_of_stock"] = (df["qty_on_hand"] / df["daily_rate"]).round(1)

    df["recommended_reorder_qty"] = (
        df["forecast_demand"] + df["safety_stock"] - df["qty_on_hand"]
    ).clip(lower=0).round().astype(int)

    df["reorder_value_inr"] = (
        df["recommended_reorder_qty"] * df["unit_cost"]
    ).round(2)

    def risk_flag(row):
        if row["qty_on_hand"] <= row["safety_stock"]:
            return "🔴 Critical"
        if row["days_of_stock"] < row["lead_time_days"]:
            return "🟡 Warning"
        if row["days_of_stock"] > 90:
            return "🔵 Overstock"
        return "🟢 Healthy"

    df["risk"] = df.apply(risk_flag, axis=1)
    return df