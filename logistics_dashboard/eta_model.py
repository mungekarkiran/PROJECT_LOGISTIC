"""
Shared helper: predict ETA for a shipment.
Falls back to a rule-based ETA if the trained model is not available yet.
"""
import os, math
import pandas as pd
import joblib

MODEL_PATH = os.path.join("models", "eta_rf.pkl")
_model = None

def _load_model():
    global _model
    if _model is None and os.path.exists(MODEL_PATH):
        _model = joblib.load(MODEL_PATH)
    return _model

def model_available() -> bool:
    return _load_model() is not None

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl   = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return round(2 * R * math.asin(math.sqrt(a)), 1)

def predict_eta_hours(distance_km, weight_kg, priority,
                      carrier_reliability, day_of_week, vehicle_age_years):
    """Return predicted ETA in hours."""
    mdl = _load_model()
    if mdl is not None:
        X = pd.DataFrame([{
            "distance_km": distance_km,
            "weight_kg": weight_kg,
            "priority": priority,
            "carrier_reliability": carrier_reliability,
            "day_of_week": day_of_week,
            "vehicle_age_years": vehicle_age_years,
        }])
        return round(float(mdl.predict(X)[0]), 2)

    # ---------- fallback (rule-based) ----------
    base = distance_km / 55.0
    priority_mult = {"Priority": 0.75, "Express": 1.0, "Standard": 1.5}[priority]
    weekend_penalty = 1.1 if day_of_week >= 5 else 1.0
    reliability_penalty = 1.0 + (1.0 - carrier_reliability) * 0.5
    weight_penalty = 1.0 + min(weight_kg / 1000.0, 0.2)
    return round(base * priority_mult * weekend_penalty * reliability_penalty * weight_penalty, 2)