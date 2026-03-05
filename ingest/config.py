from __future__ import annotations
from pydantic import BaseModel
import os


class Settings(BaseModel):
    """
    Centralized configuration.

    You can provide Gmail creds/token either as:
      - file paths: GMAIL_CREDENTIALS_PATH, GMAIL_TOKEN_PATH
      - raw JSON:   GMAIL_CREDENTIALS_JSON, GMAIL_TOKEN_JSON

    Mail provider is configurable:
      MAIL_PROVIDER=gmail|outlook
    """
    # Mail provider selection
    mail_provider: str = os.getenv("MAIL_PROVIDER", "gmail").lower()  # gmail|outlook

    # Where to call your MCP server's REST endpoint
    # (Recommended inside Codespace): http://127.0.0.1:8000/convert
    mcp_convert_url: str = os.getenv("MCP_CONVERT_URL", "http://127.0.0.1:8000/convert")

    # Postgres connection string
    # Example: postgresql://user:pass@host:5432/dbname
    database_url: str = os.environ["DATABASE_URL"]

    # Poll interval
    poll_seconds: int = int(os.getenv("POLL_SECONDS", "60"))

    # Gmail query to reduce scanning and API usage
    gmail_query: str = os.getenv("GMAIL_QUERY", "is:unread has:attachment filename:pdf newer_than:7d")

    # PDF archival
    pdf_store_dir: str = os.getenv("PDF_STORE_DIR", "data/pdfs")

    # Invoice detection keywords (simple baseline; we can enhance later)
    invoice_keywords: list[str] = [
        "invoice", "tax invoice", "bill", "payment due", "amount due", "balance due"
    ]

    # Gmail credentials inputs
    gmail_credentials_path: str | None = os.getenv("GMAIL_CREDENTIALS_PATH")
    gmail_token_path: str | None = os.getenv("GMAIL_TOKEN_PATH")
    gmail_credentials_json: str | None = os.getenv("GMAIL_CREDENTIALS_JSON")
    gmail_token_json: str | None = os.getenv("GMAIL_TOKEN_JSON")
