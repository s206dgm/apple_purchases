"""
Polls Gmail for reply texts from the user's AT&T number.

When you reply to the daily Apple spend SMS, AT&T delivers it as an email back
to the Gmail account that sent it. This script checks for those replies,
treats the message body as an app name query, and texts back the results.

Run every 5 minutes via cron:
    */5 * * * * cd /home/s206r/projects/rykailabs/apple_purchases && \
        /home/s206r/projects/rykailabs/portal/.venv/bin/python sms_watcher.py >> data/watcher.log 2>&1
"""
import base64
import logging
import re
import sys

import googleapiclient.discovery

from config import get_settings
from database import command_exists, insert_command
from gmail_auth import get_credentials
from query import format_app_sms, get_app_spending
from report import format_sms, get_spending, send_sms

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# AT&T delivers SMS replies from these domains
ATT_DOMAINS = ("@txt.att.net", "@mms.att.net", "@messaging.sprintpcs.com")


def _extract_text_body(payload: dict) -> str:
    mime = payload.get("mimeType", "")
    if mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    if mime.startswith("multipart/"):
        for part in payload.get("parts", []):
            text = _extract_text_body(part)
            if text:
                return text
    return ""


def _extract_command(body: str) -> str:
    """
    Pull the user's query from the reply body.
    AT&T prepends the original message after a blank line or dashes — take only the first line.
    """
    for line in body.splitlines():
        line = line.strip()
        # Skip blank lines, AT&T boilerplate, and quoted-reply markers
        if not line:
            continue
        if line.startswith(">") or line.startswith("-") or re.match(r"^[_=]{3,}$", line):
            break
        return line
    return ""


def run_watcher():
    s = get_settings()
    creds = get_credentials()
    service = googleapiclient.discovery.build("gmail", "v1", credentials=creds)

    att_from = f"{s.att_phone}@txt.att.net"
    result = service.users().messages().list(
        userId="me",
        q=f"from:{att_from} is:unread",
        maxResults=20,
    ).execute()

    messages = result.get("messages", [])
    if not messages:
        logger.info("No new SMS replies.")
        return

    for msg in messages:
        msg_id = msg["id"]
        if command_exists(msg_id):
            continue

        full = service.users().messages().get(
            userId="me", id=msg_id, format="full"
        ).execute()

        payload = full.get("payload", {})
        headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
        from_addr = headers.get("From", "")

        body = _extract_text_body(payload)
        command = _extract_command(body).strip()

        logger.info("Command from %s: %r", from_addr, command)
        insert_command(msg_id, from_addr, command)

        # Mark as read so we don't reprocess
        service.users().messages().modify(
            userId="me", id=msg_id, body={"removeLabelIds": ["UNREAD"]}
        ).execute()

        if not command:
            logger.warning("Empty command, skipping reply.")
            continue

        app_result = get_app_spending(command)
        if app_result:
            reply = format_app_sms(app_result)
        else:
            reply = f"No Apple purchases found for: {command}"

        send_sms(reply)
        logger.info("Replied: %s", reply.replace("\n", " | "))


if __name__ == "__main__":
    run_watcher()
