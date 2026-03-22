"""Gmail API client for reading, sending, and managing emails."""

import base64
import os
from email.mime.text import MIMEText

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from config import CREDENTIALS_FILE, TOKEN_FILE, GMAIL_SCOPES

# Cache the Gmail service object (MCP server is long-running)
_cached_service = None


def get_gmail_service():
    """Authenticate and return Gmail API service. Caches for reuse."""
    global _cached_service

    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    f"Gmail credentials not found at {CREDENTIALS_FILE}. "
                    "Run 'python3 setup_wizard.py' to set up your account."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)

        fd = os.open(str(TOKEN_FILE), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as token:
            token.write(creds.to_json())

        # Invalidate cache when credentials change
        _cached_service = None

    if _cached_service is None:
        _cached_service = build("gmail", "v1", credentials=creds)

    return _cached_service


def get_header(headers, name):
    """Extract a header value by name."""
    for header in headers:
        if header["name"].lower() == name.lower():
            return header["value"]
    return ""


def decode_body(payload):
    """Recursively extract plain text body from message payload."""
    if payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode(
            "utf-8", errors="replace"
        )

    if payload.get("parts"):
        for part in payload["parts"]:
            mime = part.get("mimeType", "")
            if mime == "text/plain":
                if part.get("body", {}).get("data"):
                    return base64.urlsafe_b64decode(part["body"]["data"]).decode(
                        "utf-8", errors="replace"
                    )
            elif mime.startswith("multipart/"):
                result = decode_body(part)
                if result:
                    return result
        for part in payload["parts"]:
            result = decode_body(part)
            if result:
                return result

    return ""


def extract_email_address(from_header):
    """Extract just the email address from a From header like 'Name <email>'."""
    if "<" in from_header and ">" in from_header:
        return from_header.split("<")[1].split(">")[0].lower()
    return from_header.lower().strip()


def fetch_unread_emails(service, max_results=100):
    """Fetch unread emails from inbox."""
    results = service.users().messages().list(
        userId="me",
        q="is:unread in:inbox",
        maxResults=max_results,
    ).execute()

    messages = results.get("messages", [])
    emails = []

    for msg_meta in messages:
        msg = service.users().messages().get(
            userId="me",
            id=msg_meta["id"],
            format="full",
        ).execute()

        headers = msg["payload"].get("headers", [])
        body = decode_body(msg["payload"])

        truncated = len(body) > 3000
        emails.append({
            "id": msg["id"],
            "threadId": msg["threadId"],
            "date": get_header(headers, "Date"),
            "from": get_header(headers, "From"),
            "from_email": extract_email_address(get_header(headers, "From")),
            "to": get_header(headers, "To"),
            "subject": get_header(headers, "Subject"),
            "body": body[:3000] + ("\n[... truncated]" if truncated else ""),
            "labels": msg.get("labelIds", []),
        })

    return emails


def fetch_thread(service, thread_id):
    """Fetch all messages in a thread, sorted chronologically."""
    thread = service.users().threads().get(userId="me", id=thread_id).execute()
    messages = []

    for msg in thread.get("messages", []):
        headers = msg["payload"].get("headers", [])
        body = decode_body(msg["payload"])

        truncated = len(body) > 3000
        messages.append({
            "id": msg["id"],
            "threadId": msg["threadId"],
            "date": get_header(headers, "Date"),
            "from": get_header(headers, "From"),
            "from_email": extract_email_address(get_header(headers, "From")),
            "to": get_header(headers, "To"),
            "subject": get_header(headers, "Subject"),
            "body": body[:3000] + ("\n[... truncated]" if truncated else ""),
            "labels": msg.get("labelIds", []),
        })

    return messages


def trash_email(service, msg_id):
    """Move an email to trash."""
    service.users().messages().trash(userId="me", id=msg_id).execute()


def archive_email(service, msg_id):
    """Archive an email (remove from inbox but keep in All Mail)."""
    service.users().messages().modify(
        userId="me",
        id=msg_id,
        body={"removeLabelIds": ["INBOX", "UNREAD"]},
    ).execute()


def mark_as_read(service, msg_id):
    """Mark an email as read."""
    service.users().messages().modify(
        userId="me",
        id=msg_id,
        body={"removeLabelIds": ["UNREAD"]},
    ).execute()


def send_email(service, to, subject, body, cc=None, thread_id=None):
    """Send a plain text email. If thread_id is provided, fetches the original
    message's RFC Message-ID header so the reply threads correctly."""
    message = MIMEText(body, "plain")
    message["to"] = to
    message["subject"] = subject

    if cc:
        message["cc"] = cc

    send_body = {"raw": None}

    if thread_id:
        send_body["threadId"] = thread_id
        # Fetch the RFC 2822 Message-ID from the first message in the thread
        # so In-Reply-To/References headers are correct for recipients
        try:
            thread = service.users().threads().get(
                userId="me", id=thread_id, format="metadata",
                metadataHeaders=["Message-ID"],
            ).execute()
            msgs = thread.get("messages", [])
            if msgs:
                rfc_msg_id = get_header(
                    msgs[-1].get("payload", {}).get("headers", []), "Message-ID"
                )
                if rfc_msg_id:
                    message["In-Reply-To"] = rfc_msg_id
                    message["References"] = rfc_msg_id
        except Exception:
            pass  # Still send even if we can't fetch the Message-ID

    send_body["raw"] = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return service.users().messages().send(userId="me", body=send_body).execute()


def archive_batch(service, msg_ids):
    """Archive multiple emails."""
    results = {"archived": [], "errors": []}
    for msg_id in msg_ids:
        try:
            archive_email(service, msg_id)
            results["archived"].append(msg_id)
        except Exception as e:
            results["errors"].append({"id": msg_id, "error": str(e)})
    return results


def send_batch(service, emails):
    """Send multiple emails. Each item: {to, subject, body, cc?, thread_id?, mark_read_id?}."""
    results = {"sent": [], "errors": []}
    for email in emails:
        try:
            result = send_email(
                service,
                to=email["to"],
                subject=email["subject"],
                body=email["body"],
                cc=email.get("cc"),
                thread_id=email.get("thread_id"),
            )
            sent_entry = {"id": result["id"], "to": email["to"]}
            if email.get("mark_read_id"):
                try:
                    mark_as_read(service, email["mark_read_id"])
                    sent_entry["marked_read"] = email["mark_read_id"]
                except Exception:
                    pass
            results["sent"].append(sent_entry)
        except Exception as e:
            results["errors"].append({"to": email["to"], "error": str(e)})
    return results


def mark_read_batch(service, msg_ids):
    """Mark multiple emails as read."""
    results = {"marked_read": [], "errors": []}
    for msg_id in msg_ids:
        try:
            mark_as_read(service, msg_id)
            results["marked_read"].append(msg_id)
        except Exception as e:
            results["errors"].append({"id": msg_id, "error": str(e)})
    return results
