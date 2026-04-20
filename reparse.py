"""
Re-parse receipts where the sum of line items doesn't match the receipt total.
Deletes only those rows + their items, then re-ingests from Gmail.
"""
import logging
import sqlite3
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)

from config import get_settings
from ingest import run_ingest


def get_mismatch_ids(conn: sqlite3.Connection, threshold: float = 0.01) -> list[tuple[int, str]]:
    return conn.execute("""
        SELECT p.id, p.gmail_message_id
        FROM apple_purchase p
        JOIN apple_purchase_item i ON i.purchase_id = p.id
        GROUP BY p.id
        HAVING ABS(p.amount - SUM(i.amount)) > ?
    """, (threshold,)).fetchall()


def main():
    s = get_settings()
    conn = sqlite3.connect(s.db_path)

    mismatches = get_mismatch_ids(conn)
    if not mismatches:
        logger.info("No mismatched receipts found.")
        return

    logger.info("Found %d mismatched receipts — removing for re-parse...", len(mismatches))
    ids = [row[0] for row in mismatches]

    conn.execute(f"DELETE FROM apple_purchase_item WHERE purchase_id IN ({','.join('?'*len(ids))})", ids)
    conn.execute(f"DELETE FROM apple_purchase WHERE id IN ({','.join('?'*len(ids))})", ids)
    conn.commit()
    conn.close()

    logger.info("Deleted. Re-ingesting from Gmail...")
    new = run_ingest()
    logger.info("Re-parsed %d receipt(s).", new)

    # Check results
    conn = sqlite3.connect(s.db_path)
    remaining = get_mismatch_ids(conn)
    receipt_sum = conn.execute("SELECT ROUND(SUM(amount),2) FROM apple_purchase").fetchone()[0]
    items_sum = conn.execute("SELECT ROUND(SUM(amount),2) FROM apple_purchase_item").fetchone()[0]
    conn.close()

    logger.info("Remaining mismatches: %d", len(remaining))
    logger.info("Receipt sum: $%.2f | Items sum: $%.2f | Gap: $%.2f",
                receipt_sum, items_sum, receipt_sum - items_sum)


if __name__ == "__main__":
    main()
