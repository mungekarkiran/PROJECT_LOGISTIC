import streamlit as st
from database import init_db
from auth import login_register_page
from pages import admin_page, operator_page, planner_page

st.set_page_config(
    page_title="Logistics Ops Dashboard",
    page_icon="🚚",
    layout="wide",
)

# Initialize DB once
init_db()

# If user not logged in → show auth page
if "user" not in st.session_state:
    login_register_page()
    st.stop()

# ---------- Logged in: render header + sidebar ----------
user = st.session_state["user"]

with st.sidebar:
    st.markdown(
        f"""
        <div style='background:#1565C0; color:white; padding:14px;
                    border-radius:10px; text-align:center;'>
            <h3 style='margin:0; color:white;'>👤 {user['username']}</h3>
            <p style='margin:4px 0 0; color:#66BB6A; font-weight:600;'>{user['role']}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write("")
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.clear()
        st.rerun()

# ---------- Role-based redirect ----------
if user["role"] == "Admin":
    admin_page.render()
elif user["role"] == "Operator":
    operator_page.render()
elif user["role"] == "Planner":
    planner_page.render()
else:
    st.error("Unknown role. Please contact admin.")