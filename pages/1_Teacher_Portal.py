import json, streamlit as st, pandas as pd
import db, agents, ui

ui.setup("Teacher")

db.init()
u = st.session_state.get("user")
if not u or u["role"] != "teacher":
    st.warning("Please log in as a teacher on the main page."); st.stop()

ui.header("Teacher Portal: manage courses, materials and insights", u)
ui.sidebar_brand(u)

with st.sidebar.expander("➕ Create course"):
    name = st.text_input("Course name")
    if st.button("Create") and name:
        db.run("INSERT INTO courses(name,code,teacher_id) VALUES(?,?,?)", (name, db.code(), u["id"]))
        st.rerun()

courses = db.q("SELECT * FROM courses WHERE teacher_id=?", (u["id"],))
if not courses:
    st.info("Create your first course from the sidebar."); st.stop()

course = st.sidebar.selectbox("Course", courses, format_func=lambda c: f"{c['name']} ({c['code']})")
st.sidebar.caption(f"Student join code: **{course['code']}**")
strict = st.sidebar.toggle("Strict mode (course material only)", bool(course["strict"]))
db.run("UPDATE courses SET strict=? WHERE id=?", (int(strict), course["id"]))

t1, t2, t3 = st.tabs(["📂 Materials", "📝 Quiz Approval", "📊 Class Analytics"])

with t1:
    files = st.file_uploader("Upload lectures (PDF, PPTX, DOCX, TXT)", accept_multiple_files=True,
                             type=["pdf", "pptx", "docx", "txt"])
    if files and st.button("Process files"):
        for f in files:
            with st.spinner(f"Processing {f.name}..."):
                agents.ingest(course["id"], f)
        st.success("Done!")
    for d in db.q("SELECT * FROM docs WHERE course_id=?", (course["id"],)):
        with st.expander(d["name"]):
            st.markdown(d["summary"])

with t2:
    topic = st.text_input("Quiz topic")
    if st.button("Generate quiz draft") and topic:
        with st.spinner("Quiz Agent working..."):
            qs = agents.make_quiz(course["id"], topic)
            db.run("INSERT INTO quizzes(course_id,topic,data) VALUES(?,?,?)",
                   (course["id"], topic, json.dumps(qs)))
    for z in db.q("SELECT * FROM quizzes WHERE course_id=?", (course["id"],)):
        with st.expander(f"{z['topic']} — {'✅ Approved' if z['approved'] else '⏳ Draft'}"):
            for i, qn in enumerate(json.loads(z["data"]), 1):
                st.write(f"**{i}. {qn['q']}**")
                st.write(qn["options"], "→ correct:", qn["options"][qn["answer"]])
            if not z["approved"] and st.button("Approve & publish", key=f"a{z['id']}"):
                db.run("UPDATE quizzes SET approved=1 WHERE id=?", (z["id"],)); st.rerun()

with t3:
    a = db.q("""SELECT topic, SUM(correct) c, SUM(total) t, COUNT(DISTINCT user_id) students
                FROM attempts WHERE course_id=? GROUP BY topic""", (course["id"],))
    if a:
        df = pd.DataFrame(a); df["accuracy %"] = (df.c / df.t * 100).round(1)
        st.dataframe(df, use_container_width=True)
        st.bar_chart(df.set_index("topic")["accuracy %"])
        st.warning("Weak topics: " + ", ".join(df[df["accuracy %"] < 60].topic) or "none")
        st.download_button("Export CSV", df.to_csv(index=False), "class_report.csv")
    else:
        st.info("No quiz attempts yet.")
    qs = db.q("SELECT question, COUNT(*) n FROM chats WHERE course_id=? GROUP BY question ORDER BY n DESC LIMIT 10",
              (course["id"],))
    st.subheader("Most-asked questions")
    st.table(pd.DataFrame(qs)) if qs else st.caption("No questions yet.")
