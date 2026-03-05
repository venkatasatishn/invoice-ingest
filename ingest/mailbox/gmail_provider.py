from __future__ import annotations
import json
import base64
from typing import List, Optional
from email.utils import parsedate_to_datetime

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from ingest.mailbox.base import AttachmentRef, MessageMeta


SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def _load_json_from_path_or_string(path: str | None, raw_json: str | None) -> dict | None:
    """
    Utility: load JSON from file path OR from raw JSON string (env var).
    """
    if raw_json:
        return json.loads(raw_json)
    if path:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _build_creds(credentials_payload: dict | None, token_payload: dict | None) -> Credentials:
    """
    Build Google OAuth Credentials.

    token_payload is expected to be the standard google Credentials JSON
    (the file created by creds.to_json()).

    This function supports:
      - credentials.json (OAuth client)
      - token.json (authorized user token)
    """
    if not token_payload:
        raise RuntimeError("Missing Gmail token. Provide GMAIL_TOKEN_PATH or GMAIL_TOKEN_JSON.")

    creds = Credentials.from_authorized_user_info(token_payload, SCOPES)

    # Refresh if expired and refresh token exists
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return creds


class GmailProvider:
    """
    Gmail polling provider.

    Uses a Gmail query string to fetch candidate messages, then downloads PDF attachments.
    """
    name = "gmail"

    def __init__(self, gmail_query: str, credentials_path: str | None, token_path: str | None,
                 credentials_json: str | None, token_json: str | None):
        self.gmail_query = gmail_query

        credentials_payload = _load_json_from_path_or_string(credentials_path, credentials_json)
        token_payload = _load_json_from_path_or_string(token_path, token_json)
        self.creds = _build_creds(credentials_payload, token_payload)

        self.svc = build("gmail", "v1", credentials=self.creds)

    def list_candidate_messages(self) -> list[str]:
        """
        Use Gmail search query language to get message ids.
        """
        res = self.svc.users().messages().list(userId="me", q=self.gmail_query).execute()
        return [m["id"] for m in res.get("messages", [])]

    def get_message_meta(self, message_id: str) -> MessageMeta:
        """
        Fetch message headers/snippet for invoice detection and DB storage.
        """
        msg = self.svc.users().messages().get(userId="me", id=message_id, format="metadata").execute()
        headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}

        subject = headers.get("subject", "")
        snippet = msg.get("snippet", "")
        thread_id = msg.get("threadId")

        # Received date from header if available
        received_at = None
        if "date" in headers:
            try:
                received_at = parsedate_to_datetime(headers["date"]).astimezone().isoformat()
            except Exception:
                received_at = None

        return MessageMeta(
            message_id=message_id,
            thread_id=thread_id,
            subject=subject,
            snippet=snippet,
            received_at=received_at,
        )

    def list_pdf_attachments(self, message_id: str) -> List[AttachmentRef]:
        """
        Walk MIME parts and return only PDF attachments.
        """
        msg = self.svc.users().messages().get(userId="me", id=message_id, format="full").execute()
        payload = msg.get("payload", {})
        parts = payload.get("parts", []) or []

        out: List[AttachmentRef] = []

        def walk(ps):
            for p in ps:
                # nested multipart
                if p.get("parts"):
                    walk(p["parts"])

                mime = p.get("mimeType", "")
                filename = p.get("filename", "")
                body = p.get("body", {})

                if mime == "application/pdf" and body.get("attachmentId"):
                    out.append(
                        AttachmentRef(
                            attachment_id=body["attachmentId"],
                            filename=filename or "attachment.pdf",
                            mime_type=mime,
                        )
                    )

        walk(parts)
        return out

    def download_attachment_bytes(self, message_id: str, attachment_id: str) -> bytes:
        """
        Download attachment bytes.
        Gmail returns base64url; we decode to raw bytes.
        """
        att = self.svc.users().messages().attachments().get(
            userId="me", messageId=message_id, id=attachment_id
        ).execute()

        data = att["data"]
        return base64.urlsafe_b64decode(data.encode("utf-8"))

    def mark_message_read(self, message_id: str) -> None:
        """
        Mark message as read to avoid reprocessing.
        """
        self.svc.users().messages().modify(
            userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}
        ).execute()
