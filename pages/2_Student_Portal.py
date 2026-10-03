import json, streamlit as st, pandas as pd
import datetime as dt
import db, agents, ui, planner, analytics


db.init()
u = st.session_state.get("user")
if not u or u["role"] != "student":
    st.warning("Please log in as a student on the main page."); st.stop()

ui.header("Student Portal: learn, practice and track progress", u)
ui.sidebar_brand(u)

if not u.get("enrollment_no") or not u.get("full_name"):
    st.subheader("Complete your profile")
    fn = st.text_input("Full name", value=u.get("full_name") or "")
    en = st.text_input("Enrollment number")
    if st.button("Save profile"):
        if not (fn.strip() and en.strip()):
            st.error("Both fields are required.")
        elif db.q("SELECT id FROM users WHERE enrollment_no=? AND id!=?", (en.strip(), u["id"])):
            st.error("This enrollment number is already registered.")
        else:
            db.run("UPDATE users SET full_name=?, enrollment_no=? WHERE id=?", (fn.strip(), en.strip(), u["id"]))
            st.session_state.user = db.q("SELECT * FROM users WHERE id=?", (u["id"],))[0]
            st.rerun()
    st.stop()

with st.sidebar.expander("➕ Join a course"):
    code = st.text_input("Course code").upper().strip()
    if st.button("Join"):
        c = db.q("SELECT id FROM courses WHERE code=?", (code,))
        if c:
            db.run("INSERT OR IGNORE INTO enrollments VALUES(?,?)", (u["id"], c[0]["id"])); st.rerun()
        else:
            st.error("Invalid code")

courses = db.q("""SELECT c.*, COALESCE(t.full_name, t.username) AS teacher
                  FROM courses c JOIN enrollments e ON e.course_id=c.id
                  JOIN users t ON t.id=c.teacher_id WHERE e.user_id=?""", (u["id"],))
if not courses:
    st.info("Join a course using the code from your faculty."); st.stop()

course = st.sidebar.selectbox("Course", courses, format_func=lambda c: f"{c['name']} ({c['teacher']})")
st.sidebar.caption(f"👩‍🏫 Instructor: **{course['teacher']}**")
st.info(f"📘 **{course['name']}**  |  Instructor: **{course['teacher']}**  |  "
        f"Student: **{u['full_name']}** ({u['enrollment_no']})")
mode = st.sidebar.radio("Tutor mode", ["Simple", "Step-by-step", "Socratic"])
lang = st.sidebar.selectbox("Language", ["English", "Urdu", "Roman Urdu"])

t1, t2, t3, t5, t4 = st.tabs(["💬 Tutor Chat", "📝 Quizzes", "📊 My Progress", "🗓️ Study Planner", "📚 Reading List"])

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
    done = {r["quiz_id"]: r for r in db.q(
        "SELECT * FROM attempts WHERE user_id=? AND quiz_id IS NOT NULL", (u["id"],))}
    if not quizzes:
        st.info("No published quizzes yet.")
    else:
        z = st.selectbox("Quiz", quizzes, format_func=lambda z:
                         f"{z['topic']}  -  {'✅ Completed' if z['id'] in done else '🆕 Not attempted'}")
        qs = json.loads(z["data"])
        if z["id"] in done:
            r = done[z["id"]]
            st.success(f"You have already completed this quiz. Your score: {r['correct']}/{r['total']}. "
                       "Each quiz can be attempted only once.")
            saved = json.loads(r["answers"] or "{}")
            with st.expander("Review your answers"):
                for i, qn in enumerate(qs):
                    pick = saved.get(str(i))
                    st.write(f"**Q{i+1}. {qn['q']}** {'✅' if pick == qn['answer'] else '❌'}")
                    st.write("Your answer: " + (qn["options"][pick] if pick is not None else "Not answered"))
                    st.write("Correct answer: " + qn["options"][qn["answer"]])
                    st.caption(qn["explanation"])
        else:
            st.warning("You can submit this quiz only once. Answer carefully.")
            ans = {}
            for i, qn in enumerate(qs):
                ch = st.radio(f"{i+1}. {qn['q']}", qn["options"], index=None, key=f"q{z['id']}_{i}")
                ans[i] = qn["options"].index(ch) if ch else None
            if st.button("Submit quiz (final)"):
                if any(v is None for v in ans.values()):
                    st.error("Please answer all questions before submitting.")
                elif db.q("SELECT 1 FROM attempts WHERE user_id=? AND quiz_id=?", (u["id"], z["id"])):
                    st.error("You have already submitted this quiz.")
                else:
                    c, t = agents.grade(qs, ans)
                    db.run("INSERT INTO attempts(user_id,course_id,topic,correct,total,quiz_id,answers) "
                           "VALUES(?,?,?,?,?,?,?)",
                           (u["id"], course["id"], z["topic"], c, t, z["id"],
                            json.dumps({str(k): v for k, v in ans.items()})))
                    st.rerun()

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

    st.divider()
    st.subheader("🤖 AI insights about my learning")
    ikey = f"si_{course['id']}"
    if st.button("Generate my insights", key="si_go"):
        with st.spinner("Analytics Agent is reading your activity..."):
            try:
                st.session_state[ikey] = analytics.student_insights(u["id"], course["id"])
            except Exception as e:
                st.error(f"Could not generate insights: {e}")
    if st.session_state.get(ikey):
        st.markdown(st.session_state[ikey])

with t4:
    st.subheader("Recommended research papers")
    lst = db.q("SELECT * FROM papers WHERE course_id=? ORDER BY id DESC", (course["id"],))
    if not lst:
        st.info("Your faculty has not added any papers yet.")
    for r in lst:
        with st.container(border=True):
            st.markdown(f"**[{r['title']}]({r['url']})**")
            st.caption(f"{r['authors']} · {r['year']}" + (f" · {r['venue']}" if r["venue"] else ""))
            if r["pdf"]:
                st.link_button("PDF", r["pdf"])

with t5:
    st.subheader("🗓️ Smart study planner")
    st.caption("The Planner Agent builds a day-by-day plan around your weak topics (up to 14 days).")
    mastery = planner.topic_mastery(u["id"], course["id"])
    if mastery:
        st.write("**Your topic mastery** (lowest first)")
        st.dataframe(pd.DataFrame(mastery, columns=["Topic", "Mastery %"]), hide_index=True, width="stretch")
    else:
        st.info("No quiz results yet, so the plan will cover the course topics evenly. Take a quiz for a personalised plan.")
    kind_label = st.radio("Plan type", ["Exam preparation", "Weekly study schedule"], horizontal=True, key="pl_kind")
    c1, c2 = st.columns(2)
    exam = c1.date_input("Exam date", value=dt.date.today() + dt.timedelta(days=14), min_value=dt.date.today(),
                         disabled=(kind_label != "Exam preparation"), key="pl_exam")
    hrs = c2.slider("Study hours per day", 0.5, 6.0, 2.0, 0.5, key="pl_hrs")
    if st.button("✨ Generate my plan", type="primary", key="pl_go"):
        with st.spinner("Planner Agent is building your schedule..."):
            try:
                kind = "exam" if kind_label == "Exam preparation" else "week"
                planner.save_plan(u["id"], course["id"], planner.build_plan(course, mastery, kind, exam, hrs))
            except Exception as e:
                st.error(f"Could not build the plan: {e}")
    plan = planner.load_plan(u["id"], course["id"])
    if plan:
        if plan.get("summary"):
            st.success(plan["summary"])
        st.caption("Focus topics: " + ", ".join(plan["topics"]) + (f"  |  Exam date: {plan['exam_date']}" if plan.get("exam_date") else ""))
        for d in plan["days"]:
            with st.container(border=True):
                a, b = st.columns([1, 4])
                a.markdown(f"**Day {d['day']}**  \n{d['date']}  \n⏱ {d['minutes']} min")
                b.markdown(f"**{d['focus']}**\n\n" + "\n".join(f"- {t}" for t in d["tasks"]))
        csv = pd.DataFrame([{"Day": d["day"], "Date": d["date"], "Focus": d["focus"],
                             "Tasks": " | ".join(d["tasks"]), "Minutes": d["minutes"]} for d in plan["days"]]).to_csv(index=False)
        st.download_button("⬇ Download plan (CSV)", csv, "study_plan.csv", key="pl_dl")
