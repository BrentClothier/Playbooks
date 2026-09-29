from __future__ import annotations

import os
from typing import Any

import psycopg
from psycopg.types.json import Jsonb


def database_dsn() -> str:
    return (
        f"host={os.environ.get('DATABASE_HOST', 'db')} "
        f"port={os.environ.get('DATABASE_PORT', '5432')} "
        f"dbname={os.environ.get('DATABASE_NAME', 'humboldt')} "
        f"user={os.environ.get('DATABASE_USER', 'humboldt_admin')} "
        f"password={os.environ['DATABASE_PASSWORD']}"
    )


def connect() -> psycopg.Connection:
    return psycopg.connect(database_dsn(), connect_timeout=15)


def ensure_source(
    conn: psycopg.Connection,
    *,
    source_key: str,
    name: str,
    agency: str,
    source_type: str,
    base_url: str,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO core.sources (
                source_key, name, agency, source_type, base_url
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (source_key) DO UPDATE
            SET name = EXCLUDED.name,
                agency = EXCLUDED.agency,
                source_type = EXCLUDED.source_type,
                base_url = EXCLUDED.base_url,
                updated_at = now()
            RETURNING id
            """,
            (source_key, name, agency, source_type, base_url),
        )
        return int(cur.fetchone()[0])


def start_run(
    conn: psycopg.Connection,
    source_id: int,
    metadata: dict[str, Any] | None = None,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit.ingest_runs (source_id, metadata)
            VALUES (%s, %s)
            RETURNING id
            """,
            (source_id, Jsonb(metadata or {})),
        )
        return int(cur.fetchone()[0])


def finish_run(
    conn: psycopg.Connection,
    run_id: int,
    *,
    status: str,
    records_seen: int,
    records_written: int,
    error_message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE audit.ingest_runs
            SET finished_at = now(),
                status = %s,
                records_seen = %s,
                records_written = %s,
                error_message = %s,
                metadata = metadata || %s
            WHERE id = %s
            """,
            (
                status,
                records_seen,
                records_written,
                error_message,
                Jsonb(metadata or {}),
                run_id,
            ),
        )
