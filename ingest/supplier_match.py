from __future__ import annotations
import re
from typing import Optional
import psycopg

# Common suffixes; we remove them during normalization to reduce duplicates.
SUFFIXES = {"ltd", "limited", "pvt", "private", "inc", "llc", "co", "company", "corp", "corporation"}


def normalize_name(name: str) -> str:
    """
    Normalize supplier names for matching:
    - lowercase
    - remove punctuation
    - remove common company suffixes
    - collapse spaces
    """
    s = (name or "").lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    parts = [p for p in s.split() if p and p not in SUFFIXES]
    return " ".join(parts)


def get_or_create_supplier(conn: psycopg.Connection, seller: dict) -> int:
    """
    Find the supplier record to link this invoice to.

    Matching strategy:
      1) If tax_id exists (gstin/vat/etc), match on that.
      2) Else match on normalized name.
      3) Else create new supplier.

    Returns:
      supplier_id
    """
    name = seller.get("name") or ""
    addr = seller.get("address") or ""
    tax_id = seller.get("gstin") or seller.get("tax_id")  # tolerate alternate key naming
    country = seller.get("country")

    name_norm = normalize_name(name)

    # 1) tax_id exact match
    if tax_id:
        row = conn.execute("SELECT id FROM suppliers WHERE tax_id=%s", (tax_id,)).fetchone()
        if row:
            return int(row["id"])

    # 2) normalized name match
    if name_norm:
        row = conn.execute("SELECT id FROM suppliers WHERE name_normalized=%s", (name_norm,)).fetchone()
        if row:
            return int(row["id"])

    # 3) create new supplier
    cur = conn.execute(
        """INSERT INTO suppliers(name_normalized, display_name, address_text, tax_id, country)
           VALUES (%s,%s,%s,%s,%s)
           RETURNING id""",
        (name_norm or "unknown", name, addr, tax_id, country),
    )
    supplier_id = int(cur.fetchone()["id"])
    conn.commit()
    return supplier_id
