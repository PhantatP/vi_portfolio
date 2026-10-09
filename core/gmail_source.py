# core/gmail_source.py
"""
Read-only Gmail access for downloading broker PDFs.

One-time setup (on a machine with a browser):
  1. Google Cloud console: create a project, enable the Gmail API, create an OAuth
     client of type "Desktop app", download it to secrets/gmail_credentials.json.
     Set the OAuth consent screen to "In production" (otherwise the token expires every 7 days).
  2. python app/cli.py dime-auth   -> writes secrets/gmail_token.json
  3. Copy both files to the same place on the Jetson. The token refreshes itself.
"""
import base64
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .db import PROJECT_ROOT

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
CREDENTIALS = Path(os.getenv("VI_GMAIL_CREDENTIALS", PROJECT_ROOT / "secrets" / "gmail_credentials.json"))
TOKEN = Path(os.getenv("VI_GMAIL_TOKEN", PROJECT_ROOT / "secrets" / "gmail_token.json"))
# Broad on purpose; file names are filtered in code (see core/dime_import.file_kind)
QUERY = os.getenv("VI_GMAIL_QUERY", "has:attachment filename:pdf dime")


def authorize() -> Path:
    """Interactive: opens a browser for consent and saves the token."""
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN.parent.mkdir(parents=True, exist_ok=True)
    TOKEN.write_text(creds.to_json())
    return TOKEN


def _service():
    if not TOKEN.exists():
        raise RuntimeError(f"No Gmail token at {TOKEN}. Run `python app/cli.py dime-auth` on a machine "
                           "with a browser, then copy the secrets/ folder here.")
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds.valid:
        if not (creds.expired and creds.refresh_token):
            raise RuntimeError("Gmail token is invalid. Run `python app/cli.py dime-auth` again.")
        creds.refresh(Request())
        TOKEN.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _parts(part):
    yield part
    for p in part.get("parts") or []:
        yield from _parts(p)


def fetch_attachments(want, query: str = QUERY) -> list[tuple[str, bytes]]:
    """Return (filename, bytes) for every attachment in messages matching `query` where want(filename)."""
    messages = _service().users().messages()
    files, seen, page = [], set(), None
    while True:
        resp = messages.list(userId="me", q=query, pageToken=page).execute()
        for ref in resp.get("messages", []):
            msg = messages.get(userId="me", id=ref["id"]).execute()
            for part in _parts(msg["payload"]):
                name, att_id = part.get("filename"), part.get("body", {}).get("attachmentId")
                if not name or not att_id or name in seen or not want(name):
                    continue
                att = messages.attachments().get(userId="me", messageId=ref["id"], id=att_id).execute()
                files.append((name, base64.urlsafe_b64decode(att["data"])))
                seen.add(name)
        page = resp.get("nextPageToken")
        if not page:
            return files
