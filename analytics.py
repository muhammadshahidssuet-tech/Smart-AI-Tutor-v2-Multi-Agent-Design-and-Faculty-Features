"""Analytics Agent: turns quiz results and chat logs into written insights for faculty and students.
Numbers are computed in code; the LLM only writes the explanation (it never invents data).
Faculty reports use anonymous codes (S1, S2...) when calling the LLM; real names are restored locally."""
import json, re
from collections import Counter
import db, agents

def _pct(c, t):
    return round(c / t * 100) if t else None

def class_stats(course_id):
    studs = db.q("""SELECT u.id, COALESCE(u.full_name, u.username) AS name, COALESCE(u.enrollment_no, '-') AS enr
                    FROM enrollments e JOIN users u ON u.id = e.user_id WHERE e.course_id=?""", (course_id,))
    att = db.q("SELECT user_id, topic, correct, total FROM attempts WHERE course_id=?", (course_id,))
    chats = db.q("SELECT user_id, question, grounded FROM chats WHERE course_id=?", (course_id,))
    code = {s["id"]: f"S{i}" for i, s in enumerate(studs, 1)}
    people = {code[s["id"]]: f"{s['name']} ({s['enr']})" for s in studs}
    tp = {}
    for a in att:
        v = tp.setdefault(a["topic"], [0, 0, set()])
        v[0] += a["correct"] or 0; v[1] += a["total"] or 0; v[2].add(a["user_id"])
    topics = sorted(({"topic": t, "accuracy_pct": _pct(v[0], v[1]), "students": len(v[2])} for t, v in tp.items()),
                    key=lambda x: 101 if x["accuracy_pct"] is None else x["accuracy_pct"])
    rows = []
    for s in studs:
        mine = [a for a in att if a["user_id"] == s["id"]]
        per = {}
        for a in mine:
            x = per.setdefault(a["topic"], [0, 0]); x[0] += a["correct"] or 0; x[1] += a["total"] or 0
        weakest = min(per, key=lambda k: per[k][0] / per[k][1] if per[k][1] else 1) if per else None
        rows.append({"student": code[s["id"]],
                     "avg_score_pct": _pct(sum(a["correct"] or 0 for a in mine), sum(a["total"] or 0 for a in mine)),
                     "quizzes_taken": len(mine), "questions_asked": sum(1 for c in chats if c["user_id"] == s["id"]),
                     "weakest_topic": weakest})
    norm = lambda q: q.strip().lower()[:120]
    stats = {"students_enrolled": len(studs), "total_questions": len(chats), "quiz_attempts": len(att),
             "class_avg_pct": _pct(sum(a["correct"] or 0 for a in att), sum(a["total"] or 0 for a in att)),
             "topics_lowest_first": topics, "students": rows,
             "most_asked_questions": Counter(norm(c["question"]) for c in chats).most_common(5),
             "questions_tutor_could_not_answer": Counter(norm(c["question"]) for c in chats if not c["grounded"]).most_common(5)}
    return stats, people

def class_insights(course_id):
    stats, people = class_stats(course_id)
    if not stats["total_questions"] and not stats["quiz_attempts"]:
        return "Not enough activity yet. Insights appear once students ask questions or complete quizzes."
    prompt = ("You are an educational analytics agent writing for a university teacher. "
              "Use ONLY the data below; never invent numbers or names. Students appear as codes like S1.\n"
              f"DATA:\n{json.dumps(stats, default=str)}\n\n"
              "Write under 300 words in Markdown with these sections: "
              "## Overview, ## Topics to re-teach, ## Students needing attention (use codes, mention score and weakest topic), "
              "## Content gaps (questions the tutor could not answer from the material), ## Recommended actions (3 to 5 bullets). "
              "If a section has no data, write one short line saying so.")
    text = agents.llm([{"role": "user", "content": prompt}], temp=0.3)
    return re.sub(r"\bS(\d+)\b", lambda m: people.get(m.group(0), m.group(0)), text)   # restore real names locally

def student_insights(user_id, course_id):
    att = db.q("SELECT topic, correct, total FROM attempts WHERE user_id=? AND course_id=? ORDER BY id", (user_id, course_id))
    chats = db.q("SELECT question, grounded FROM chats WHERE user_id=? AND course_id=?", (user_id, course_id))
    if not att and not chats:
        return "Not enough activity yet. Ask the tutor some questions or take a quiz, then come back."
    per = {}
    for a in att:
        x = per.setdefault(a["topic"], [0, 0]); x[0] += a["correct"] or 0; x[1] += a["total"] or 0
    stats = {"questions_asked": len(chats), "questions_tutor_could_not_answer": sum(1 for c in chats if not c["grounded"]),
             "quizzes_taken": len(att), "average_score_pct": _pct(sum(a["correct"] or 0 for a in att), sum(a["total"] or 0 for a in att)),
             "mastery_by_topic_pct": {t: _pct(c, n) for t, (c, n) in per.items()},
             "score_trend_pct": [_pct(a["correct"] or 0, a["total"] or 0) for a in att],
             "recent_questions": [c["question"][:100] for c in chats[-5:]]}
    prompt = ("You are an educational analytics agent writing directly to a university student. Be friendly and encouraging. "
              "Use ONLY the data below; never invent numbers.\n"
              f"DATA:\n{json.dumps(stats, default=str)}\n\n"
              "Write under 200 words in Markdown: ## Your progress, ## Strengths, ## Needs work, ## Next steps (3 short bullets).")
    return agents.llm([{"role": "user", "content": prompt}], temp=0.4)
