#!/usr/bin/env python3
"""
Daily Apple purchase report.

Usage:
    python main.py           # ingest + send SMS
    python main.py --dry-run # ingest + print SMS, no send
"""
import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

from ingest import run_ingest
from points import update_and_get_points
from report import format_sms, get_spending, send_sms


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print SMS without sending")
    args = parser.parse_args()

    logger.info("Syncing Apple receipt emails...")
    new = run_ingest()
    logger.info("Ingested %d new receipt(s)", new)

    spending = get_spending()
    points = update_and_get_points()
    msg = format_sms(spending, points)

    if args.dry_run:
        print("\n--- SMS preview ---")
        print(msg)
        print("-------------------")
    else:
        send_sms(msg)

    logger.info("Done.")


if __name__ == "__main__":
    main()
