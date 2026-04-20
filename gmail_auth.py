"""
Loads Gmail OAuth credentials from the portal's SQLite DB.
The portal handles the OAuth flow; this script just borrows the stored token.
"""
import sqlite3

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from config import get_settings


def get_credentials() -> Credentials:
    s = get_settings()
    conn = sqlite3.connect(s.portal_db_path)
    row = conn.execute(
        "SELECT access_token, refresh_token, scopes FROM gmailtoken WHERE email = ?",
        (s.gmail_account,),
    ).fetchone()
    conn.close()

    if not row:
        raise RuntimeError(
            f"No Gmail token for {s.gmail_account}. "
            "Authenticate via the portal first (Settings → Connect Gmail)."
        )

    access_token, refresh_token, scopes = row
    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=s.google_client_id,
        client_secret=s.google_client_secret,
        scopes=scopes.split() if scopes else [],
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        conn = sqlite3.connect(s.portal_db_path)
        conn.execute(
            "UPDATE gmailtoken SET access_token = ?, updated_at = datetime('now') WHERE email = ?",
            (creds.token, s.gmail_account),
        )
        conn.commit()
        conn.close()

    return creds
