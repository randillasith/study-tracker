# Study Tracker Bot — Database Schema
# ==========================================

import sqlite3
import os

DB_PATH = os.environ.get("STUDY_DB_PATH", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "study.db"))


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            current_streak INTEGER DEFAULT 0,
            longest_streak INTEGER DEFAULT 0,
            last_study_date TEXT,
            total_minutes INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            reminder_enabled INTEGER DEFAULT 1,
            timezone TEXT DEFAULT 'Asia/Colombo'
        );

        CREATE TABLE IF NOT EXISTS study_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            subject TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL,
            logged_at TEXT DEFAULT (datetime('now')),
            note TEXT,
            xp_earned INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );

        CREATE TABLE IF NOT EXISTS daily_stats (
            user_id INTEGER,
            date TEXT,
            total_minutes INTEGER DEFAULT 0,
            subjects TEXT DEFAULT '{}',
            xp_earned INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, date),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );

        CREATE INDEX IF NOT EXISTS idx_logs_user_date
            ON study_logs(user_id, logged_at);

        CREATE INDEX IF NOT EXISTS idx_logs_subject
            ON study_logs(user_id, subject);

        CREATE TABLE IF NOT EXISTS login_tokens (
            token TEXT PRIMARY KEY,
            user_id INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            used INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS exams (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
            subject TEXT NOT NULL, exam_name TEXT NOT NULL,
            exam_date TEXT NOT NULL, syllabus_hours REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS pomodoro_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
            started_at TEXT, completed_at TEXT,
            duration_type TEXT DEFAULT 'focus', completed INTEGER DEFAULT 0,
            xp_earned INTEGER DEFAULT 0
        );
    """)
    db.commit()
    db.close()


if __name__ == "__main__":
    init_db()
    print("✅ Database initialized at", DB_PATH)
