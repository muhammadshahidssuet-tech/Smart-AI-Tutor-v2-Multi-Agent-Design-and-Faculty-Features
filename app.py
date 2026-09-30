import streamlit as st
import db, ui

ui.setup()
db.init()
ui.header("Your course-grounded AI study partner", st.session_state.get("user"))
ui.sidebar_brand(st.session_state.get("user"))

if "user" in st.session_state:
    u = st.session_state.user
    st.success(f"Logged in as **{u['username']}** ({u['role']})")
    page = "Teacher Portal" if u["role"] == "teacher" else "Student Portal"
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
    un = st.text_input("Choose username", key="ru")
    pw = st.text_input("Choose password", type="password", key="rp")
    role = st.selectbox("I am a", ["student", "teacher"])
    if st.button("Create account"):
        try:
            db.run("INSERT INTO users(username,pw,role) VALUES(?,?,?)", (un, db.hp(pw), role))
            st.success("Account created. Go to the Login tab.")
        except Exception:
            st.error("Username already taken")
