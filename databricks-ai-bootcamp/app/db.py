"""Lakebase (managed Postgres) access layer for the support app.

Connection settings come from environment variables, which Databricks Apps
injects when you attach a Lakebase database resource:

    PGHOST, PGPORT, PGDATABASE, PGUSER, PGSSLMODE   -- standard libpq vars
    PGPASSWORD                                       -- if set, used directly

When PGPASSWORD is not provided, a short-lived OAuth token is minted for the
Lakebase instance named in LAKEBASE_INSTANCE_NAME using the Databricks SDK.
That means no long-lived database password ever lives in the code or config.
"""

from __future__ import annotations

import os

import psycopg
from psycopg.rows import dict_row

SCHEMA = os.getenv("PGSCHEMA", "support")

_conn: psycopg.Connection | None = None


def _password() -> str:
    """Return the database password from the environment (PGPASSWORD)."""
    static = os.getenv("PGPASSWORD")
    if static:
        return static

    raise RuntimeError(
        "PGPASSWORD is not set. The 'lakebase-password' secret is not reaching "
        "the app. Check that a Secret resource is attached with resource key "
        "'lakebase-password' (matching valueFrom in app.yaml), that the secret "
        "database/lakebase-password exists, and that you redeployed after adding it."
    )


def _connect() -> psycopg.Connection:
    # Simplest path: a full connection URL from a secret (LAKEBASE_URL). This
    # skips the PG* assembly and the runtime token minting entirely.
    url = os.getenv("LAKEBASE_URL")
    if url:
        return psycopg.connect(
            url,
            row_factory=dict_row,
            autocommit=True,
        )

    return psycopg.connect(
        host=os.environ["PGHOST"],
        port=int(os.getenv("PGPORT", "5432")),
        dbname=os.getenv("PGDATABASE", "databricks_postgres"),
        user=os.environ["PGUSER"],
        password=_password(),
        sslmode=os.getenv("PGSSLMODE", "require"),
        row_factory=dict_row,
        autocommit=True,
        application_name=os.getenv("PGAPPNAME", "lakebase-support-app"),
    )


def get_connection() -> psycopg.Connection:
    """Return a live connection, reconnecting if it is closed or the token expired."""
    global _conn
    if _conn is not None and not _conn.closed:
        try:
            with _conn.cursor() as cur:
                cur.execute("SELECT 1")
            return _conn
        except psycopg.Error:
            try:
                _conn.close()
            except psycopg.Error:
                pass
    _conn = _connect()
    return _conn


# --- Queries -------------------------------------------------------------

def list_tickets(status: str | None = None) -> list[dict]:
    sql = f"""
        SELECT t.ticket_id, t.title, t.status, t.priority, t.category,
               t.created_by, t.created_at, t.updated_at,
               COUNT(m.message_id) AS message_count
        FROM {SCHEMA}.tickets t
        LEFT JOIN {SCHEMA}.ticket_messages m ON m.ticket_id = t.ticket_id
        {{where}}
        GROUP BY t.ticket_id
        ORDER BY t.created_at DESC
    """
    params: list = []
    if status:
        sql = sql.format(where="WHERE t.status = %s")
        params.append(status)
    else:
        sql = sql.format(where="")
    with get_connection().cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def get_ticket(ticket_id: int) -> dict | None:
    with get_connection().cursor() as cur:
        cur.execute(
            f"SELECT * FROM {SCHEMA}.tickets WHERE ticket_id = %s", (ticket_id,)
        )
        return cur.fetchone()


def list_messages(ticket_id: int) -> list[dict]:
    with get_connection().cursor() as cur:
        cur.execute(
            f"""SELECT message_id, ticket_id, message_text, author, created_at
                FROM {SCHEMA}.ticket_messages
                WHERE ticket_id = %s
                ORDER BY created_at ASC""",
            (ticket_id,),
        )
        return cur.fetchall()


def create_ticket(
    title: str,
    created_by: str,
    priority: str = "medium",
    category: str | None = None,
    status: str = "open",
) -> int:
    with get_connection().cursor() as cur:
        cur.execute(
            f"""INSERT INTO {SCHEMA}.tickets
                    (title, status, priority, category, created_by)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING ticket_id""",
            (title, status, priority, category, created_by),
        )
        return cur.fetchone()["ticket_id"]


def add_message(ticket_id: int, message_text: str, author: str) -> int:
    with get_connection().cursor() as cur:
        cur.execute(
            f"""INSERT INTO {SCHEMA}.ticket_messages (ticket_id, message_text, author)
                VALUES (%s, %s, %s)
                RETURNING message_id""",
            (ticket_id, message_text, author),
        )
        message_id = cur.fetchone()["message_id"]
        # Touch the parent ticket so ordering reflects recent activity.
        cur.execute(
            f"UPDATE {SCHEMA}.tickets SET updated_at = now() WHERE ticket_id = %s",
            (ticket_id,),
        )
        return message_id


def update_status(ticket_id: int, status: str) -> None:
    with get_connection().cursor() as cur:
        cur.execute(
            f"""UPDATE {SCHEMA}.tickets
                SET status = %s, updated_at = now()
                WHERE ticket_id = %s""",
            (status, ticket_id),
        )


def delete_ticket(ticket_id: int) -> None:
    # ticket_messages cascades via the foreign key.
    with get_connection().cursor() as cur:
        cur.execute(
            f"DELETE FROM {SCHEMA}.tickets WHERE ticket_id = %s", (ticket_id,)
        )


def stats() -> dict:
    with get_connection().cursor() as cur:
        cur.execute(
            f"""SELECT
                    COUNT(*)                                        AS total,
                    COUNT(*) FILTER (WHERE status = 'open')         AS open,
                    COUNT(*) FILTER (WHERE status = 'in_progress')  AS in_progress,
                    COUNT(*) FILTER (WHERE status = 'resolved')     AS resolved
                FROM {SCHEMA}.tickets"""
        )
        row = cur.fetchone()
        cur.execute(f"SELECT COUNT(*) AS c FROM {SCHEMA}.ticket_messages")
        row["messages"] = cur.fetchone()["c"]
        return row
