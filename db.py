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

def hp(p): return hashlib.sha256(p.encode()).hexdigest()
def code(): return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
