import streamlit as st
import db, ui

ui.setup()      # page config + branding (runs once, before navigation)
db.init()

user = st.session_state.get("user")
pages = [st.Page("login.py", title="My Account" if user else "Login & Register",
                 icon="👤" if user else "🔐", default=True)]
if user and user["role"] == "teacher":
    pages.append(st.Page("pages/1_Faculty_Portal.py", title="Faculty Portal", icon="👩‍🏫"))
elif user:
    pages.append(st.Page("pages/2_Student_Portal.py", title="Student Portal", icon="🎓"))

st.navigation(pages).run()
