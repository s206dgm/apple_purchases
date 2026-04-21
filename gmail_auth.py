"""
Loads Gmail OAuth credentials from data/token.json (written by auth.py).
Run `python auth.py` to authenticate or re-authenticate.
"""
import json
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

TOKEN_FILE = Path(__file__).parent / "data" / "token.json"


def get_credentials() -> Credentials:
    if not TOKEN_FILE.exists():
        raise RuntimeError(
            "No Gmail token found. Run `python auth.py` to authenticate."
        )

    data = json.loads(TOKEN_FILE.read_text())
    creds = Credentials(
        token=data["token"],
        refresh_token=data["refresh_token"],
        token_uri=data["token_uri"],
        client_id=data["client_id"],
        client_secret=data["client_secret"],
        scopes=data["scopes"],
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        data["token"] = creds.token
        TOKEN_FILE.write_text(json.dumps(data))

    return creds
