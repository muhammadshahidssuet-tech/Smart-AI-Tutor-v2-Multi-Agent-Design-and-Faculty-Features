import streamlit as st
import db, ui

ui.setup()
db.init()
ui.header("Your course-grounded AI study partner", st.session_state.get("user"))
ui.sidebar_brand(st.session_state.get("user"))

if "user" in st.session_state:
    u = st.session_state.user
    st.success(f"Logged in as **{u['username']}** ({'faculty' if u['role'] == 'teacher' else u['role']})")
    page = "Faculty Portal" if u["role"] == "teacher" else "Student Portal"
    st.info(f"Open **{page}** from the left sidebar.")
    st.stop()

login, reg = st.tabs(["Login", "Register"])
with login:
    un = st.text_input("Username", key="lu")
    pw = st.text_input("Password", type="password", key="lp")
    if st.button("Login"):
        r = db.q("SELECT * FROM users WHERE username=? AND pw=?", (un, db.hp(pw)))
        if r:
            st.session_state.user = r[0]; st.rerun()
        else:
            st.error("Wrong username or password")
with reg:
    full = st.text_input("Full name", key="rf")
    role = st.selectbox("I am a", ["student", "teacher"], format_func=lambda r: "Faculty" if r == "teacher" else "Student")
    enr = st.text_input("Enrollment number", key="re") if role == "student" else ""
    un = st.text_input("Choose username", key="ru")
    pw = st.text_input("Choose password", type="password", key="rp")
    if st.button("Create account"):
        if not (full.strip() and un.strip() and pw) or (role == "student" and not enr.strip()):
            st.error("Please fill in all fields.")
        elif role == "student" and db.q("SELECT id FROM users WHERE enrollment_no=?", (enr.strip(),)):
            st.error("This enrollment number is already registered.")
        else:
            try:
                db.run("INSERT INTO users(username,pw,role,full_name,enrollment_no) VALUES(?,?,?,?,?)",
                       (un.strip(), db.hp(pw), role, full.strip(), enr.strip() or None))
                st.success("Account created. Go to the Login tab.")
            except Exception:
                st.error("Username already taken")
