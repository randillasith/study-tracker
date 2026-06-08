# Study Tracker Bot — Gamification Engine
# ==========================================

import math
from datetime import datetime, date, timedelta


# ── XP & Leveling ────────────────────────────────────────────────────────

XP_PER_HOUR = 100  # 100 XP per hour studied


def calculate_xp(duration_minutes: int, streak: int = 0) -> int:
    """Calculate XP earned for a study session.

    Base: XP_PER_HOUR * hours
    Streak bonus: +10% per consecutive day beyond 3
    """
    base = int((duration_minutes / 60) * XP_PER_HOUR)
    bonus = 1.0
    if streak > 3:
        bonus += (streak - 3) * 0.10  # +10% per day beyond 3
    return max(1, int(base * bonus))


def xp_to_level(xp: int) -> int:
    """Convert total XP to level. Level 1 = 0 XP, Level N = 100*(N-1)² XP"""
    return math.floor(math.sqrt(xp / 100)) + 1


def xp_for_next_level(level: int) -> int:
    """XP needed to reach the given level from level 1."""
    return 100 * (level - 1) ** 2


def xp_progress(xp: int) -> tuple:
    """Return (current_level, xp_in_current_level, xp_needed_for_next, progress_pct)"""
    level = xp_to_level(xp)
    current_level_start = xp_for_next_level(level)
    next_level_start = xp_for_next_level(level + 1)
    xp_in_level = xp - current_level_start
    xp_needed = next_level_start - current_level_start
    progress = min(99, int((xp_in_level / xp_needed) * 100)) if xp_needed > 0 else 0
    return level, xp_in_level, xp_needed, progress


# ── Streaks ───────────────────────────────────────────────────────────────

def update_streak(user: dict, study_date: str) -> tuple:
    """Update streak based on study date. Returns (new_streak, streak_bonus_pct)."""
    current_streak = user.get("current_streak", 0)
    longest_streak = user.get("longest_streak", 0)
    last_date = user.get("last_study_date")

    today = date.today()
    study_day = date.fromisoformat(study_date)

    if last_date:
        last = date.fromisoformat(last_date)
        diff = (study_day - last).days

        if diff == 0:
            # Same day — streak unchanged
            pass
        elif diff == 1:
            # Consecutive day — increase streak
            current_streak += 1
        else:
            # Streak broken
            current_streak = 1
    else:
        current_streak = 1

    longest_streak = max(longest_streak, current_streak)

    # Calculate streak bonus
    if current_streak > 3:
        bonus_pct = (current_streak - 3) * 10
    else:
        bonus_pct = 0

    return current_streak, longest_streak, bonus_pct


# ── Rank / Titles ─────────────────────────────────────────────────────────

RANKS = [
    (1, "🌱 Novice Learner"),
    (5, "📖 Apprentice Scholar"),
    (10, "⚔️ Knowledge Seeker"),
    (20, "🛡️ Disciplined Student"),
    (35, "🔥 Focus Master"),
    (50, "⭐ Study Elite"),
    (75, "👑 Academic Knight"),
    (100, "🐉 Legendary Scholar"),
]


def get_rank(level: int) -> str:
    """Get the rank title for a given level."""
    rank = RANKS[0][1]
    for lvl, title in RANKS:
        if level >= lvl:
            rank = title
    return rank


# ── Formatting ────────────────────────────────────────────────────────────


def format_duration(minutes: int) -> str:
    """Format minutes into human-readable string."""
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    mins = minutes % 60
    if mins == 0:
        return f"{hours}h"
    return f"{hours}h {mins}m"


def progress_bar(progress_pct: int, length: int = 10) -> str:
    """Create a visual progress bar."""
    filled = int(length * progress_pct / 100)
    return "█" * filled + "░" * (length - filled)
