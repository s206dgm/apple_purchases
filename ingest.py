"""
Fetches all emails under the Gmail label "00. Finance/00A. Apple",
parses each with Claude to extract the charge amount and item description,
and stores new records in the local SQLite DB.
"""
import base64
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import anthropic
import googleapiclient.discovery

from config import get_settings
from database import init_db, insert_items, insert_purchase, message_exists
from gmail_auth import get_credentials

logger = logging.getLogger(__name__)

APPLE_LABEL = "00. Finances/00A. Apple"


def _find_label_id(service) -> str | None:
    result = service.users().labels().list(userId="me").execute()
    for label in result.get("labels", []):
        if label["name"] == APPLE_LABEL:
            return label["id"]
    return None


def _decode_part(part: dict) -> str:
    data = part.get("body", {}).get("data", "")
    if not data:
        return ""
    return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")


def _extract_body(payload: dict, mime: str) -> str:
    if payload.get("mimeType", "") == mime:
        return _decode_part(payload)
    if payload.get("mimeType", "").startswith("multipart/"):
        for part in payload.get("parts", []):
            result = _extract_body(part, mime)
            if result:
                return result
    return ""


def _strip_html(html: str) -> str:
    """Strip HTML tags and Apple boilerplate, leaving just the receipt content."""
    # Remove script/style blocks
    text = re.sub(r'<(script|style)[^>]*>.*?</(script|style)>', '', html, flags=re.DOTALL | re.IGNORECASE)
    # Remove tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Decode common entities
    text = (text.replace('&nbsp;', ' ').replace('&amp;', '&')
                .replace('&lt;', '<').replace('&gt;', '>').replace('&#39;', "'"))
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # Truncate at Apple legal boilerplate — everything useful is above this
    for marker in ['1. 3% savings is earned', 'Get help with subscriptions', 'Apple Account \u2022 Terms']:
        idx = text.find(marker)
        if idx > 0:
            text = text[:idx].strip()
            break
    return text


def _parse_with_claude(subject: str, body_html: str, body_text: str) -> dict:
    """
    Returns {amount, description, items: [{app_name, item_name, item_type, amount}]}
    """
    s = get_settings()
    client = anthropic.Anthropic(api_key=s.anthropic_api_key)

    if body_text:
        body = body_text[:12000]
    elif body_html:
        body = _strip_html(body_html)[:12000]
    else:
        body = ""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": (
                "Extract all purchase details from this Apple receipt email.\n\n"
                f"Subject: {subject}\n\n"
                f"Body:\n{body}\n\n"
                "Respond in this exact format (no extra text):\n"
                "TOTAL: <number only, e.g. 34.97>\n"
                "DESCRIPTION: <brief summary, e.g. 'App Store: Kingshot (3 items)'>\n"
                "ITEM: <app/service name> | <item name> | <type> | <amount>\n"
                "ITEM: <app/service name> | <item name> | <type> | <amount>\n"
                "...\n\n"
                "Types: In-App Purchase, App, Subscription, Movie, Music, Book, TV Show, iCloud Storage, Other\n"
                "If there is only one item, still include one ITEM line.\n"
                "Amount on each ITEM line should be the individual item price (number only)."
            ),
        }],
    )

    result = {"amount": 0.0, "description": subject, "items": []}
    for line in response.content[0].text.strip().splitlines():
        if line.startswith("TOTAL:"):
            try:
                result["amount"] = float(
                    line.split(":", 1)[1].strip().replace("$", "").replace(",", "")
                )
            except ValueError:
                pass
        elif line.startswith("DESCRIPTION:"):
            result["description"] = line.split(":", 1)[1].strip()
        elif line.startswith("ITEM:"):
            parts = [p.strip() for p in line[5:].split("|")]
            if len(parts) >= 4:
                try:
                    item_amount = float(parts[3].replace("$", "").replace(",", ""))
                except ValueError:
                    item_amount = 0.0
                result["items"].append({
                    "app_name":  parts[0],
                    "item_name": parts[1],
                    "item_type": parts[2],
                    "amount":    item_amount,
                })

    return result


def run_ingest() -> int:
    init_db()
    s = get_settings()
    creds = get_credentials()
    service = googleapiclient.discovery.build("gmail", "v1", credentials=creds)

    label_id = _find_label_id(service)
    if not label_id:
        logger.error("Label '%s' not found in Gmail", APPLE_LABEL)
        return 0

    # Page through all message IDs under the label
    messages = []
    page_token = None
    while True:
        kwargs: dict = dict(userId="me", labelIds=[label_id], maxResults=500)
        if page_token:
            kwargs["pageToken"] = page_token
        result = service.users().messages().list(**kwargs).execute()
        messages.extend(result.get("messages", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break

    new_count = 0
    for msg in messages:
        msg_id = msg["id"]
        if message_exists(msg_id):
            continue

        full = service.users().messages().get(
            userId="me", id=msg_id, format="full"
        ).execute()

        payload = full.get("payload", {})
        headers = {h["name"]: h["value"] for h in payload.get("headers", [])}

        subject = headers.get("Subject", "")
        date_str = headers.get("Date", "")

        try:
            purchase_date = parsedate_to_datetime(date_str).astimezone(timezone.utc)
        except Exception:
            purchase_date = datetime.now(timezone.utc)

        body_html = _extract_body(payload, "text/html")
        body_text = _extract_body(payload, "text/plain")

        try:
            parsed = _parse_with_claude(subject, body_html, body_text)
        except Exception as exc:
            logger.warning("Claude parse failed for %s: %s", msg_id, exc)
            parsed = {"amount": 0.0, "description": subject, "items": []}

        purchase_id = insert_purchase(
            gmail_message_id=msg_id,
            account_email=s.gmail_account,
            purchase_date=purchase_date.isoformat(),
            amount=parsed["amount"],
            item_description=parsed["description"],
            raw_subject=subject,
        )
        if purchase_id and parsed["items"]:
            insert_items(purchase_id, parsed["items"])

        new_count += 1
        logger.info(
            "Ingested: %s | $%.2f | %d item(s)",
            subject, parsed["amount"], len(parsed["items"]),
        )

    return new_count
