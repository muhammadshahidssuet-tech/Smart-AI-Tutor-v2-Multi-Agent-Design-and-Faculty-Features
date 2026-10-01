import json, streamlit as st, pandas as pd
import db, agents, ui

ui.setup("Student")

db.init()
u = st.session_state.get("user")
if not u or u["role"] != "student":
    st.warning("Please log in as a student on the main page."); st.stop()

ui.header("Student Portal: learn, practice and track progress", u)
ui.sidebar_brand(u)

with st.sidebar.expander("➕ Join a course"):
    code = st.text_input("Course code").upper().strip()
    if st.button("Join"):
        c = db.q("SELECT id FROM courses WHERE code=?", (code,))
        if c:
            db.run("INSERT OR IGNORE INTO enrollments VALUES(?,?)", (u["id"], c[0]["id"])); st.rerun()
        else:
            st.error("Invalid code")

courses = db.q("""SELECT c.* FROM courses c JOIN enrollments e ON e.course_id=c.id
                  WHERE e.user_id=?""", (u["id"],))
if not courses:
    st.info("Join a course using the code from your teacher."); st.stop()

course = st.sidebar.selectbox("Course", courses, format_func=lambda c: c["name"])
mode = st.sidebar.radio("Tutor mode", ["Simple", "Step-by-step", "Socratic"])
lang = st.sidebar.selectbox("Language", ["English", "Urdu", "Roman Urdu"])

t1, t2, t3 = st.tabs(["💬 Tutor Chat", "📝 Quizzes", "📊 My Progress"])

with t1:
    key = f"hist_{course['id']}"
    hist = st.session_state.setdefault(key, [])
    for m in hist:
        st.chat_message(m["role"]).markdown(m["content"])
    if msg := st.chat_input("Ask about your course..."):
        st.chat_message("user").markdown(msg)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                intent = agents.route(msg)
                if intent == "quiz":
                    reply, ok = "Open the **Quizzes** tab to practice this topic.", True
                else:
                    reply, ok, chunks = agents.tutor(course, msg, mode, lang, hist)
            st.markdown(reply)
        hist += [{"role": "user", "content": msg}, {"role": "assistant", "content": reply}]
        db.run("INSERT INTO chats(user_id,course_id,question,grounded) VALUES(?,?,?,?)",
               (u["id"], course["id"], msg, int(ok)))

with t2:
    quizzes = db.q("SELECT * FROM quizzes WHERE course_id=? AND approved=1", (course["id"],))
    if not quizzes:
        st.info("No published quizzes yet.")
    else:
        z = st.selectbox("Quiz", quizzes, format_func=lambda z: z["topic"])
        qs = json.loads(z["data"]); ans = {}
        for i, qn in enumerate(qs):
            ch = st.radio(f"{i+1}. {qn['q']}", qn["options"], index=None, key=f"q{z['id']}_{i}")
            ans[i] = qn["options"].index(ch) if ch else None
        if st.button("Submit"):
            c, t = agents.grade(qs, ans)
            db.run("INSERT INTO attempts(user_id,course_id,topic,correct,total) VALUES(?,?,?,?,?)",
                   (u["id"], course["id"], z["topic"], c, t))
            st.success(f"Score: {c}/{t}")
            for i, qn in enumerate(qs):
                st.write(f"**Q{i+1}** {'✅' if ans[i] == qn['answer'] else '❌'} {qn['explanation']}")

with t3:
    att = db.q("SELECT topic, correct, total FROM attempts WHERE user_id=? AND course_id=? ORDER BY id",
               (u["id"], course["id"]))
    n = db.q("SELECT COUNT(*) n FROM chats WHERE user_id=? AND course_id=?", (u["id"], course["id"]))[0]["n"]
    tot = sum(a["total"] for a in att); cor = sum(a["correct"] for a in att)

    m1, m2, m3 = st.columns(3)
    m1.metric("Questions asked", n)
    m2.metric("Quizzes taken", len(att))
    m3.metric("Average score", f"{cor / tot * 100:.0f}%" if tot else "-")

    if att:
        df = pd.DataFrame(att)
        df["score %"] = (df["correct"] / df["total"] * 100).round(1)
        st.subheader("Mastery by topic")
        m = df.groupby("topic").agg(c=("correct", "sum"), t=("total", "sum")).reset_index()
        m["mastery %"] = (m["c"] / m["t"] * 100).round(1)
        st.bar_chart(m.set_index("topic")["mastery %"])
        st.subheader("Score trend")
        st.line_chart(df["score %"].reset_index(drop=True))
        weak = m[m["mastery %"] < 60]["topic"].tolist()
        st.info("Focus on: " + ", ".join(weak) if weak else "Great work, no weak topics!")
    else:
        st.info("Take and submit a quiz in the Quizzes tab to see your progress here.")
