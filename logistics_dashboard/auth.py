import streamlit as st
from database import create_user, authenticate
import re

# ---------- Theme ----------
PRIMARY_BLUE = "#1565C0"
DARK_BLUE    = "#0D47A1"
GREEN        = "#2E7D32"
LIGHT_GREEN  = "#66BB6A"
WHITE        = "#FFFFFF"
BG_LIGHT     = "#F5F9FF"

def inject_theme():
    st.markdown(f"""
    <style>
        /* App background */
        .stApp {{
            background: linear-gradient(135deg, {WHITE} 0%, {BG_LIGHT} 100%);
        }}

        /* Buttons */
        div.stButton > button {{
            background-color: {PRIMARY_BLUE};
            color: {WHITE};
            border: none;
            border-radius: 8px;
            padding: 0.55em 1.4em;
            font-weight: 600;
            transition: 0.2s;
        }}
        div.stButton > button:hover {{
            background-color: {GREEN};
            color: {WHITE};
        }}

        /* Inputs */
        .stTextInput input, .stSelectbox div[data-baseweb="select"] {{
            border-radius: 8px !important;
            border: 1px solid {PRIMARY_BLUE} !important;
        }}

        /* Tabs */
        .stTabs [data-baseweb="tab-list"] {{
            gap: 6px;
        }}
        .stTabs [data-baseweb="tab"] {{
            background-color: {WHITE};
            border-radius: 8px;
            padding: 8px 18px;
            border: 1px solid #E0E0E0;
        }}
        .stTabs [aria-selected="true"] {{
            background-color: {PRIMARY_BLUE} !important;
            color: {WHITE} !important;
        }}

        /* Card */
        .card {{
            background-color: {WHITE};
            padding: 2rem;
            border-radius: 14px;
            box-shadow: 0 6px 24px rgba(21,101,192,0.08);
            border-top: 4px solid {GREEN};
        }}

        /* Headings */
        h1, h2, h3 {{ color: {DARK_BLUE}; }}
    </style>
    """, unsafe_allow_html=True)


def is_valid_email(email: str) -> bool:
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email) is not None


def login_register_page():
    inject_theme()

    st.markdown(
        f"""
        <div style='text-align:center; margin-bottom: 1rem;'>
            <h1 style='color:{DARK_BLUE}; margin-bottom:0;'>🚚 Logistics Operations Dashboard</h1>
            <p style='color:{GREEN}; font-weight:600;'>Sign in or create your account</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_login, tab_register = st.tabs(["🔐 Login", "📝 Register"])

    # ---------------- LOGIN ----------------
    with tab_login:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        with st.form("login_form"):
            st.subheader("Welcome back")
            username = st.text_input("Username", key="login_user")
            password = st.text_input("Password", type="password", key="login_pass")
            submitted = st.form_submit_button("Login", use_container_width=True)

        if submitted:
            if not username or not password:
                st.error("Please enter username and password.")
            else:
                user, error = authenticate(username, password)
                if error:
                    st.error(error)
                else:
                    st.session_state["user"] = user
                    st.success(f"Welcome, {user['username']}! Redirecting...")
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    # ---------------- REGISTER ----------------
    with tab_register:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        with st.form("register_form"):
            st.subheader("Create new account")
            new_user  = st.text_input("Username", key="reg_user")
            new_email = st.text_input("Email", key="reg_email")
            new_pass  = st.text_input("Password", type="password", key="reg_pass")
            confirm   = st.text_input("Confirm Password", type="password", key="reg_confirm")
            role      = st.selectbox("Role", ["Operator", "Planner", "Admin"])
            reg_submit = st.form_submit_button("Register", use_container_width=True)

        if reg_submit:
            errors = []
            if not new_user or len(new_user) < 3:
                errors.append("Username must be at least 3 characters.")
            if not is_valid_email(new_email):
                errors.append("Enter a valid email.")
            if len(new_pass) < 6:
                errors.append("Password must be at least 6 characters.")
            if new_pass != confirm:
                errors.append("Passwords do not match.")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                ok, msg = create_user(new_user, new_email, new_pass, role)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)
        st.markdown('</div>', unsafe_allow_html=True)