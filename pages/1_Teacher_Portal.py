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
if st.sidebar.button("Load demo data"):
    db.seed_demo(course["id"]); st.rerun()
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
            try:
                qs = agents.make_quiz(course["id"], topic)
                db.run("INSERT INTO quizzes(course_id,topic,data) VALUES(?,?,?)",
                       (course["id"], topic, json.dumps(qs)))
            except Exception as e:
                st.error(f"Could not generate quiz. Upload material first, then retry. ({e})")
    for z in db.q("SELECT * FROM quizzes WHERE course_id=?", (course["id"],)):
        with st.expander(f"{z['topic']} — {'✅ Approved' if z['approved'] else '⏳ Draft'}"):
            for i, qn in enumerate(json.loads(z["data"]), 1):
                st.write(f"**{i}. {qn['q']}**")
                st.write(qn["options"], "→ correct:", qn["options"][qn["answer"]])
            if not z["approved"] and st.button("Approve & publish", key=f"a{z['id']}"):
                db.run("UPDATE quizzes SET approved=1 WHERE id=?", (z["id"],)); st.rerun()

with t3:
    att = db.q("SELECT user_id, topic, correct, total FROM attempts WHERE course_id=?", (course["id"],))
    chats = db.q("SELECT question, grounded FROM chats WHERE course_id=?", (course["id"],))
    enrolled = db.q("SELECT COUNT(*) n FROM enrollments WHERE course_id=?", (course["id"],))[0]["n"]
    tot = sum(a["total"] for a in att); cor = sum(a["correct"] for a in att)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Students enrolled", enrolled)
    m2.metric("Questions asked", len(chats))
    m3.metric("Quiz attempts", len(att))
    m4.metric("Average score", f"{cor / tot * 100:.0f}%" if tot else "-")

    if att:
        df = (pd.DataFrame(att).groupby("topic")
              .agg(correct=("correct", "sum"), total=("total", "sum"), students=("user_id", "nunique"))
              .reset_index())
        df["accuracy %"] = (df["correct"] / df["total"] * 100).round(1)
        st.subheader("Accuracy by topic")
        st.bar_chart(df.set_index("topic")["accuracy %"])
        st.dataframe(df, use_container_width=True, hide_index=True)
        weak = df[df["accuracy %"] < 60]["topic"].tolist()
        if weak:
            st.warning("Weak topics to re-teach: " + ", ".join(weak))
        else:
            st.success("No weak topics found.")
        st.download_button("Export CSV", df.to_csv(index=False), "class_report.csv")
    else:
        st.info("No quiz attempts yet. Students must submit an approved quiz. "
                "Or click 'Load demo data' in the sidebar to preview this dashboard.")

    if chats:
        qs = pd.Series([c["question"] for c in chats]).value_counts().head(10).reset_index()
        qs.columns = ["Question", "Times asked"]
        st.subheader("Most-asked questions")
        st.dataframe(qs, use_container_width=True, hide_index=True)
