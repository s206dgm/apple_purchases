"""
Spending breakdown filtered by app name (case-insensitive partial match against
apple_purchase_item.app_name).
"""
from datetime import datetime, timedelta, timezone

from database import get_conn
from report import _week_start


def get_app_spending(app_name: str) -> dict | None:
    """
    Returns spending totals for any app whose name contains app_name (partial, case-insensitive).
    Returns None if no matching items found.
    """
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT p.purchase_date, i.amount, i.app_name, i.item_name, i.item_type
        FROM apple_purchase_item i
        JOIN apple_purchase p ON p.id = i.purchase_id
        WHERE LOWER(i.app_name) LIKE LOWER(?)
        ORDER BY p.purchase_date DESC
        """,
        (f"%{app_name}%",),
    ).fetchall()
    conn.close()

    if not rows:
        return None

    now = datetime.now(timezone.utc)
    year_start  = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1,             hour=0, minute=0, second=0, microsecond=0)
    week_start  = _week_start()
    two_days_ago = now - timedelta(days=2)

    def total(since: datetime | None = None) -> float:
        return sum(
            r["amount"]
            for r in rows
            if since is None or r["purchase_date"] >= since.isoformat()
        )

    matched_names = list(dict.fromkeys(r["app_name"] for r in rows))  # unique, ordered
    display_name = matched_names[0] if len(matched_names) == 1 else f"{app_name} ({len(matched_names)} apps)"

    return {
        "display_name": display_name,
        "all_time":     total(),
        "year":         total(year_start),
        "month":        total(month_start),
        "week":         total(week_start),
        "two_days":     total(two_days_ago),
    }


def format_app_sms(result: dict) -> str:
    now = datetime.now(timezone.utc)
    name = result["display_name"][:20]  # keep within 160 chars total
    return (
        f"{name}\n"
        f"All: ${result['all_time']:,.2f}\n"
        f"{now.year}: ${result['year']:,.2f}\n"
        f"{now.strftime('%b')}: ${result['month']:,.2f}\n"
        f"Wk: ${result['week']:,.2f}\n"
        f"2d: ${result['two_days']:,.2f}"
    )
