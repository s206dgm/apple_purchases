import sqlite3
import os
from config import get_settings


def get_conn() -> sqlite3.Connection:
    s = get_settings()
    os.makedirs(os.path.dirname(s.db_path), exist_ok=True)
    conn = sqlite3.connect(s.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS apple_purchase (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            gmail_message_id  TEXT    UNIQUE NOT NULL,
            account_email     TEXT    NOT NULL,
            purchase_date     TEXT    NOT NULL,
            amount            REAL    NOT NULL DEFAULT 0,
            item_description  TEXT    DEFAULT '',
            raw_subject       TEXT    DEFAULT '',
            ingested_at       TEXT    DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS apple_purchase_item (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            purchase_id  INTEGER NOT NULL REFERENCES apple_purchase(id),
            app_name     TEXT    DEFAULT '',
            item_name    TEXT    DEFAULT '',
            item_type    TEXT    DEFAULT '',
            amount       REAL    NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sms_command (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            gmail_message_id TEXT    UNIQUE NOT NULL,
            from_address     TEXT    DEFAULT '',
            command          TEXT    DEFAULT '',
            processed_at     TEXT    DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def message_exists(gmail_message_id: str) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM apple_purchase WHERE gmail_message_id = ?",
        (gmail_message_id,),
    ).fetchone()
    conn.close()
    return row is not None


def insert_purchase(
    gmail_message_id: str,
    account_email: str,
    purchase_date: str,
    amount: float,
    item_description: str,
    raw_subject: str,
) -> int:
    """Insert a receipt row and return its id."""
    conn = get_conn()
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO apple_purchase
            (gmail_message_id, account_email, purchase_date, amount, item_description, raw_subject)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (gmail_message_id, account_email, purchase_date, amount, item_description, raw_subject),
    )
    conn.commit()
    purchase_id = cur.lastrowid
    conn.close()
    return purchase_id


def command_exists(gmail_message_id: str) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM sms_command WHERE gmail_message_id = ?",
        (gmail_message_id,),
    ).fetchone()
    conn.close()
    return row is not None


def insert_command(gmail_message_id: str, from_address: str, command: str):
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO sms_command (gmail_message_id, from_address, command) VALUES (?, ?, ?)",
        (gmail_message_id, from_address, command),
    )
    conn.commit()
    conn.close()


def insert_items(purchase_id: int, items: list[dict]):
    """Insert line items for a receipt. Each dict: {app_name, item_name, item_type, amount}"""
    if not items:
        return
    conn = get_conn()
    conn.executemany(
        """
        INSERT INTO apple_purchase_item (purchase_id, app_name, item_name, item_type, amount)
        VALUES (:purchase_id, :app_name, :item_name, :item_type, :amount)
        """,
        [{"purchase_id": purchase_id, **item} for item in items],
    )
    conn.commit()
    conn.close()
