import streamlit as st

BRAND = "Smart AI Tutor"
CSS = """
<style>
#MainMenu, footer {visibility: hidden;}
.block-container {padding-top: 1.5rem; max-width: 1100px;}
.brand-bar {background: linear-gradient(135deg,#4F46E5 0%,#7C3AED 100%);
  color:#fff; padding:1.1rem 1.5rem; border-radius:16px; margin-bottom:1.2rem;
  display:flex; align-items:center; justify-content:space-between;}
.brand-bar h1 {color:#fff; font-size:1.6rem; margin:0; padding:0;}
.brand-bar span {opacity:.85; font-size:.9rem;}
.pill {background:rgba(255,255,255,.2); padding:.25rem .8rem; border-radius:999px; font-size:.8rem;}
[data-testid="stMetric"] {background:#F1F3FB; border-radius:12px; padding:.8rem 1rem;}
.stButton>button {border-radius:10px; font-weight:600;}
[data-testid="stSidebar"] {border-right:1px solid #E3E6F5;}
.stTabs [data-baseweb="tab"] {font-weight:600;}
</style>
"""

def setup(title="", icon="🎓", wide=True):
    st.set_page_config(page_title=f"{BRAND}" + (f" | {title}" if title else ""),
                       page_icon=icon, layout="wide" if wide else "centered")
    st.markdown(CSS, unsafe_allow_html=True)

def header(subtitle, user=None):
    who = ""
    if user:
        name = user.get("full_name") or user["username"]
        extra = f" · {user['enrollment_no']}" if user.get("enrollment_no") else ""
        who = f"<span class='pill'>{name}{extra} · {'faculty' if user['role'] == 'teacher' else user['role']}</span>"
    st.markdown(f"<div class='brand-bar'><div><h1>🎓 {BRAND}</h1>"
                f"<span>{subtitle}</span></div>{who}</div>", unsafe_allow_html=True)

def sidebar_brand(user=None):
    st.sidebar.markdown(f"### 🎓 {BRAND}")
    if user and st.sidebar.button("Log out"):
        del st.session_state["user"]
        st.rerun()
