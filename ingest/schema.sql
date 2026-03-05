-- ingest/schema.sql
-- Postgres schema for invoice ingestion with supplier master, invoice header, line items,
-- and dedupe tracking for processed email attachments.

CREATE TABLE IF NOT EXISTS suppliers (
  id              BIGSERIAL PRIMARY KEY,
  name_normalized TEXT NOT NULL,
  display_name    TEXT,
  address_text    TEXT,
  tax_id          TEXT,
  country         TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_suppliers_tax_id ON suppliers(tax_id);
CREATE INDEX IF NOT EXISTS idx_suppliers_name_norm ON suppliers(name_normalized);

CREATE TABLE IF NOT EXISTS invoices (
  id               BIGSERIAL PRIMARY KEY,

  supplier_id      BIGINT REFERENCES suppliers(id),

  invoice_number   TEXT,
  invoice_date     DATE,
  payment_due_date DATE,

  currency         TEXT,
  sub_total        NUMERIC(18,2),
  tax_total        NUMERIC(18,2),
  grand_total      NUMERIC(18,2),
  amount_due       NUMERIC(18,2),

  mailbox_provider TEXT NOT NULL,       -- 'gmail' or 'outlook'
  mail_message_id  TEXT NOT NULL,
  mail_thread_id   TEXT,
  mail_received_at TIMESTAMPTZ,

  processed_at     TIMESTAMPTZ,
  status           TEXT NOT NULL,       -- 'SUCCESS' or 'FAILED'

  error_code       TEXT,
  error_message    TEXT,

  trace_id         TEXT,

  pdf_path         TEXT,
  canonical_json   JSONB,
  peppol_xml       TEXT,

  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_invoices_msg ON invoices(mailbox_provider, mail_message_id);

CREATE TABLE IF NOT EXISTS invoice_items (
  id          BIGSERIAL PRIMARY KEY,
  invoice_id  BIGINT NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,

  line_no     INT,
  description TEXT,
  quantity    NUMERIC(18,4),
  unit_price  NUMERIC(18,4),
  line_amount NUMERIC(18,2),
  tax_rate    NUMERIC(9,4),
  tax_amount  NUMERIC(18,2),
  hsn_sac     TEXT
);

CREATE INDEX IF NOT EXISTS idx_items_invoice ON invoice_items(invoice_id);

CREATE TABLE IF NOT EXISTS processed_attachments (
  id               BIGSERIAL PRIMARY KEY,

  mailbox_provider TEXT NOT NULL,
  mail_message_id  TEXT NOT NULL,
  attachment_id    TEXT NOT NULL,

  sha256           TEXT,
  processed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

  UNIQUE(mailbox_provider, mail_message_id, attachment_id)
);

CREATE INDEX IF NOT EXISTS idx_processed_sha ON processed_attachments(sha256);
