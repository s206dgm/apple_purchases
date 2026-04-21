"""
Run this once to authenticate with Gmail and save a local token.

    python auth.py

Opens a browser for Google OAuth consent. Token saved to data/token.json.
Re-run any time the token is revoked.
"""
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from google_auth_oauthlib.flow import Flow

from config import get_settings

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]
REDIRECT_URI = "http://localhost:8000/auth/callback"
TOKEN_FILE = Path(__file__).parent / "data" / "token.json"

_auth_code = None


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _auth_code
        parsed = urlparse(self.path)
        if parsed.path == "/auth/callback":
            params = parse_qs(parsed.query)
            _auth_code = params.get("code", [None])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<h2>Authenticated! You can close this tab.</h2>")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass  # suppress request logging


def main():
    s = get_settings()
    client_config = {
        "web": {
            "client_id": s.google_client_id,
            "client_secret": s.google_client_secret,
            "redirect_uris": [REDIRECT_URI],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=REDIRECT_URI)
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")

    server = HTTPServer(("localhost", 8000), _CallbackHandler)
    t = threading.Thread(target=server.handle_request)
    t.start()

    print(f"Opening browser for authentication...")
    webbrowser.open(auth_url)
    t.join()
    server.server_close()

    if not _auth_code:
        print("No auth code received.")
        return

    flow.fetch_token(code=_auth_code)
    creds = flow.credentials

    TOKEN_FILE.parent.mkdir(exist_ok=True)
    TOKEN_FILE.write_text(json.dumps({
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes),
    }))
    print(f"Token saved to {TOKEN_FILE}")


if __name__ == "__main__":
    main()
