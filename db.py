import sqlite3, hashlib, random, string
DB = "tutor.db"

def _c():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c

def q(sql, args=()):
    with _c() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]

def run(sql, args=()):
    with _c() as c:
        return c.execute(sql, args).lastrowid

def init():
    with _c() as c:
        c.executescript("""
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE, pw TEXT, role TEXT);
CREATE TABLE IF NOT EXISTS courses(id INTEGER PRIMARY KEY, name TEXT, code TEXT UNIQUE, teacher_id INTEGER, strict INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS enrollments(user_id INTEGER, course_id INTEGER, PRIMARY KEY(user_id, course_id));
CREATE TABLE IF NOT EXISTS docs(id INTEGER PRIMARY KEY, course_id INTEGER, name TEXT, summary TEXT);
CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY, course_id INTEGER, source TEXT, page INTEGER, text TEXT);
CREATE TABLE IF NOT EXISTS quizzes(id INTEGER PRIMARY KEY, course_id INTEGER, topic TEXT, data TEXT, approved INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY, user_id INTEGER, course_id INTEGER, topic TEXT, correct INTEGER, total INTEGER);
CREATE TABLE IF NOT EXISTS chats(id INTEGER PRIMARY KEY, user_id INTEGER, course_id INTEGER, question TEXT, grounded INTEGER);
""")
        for col in ("full_name", "enrollment_no"):      # migration for older databases
            try:
                c.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass

def hp(p): return hashlib.sha256(p.encode()).hexdigest()
def code(): return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

def seed_demo(course_id):
    """Fill a course with demo students, quiz attempts and questions (for testing dashboards)."""
    import random
    names = ["Ali Raza", "Sara Khan", "Ahmed Hassan", "Fatima Noor", "Usman Tariq"]
    topics = ["Basics", "Normalization", "SQL Joins", "Indexing"]
    qs = ["What is normalization?", "Explain SQL joins", "What is a primary key?",
          "What is normalization?", "How does indexing work?", "Explain SQL joins"]
    for i, full in enumerate(names, 1):
        uname, enr = f"demo_student{i}", f"2026-CS-{i:03d}"
        r = q("SELECT id FROM users WHERE username=?", (uname,))
        if r:
            uid = r[0]["id"]
            run("UPDATE users SET full_name=?, enrollment_no=? WHERE id=?", (full, enr, uid))
        else:
            uid = run("INSERT INTO users(username,pw,role,full_name,enrollment_no) VALUES(?,?,?,?,?)",
                      (uname, hp("demo"), "student", full, enr))
        run("INSERT OR IGNORE INTO enrollments VALUES(?,?)", (uid, course_id))
        if q("SELECT 1 FROM attempts WHERE user_id=? AND course_id=?", (uid, course_id)):
            continue
        for t in topics:
            base = 0.35 if t == "Normalization" else (0.2 if i == 5 else 0.8)
            run("INSERT INTO attempts(user_id,course_id,topic,correct,total) VALUES(?,?,?,?,?)",
                (uid, course_id, t, sum(random.random() < base for _ in range(5)), 5))
        for question in random.sample(qs, 4):
            run("INSERT INTO chats(user_id,course_id,question,grounded) VALUES(?,?,?,1)",
                (uid, course_id, question))
