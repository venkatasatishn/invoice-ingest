from __future__ import annotations
from ingest.mailbox.base import MailProvider

class OutlookProvider:
    """
    Stub for Outlook integration.
    We'll implement using Microsoft Graph in the next upgrade.
    """
    name = "outlook"

    def __init__(self, *args, **kwargs):
        raise NotImplementedError("Outlook integration not implemented yet (planned upgrade).")
