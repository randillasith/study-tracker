# Study Tracker — Telegram Bot + Web Dashboard

A personal study tracking system built for SLIIT study workflows. It combines a Telegram bot with a modern Flask web dashboard so students can log study time, track XP/levels, manage exam countdowns, and view analytics.

> Portfolio Project — Randil
> Focus: Python, Flask, Telegram Bot, SQLite, VPS Deployment

---

## Features

### Telegram Bot

- `/log OOP 2h` or `/log DSA 45m` study logging
- Inline menu for quick actions
- XP, levels, ranks, and streak tracking
- Daily and weekly reports
- Subject breakdown
- Pomodoro timer reminders
- Exam countdowns
- Bot-generated one-time dashboard login links

### Web Dashboard

- Telegram Login Widget authentication
- Bot-login deep link support
- Dashboard cards for XP, level, streaks, today, and weekly study time
- Pomodoro timer with XP logging
- Quick manual study logging
- Exam countdown management
- Leaderboard
- Analytics page with weekly/monthly charts
- AI Coach endpoint using Gemini when configured

### Shared Data

- Bot and web dashboard use the same SQLite database
- Tables for users, study logs, daily stats, exams, Pomodoro sessions, and login tokens

---

## Tech Stack

- Python 3.11+
- Flask
- python-telegram-bot
- SQLite
- Jinja2 templates
- Chart.js
- nginx reverse proxy
- systemd services
- Optional: Gemini API for AI Coach

---

## Project Structure

```text
study-tracker/
├── study_bot/
│   ├── bot.py
│   ├── database.py
│   └── gamification.py
├── study_web/
│   ├── app.py
│   └── templates/
├── deploy/
│   ├── nginx-study-location.conf
│   ├── study-bot.service.example
│   └── study-web.service.example
├── scripts/
│   └── init_db.py
├── requirements.txt
├── .env.example
└── README.md
```

---

## Getting Started

```bash
git clone <repo-url>
cd study-tracker
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

```env
STUDY_BOT_TOKEN=your_bot_token
SECRET_KEY=your_random_secret
GEMINI_API_KEY=optional
STUDY_DB_PATH=/home/ubuntu/study-tracker/data/study.db
PORT=5052
```

Initialize database:

```bash
mkdir -p data
python -m scripts.init_db
```

Run web dashboard locally:

```bash
flask --app study_web.app run --host 127.0.0.1 --port 5052
```

Run Telegram bot:

```bash
python -m study_bot.bot
```

---

## VPS Deployment

Example systemd and nginx files are inside `deploy/`.

Recommended production layout:

- Web app: Gunicorn on `127.0.0.1:5052`
- nginx public path: `https://yourdomain.com/study/`
- Telegram bot: separate systemd service
- DB: shared SQLite file in `data/study.db`

Install service templates:

```bash
sudo cp deploy/study-web.service.example /etc/systemd/system/study-web.service
sudo cp deploy/study-bot.service.example /etc/systemd/system/study-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now study-web study-bot
```

Add nginx location from:

```text
deploy/nginx-study-location.conf
```

Then reload nginx:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

---

## Security Notes

Do not commit:

- `.env`
- bot tokens
- Gemini/API keys
- live SQLite database files

Current production hardening recommendations:

- Protect notification endpoints with API keys
- Expire bot-login tokens
- Check Telegram `auth_date` freshness
- Add CSRF protection for web POST/DELETE APIs
- Use SQLite WAL + busy timeout for bot/web concurrency

---

## License

MIT License
