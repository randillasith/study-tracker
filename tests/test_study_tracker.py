import os
import sqlite3
import sys
from pathlib import Path
from datetime import date, datetime, timedelta
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "study.db"
    monkeypatch.setenv("STUDY_DB_PATH", str(db_path))
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("STUDY_NOTIFY_KEY", "notify-secret")
    monkeypatch.setenv("STUDY_BOT_TOKEN", "123:test-token")

    import importlib
    import study_bot.database as database
    import study_bot.bot as bot
    import study_web.app as web

    importlib.reload(database)
    importlib.reload(bot)
    importlib.reload(web)
    database.init_db()
    web.init_db()
    yield db_path, bot, web


def row_count(db_path, table):
    with sqlite3.connect(db_path) as db:
        return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def get_user(db_path, uid=1):
    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        return db.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()


def test_bot_rejects_unrealistic_duration(temp_db):
    db_path, bot, _ = temp_db
    msg = bot.do_log(1, "randil", "Randil", "DSA", 999 * 60)
    assert "Invalid" in msg
    assert row_count(db_path, "study_logs") == 0


def test_bot_plan_uses_sqlite_row_without_get_crash(temp_db):
    db_path, bot, _ = temp_db
    bot.do_log(1, "randil", "Randil", "OOP", 60)
    plan = bot.build_study_plan_text(1)
    assert "Study" in plan
    assert "OOP" in plan


def test_undo_restores_daily_stats_and_user_totals(temp_db):
    db_path, bot, _ = temp_db
    bot.do_log(1, "randil", "Randil", "OOP", 60)
    message = bot.undo_last_log(1)
    assert "Undid" in message
    user = get_user(db_path)
    assert user["xp"] == 0
    assert user["total_minutes"] == 0
    with sqlite3.connect(db_path) as db:
        daily = db.execute("SELECT total_minutes, xp_earned, subjects FROM daily_stats WHERE user_id=? AND date=?", (1, date.today().isoformat())).fetchone()
    assert daily is None or (daily[0] == 0 and daily[1] == 0)


def test_notify_check_requires_api_key(temp_db):
    _, _, web = temp_db
    client = web.app.test_client()
    assert client.get("/api/notify/check").status_code == 403
    assert client.get("/api/notify/check", headers={"X-Study-Notify-Key": "notify-secret"}).status_code == 200


def test_bot_login_token_expiry(temp_db):
    db_path, _, web = temp_db
    old = (datetime.utcnow() - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(db_path) as db:
        db.execute("INSERT INTO users (user_id, first_name) VALUES (?, ?)", (1, "Randil"))
        db.execute("INSERT INTO login_tokens (token,user_id,created_at,used) VALUES (?,?,?,0)", ("oldtoken", 1, old))
        db.commit()
    client = web.app.test_client()
    assert client.get("/auth/bot/oldtoken").status_code == 403


def test_web_pomodoro_break_does_not_award_xp(temp_db):
    db_path, _, web = temp_db
    with sqlite3.connect(db_path) as db:
        db.execute("INSERT INTO users (user_id, first_name) VALUES (?, ?)", (1, "Randil"))
        db.commit()
    client = web.app.test_client()
    with client.session_transaction() as s:
        s["user_id"] = 1
        s["first_name"] = "Randil"
    r = client.post("/api/pomodoro/complete", json={"minutes": 5, "type": "break"})
    assert r.status_code == 200
    assert r.json["xp_earned"] == 0
    assert row_count(db_path, "study_logs") == 0


def test_mission_and_exam_progress_have_actionable_targets(temp_db):
    _, bot, web = temp_db
    bot.do_log(1, "randil", "Randil", "OOP", 30)
    with sqlite3.connect(bot.DB_PATH) as db:
        db.execute(
            "INSERT INTO exams (user_id,subject,exam_name,exam_date,syllabus_hours) VALUES (?,?,?,?,?)",
            (1, "DSA", "Final", (date.today() + timedelta(days=10)).isoformat(), 20),
        )
        db.commit()
    with web.app.app_context():
        mission = web.build_study_mission(1)
        exams = web.get_exam_progress(1)
    assert mission["target_minutes"] >= 30
    assert mission["tasks"]
    assert any("DSA" in t["subject"] for t in mission["tasks"])
    assert exams[0]["remaining_hours"] == 20
    assert exams[0]["hours_per_day"] == 2.0
