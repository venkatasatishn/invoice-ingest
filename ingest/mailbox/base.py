from __future__ import annotations
from dataclasses import dataclass
from typing import List, Protocol


@dataclass
class MessageMeta:
    """
    Minimal metadata we store for auditability and linking.
    """
    message_id: str
    thread_id: str | None
    subject: str
    snippet: str
    received_at: str | None  # ISO datetime if available


@dataclass
class AttachmentRef:
    """
    Attachment reference from the mailbox provider.
    """
    attachment_id: str
    filename: str
    mime_type: str


class MailProvider(Protocol):
    """
    Provider interface so we can switch between Gmail/Outlook via configuration.
    """
    name: str

    def list_candidate_messages(self) -> list[str]:
        """Return message IDs that likely contain invoices (query-based)."""
        ...

    def get_message_meta(self, message_id: str) -> MessageMeta:
        """Return metadata for invoice detection + DB storage."""
        ...

    def list_pdf_attachments(self, message_id: str) -> List[AttachmentRef]:
        """Return all PDF attachments for a message."""
        ...

    def download_attachment_bytes(self, message_id: str, attachment_id: str) -> bytes:
        """Download attachment content as bytes."""
        ...

    def mark_message_read(self, message_id: str) -> None:
        """Mark message as read after successful processing (optional)."""
        ...
