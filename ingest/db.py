from __future__ import annotations
import psycopg
from psycopg.rows import dict_row


def connect(database_url: str) -> psycopg.Connection:
    """
    Create a psycopg connection.
    For high throughput, you can use a pool later (psycopg_pool),
    but a single connection is fine for a polling worker.
    """
    conn = psycopg.connect(database_url, row_factory=dict_row)
    conn.execute("SET TIME ZONE 'UTC'")
    return conn
