"""
Calculates Apple spending totals and sends a daily SMS via the AT&T free gateway
(sends an email to {phone}@txt.att.net using the authenticated Gmail account).
"""
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from config import get_settings
from database import get_conn

logger = logging.getLogger(__name__)


_EASTERN = ZoneInfo("America/New_York")

def _week_start() -> datetime:
    now = datetime.now(_EASTERN)
    monday = now - timedelta(days=now.weekday())
    monday_midnight = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    return monday_midnight.astimezone(timezone.utc)


def get_spending() -> dict:
    conn = get_conn()
    now = datetime.now(timezone.utc)

    year_start  = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    week_start  = _week_start()

    def total(since: datetime | None = None) -> float:
        if since is None:
            row = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM apple_purchase").fetchone()
        else:
            row = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM apple_purchase WHERE purchase_date >= ?",
                (since.isoformat(),),
            ).fetchone()
        return float(row[0])

    def ks_week() -> float:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(i.amount), 0)
            FROM apple_purchase_item i
            JOIN apple_purchase p ON p.id = i.purchase_id
            WHERE LOWER(i.app_name) LIKE '%kingshot%'
              AND p.purchase_date >= ?
            """,
            (week_start.isoformat(),),
        ).fetchone()
        return float(row[0])

    def sub_total(since: datetime) -> float:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(i.amount), 0)
            FROM apple_purchase_item i
            JOIN apple_purchase p ON p.id = i.purchase_id
            WHERE i.item_type = 'Subscription'
              AND p.purchase_date >= ?
            """,
            (since.isoformat(),),
        ).fetchone()
        return float(row[0])

    def sub_breakdown(since: datetime) -> list[tuple[str, float]]:
        rows = conn.execute(
            """
            SELECT i.app_name, COALESCE(SUM(i.amount), 0) as total
            FROM apple_purchase_item i
            JOIN apple_purchase p ON p.id = i.purchase_id
            WHERE i.item_type = 'Subscription'
              AND p.purchase_date >= ?
            GROUP BY i.app_name
            ORDER BY total DESC
            """,
            (since.isoformat(),),
        ).fetchall()
        return [(r[0], float(r[1])) for r in rows]

    result = {
        "all_time":      total(),
        "year":          total(year_start),
        "month":         total(month_start),
        "week":          total(week_start),
        "ks_week":       ks_week(),
        "sub_month":     sub_total(month_start),
        "sub_year":      sub_total(year_start),
        "sub_breakdown": sub_breakdown(month_start),
    }
    conn.close()
    return result


def _tier_remaining(value: float, thresholds: list[float]) -> str:
    for t in thresholds:
        if value < t:
            return f"  (${t - value:,.2f} to 🟡)" if t == thresholds[0] else f"  (${t - value:,.2f} to 🚨)"
    return f"  (+${value - thresholds[0]:,.2f} over budget)"


def _week_icon(value: float) -> str:
    if value < 120:
        return "🟢"
    elif value < 200:
        return "🟡"
    return "🚨"


def format_sms(spending: dict) -> str:
    now = datetime.now(timezone.utc)
    week = spending['week']
    ks_week = spending['ks_week']
    sub_lines = "\n".join(f"{name}: ${amt:,.2f}" for name, amt in spending['sub_breakdown'])
    return (
        f"SUMMARY\n"
        f"{_week_icon(ks_week)} KS Wk: ${ks_week:,.2f}{_tier_remaining(ks_week, [150, 200])}\n"
        f"{_week_icon(week)} TOTAL Wk: ${week:,.2f}{_tier_remaining(week, [150, 200])}\n"
        f"\n"
        f"SUBS\n"
        f"{sub_lines}\n"
        f"{now.strftime('%b')}: ${spending['sub_month']:,.2f}  •  {now.year}: ${spending['sub_year']:,.2f}\n"
        f"\n"
        f"{now.strftime('%b')} ${spending['month']:,.0f}  •  {now.year} ${spending['year']:,.0f}  •  All ${spending['all_time']:,.0f}"
    )



def send_sms(body: str):
    s = get_settings()
    httpx.post(f"https://ntfy.sh/{s.ntfy_topic}", content=body.encode(),
               headers={"Priority": "high", "Title": "Apple Spend"}, timeout=10)
    logger.info("Notification sent to ntfy topic %s", s.ntfy_topic)
