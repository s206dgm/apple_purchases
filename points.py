"""
Weekly streak tracker. Green week (<$300 total) earns a star.
5 consecutive stars → moon. 5 moons → sun.
2 consecutive over-budget weeks → lose a star (floored at 0, counter then resets).
Updates once per week (on Monday) by checking the previous week's DB total.
"""
import json
from datetime import timedelta
from pathlib import Path

from database import get_conn
from report import _week_start

POINTS_FILE = Path(__file__).parent / "data" / "points.json"
GREEN_THRESHOLD = 300.0
YELLOW_THRESHOLD = 400.0
STARS_PER_MOON = 5
MOONS_PER_SUN = 5
OVER_STREAK_PENALTY = 2


def _load() -> dict:
    state = {"stars": 0, "moons": 0, "suns": 0, "over_streak": 0, "last_week_start": None}
    if POINTS_FILE.exists():
        state.update(json.loads(POINTS_FILE.read_text()))
    return state


def _save(state: dict):
    POINTS_FILE.write_text(json.dumps(state, indent=2))


def _week_total(start, end) -> float:
    conn = get_conn()
    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM apple_purchase WHERE purchase_date >= ? AND purchase_date < ?",
        (start.isoformat(), end.isoformat()),
    ).fetchone()
    conn.close()
    return float(row[0])


def _week_color(total: float) -> str:
    if total < GREEN_THRESHOLD:
        return "🟢"
    elif total < YELLOW_THRESHOLD:
        return "🟡"
    return "🔴"


def trailing_week_icons(n: int = 2) -> str:
    current = _week_start()
    icons = []
    for i in range(n, 0, -1):
        start = current - timedelta(weeks=i)
        end = start + timedelta(weeks=1)
        total = _week_total(start, end)
        icons.append(_week_color(total))
    # current week (in progress)
    icons.append(_week_color(_week_total(current, current + timedelta(weeks=1))))
    return " ".join(icons)


def update_and_get_points() -> dict:
    state = _load()
    current_week = _week_start()
    current_week_str = current_week.date().isoformat()

    if state["last_week_start"] == current_week_str:
        return state

    if state["last_week_start"] is not None:
        prev_start = current_week - timedelta(weeks=1)
        prev_total = _week_total(prev_start, current_week)
        if prev_total < GREEN_THRESHOLD:
            state["over_streak"] = 0
            state["stars"] += 1
            if state["stars"] >= STARS_PER_MOON:
                state["moons"] += 1
                state["stars"] = 0
                if state["moons"] >= MOONS_PER_SUN:
                    state["suns"] += 1
                    state["moons"] = 0
        else:
            state["over_streak"] += 1
            if state["over_streak"] >= OVER_STREAK_PENALTY:
                state["stars"] = max(0, state["stars"] - 1)
                state["over_streak"] = 0

    state["last_week_start"] = current_week_str
    _save(state)
    return state


def format_points(state: dict) -> str:
    parts = []
    if state["suns"]:
        parts.append("☀️" * state["suns"])
    if state["moons"]:
        parts.append("🌙" * state["moons"])
    if state["stars"]:
        parts.append("⭐" * state["stars"])

    return " ".join(parts) if parts else "⭐"
