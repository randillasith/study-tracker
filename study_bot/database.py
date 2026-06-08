# Study Tracker Bot — Database Schema
# ==========================================

import sqlite3
import os

DB_PATH = os.environ.get("STUDY_DB_PATH", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "study.db"))


def init_db():
    db = sqlite3.connect(DB_PATH)
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
    """)
    db.commit()
    db.close()


if __name__ == "__main__":
    init_db()
    print("✅ Database initialized at", DB_PATH)
