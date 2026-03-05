from __future__ import annotations
import time

from ingest.config import Settings
from ingest.db import connect
from ingest.log import log
from ingest.mailbox.gmail_provider import GmailProvider
from ingest.mailbox.outlook_provider import OutlookProvider
from ingest.pipeline import process_message


def build_provider(settings: Settings):
    """
    Factory to choose mailbox provider based on configuration.
    """
    if settings.mail_provider == "gmail":
        return GmailProvider(
            gmail_query=settings.gmail_query,
            credentials_path=settings.gmail_credentials_path,
            token_path=settings.gmail_token_path,
            credentials_json=settings.gmail_credentials_json,
            token_json=settings.gmail_token_json,
        )

    if settings.mail_provider == "outlook":
        return OutlookProvider()  # not implemented yet

    raise ValueError(f"Unknown MAIL_PROVIDER: {settings.mail_provider}")


def main():
    settings = Settings()
    log("ingest_start", provider=settings.mail_provider, mcp_convert_url=settings.mcp_convert_url)

    conn = connect(settings.database_url)
    provider = build_provider(settings)

    while True:
        try:
            msg_ids = provider.list_candidate_messages()
            log("poll_cycle", provider=provider.name, message_count=len(msg_ids))

            for msg_id in msg_ids:
                process_message(conn, settings, provider, msg_id)

        except Exception as e:
            # Do not crash the daemon; log and continue.
            log("poll_cycle_exception", level="ERROR", error=str(e))

        time.sleep(settings.poll_seconds)


if __name__ == "__main__":
    main()
