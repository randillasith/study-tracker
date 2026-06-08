#!/usr/bin/env python3
"""
📝 Study Tracker v2 — Web Dashboard
Pomodoro Timer · Analytics · AI Coach · Exam Countdown · Leaderboard
"""

import os, re, hmac, hashlib, json, sqlite3, math, secrets
from datetime import date, timedelta, datetime
from collections import defaultdict
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, g
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "study-tracker-web-secret-2026-randil")

BOT_TOKEN = os.environ.get("STUDY_BOT_TOKEN", "MISSING")
BOT_USERNAME = "KirithoStudybot"
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
DB_PATH = os.environ.get("STUDY_DB_PATH", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "study.db"))

XP_PER_HOUR = 100

# ─── Database ───────────────────────────────────────────────

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exc):
    g.pop("db", None)

def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
            last_name TEXT, photo_url TEXT, xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1, current_streak INTEGER DEFAULT 0,
            longest_streak INTEGER DEFAULT 0, last_study_date TEXT,
            total_minutes INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS study_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            subject TEXT NOT NULL, duration_minutes INTEGER NOT NULL,
            logged_at TEXT DEFAULT (datetime('now')), note TEXT, xp_earned INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS daily_stats (
            user_id INTEGER, date TEXT, total_minutes INTEGER DEFAULT 0,
            subjects TEXT DEFAULT '{}', xp_earned INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, date)
        );

        CREATE TABLE IF NOT EXISTS pomodoro_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
            started_at TEXT, completed_at TEXT,
            duration_type TEXT DEFAULT 'focus', completed INTEGER DEFAULT 0,
            xp_earned INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS exams (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
            subject TEXT NOT NULL, exam_name TEXT NOT NULL,
            exam_date TEXT NOT NULL, syllabus_hours REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS weekly_leaderboard (
            user_id INTEGER, week_start TEXT, total_xp INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, week_start)
        );
    """)
    db.commit()
    db.close()

# ─── Gamification ───────────────────────────────────────────

def calc_xp(minutes: int, streak: int = 0) -> int:
    base = int((minutes / 60) * XP_PER_HOUR)
    bonus = 1.0 + max(0, (streak - 3) * 0.10)
    return max(1, int(base * bonus))

def xp_to_level(xp: int) -> int:
    return math.floor(math.sqrt(xp / 100)) + 1

def get_rank(level: int) -> str:
    for lvl, title in [(100,"Legendary Scholar"),(75,"Academic Knight"),
        (50,"Study Elite"),(35,"Focus Master"),(20,"Disciplined Student"),
        (10,"Knowledge Seeker"),(5,"Apprentice Scholar")]:
        if level >= lvl: return title
    return "Novice Learner"

RANK_EMOJIS = {"Novice Learner":"🌱","Apprentice Scholar":"📖","Knowledge Seeker":"⚔️",
    "Disciplined Student":"🛡️","Focus Master":"🔥","Study Elite":"⭐",
    "Academic Knight":"👑","Legendary Scholar":"🐉"}

def xp_progress(xp: int) -> dict:
    level = xp_to_level(xp)
    xp_in = xp - 100 * (level - 1)**2
    xp_needed = 100 * level**2 - 100 * (level - 1)**2
    pct = min(99, int(xp_in/xp_needed*100)) if xp_needed else 0
    return {"level": level, "xp_in_level": xp_in, "xp_needed": xp_needed, "pct": pct}

def fmt_duration(m: int) -> str:
    if m < 60: return f"{m}m"
    h, r = divmod(m, 60)
    return f"{h}h {r}m" if r else f"{h}h"

# ─── Telegram Auth ──────────────────────────────────────────

def verify_telegram_auth(data: dict) -> bool:
    received = data.pop("hash", None)
    if not received: return False
    check = "\n".join(f"{k}={v}" for k,v in sorted(data.items()))
    secret = hashlib.sha256(BOT_TOKEN.encode()).digest()
    return hmac.new(secret, check.encode(), hashlib.sha256).hexdigest() == received

def login_required(f):
    @wraps(f)
    def wrap(*a,**kw):
        if "user_id" not in session:
            return redirect(url_for("login_page"))
        return f(*a,**kw)
    return wrap

# ─── Pages ──────────────────────────────────────────────────

@app.route("/")
def index():
    if "user_id" in session: return redirect(url_for("dashboard"))
    return redirect(url_for("login_page"))

@app.route("/login")
def login_page():
    if "user_id" in session: return redirect(url_for("dashboard"))
    return render_template("login.html", bot_username=BOT_USERNAME)

@app.route("/auth/telegram")
def telegram_auth():
    data = dict(request.args)
    if not verify_telegram_auth(data.copy()):
        return "Authentication failed", 403
    uid = int(data["id"])
    db = get_db()
    if not db.execute("SELECT 1 FROM users WHERE user_id=?",(uid,)).fetchone():
        db.execute("INSERT INTO users (user_id,username,first_name,last_name,photo_url) VALUES (?,?,?,?,?)",
            (uid, data.get("username",""), data.get("first_name",""), data.get("last_name",""), data.get("photo_url","")))
        db.commit()
    session["user_id"] = uid
    session["first_name"] = data.get("first_name","")
    return redirect(url_for("dashboard"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))

@app.route("/dashboard")
@login_required
def dashboard():
    uid = session["user_id"]
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE user_id=?",(uid,)).fetchone()
    if not user: session.clear(); return redirect(url_for("login_page"))

    progress = xp_progress(user["xp"])
    rank = get_rank(progress["level"])
    today = date.today().isoformat()
    today_row = db.execute("SELECT COALESCE(total_minutes,0) as tm, COALESCE(xp_earned,0) as xp FROM daily_stats WHERE user_id=? AND date=?",
        (uid,today)).fetchone()
    today_minutes = today_row["tm"] if today_row else 0
    today_xp = today_row["xp"] if today_row else 0

    # Week data
    ws = (date.today()-timedelta(days=date.today().weekday())).isoformat()
    week = db.execute("SELECT COALESCE(SUM(total_minutes),0), COALESCE(SUM(xp_earned),0) FROM daily_stats WHERE user_id=? AND date>=?",
        (uid,ws)).fetchone()
    week_m, week_xp = week[0], week[1]

    # Recent logs
    recent = db.execute("SELECT * FROM study_logs WHERE user_id=? ORDER BY id DESC LIMIT 8",(uid,)).fetchall()

    # Subject breakdown
    subs = db.execute("SELECT subject, SUM(duration_minutes) as t, COUNT(*) as n FROM study_logs WHERE user_id=? GROUP BY subject ORDER BY t DESC",
        (uid,)).fetchall()

    # Exams
    exams = db.execute("SELECT * FROM exams WHERE user_id=? ORDER BY exam_date",(uid,)).fetchall()

    # Leaderboard (all-time)
    lb = db.execute("""
        SELECT u.user_id, u.first_name, u.xp, u.level, u.current_streak
        FROM users u ORDER BY u.xp DESC LIMIT 10
    """).fetchall()

    # Chart
    day_names = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
    cl, cd_labels = [], []
    for i in range(7):
        d = (date.today()-timedelta(days=date.today().weekday()-i)).isoformat()
        cl.append(day_names[i])
        r = db.execute("SELECT total_minutes FROM daily_stats WHERE user_id=? AND date=?",(uid,d)).fetchone()
        cd_labels.append(r[0] if r else 0)

    return render_template("dashboard.html",
        user=user, rank=rank, rank_emoji=RANK_EMOJIS.get(rank,"📚"),
        progress=progress, today_minutes=today_minutes, today_xp=today_xp,
        week_minutes=week_m, week_xp=week_xp,
        recent=recent, subjects=subs, exams=exams, leaderboard=lb,
        chart_labels=json.dumps(cl), chart_data=json.dumps(cd_labels),
        fmt_duration=fmt_duration, gemini_key_available=bool(GEMINI_KEY),
        datetime=datetime, today=date.today())

# ─── Analytics Page ─────────────────────────────────────────

@app.route("/analytics")
@login_required
def analytics():
    uid = session["user_id"]
    db = get_db()

    # Weekly
    ws = (date.today()-timedelta(days=date.today().weekday())).isoformat()
    week_data = db.execute(
        "SELECT date, total_minutes, xp_earned FROM daily_stats WHERE user_id=? AND date>=? ORDER BY date",
        (uid, ws)).fetchall()
    # Monthly
    ms = date.today().replace(day=1).isoformat()
    month_data = db.execute(
        "SELECT date, total_minutes, xp_earned FROM daily_stats WHERE user_id=? AND date>=? ORDER BY date",
        (uid, ms)).fetchall()

    # Subject hours this week
    week_subs = db.execute("""
        SELECT subject, SUM(duration_minutes) as t
        FROM study_logs WHERE user_id=? AND logged_at>=? GROUP BY subject ORDER BY t DESC
    """, (uid, ws)).fetchall()

    # All subjects all time
    all_subs = db.execute("""
        SELECT subject, SUM(duration_minutes) as t, COUNT(*) as n
        FROM study_logs WHERE user_id=? GROUP BY subject ORDER BY t DESC
    """, (uid,)).fetchall()

    day_names = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
    wk_labels = [day_names[i] for i in range(7)]
    wk_values = []
    for i in range(7):
        d = (date.today()-timedelta(days=date.today().weekday()-i)).isoformat()
        r = [x for x in week_data if x["date"]==d]
        wk_values.append(r[0]["total_minutes"] if r else 0)

    # Monthly labels
    import calendar
    _, days_in_month = calendar.monthrange(date.today().year, date.today().month)
    mo_labels = [str(i+1) for i in range(days_in_month)]
    mo_values = []
    for day_num in range(1, days_in_month+1):
        d = date.today().replace(day=min(day_num, days_in_month)).isoformat()
        r = [x for x in month_data if x["date"]==d]
        mo_values.append(r[0]["total_minutes"] if r else 0)

    # Streak history
    user = db.execute("SELECT current_streak, longest_streak FROM users WHERE user_id=?",(uid,)).fetchone()

    return render_template("analytics.html",
        week_labels=json.dumps(wk_labels), week_values=json.dumps(wk_values),
        month_labels=json.dumps(mo_labels), month_values=json.dumps(mo_values),
        week_subs=week_subs, all_subs=all_subs, week_minutes=sum(v for v in wk_values),
        month_minutes=sum(v for v in mo_values),
        current_streak=user["current_streak"], longest_streak=user["longest_streak"],
        fmt_duration=fmt_duration)

# ─── API: Pomodoro ─────────────────────────────────────────

@app.route("/api/pomodoro/complete", methods=["POST"])
@login_required
def pomodoro_complete():
    uid = session["user_id"]
    data = request.get_json()
    duration = int(data.get("minutes", 25))
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE user_id=?",(uid,)).fetchone()
    today = date.today().isoformat()

    # Streak
    streak = user["current_streak"]
    if user["last_study_date"]:
        ld = date.fromisoformat(user["last_study_date"])
        diff = (date.today()-ld).days
        if diff == 1: streak += 1
        elif diff > 1: streak = 1
    else: streak = 1

    xp_earned = calc_xp(duration, streak)
    longest = max(user["longest_streak"], streak)

    # Log session
    db.execute("INSERT INTO pomodoro_sessions (user_id, started_at, completed_at, duration_type, completed, xp_earned) VALUES (?, datetime('now','-25 minutes'), datetime('now'), 'focus', 1, ?)",
        (uid, xp_earned))
    db.execute("INSERT INTO study_logs (user_id, subject, duration_minutes, xp_earned, note) VALUES (?,?,?,?,?)",
        (uid, "Pomodoro", duration, xp_earned, f"Pomodoro session {duration}min"))

    # Daily stats
    daily = db.execute("SELECT * FROM daily_stats WHERE user_id=? AND date=?",(uid,today)).fetchone()
    subs = json.loads(daily["subjects"]) if daily else {}
    subs["Pomodoro"] = subs.get("Pomodoro", 0) + duration
    db.execute("""INSERT INTO daily_stats (user_id, date, total_minutes, subjects, xp_earned)
        VALUES (?,?,?,?,?) ON CONFLICT(user_id,date) DO UPDATE SET
        total_minutes=total_minutes+?, subjects=?, xp_earned=xp_earned+?""",
        (uid,today,duration,json.dumps(subs),xp_earned,duration,json.dumps(subs),xp_earned))

    # User update
    new_xp = user["xp"] + xp_earned
    new_lvl = xp_to_level(new_xp)
    db.execute("UPDATE users SET xp=?,level=?,current_streak=?,longest_streak=?,last_study_date=?,total_minutes=total_minutes+? WHERE user_id=?",
        (new_xp,new_lvl,streak,longest,today,duration,uid))
    db.commit()

    return jsonify({"ok":True, "xp_earned":xp_earned, "streak":streak, "new_xp":new_xp,
        "level_up":new_lvl>user["level"], "new_level":new_lvl if new_lvl>user["level"] else None,
        "rank":get_rank(new_lvl), "today_minutes":(daily["total_minutes"] if daily else 0)+duration})

# ─── API: Log ───────────────────────────────────────────────

@app.route("/api/log", methods=["POST"])
@login_required
def api_log():
    uid = session["user_id"]
    data = request.get_json()
    subject = data.get("subject","").strip()
    try: minutes = int(data.get("minutes",0))
    except: return jsonify({"error":"Invalid minutes"}),400
    if not subject or minutes<1 or minutes>480: return jsonify({"error":"Invalid input"}),400

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE user_id=?",(uid,)).fetchone()
    today = date.today().isoformat()

    streak = user["current_streak"]
    if user["last_study_date"]:
        ld = date.fromisoformat(user["last_study_date"])
        diff = (date.today()-ld).days
        if diff == 1: streak += 1
        elif diff > 1: streak = 1
    else: streak = 1

    xp = calc_xp(minutes, streak)
    longest = max(user["longest_streak"], streak)

    db.execute("INSERT INTO study_logs (user_id,subject,duration_minutes,xp_earned) VALUES (?,?,?,?)",
        (uid,subject,minutes,xp))

    daily = db.execute("SELECT * FROM daily_stats WHERE user_id=? AND date=?",(uid,today)).fetchone()
    subs = json.loads(daily["subjects"]) if daily else {}
    subs[subject] = subs.get(subject,0)+minutes
    db.execute("""INSERT INTO daily_stats (user_id,date,total_minutes,subjects,xp_earned)
        VALUES (?,?,?,?,?) ON CONFLICT(user_id,date) DO UPDATE SET
        total_minutes=total_minutes+?, subjects=?, xp_earned=xp_earned+?""",
        (uid,today,minutes,json.dumps(subs),xp,minutes,json.dumps(subs),xp))

    new_xp = user["xp"]+xp
    new_lvl = xp_to_level(new_xp)
    db.execute("UPDATE users SET xp=?,level=?,current_streak=?,longest_streak=?,last_study_date=?,total_minutes=total_minutes+? WHERE user_id=?",
        (new_xp,new_lvl,streak,longest,today,minutes,uid))
    db.commit()

    return jsonify({"ok":True,"subject":subject,"minutes":minutes,"xp_earned":xp,
        "streak":streak,"level_up":new_lvl>user["level"],
        "new_level":new_lvl if new_lvl>user["level"] else None,
        "new_rank":get_rank(new_lvl) if new_lvl>user["level"] else None,
        "today_minutes":(daily["total_minutes"] if daily else 0)+minutes})

# ─── API: Exams ─────────────────────────────────────────────

@app.route("/api/exams", methods=["GET"])
@login_required
def api_exams():
    db = get_db()
    exams = db.execute("SELECT * FROM exams WHERE user_id=? ORDER BY exam_date",
        (session["user_id"],)).fetchall()
    return jsonify([dict(e) for e in exams])

@app.route("/api/exams", methods=["POST"])
@login_required
def api_exam_add():
    uid = session["user_id"]
    data = request.get_json()
    subj, name, edate = data.get("subject",""), data.get("name",""), data.get("date","")
    hours = float(data.get("hours", 0))
    if not all([subj,name,edate]): return jsonify({"error":"Missing fields"}),400
    db = get_db()
    db.execute("INSERT INTO exams (user_id,subject,exam_name,exam_date,syllabus_hours) VALUES (?,?,?,?,?)",
        (uid,subj,name,edate,hours))
    db.commit()
    return jsonify({"ok":True, "id": db.execute("SELECT last_insert_rowid()").fetchone()[0]})

@app.route("/api/exams/<int:eid>", methods=["DELETE"])
@login_required
def api_exam_del(eid):
    db = get_db()
    db.execute("DELETE FROM exams WHERE id=? AND user_id=?",(eid,session["user_id"]))
    db.commit()
    return jsonify({"ok":True})

# ─── API: Leaderboard ───────────────────────────────────────

@app.route("/api/leaderboard")
@login_required
def api_leaderboard():
    db = get_db()
    lb = db.execute("""
        SELECT user_id, first_name, xp, level, current_streak, total_minutes
        FROM users ORDER BY xp DESC LIMIT 20
    """).fetchall()
    return jsonify([{
        "user_id": r["user_id"], "name": r["first_name"] or f"User{r['user_id']}",
        "xp": r["xp"], "level": r["level"], "rank": get_rank(r["level"]),
        "streak": r["current_streak"], "hours": round(r["total_minutes"]/60, 1)
    } for r in lb])

# ─── API: AI Coach ──────────────────────────────────────────

@app.route("/api/coach/analyze", methods=["POST"])
@login_required
def coach_analyze():
    uid = session["user_id"]
    db = get_db()

    user = db.execute("SELECT * FROM users WHERE user_id=?",(uid,)).fetchone()
    subs = db.execute("SELECT subject, SUM(duration_minutes) as t FROM study_logs WHERE user_id=? GROUP BY subject ORDER BY t DESC",
        (uid,)).fetchall()
    ws = (date.today()-timedelta(days=date.today().weekday())).isoformat()
    wr = db.execute("SELECT COALESCE(SUM(total_minutes),0) as m FROM daily_stats WHERE user_id=? AND date>=?",(uid,ws)).fetchone()
    week = wr["m"] if wr else 0
    tr = db.execute("SELECT COALESCE(total_minutes,0) as m FROM daily_stats WHERE user_id=? AND date=?",(uid,date.today().isoformat())).fetchone()
    today_m = tr["m"] if tr else 0
    exams = db.execute("SELECT * FROM exams WHERE user_id=? ORDER BY exam_date",(uid,)).fetchall()

    total_m = user["total_minutes"]

    # Try Gemini first, fall back to rule-based
    if GEMINI_KEY:
        try:
            subj_str = ", ".join(f"{s['subject']} {fmt_duration(s['t'])}" for s in subs[:5]) if subs else "none"
            exam_str = ", ".join(f"{e['exam_name']} ({e['subject']}) on {e['exam_date']}, {e['syllabus_hours']}h syllabus" for e in exams[:5]) if exams else "none"
            prompt = (
                f"You are an exam study planner. Student: {user['first_name'] or 'Student'}, "
                f"Level {xp_to_level(user['xp'])}, {user['current_streak']} day streak. "
                f"Total studied: {fmt_duration(total_m)}. This week: {fmt_duration(week)}. Today: {fmt_duration(today_m)}. "
                f"Subjects: {subj_str}. Exams: {exam_str}. "
                f"Create a realistic daily study plan for each exam. "
                f"For each exam calculate hours/day needed (syllabus/days_left). "
                f"Suggest which subjects to prioritize. Give specific daily targets. "
                f"Keep it practical and encouraging. Use bullet points."
            )
            import requests
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}",
                json={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.8,"maxOutputTokens":500}},
                timeout=20
            )
            ai_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            if ai_text and len(ai_text) > 10:
                return jsonify({"ok":True, "analysis": "🤖 *AI Exam Study Plan*\\n\\n" + ai_text})
        except:
            pass

    # Rule-based exam study plan
    analysis = f"📋 *Exam Study Plan*\\n\\n👋 {user['first_name'] or 'Student'}!\\n\\n"
    analysis += f"⏱️ {fmt_duration(total_m)} total | 🔥 {user['current_streak']}d streak\\n"
    analysis += f"🏅 {get_rank(xp_to_level(user['xp']))} | Wk: {fmt_duration(week)} | Today: {fmt_duration(today_m)}\\n\\n"

    if exams:
        analysis += "*── Exam Prep Plan ──*\\n\\n"
        for e in exams:
            try: d = (datetime.strptime(e["exam_date"],"%Y-%m-%d").date()-date.today()).days
            except: d = "?"
            if isinstance(d,int) and d>0:
                hr_day = round(e["syllabus_hours"]/d, 1) if e["syllabus_hours"] else "?"
                urgency = "🔴" if d<=7 else "🟠" if d<=21 else "🟢"
                analysis += f"{urgency} *{e['exam_name']}* ({e['subject']})\\n"
                analysis += f"   📅 {d} days left | 📖 {e['syllabus_hours']}h syllabus\\n"
                if hr_day != "?":
                    analysis += f"   🎯 Target: *{hr_day}h/day* needed\\n"
                    # Check if they've been studying this subject
                    sub_total = sum(s["t"] for s in subs if s["subject"].lower()==e["subject"].lower())
                    if sub_total>0:
                        analysis += f"   ✅ Studied {fmt_duration(sub_total)} so far\\n"
                    else:
                        analysis += f"   ⚠️ No study logged for {e['subject']} yet!\\n"
                analysis += "\\n"
            else:
                analysis += f"⚠️ *{e['exam_name']}* is today/past!\\n\\n"

        # Overall plan
        analysis += "*── Daily Schedule ──*\\n\\n"
        total_hpd = 0
        for e in exams:
            try: d = (datetime.strptime(e["exam_date"],"%Y-%m-%d").date()-date.today()).days
            except: d = 0
            if isinstance(d,int) and d>0 and e["syllabus_hours"]>0:
                total_hpd += e["syllabus_hours"]/d

        analysis += f"📊 Combined target: *~{round(total_hpd,1)}h/day*\\n\\n"

        if today_m >= 30: analysis += "✅ You studied today — on track!\\n"
        else: analysis += "⚠️ You haven't studied 30+ min today. Start now!\\n"

        analysis += "\\n*Priority order:*\\n"
        # Sort exams by urgency (closest first)
        urgent = sorted(exams, key=lambda e: e["exam_date"])
        for i, e in enumerate(urgent[:5], 1):
            try: d = (datetime.strptime(e["exam_date"],"%Y-%m-%d").date()-date.today()).days
            except: d = "?"
            icon = "1️⃣" if i==1 else "2️⃣" if i==2 else "3️⃣" if i==3 else "•"
            analysis += f"{icon} {e['exam_name']} ({e['subject']}) — {d} days left\\n"
    else:
        analysis += "📅 *No exams added!*\\n\\nAdd exams to get a personalized study plan.\\nUse: `/addexam OOP Final 2026-07-15 40`\\n\\n"

    analysis += "\\n💪 *Tip:* Study your closest exam first, but spend at least some time on all subjects daily."

    return jsonify({"ok": True, "analysis": analysis})


# ─── Bot Login ──────────────────────────────────────────────

@app.route("/auth/bot/<token>")
def bot_login(token):
    """One-time login via bot-generated token."""
    db = get_db()
    row = db.execute("SELECT * FROM login_tokens WHERE token=? AND used=0", (token,)).fetchone()
    if not row:
        return "<h2>Invalid or expired login link.</h2>", 403

    db.execute("UPDATE login_tokens SET used=1 WHERE token=?", (token,))
    user = db.execute("SELECT * FROM users WHERE user_id=?", (row["user_id"],)).fetchone()
    db.commit()

    if user:
        session["user_id"] = user["user_id"]
        session["first_name"] = user["first_name"] or ""
        return redirect(url_for("dashboard"))

    # Create user if somehow missing
    db.execute("INSERT OR IGNORE INTO users (user_id, first_name) VALUES (?, 'Student')", (row["user_id"],))
    db.commit()
    session["user_id"] = row["user_id"]
    return redirect(url_for("dashboard"))


# ─── API: Notification Check (for n8n) ───────────────────

@app.route("/api/notify/check")
def notify_check():
    """Called by n8n cron to find users who haven't studied today."""
    db = get_db()
    today = date.today().isoformat()
    at_risk = db.execute("""
        SELECT u.user_id, u.first_name, u.current_streak,
               COALESCE(d.total_minutes, 0) as today_mins
        FROM users u
        LEFT JOIN daily_stats d ON u.user_id = d.user_id AND d.date = ?
        WHERE u.current_streak >= 3
    """, (today,)).fetchall()
    need_reminder = []
    for r in at_risk:
        if r["today_mins"] < 30:
            need_reminder.append({
                "user_id": r["user_id"],
                "name": r["first_name"] or "Student",
                "streak": r["current_streak"],
                "today_mins": r["today_mins"]
            })
    return jsonify({"at_risk": need_reminder, "count": len(need_reminder)})

# ─── Main ───────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5052))
    app.run(host="127.0.0.1", port=port, debug=False)
