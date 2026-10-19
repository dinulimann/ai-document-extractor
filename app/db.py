import json
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id           bigserial PRIMARY KEY,
    filename     text NOT NULL,
    sha256       text NOT NULL UNIQUE,
    uploaded_at  timestamptz NOT NULL DEFAULT now(),
    -- processing -> needs_review | extracted -> approved ; or failed
    status       text NOT NULL DEFAULT 'processing',
    model        text,
    seconds      numeric(8,2),
    raw_text     text,
    data         jsonb,
    issues       jsonb NOT NULL DEFAULT '[]',
    error        text,
    reviewed_at  timestamptz
);

-- Flat view for reporting / BI tools
CREATE OR REPLACE VIEW v_invoices AS
SELECT d.id,
       d.status,
       d.filename,
       d.data->>'vendor_name'               AS vendor_name,
       d.data->>'vendor_tax_id'             AS vendor_tax_id,
       d.data->>'invoice_number'            AS invoice_number,
       (d.data->>'invoice_date')::date      AS invoice_date,
       NULLIF(d.data->>'due_date', '')::date AS due_date,
       d.data->>'currency'                  AS currency,
       d.data->>'bill_to'                   AS bill_to,
       (d.data->>'subtotal')::numeric       AS subtotal,
       (d.data->>'tax')::numeric            AS tax,
       (d.data->>'total')::numeric          AS total,
       jsonb_array_length(d.data->'line_items') AS line_count,
       jsonb_array_length(d.issues)         AS issue_count,
       d.uploaded_at
FROM documents d
WHERE d.data IS NOT NULL
  AND d.data->>'invoice_date' ~ '^\\d{4}-\\d{2}-\\d{2}$'
  AND coalesce(d.data->>'due_date', '') ~ '^(\\d{4}-\\d{2}-\\d{2})?$';
"""


@contextmanager
def connect():
    with psycopg.connect(config.DATABASE_URL, row_factory=dict_row) as conn:
        yield conn


def init_db() -> None:
    with connect() as conn:
        conn.execute(SCHEMA)


def insert_document(filename: str, sha256: str) -> tuple[int, bool]:
    """Returns (id, created). Uploading the same file twice returns the existing row."""
    with connect() as conn:
        row = conn.execute(
            "INSERT INTO documents (filename, sha256) VALUES (%s, %s) "
            "ON CONFLICT (sha256) DO NOTHING RETURNING id",
            (filename, sha256),
        ).fetchone()
        if row:
            return row["id"], True
        return conn.execute("SELECT id FROM documents WHERE sha256 = %s", (sha256,)).fetchone()["id"], False


def save_result(doc_id: int, *, status: str, model: str | None = None, seconds: float | None = None,
                raw_text: str | None = None, data: dict | None = None, issues: list | None = None,
                error: str | None = None) -> None:
    with connect() as conn:
        conn.execute(
            """UPDATE documents
               SET status = %s, model = %s, seconds = %s, raw_text = %s, data = %s,
                   issues = %s, error = %s
               WHERE id = %s""",
            (status, model, seconds, raw_text, Jsonb(data) if data is not None else None,
             Jsonb(issues or []), error, doc_id),
        )


def update_review(doc_id: int, data: dict, issues: list, approve: bool) -> None:
    with connect() as conn:
        conn.execute(
            """UPDATE documents
               SET data = %s, issues = %s,
                   status = CASE WHEN %s THEN 'approved'
                                 WHEN jsonb_array_length(%s) > 0 THEN 'needs_review'
                                 ELSE 'extracted' END,
                   reviewed_at = CASE WHEN %s THEN now() ELSE reviewed_at END
               WHERE id = %s""",
            (Jsonb(data), Jsonb(issues), approve, Jsonb(issues), approve, doc_id),
        )


def list_documents() -> list[dict]:
    with connect() as conn:
        return conn.execute(
            """SELECT id, filename, status, uploaded_at, seconds, error,
                      data->>'vendor_name' AS vendor_name, data->>'invoice_number' AS invoice_number,
                      data->>'invoice_date' AS invoice_date, data->>'currency' AS currency,
                      (data->>'total')::numeric AS total, jsonb_array_length(issues) AS issue_count
               FROM documents ORDER BY id DESC"""
        ).fetchall()


def get_document(doc_id: int) -> dict | None:
    with connect() as conn:
        return conn.execute("SELECT * FROM documents WHERE id = %s", (doc_id,)).fetchone()


def stats() -> dict:
    with connect() as conn:
        return conn.execute(
            """SELECT count(*) AS total,
                      count(*) FILTER (WHERE status = 'approved')     AS approved,
                      count(*) FILTER (WHERE status = 'needs_review') AS needs_review,
                      count(*) FILTER (WHERE status = 'extracted')    AS extracted,
                      count(*) FILTER (WHERE status = 'failed')       AS failed,
                      round(avg(seconds), 1)                          AS avg_seconds
               FROM documents"""
        ).fetchone()


def export_rows() -> tuple[list[str], list[tuple]]:
    with connect() as conn:
        cur = conn.execute("SELECT * FROM v_invoices ORDER BY id")
        cols = [c.name for c in cur.description]
        return cols, [tuple(r.values()) for r in cur.fetchall()]


def to_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)
