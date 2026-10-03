import json, streamlit as st, pandas as pd
import db, agents, ui, reports, scholar, analytics


db.init()
u = st.session_state.get("user")
if not u or u["role"] != "teacher":
    st.warning("Please log in as faculty on the main page."); st.stop()

ui.header("Faculty Portal: manage courses, materials, research and insights", u)
ui.sidebar_brand(u)

if not u.get("full_name"):
    st.subheader("Complete your profile")
    fn = st.text_input("Your full name (shown to students)")
    if st.button("Save profile") and fn.strip():
        db.run("UPDATE users SET full_name=? WHERE id=?", (fn.strip(), u["id"]))
        st.session_state.user = db.q("SELECT * FROM users WHERE id=?", (u["id"],))[0]
        st.rerun()
    st.stop()

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

t1, t2, t3, t5, t4 = st.tabs(["📂 Materials", "📝 Quiz Approval", "📊 Class Analytics", "🤖 AI Insights", "🔎 Research Papers"])

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
    chats = db.q("SELECT user_id, question, grounded FROM chats WHERE course_id=?", (course["id"],))
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
        st.dataframe(df, width="stretch", hide_index=True)
        weak = df[df["accuracy %"] < 60]["topic"].tolist()
        if weak:
            st.warning("Weak topics to re-teach: " + ", ".join(weak))
        else:
            st.success("No weak topics found.")
        st.download_button("Export CSV", df.to_csv(index=False), "class_report.csv")
    else:
        st.info("No quiz attempts yet. Students must submit an approved quiz. "
                "Or click 'Load demo data' in the sidebar to preview this dashboard.")

    st.subheader("Student performance")
    studs = db.q("""SELECT u.id, COALESCE(u.full_name, u.username) AS name,
                           COALESCE(u.enrollment_no, '-') AS enrollment
                    FROM enrollments e JOIN users u ON u.id = e.user_id
                    WHERE e.course_id=? ORDER BY u.enrollment_no""", (course["id"],))
    if studs:
        rows = []
        for s_ in studs:
            mine = [a for a in att if a["user_id"] == s_["id"]]
            t_ = sum(a["total"] for a in mine); c_ = sum(a["correct"] for a in mine)
            avg = round(c_ / t_ * 100) if t_ else None
            per = {}
            for a in mine:
                x = per.setdefault(a["topic"], [0, 0]); x[0] += a["correct"]; x[1] += a["total"]
            weakest = min(per, key=lambda k: per[k][0] / per[k][1]) if per else "-"
            asked = sum(1 for c in chats if c["user_id"] == s_["id"])
            status = "No activity" if (not mine and not asked) else ("At risk" if avg is not None and avg < 50 else "On track")
            rows.append({"Student Name": s_["name"], "Enrollment No.": s_["enrollment"],
                         "Questions Asked": asked, "Quizzes Taken": len(mine),
                         "Avg Score %": avg if avg is not None else "-",
                         "Weakest Topic": weakest, "Status": status})
        sdf = pd.DataFrame(rows)
        st.dataframe(sdf, width="stretch", hide_index=True)
        st.download_button("Export student report (CSV)", sdf.to_csv(index=False), "student_report.csv")
    else:
        st.info("No students have joined yet. Share the join code from the sidebar.")

    st.subheader("Quiz result report")
    pub = db.q("SELECT * FROM quizzes WHERE course_id=? AND approved=1", (course["id"],))
    if not pub:
        st.info("Publish a quiz to generate a result report.")
    else:
        zq = st.selectbox("Select quiz", pub, format_func=lambda z: z["topic"], key="rep_quiz")
        rep = reports.build_report(course["id"], zq)
        if rep.empty:
            st.info("No students have joined this course yet.")
        else:
            qcols = [c for c in rep.columns if c.startswith("Q") and c[1:].isdigit()]
            colour = lambda v: ("background-color:#C6EFCE" if v == "Correct"
                                else "background-color:#FFC7CE" if v == "Wrong" else "")
            try:
                sty = rep.style
                sty = (sty.map if hasattr(sty, "map") else sty.applymap)(colour, subset=qcols)
            except Exception:
                sty = rep
            st.dataframe(sty, width="stretch", hide_index=True, column_config={
                "Percentage": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d%%")})
            d1, d2 = st.columns(2)
            d1.download_button("⬇ Download CSV report", reports.to_csv(rep),
                               f"quiz_report_{zq['topic']}.csv", "text/csv")
            d2.download_button("⬇ Download Excel report (colored)", reports.to_excel(rep),
                               f"quiz_report_{zq['topic']}.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    if chats:
        qs = pd.Series([c["question"] for c in chats]).value_counts().head(10).reset_index()
        qs.columns = ["Question", "Times asked"]
        st.subheader("Most-asked questions")
        st.dataframe(qs, width="stretch", hide_index=True)

with t4:
    st.subheader("Research paper search")
    st.caption("Free search across OpenAlex (250M+ works) and arXiv. No API key needed.")
    c1, c2 = st.columns([3, 1])
    query = c1.text_input("Topic, keywords or paper title", key="ps_q", placeholder="e.g. database normalization")
    src = c2.selectbox("Source", ["OpenAlex + arXiv", "OpenAlex", "arXiv"], key="ps_src")
    f1, f2, f3, f4 = st.columns(4)
    sort = f1.selectbox("Sort by", ["Relevance", "Most cited", "Newest"], key="ps_sort")
    yfrom = f2.number_input("From year", 1990, 2026, 2018, key="ps_year")
    oa = f3.checkbox("Open access only", key="ps_oa")
    n = f4.slider("Results per source", 5, 25, 10, key="ps_n")
    if st.button("Search papers", type="primary") and query.strip():
        with st.spinner("Searching..."):
            st.session_state.papers, st.session_state.perrs = scholar.search(query.strip(), src, sort, yfrom, oa, n)
    for e in st.session_state.get("perrs", []):
        st.warning(e + ". Try again in a moment or switch the source.")
    found = st.session_state.get("papers")
    if found is not None:
        st.write(f"**{len(found)} papers found**")
        if found:
            st.download_button("Export results (CSV)", pd.DataFrame(found).drop(columns=["abstract"]).to_csv(index=False),
                               "papers.csv", key="ps_csv")
    for i, p in enumerate(found or []):
        with st.container(border=True):
            st.markdown(f"**[{p['title'].replace('[', '(').replace(']', ')')}]({p['url']})**")
            meta = f"{p['authors']} · {p['year']}" + (f" · *{p['venue']}*" if p["venue"] else "")
            st.caption(meta)
            tags = [f"📚 {p['source']}"]
            if p["citations"] is not None:
                tags.append(f"🔗 {p['citations']} citations")
            if p["open_access"]:
                tags.append("🟢 Open access")
            st.caption("  ·  ".join(tags))
            if p["abstract"]:
                with st.expander("Abstract"):
                    st.write(p["abstract"])
            b1, b2, _ = st.columns([1, 2, 4])
            if p["pdf"]:
                b1.link_button("PDF", p["pdf"])
            if b2.button("➕ Add to reading list", key=f"sv{i}"):
                if db.q("SELECT 1 FROM papers WHERE course_id=? AND title=?", (course["id"], p["title"])):
                    st.toast("Already in the reading list")
                else:
                    db.run("INSERT INTO papers(course_id,title,authors,year,venue,url,pdf,added_by) VALUES(?,?,?,?,?,?,?,?)",
                           (course["id"], p["title"], p["authors"], p["year"], p["venue"], p["url"], p["pdf"], u["id"]))
                    st.toast("Added to reading list")

    st.divider()
    st.subheader("📚 Course reading list (visible to students)")
    lst = db.q("SELECT * FROM papers WHERE course_id=? ORDER BY id DESC", (course["id"],))
    if not lst:
        st.caption("No papers saved yet. Use ➕ Add to reading list above.")
    for r in lst:
        a, b = st.columns([6, 1])
        a.markdown(f"[{r['title']}]({r['url']})  \n<small>{r['authors']} · {r['year']}</small>", unsafe_allow_html=True)
        if b.button("Remove", key=f"rm{r['id']}"):
            db.run("DELETE FROM papers WHERE id=?", (r["id"],)); st.rerun()

with t5:
    st.subheader("🤖 AI insights for this course")
    st.caption("The Analytics Agent turns chats and quiz results into written findings. "
               "Student names are replaced with codes (S1, S2...) before analysis and restored here.")
    key = f"ci_{course['id']}"
    if st.button("Generate class insights", type="primary", key="ci_go"):
        with st.spinner("Analytics Agent is reading class activity..."):
            try:
                st.session_state[key] = analytics.class_insights(course["id"])
            except Exception as e:
                st.error(f"Could not generate insights: {e}")
    if st.session_state.get(key):
        st.markdown(st.session_state[key])
        st.download_button("⬇ Download insights (Markdown)", st.session_state[key], "class_insights.md", key="ci_dl")
