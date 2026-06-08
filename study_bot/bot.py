#!/usr/bin/env python3
"""
🤖 KirithoStudybot — Smart Study Tracker
Inline keyboards, pomodoro timer, exam countdown, AI study plan
"""

import os, re, sqlite3, json, math, secrets, asyncio
from datetime import datetime, date, timedelta
from collections import defaultdict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

TOKEN = os.environ.get("STUDY_BOT_TOKEN", "") or os.environ.get("BOT_TOKEN", "")
DB_PATH = os.environ.get("STUDY_DB_PATH", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "study.db"))
XP_PER_HOUR = 100

# ── DB Helpers ─────────────────────────────────────────────

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def ensure_user(uid, uname, fname):
    db = get_db()
    u = db.execute("SELECT * FROM users WHERE user_id=?",(uid,)).fetchone()
    if not u:
        db.execute("INSERT INTO users (user_id,username,first_name) VALUES (?,?,?)",(uid,uname or "?",fname or "?"))
        db.commit()
        u = db.execute("SELECT * FROM users WHERE user_id=?",(uid,)).fetchone()
    db.close()
    return u

# ── Gamification ───────────────────────────────────────────

def calc_xp(minutes, streak=0):
    base = int((minutes/60)*XP_PER_HOUR)
    bonus = 1.0 + max(0,(streak-3)*0.10)
    return max(1,int(base*bonus))

def xp_to_level(xp): return int(math.sqrt(xp/100))+1

def get_rank(lvl):
    for l,t in [(100,"Legendary Scholar"),(75,"Academic Knight"),(50,"Study Elite"),
        (35,"Focus Master"),(20,"Disciplined Student"),(10,"Knowledge Seeker"),
        (5,"Apprentice Scholar")]:
        if lvl>=l: return t
    return "Novice Learner"

def fmt_duration(m):
    if m<60: return f"{m}m"
    h,r=divmod(m,60)
    return f"{h}h{r}m" if r else f"{h}h"

def xp_progress(xp):
    lvl=xp_to_level(xp)
    start=100*(lvl-1)**2
    end=100*lvl**2
    pct=min(99,int((xp-start)/(end-start)*100)) if end>start else 0
    return lvl, xp-start, end-start, pct

# ── Streak Logic ───────────────────────────────────────────

def update_streak_db(uid, today):
    db = get_db()
    u = db.execute("SELECT * FROM users WHERE user_id=?",(uid,)).fetchone()
    streak = u["current_streak"]
    if u["last_study_date"]:
        diff = (date.today()-date.fromisoformat(u["last_study_date"])).days
        if diff==1: streak+=1
        elif diff>1: streak=1
    else: streak=1
    db.close()
    return streak

# ── Parse Log ──────────────────────────────────────────────

def parse_log(text):
    text = text.replace("/log","",1).strip()
    m = re.match(r"(.+?)\s+(\d+\.?\d*)\s*(h|m|hr|hrs|hour|hours|min|mins|minute|minutes)?", text, re.I)
    if not m: return None,None
    subj = m.group(1).strip()
    val = float(m.group(2))
    unit = (m.group(3) or "m").lower()
    minutes = int(val*60) if unit.startswith("h") else int(val)
    return subj, minutes

# ── Main Menu Keyboard ─────────────────────────────────────

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Log Study", callback_data="log"),
         InlineKeyboardButton("🍅 Pomodoro", callback_data="pomo")],
        [InlineKeyboardButton("📊 Today", callback_data="today"),
         InlineKeyboardButton("📈 Weekly", callback_data="week")],
        [InlineKeyboardButton("🎮 Stats", callback_data="stats"),
         InlineKeyboardButton("📚 Subjects", callback_data="subjects")],
        [InlineKeyboardButton("📅 Exams", callback_data="exams"),
         InlineKeyboardButton("🤖 Study Plan", callback_data="plan")],
        [InlineKeyboardButton("🔐 Login Dashboard", callback_data="login")],
    ])

# ── Commands ───────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db = ensure_user(user.id, user.username, user.first_name)

    # Deep link: /start login
    if ctx.args and ctx.args[0]=="login":
        t = secrets.token_urlsafe(16)
        db2 = get_db()
        db2.execute("INSERT OR REPLACE INTO login_tokens (token,user_id,used) VALUES (?,?,0)",(t,user.id))
        db2.commit(); db2.close()
        await update.message.reply_text(
            f"🔐 *One-time Login*\n\n[Click to open Dashboard](https://kiritho.duckdns.org/study/auth/bot/{t})\n\n⏰ Link expires after use.",
            parse_mode="Markdown", disable_web_page_preview=True)
        return

    rank = get_rank(db["level"])
    lvl,_,_,_ = xp_progress(db["xp"])
    await update.message.reply_text(
        f"👋 *Hey {user.first_name}!*\n\n"
        f"🏅 {rank} · Lv.{lvl} · 🔥 {db['current_streak']} day streak\n"
        f"⏱️ {fmt_duration(db['total_minutes'])} total studied\n\n"
        f"👇 *Use the menu or type /log*",
        parse_mode="Markdown", reply_markup=main_menu())

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*📋 Commands:*\n\n"
        "📝 `/log OOP 2h` — Log study\n"
        "🍅 `/pomo` — 25min timer\n"
        "📊 `/today` — Today's stats\n"
        "📈 `/week` — Weekly report\n"
        "🎮 `/stats` — XP & level\n"
        "📚 `/subjects` — Breakdown\n"
        "📅 `/exams` — Exam list\n"
        "➕ `/addexam` — Add exam\n"
        "🤖 `/plan` — AI study plan\n"
        "↩️ `/undo` — Remove last",
        parse_mode="Markdown", reply_markup=main_menu())

# ── Log ────────────────────────────────────────────────────

async def log_study(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()
    subj, mins = parse_log(text)
    if not subj:
        await update.message.reply_text(
            "❓ *How to log:*\n`/log OOP 2h` or `/log DSA 45m`",
            parse_mode="Markdown")
        return
    result = do_log(user.id, user.username, user.first_name, subj, mins)
    await update.message.reply_text(result, parse_mode="Markdown")

def do_log(uid, uname, fname, subj, mins):
    db = get_db()
    ensure_user(uid, uname, fname)
    today = date.today().isoformat()

    streak = update_streak_db(uid, today)
    xp = calc_xp(mins, streak)
    u = db.execute("SELECT * FROM users WHERE user_id=?",(uid,)).fetchone()
    ls = max(u["longest_streak"], streak)
    new_xp = u["xp"] + xp
    new_lvl = xp_to_level(new_xp)

    db.execute("INSERT INTO study_logs (user_id,subject,duration_minutes,xp_earned) VALUES (?,?,?,?)",
        (uid,subj,mins,xp))

    # Daily stats
    dr = db.execute("SELECT * FROM daily_stats WHERE user_id=? AND date=?",(uid,today)).fetchone()
    subs = json.loads(dr["subjects"]) if dr else {}
    subs[subj] = subs.get(subj,0)+mins
    db.execute("""INSERT INTO daily_stats (user_id,date,total_minutes,subjects,xp_earned)
        VALUES (?,?,?,?,?) ON CONFLICT(user_id,date) DO UPDATE SET
        total_minutes=total_minutes+?, subjects=?, xp_earned=xp_earned+?""",
        (uid,today,mins,json.dumps(subs),xp,mins,json.dumps(subs),xp))

    db.execute("UPDATE users SET xp=?,level=?,current_streak=?,longest_streak=?,last_study_date=?,total_minutes=total_minutes+? WHERE user_id=?",
        (new_xp,new_lvl,streak,ls,today,mins,uid))
    db.commit(); db.close()

    msg = f"✅ *Logged {fmt_duration(mins)} of {subj}*\n\n+{xp} XP · 🔥 {streak} day streak"
    if new_lvl > u["level"]:
        msg += f"\n\n🎉 *LEVEL UP!* Lv.{new_lvl} — {get_rank(new_lvl)}!"
    return msg

# ── Today / Week / Stats ───────────────────────────────────

async def today_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    db = get_db()
    today = date.today().isoformat()
    dr = db.execute("SELECT * FROM daily_stats WHERE user_id=? AND date=?",(uid,today)).fetchone()
    logs = db.execute("SELECT * FROM study_logs WHERE user_id=? AND date(logged_at)=? ORDER BY id DESC",(uid,today)).fetchall()
    db.close()
    tm = dr["total_minutes"] if dr else 0
    xp = dr["xp_earned"] if dr else 0
    msg = f"📊 *Today's Study*\n\n⏱️ {fmt_duration(tm)} · ⭐ {xp} XP\n"
    if logs:
        msg += "\n📝 *Sessions:*\n"
        for l in logs:
            msg += f"  • {l['subject']}: {fmt_duration(l['duration_minutes'])}\n"
    else:
        msg += "\nNo study logged yet today!"
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=main_menu())

async def week_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    db = get_db()
    ws = (date.today()-timedelta(days=date.today().weekday())).isoformat()
    data = db.execute("SELECT * FROM daily_stats WHERE user_id=? AND date>=? ORDER BY date",(uid,ws)).fetchall()
    db.close()
    total = sum(r["total_minutes"] for r in data)
    xp = sum(r["xp_earned"] for r in data)
    days = [r for r in data if r["total_minutes"]>0]
    msg = f"📈 *Weekly Report*\n\n⏱️ {fmt_duration(total)} · ⭐ {xp} XP\n📅 {len(days)}/7 days studied\n"
    if days:
        msg += "\n*Daily breakdown:*\n"
        for r in days:
            dname = date.fromisoformat(r["date"]).strftime("%a")
            msg += f"  {dname}: {fmt_duration(r['total_minutes'])} ({r['xp_earned']} XP)\n"
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=main_menu())

async def stats_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    db = get_db()
    u = db.execute("SELECT * FROM users WHERE user_id=?",(uid,)).fetchone()
    db.close()
    lvl, cur, nxt, pct = xp_progress(u["xp"])
    bar = "█"*int(pct/5)+"░"*(20-int(pct/5))
    await update.message.reply_text(
        f"🎮 *Stats*\n\n🏅 {get_rank(lvl)} · Lv.{lvl}\n"
        f"⭐ {u['xp']} XP ({cur}/{nxt})\n{bar} {pct}%\n\n"
        f"🔥 Streak: {u['current_streak']} days (best: {u['longest_streak']})\n"
        f"⏱️ Total: {fmt_duration(u['total_minutes'])}",
        parse_mode="Markdown", reply_markup=main_menu())

async def subjects_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    db = get_db()
    subs = db.execute("SELECT subject, SUM(duration_minutes) as t, COUNT(*) as n FROM study_logs WHERE user_id=? GROUP BY subject ORDER BY t DESC",(uid,)).fetchall()
    db.close()
    if not subs:
        await update.message.reply_text("📚 No subjects yet! Use /log to start.", reply_markup=main_menu())
        return
    msg = "📚 *Subject Breakdown*\n\n"
    for s in subs:
        msg += f"  {s['subject']}: {fmt_duration(s['t'])} ({s['n']} sessions)\n"
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=main_menu())

# ── Pomodoro ───────────────────────────────────────────────

async def pomo_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🍅 25min Focus", callback_data="pomo_start_25"),
         InlineKeyboardButton("☕ 5min Break", callback_data="pomo_start_5")],
        [InlineKeyboardButton("📚 50min Deep Focus", callback_data="pomo_start_50")],
        [InlineKeyboardButton("« Back", callback_data="menu")],
    ])
    await update.message.reply_text(
        "🍅 *Pomodoro Timer*\n\nPick a session:",
        parse_mode="Markdown", reply_markup=keyboard)

# ── Exams ──────────────────────────────────────────────────

async def exams_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    db = get_db()
    exams = db.execute("SELECT * FROM exams WHERE user_id=? ORDER BY exam_date",(uid,)).fetchall()
    db.close()
    if not exams:
        await update.message.reply_text(
            "📅 No exams added yet!\n\nUse: `/addexam OOP Final 2026-07-15`\nOr add syllabus hours:\n`/addexam OOP Final 2026-07-15 40`",
            parse_mode="Markdown", reply_markup=main_menu())
        return
    msg = "📅 *Exam Countdown*\n\n"
    for e in exams:
        try:
            d = (datetime.strptime(e["exam_date"],"%Y-%m-%d").date()-date.today()).days
        except: d="?"
        icon = "🔴" if isinstance(d,int) and d<=7 else "🟠" if isinstance(d,int) and d<=21 else "🟢"
        msg += f"{icon} *{e['exam_name']}* ({e['subject']})\n"
        msg += f"   {d} days left · {e['syllabus_hours']}h syllabus\n\n"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Exam", callback_data="addexam")],
        [InlineKeyboardButton("« Back", callback_data="menu")],
    ])
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)

async def addexam_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.replace("/addexam","",1).strip()
    parts = text.split()
    if len(parts)<3:
        await update.message.reply_text(
            "❓ *Usage:*\n`/addexam OOP Final 2026-07-15 40`\n\nSubject, exam name, date (YYYY-MM-DD), optional syllabus hours.",
            parse_mode="Markdown")
        return
    subj, name, edate = parts[0], parts[1], parts[2]
    hours = float(parts[3]) if len(parts)>3 else 0
    db = get_db()
    try:
        datetime.strptime(edate,"%Y-%m-%d")
    except:
        await update.message.reply_text("❌ Invalid date! Use YYYY-MM-DD format.", parse_mode="Markdown")
        return
    db.execute("INSERT INTO exams (user_id,subject,exam_name,exam_date,syllabus_hours) VALUES (?,?,?,?,?)",
        (uid,subj,name,edate,hours))
    db.commit(); db.close()
    try:
        d = (datetime.strptime(edate,"%Y-%m-%d").date()-date.today()).days
    except: d="?"
    await update.message.reply_text(
        f"✅ *Exam added!*\n\n📚 {name} ({subj})\n📅 {edate} · {d} days left\n📖 {hours}h syllabus",
        parse_mode="Markdown", reply_markup=main_menu())

# ── AI Study Plan ──────────────────────────────────────────

async def plan_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    db = get_db()
    u = db.execute("SELECT * FROM users WHERE user_id=?",(uid,)).fetchone()
    subs = db.execute("SELECT subject, SUM(duration_minutes) as t FROM study_logs WHERE user_id=? GROUP BY subject ORDER BY t DESC",(uid,)).fetchall()
    exams = db.execute("SELECT * FROM exams WHERE user_id=? ORDER BY exam_date",(uid,)).fetchall()
    db.close()

    if not subs and not exams:
        await update.message.reply_text(
            "🤖 *Study Plan*\n\nNot enough data yet! Log some study time and add exams first.",
            parse_mode="Markdown")
        return

    await update.message.reply_text("🤖 *Analyzing your progress...*", parse_mode="Markdown")

    # Build analysis (rule-based + optional Gemini)
    total = u["total_minutes"]
    analysis = f"📊 *AI Study Coach*\n\n"
    analysis += f"⏱️ Total: {fmt_duration(total)} | 🔥 {u['current_streak']} day streak\n"
    analysis += f"🏅 {get_rank(xp_to_level(u['xp']))} · Lv.{xp_to_level(u['xp'])}\n\n"

    if subs:
        analysis += "*Subject Split:*\n"
        for s in subs[:5]:
            pct = round(s["t"]/total*100,1) if total else 0
            analysis += f"  • {s['subject']}: {fmt_duration(s['t'])} ({pct}%)\n"

    if exams:
        analysis += "\n*📅 Exam Prep:*\n"
        for e in exams:
            try:
                days_left = (datetime.strptime(e["exam_date"],"%Y-%m-%d").date()-date.today()).days
            except: days_left="?"
            if isinstance(days_left,int) and e["syllabus_hours"]>0 and days_left>0:
                daily = round(e["syllabus_hours"]/days_left,1)
                analysis += f"  • {e['exam_name']}: {days_left}d left → ~{daily}h/day needed\n"
            else:
                analysis += f"  • {e['exam_name']}: {days_left} days left\n"

    # Recommendations
    analysis += "\n*💡 Recommendations:*\n"
    if today_m := u.get("last_study_date",""):
        if today_m == date.today().isoformat():
            analysis += "✅ You studied today — keep it up!\n"

    if subs and len(subs)>=2:
        top = subs[0]["t"]
        bottom = subs[-1]["t"]
        if top > bottom*3 and total>0:
            analysis += f"⚠️ Heavy focus on {subs[0]['subject']}. Balance with {subs[-1]['subject']}.\n"

    if u["current_streak"]>0:
        analysis += f"🔥 {u['current_streak']} day streak — don't break it!\n"
    else:
        analysis += "🌱 Start a streak — study today!\n"

    analysis += f"\n🎯 *Daily Target:* {max(30,min(180,int(total/7)))} minutes"

    await update.message.reply_text(analysis, parse_mode="Markdown", reply_markup=main_menu())

# ── Undo ───────────────────────────────────────────────────

async def undo_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    db = get_db()
    last = db.execute("SELECT * FROM study_logs WHERE user_id=? ORDER BY id DESC LIMIT 1",(uid,)).fetchone()
    if not last:
        await update.message.reply_text("Nothing to undo!", reply_markup=main_menu()); db.close(); return
    db.execute("DELETE FROM study_logs WHERE id=?",(last["id"],))
    db.execute("UPDATE users SET xp=xp-?, total_minutes=total_minutes-? WHERE user_id=?",
        (last["xp_earned"],last["duration_minutes"],uid))
    db.commit(); db.close()
    await update.message.reply_text(
        f"↩️ Undid {fmt_duration(last['duration_minutes'])} of {last['subject']} (-{last['xp_earned']} XP)",
        reply_markup=main_menu())

# ── Callback Handler ───────────────────────────────────────

async def button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    uname = query.from_user.username
    fname = query.from_user.first_name
    data = query.data

    if data == "menu":
        await query.edit_message_text("📋 *Main Menu*", parse_mode="Markdown", reply_markup=main_menu())
    elif data == "today":
        await today_cmd(query, ctx)
    elif data == "week":
        await week_cmd(query, ctx)
    elif data == "stats":
        await stats_cmd(query, ctx)
    elif data == "subjects":
        await subjects_cmd(query, ctx)
    elif data == "exams":
        await exams_cmd(query, ctx)
    elif data == "plan":
        await plan_cmd(query, ctx)
    elif data == "log":
        await query.edit_message_text(
            "📝 *Log Study*\n\nReply with:\n`OOP 2h` or `/log DSA 45m`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data="menu")]]))
    elif data.startswith("pomo_start_"):
        mins = int(data.split("_")[2])
        await query.edit_message_text(
            f"🍅 *{mins}min Focus Session Started!*\n\n⏰ I'll remind you at {mins-10} min and {mins-5} min.\nFocus now! 🔥",
            parse_mode="Markdown")
        # Reminders
        for delay in [mins-10, mins-5]:
            if delay > 0:
                await asyncio.sleep(delay*60)
                try:
                    await query.message.reply_text(f"⏰ *{mins-delay} min left!* Keep going! 🔥", parse_mode="Markdown")
                except: pass
        # Complete
        result = do_log(uid, uname, fname, "Pomodoro", mins)
        try:
            await query.message.reply_text(f"🍅 *Session complete!*\n{result}", parse_mode="Markdown")
        except: pass
    elif data == "login":
        t = secrets.token_urlsafe(16)
        db = get_db()
        db.execute("INSERT OR REPLACE INTO login_tokens (token,user_id,used) VALUES (?,?,0)",(t,uid))
        db.commit(); db.close()
        await query.edit_message_text(
            f"🔐 *Login Link*\n\n[Open Dashboard](https://kiritho.duckdns.org/study/auth/bot/{t})",
            parse_mode="Markdown", disable_web_page_preview=True)
    elif data == "addexam":
        await query.edit_message_text(
            "📅 *Add Exam*\n\nReply:\n`/addexam OOP Final 2026-07-15 40`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data="menu")]]))

# ── Message handler (for log replies) ──────────────────────

async def handle_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.startswith("/"): return  # commands handled separately
    # Try to parse as log
    subj, mins = parse_log(text)
    if subj:
        result = do_log(update.effective_user.id, update.effective_user.username, update.effective_user.first_name, subj, mins)
        await update.message.reply_text(result, parse_mode="Markdown", reply_markup=main_menu())

# ── Main ──────────────────────────────────────────────────

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("log", log_study))
    app.add_handler(CommandHandler("today", today_cmd))
    app.add_handler(CommandHandler("week", week_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("subjects", subjects_cmd))
    app.add_handler(CommandHandler("pomo", pomo_cmd))
    app.add_handler(CommandHandler("exams", exams_cmd))
    app.add_handler(CommandHandler("addexam", addexam_cmd))
    app.add_handler(CommandHandler("plan", plan_cmd))
    app.add_handler(CommandHandler("undo", undo_cmd))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    print("🤖 Bot started with inline keyboards + commands")
    app.run_polling()

if __name__ == "__main__":
    main()
