from __future__ import annotations
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict

import psycopg

from ingest.log import log
from ingest.storage import store_pdf
from ingest.supplier_match import get_or_create_supplier
from ingest.mcp_client import call_convert
from ingest.mailbox.base import MessageMeta, AttachmentRef


def looks_like_invoice(subject: str, snippet: str, keywords: list[str]) -> bool:
    """
    Simple invoice detector using keywords in subject/body snippet.

    This is intentionally lightweight and deterministic.
    We can upgrade to an LLM classifier later if you want better accuracy.
    """
    t = f"{subject}\n{snippet}".lower()
    return any(k.lower() in t for k in keywords)


def already_processed(conn: psycopg.Connection, provider: str, message_id: str, attachment_id: str) -> bool:
    """
    Dedupe guard:
    If we have already processed (provider, message_id, attachment_id), skip.
    """
    row = conn.execute(
        """SELECT 1 FROM processed_attachments
           WHERE mailbox_provider=%s AND mail_message_id=%s AND attachment_id=%s""",
        (provider, message_id, attachment_id),
    ).fetchone()
    return row is not None


def mark_processed(conn: psycopg.Connection, provider: str, message_id: str, attachment_id: str, sha256: str) -> None:
    """
    Mark attachment as processed so we don't process it again.

    We store:
      - provider (gmail/outlook)
      - message id
      - attachment id
      - sha256 of PDF bytes (useful for cross-message dedupe / auditing)
    """
    conn.execute(
        """INSERT INTO processed_attachments(mailbox_provider, mail_message_id, attachment_id, sha256)
           VALUES (%s,%s,%s,%s)
           ON CONFLICT (mailbox_provider, mail_message_id, attachment_id) DO NOTHING""",
        (provider, message_id, attachment_id, sha256),
    )
    conn.commit()


def insert_invoice_success(conn: psycopg.Connection, provider: str, msg_meta: MessageMeta,
                           pdf_path: str, convert_out: dict) -> int:
    """
    Insert a SUCCESS invoice record + its line items.

    IMPORTANT: This is different from insert_invoice_failure() because:
      - Success has extracted canonical_json and peppol_xml
      - We insert supplier_id and link to supplier master
      - We insert invoice_items rows
      - We store invoice_date, due_date, totals, currency, etc.

    Returns:
      invoice_id
    """
    result = convert_out["result"]
    inv = result["custom_invoice_json"]
    trace_id = (inv.get("meta") or {}).get("trace_id")

    # Link to supplier master using seller details from invoice
    supplier_id = get_or_create_supplier(conn, inv.get("seller") or {})

    totals = inv.get("totals") or {}
    payment = inv.get("payment") or {}

    # Insert invoice header
    cur = conn.execute(
        """INSERT INTO invoices(
             supplier_id,
             invoice_number, invoice_date, payment_due_date,
             currency, sub_total, tax_total, grand_total, amount_due,
             mailbox_provider, mail_message_id, mail_thread_id, mail_received_at,
             processed_at, status, trace_id,
             pdf_path, canonical_json, peppol_xml
           )
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now(), 'SUCCESS', %s, %s, %s::jsonb, %s)
           RETURNING id""",
        (
            supplier_id,
            inv.get("invoice_number"),
            inv.get("invoice_date"),
            payment.get("due_date"),
            inv.get("currency"),
            totals.get("sub_total"),
            totals.get("tax_total"),
            totals.get("grand_total"),
            payment.get("amount_due"),
            provider,
            msg_meta.message_id,
            msg_meta.thread_id,
            msg_meta.received_at,
            trace_id,
            pdf_path,
            # Store canonical JSON in DB as JSONB
            # (inv is already a dict)
            psycopg.types.json.Json(inv),
            result.get("peppol_ubl_xml"),
        ),
    )
    invoice_id = int(cur.fetchone()["id"])

    # Insert line items in detail table
    for line_no, li in enumerate(inv.get("line_items") or [], start=1):
        conn.execute(
            """INSERT INTO invoice_items(
                 invoice_id, line_no, description, quantity, unit_price, line_amount, tax_rate, tax_amount, hsn_sac
               )
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                invoice_id,
                line_no,
                li.get("description"),
                li.get("quantity"),
                li.get("unit_price"),
                li.get("amount"),
                li.get("tax_rate"),
                li.get("tax_amount"),
                li.get("hsn_sac"),
            ),
        )

    conn.commit()
    return invoice_id


def insert_invoice_failure(conn: psycopg.Connection, provider: str, msg_meta: MessageMeta,
                           pdf_path: str | None, error_code: str, error_message: str,
                           trace_id: str | None) -> int:
    """
    Insert a FAILED invoice record.

    IMPORTANT: This differs from insert_invoice_success() because:
      - Failure might not have extracted JSON or XML
      - We still store audit info:
          mailbox_provider, message_id, received_at, processed_at
          error_code, error_message, trace_id, pdf_path
      - We do NOT insert invoice_items (we don't have reliable extracted items)
      - supplier_id is unknown (or can be inferred later on reprocess)

    Returns:
      invoice_id (failed record id)
    """
    cur = conn.execute(
        """INSERT INTO invoices(
             mailbox_provider, mail_message_id, mail_thread_id, mail_received_at,
             processed_at, status, error_code, error_message, trace_id, pdf_path
           )
           VALUES (%s,%s,%s,%s, now(), 'FAILED', %s,%s,%s,%s)
           RETURNING id""",
        (
            provider,
            msg_meta.message_id,
            msg_meta.thread_id,
            msg_meta.received_at,
            error_code,
            (error_message or "")[:2000],
            trace_id,
            pdf_path,
        ),
    )
    invoice_id = int(cur.fetchone()["id"])
    conn.commit()
    return invoice_id


def process_message(conn: psycopg.Connection, settings, mail_provider, message_id: str) -> None:
    """
    Process one email message:
      1) get meta (subject/snippet/received date)
      2) detect whether invoice-related
      3) list PDF attachments
      4) for each attachment: dedupe check, store PDF, call MCP, insert DB rows
      5) mark message read if all attachments succeed
    """
    provider_name = mail_provider.name
    msg_meta = mail_provider.get_message_meta(message_id)

    # Lightweight invoice detection
    if not looks_like_invoice(msg_meta.subject, msg_meta.snippet, settings.invoice_keywords):
        log("message_skipped_not_invoice", provider=provider_name, message_id=message_id)
        # We do not mark read here; you can choose to mark read if desired.
        return

    attachments = mail_provider.list_pdf_attachments(message_id)
    if not attachments:
        log("message_skipped_no_pdf", provider=provider_name, message_id=message_id)
        return

    all_ok = True

    for att in attachments:
        try:
            # Dedupe per (provider,message,attachment)
            if already_processed(conn, provider_name, msg_meta.message_id, att.attachment_id):
                log("attachment_skipped_dedupe", provider=provider_name, message_id=message_id, attachment_id=att.attachment_id, filename=att.filename)
                continue

            # Download bytes
            pdf_bytes = mail_provider.download_attachment_bytes(message_id, att.attachment_id)

            # Store PDF to disk (always store for audit and reprocessing)
            pdf_path, digest = store_pdf(pdf_bytes, settings.pdf_store_dir)

            # Call MCP server (/convert) which performs OpenAI extraction + Peppol XML generation
            out = call_convert(settings.mcp_convert_url, pdf_bytes)

            if out.get("ok") is True:
                invoice_id = insert_invoice_success(conn, provider_name, msg_meta, pdf_path, out)
                mark_processed(conn, provider_name, msg_meta.message_id, att.attachment_id, digest)

                inv = out["result"]["custom_invoice_json"]
                invno = inv.get("invoice_number")
                total = (inv.get("totals") or {}).get("grand_total")
                log("attachment_processed_success", provider=provider_name, message_id=message_id, attachment_id=att.attachment_id,
                    filename=att.filename, invoice_id=invoice_id, invoice_number=invno, total=total, pdf_path=pdf_path)

            else:
                # MCP returned a structured error envelope
                err = out.get("error", {})
                trace_id = (err.get("details") or {}).get("trace_id")

                invoice_id = insert_invoice_failure(conn, provider_name, msg_meta, pdf_path,
                                                    err.get("code", "UNKNOWN"),
                                                    err.get("message", ""),
                                                    trace_id)
                mark_processed(conn, provider_name, msg_meta.message_id, att.attachment_id, digest)

                log("attachment_processed_failed", level="ERROR", provider=provider_name, message_id=message_id,
                    attachment_id=att.attachment_id, filename=att.filename,
                    invoice_id=invoice_id, error_code=err.get("code"), error_message=err.get("message"), trace_id=trace_id)

                all_ok = False

        except Exception as e:
            # Hard failure (network exception / crash / unexpected response)
            all_ok = False
            log("attachment_exception", level="ERROR", provider=provider_name, message_id=message_id,
                attachment_id=att.attachment_id, filename=att.filename, error=str(e))

    # Mark message as read only if all attachments processed successfully
    if all_ok:
        mail_provider.mark_message_read(message_id)
        log("message_marked_read", provider=provider_name, message_id=message_id)
