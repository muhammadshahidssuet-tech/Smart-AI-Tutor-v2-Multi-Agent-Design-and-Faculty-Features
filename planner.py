"""Planner Agent: builds study schedules and exam-prep plans from a student's weak topics."""
import json, datetime as dt
import db, agents

def topic_mastery(user_id, course_id):
    """[(topic, mastery %)] for this student, lowest first."""
    per = {}
    for r in db.q("SELECT topic, correct, total FROM attempts WHERE user_id=? AND course_id=?", (user_id, course_id)):
        v = per.setdefault(r["topic"], [0, 0]); v[0] += r["correct"] or 0; v[1] += r["total"] or 0
    return sorted([(t, round(c / n * 100)) for t, (c, n) in per.items() if n], key=lambda x: x[1])

def pick_topics(course_id, mastery):
    weak = [t for t, p in mastery if p < 60]
    if weak:
        return weak
    if mastery:                                   # no weak topics: keep revising the lowest ones
        return [t for t, _ in mastery][:3]
    topics = [r["topic"] for r in db.q("SELECT DISTINCT topic FROM quizzes WHERE course_id=? AND approved=1", (course_id,))]
    return topics or ["General course revision"]

def _fallback(topics, days, minutes, kind):
    tasks = lambda t: [f"Review your notes on {t}", f"Solve 5 practice questions on {t}", "Write a 3-line summary from memory"]
    out = []
    for i in range(days):
        if i == days - 1:
            out.append({"focus": "Mock test and revision" if kind == "exam" else "Weekly self-check",
                        "tasks": ["Take a timed practice quiz", "Re-read mistakes", "Revise key terms"], "minutes": minutes})
        else:
            out.append({"focus": topics[i % len(topics)], "tasks": tasks(topics[i % len(topics)]), "minutes": minutes})
    return {"summary": "A simple rotation through your weakest topics, ending with a self-check.", "days": out}

def build_plan(course, mastery, kind, exam_date, hours):
    today = dt.date.today()
    days = max(1, min((exam_date - today).days, 14)) if kind == "exam" and exam_date else 7
    minutes = int(hours * 60)
    topics = pick_topics(course["id"], mastery)
    ctx = ""
    for t in topics[:4]:
        chunks, _ = agents.retrieve(course["id"], t, k=2)
        ctx += f"\n[{t}] " + " ".join(c["text"][:500] for c in chunks)
    mtxt = ", ".join(f"{t}: {p}%" for t, p in mastery) or "no quiz data yet"
    ending = "make the last day a mock test plus light revision" if kind == "exam" else "end with a weekly self-check"
    prompt = (f"You are a study-planning agent for a university student.\n"
              f"Course: {course['name']}. Student mastery by topic: {mtxt}.\n"
              f"Focus topics, weakest first: {', '.join(topics)}.\n"
              f"Create a {days}-day {'exam-preparation' if kind == 'exam' else 'weekly'} plan of about {minutes} minutes per day.\n"
              f"Rules: give weak topics the most time; include active recall and practice questions; add short spaced review of earlier topics; {ending}. "
              f"Use only the focus topics. Course excerpts for reference: {ctx[:3500]}\n"
              f'Return JSON only: {{"summary":"two sentences","days":[{{"focus":"topic","tasks":["task","task","task"],"minutes":{minutes}}}]}} '
              f"with exactly {days} items in days.")
    try:
        data = json.loads(agents.llm([{"role": "user", "content": prompt}], as_json=True, temp=0.4))
        items = data["days"]
        assert isinstance(items, list) and items
    except Exception:                              # never fail: fall back to a simple rotation
        data = _fallback(topics, days, minutes, kind); items = data["days"]
    fb = _fallback(topics, days, minutes, kind)["days"]
    plan_days = []
    for i in range(days):
        it = items[i] if i < len(items) and isinstance(items[i], dict) else fb[i]
        tasks = [str(x) for x in (it.get("tasks") or fb[i]["tasks"])][:5]
        try:
            mins = int(it.get("minutes") or minutes)
        except Exception:
            mins = minutes
        plan_days.append({"day": i + 1, "date": (today + dt.timedelta(days=i)).isoformat(),
                          "focus": str(it.get("focus") or fb[i]["focus"]), "tasks": tasks, "minutes": mins})
    return {"summary": str(data.get("summary", "")), "kind": kind, "topics": topics,
            "exam_date": exam_date.isoformat() if kind == "exam" and exam_date else None, "days": plan_days}

def save_plan(user_id, course_id, plan):
    db.run("DELETE FROM plans WHERE user_id=? AND course_id=?", (user_id, course_id))
    db.run("INSERT INTO plans(user_id,course_id,exam_date,kind,data) VALUES(?,?,?,?,?)",
           (user_id, course_id, plan.get("exam_date"), plan["kind"], json.dumps(plan)))

def load_plan(user_id, course_id):
    r = db.q("SELECT data FROM plans WHERE user_id=? AND course_id=? ORDER BY id DESC LIMIT 1", (user_id, course_id))
    return json.loads(r[0]["data"]) if r else None
