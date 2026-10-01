"""Database layer.
- If DATABASE_URL is set in Streamlit Secrets  -> permanent PostgreSQL (e.g. Supabase, free).
- Otherwise                                     -> local SQLite file (temporary on Streamlit Cloud).
"""
import sqlite3, hashlib, random, string
import streamlit as st

def _url():
    try:
        return str(st.secrets.get("DATABASE_URL", "")).strip()
    except Exception:
        return ""

URL = _url()
PG = URL.startswith("postgres")
SQLITE_FILE = "tutor.db"

if PG:
    import psycopg2, psycopg2.pool
    from psycopg2.extras import RealDictCursor

    @st.cache_resource
    def _pool(url):
        return psycopg2.pool.ThreadedConnectionPool(1, 5, url, connect_timeout=15)

    def _exec(sql, args, want):
        for attempt in (1, 2):                      # retry once if the cloud DB dropped an idle connection
            pool = _pool(URL); conn = pool.getconn()
            try:
                conn.autocommit = True
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(sql, args)
                    if want == "rows":
                        out = [dict(r) for r in cur.fetchall()]
                    else:
                        out = cur.fetchone()["id"] if cur.description else None
                pool.putconn(conn)
                return out
            except (psycopg2.OperationalError, psycopg2.InterfaceError):
                pool.putconn(conn, close=True)
                if attempt == 2:
                    raise
            except Exception:
                pool.putconn(conn)
                raise

    def q(sql, args=()):
        return _exec(sql.replace("?", "%s"), args, "rows")

    def run(sql, args=()):
        s = sql.replace("?", "%s").strip()
        if s.upper().startswith("INSERT OR IGNORE"):
            s = s.replace("INSERT OR IGNORE", "INSERT", 1) + " ON CONFLICT DO NOTHING"
        elif s.upper().startswith("INSERT"):
            s += " RETURNING id"
        return _exec(s, args, "id")
else:
    def _c():
        c = sqlite3.connect(SQLITE_FILE); c.row_factory = sqlite3.Row; return c

    def q(sql, args=()):
        with _c() as c:
            return [dict(r) for r in c.execute(sql, args).fetchall()]

    def run(sql, args=()):
        with _c() as c:
            return c.execute(sql, args).lastrowid

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id {PK}, username TEXT UNIQUE, pw TEXT, role TEXT, full_name TEXT, enrollment_no TEXT);
CREATE TABLE IF NOT EXISTS courses(id {PK}, name TEXT, code TEXT UNIQUE, teacher_id INTEGER, strict INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS enrollments(user_id INTEGER, course_id INTEGER, PRIMARY KEY(user_id, course_id));
CREATE TABLE IF NOT EXISTS docs(id {PK}, course_id INTEGER, name TEXT, summary TEXT);
CREATE TABLE IF NOT EXISTS chunks(id {PK}, course_id INTEGER, source TEXT, page INTEGER, text TEXT);
CREATE TABLE IF NOT EXISTS quizzes(id {PK}, course_id INTEGER, topic TEXT, data TEXT, approved INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS attempts(id {PK}, user_id INTEGER, course_id INTEGER, topic TEXT, correct INTEGER, total INTEGER, quiz_id INTEGER, answers TEXT);
CREATE TABLE IF NOT EXISTS papers(id {PK}, course_id INTEGER, title TEXT, authors TEXT, year INTEGER, venue TEXT, url TEXT, pdf TEXT, added_by INTEGER);
CREATE TABLE IF NOT EXISTS chats(id {PK}, user_id INTEGER, course_id INTEGER, question TEXT, grounded INTEGER);
"""

def init():
    pk = "SERIAL PRIMARY KEY" if PG else "INTEGER PRIMARY KEY"
    for stmt in SCHEMA.format(PK=pk).split(";"):
        if stmt.strip():
            if PG:
                _exec(stmt, (), "none")
            else:
                with _c() as c:
                    c.execute(stmt)
    if not PG:      # upgrade older local SQLite files
        with _c() as c:
            for tbl, col in (("users", "full_name TEXT"), ("users", "enrollment_no TEXT"),
                             ("attempts", "quiz_id INTEGER"), ("attempts", "answers TEXT")):
                try:
                    c.execute(f"ALTER TABLE {tbl} ADD COLUMN {col}")
                    if col.startswith("quiz_id"):
                        c.execute("""UPDATE attempts SET quiz_id=(SELECT id FROM quizzes
                                     WHERE quizzes.course_id=attempts.course_id
                                     AND quizzes.topic=attempts.topic LIMIT 1)""")
                except sqlite3.OperationalError:
                    pass

def hp(p): return hashlib.sha256(p.encode()).hexdigest()
def code(): return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

def seed_demo(course_id):
    """Fill a course with demo students, quiz attempts and questions (for testing dashboards)."""
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
