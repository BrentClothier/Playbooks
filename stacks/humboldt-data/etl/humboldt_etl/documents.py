from __future__ import annotations

import hashlib
import mimetypes
import os
import re
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

import boto3
import httpx
from botocore.config import Config
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .db import connect, finish_run, start_run


USER_AGENT = "HumboldtGovernmentIntelligence/1.0 (+public-records-research)"
LEGISTAR_WEB_BASE = "https://humboldt.legistar.com/"
SOURCE_KEY = "humboldt-legistar"


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not configured.")
    return value


def _safe_filename(value: str | None, source_url: str) -> str:
    candidate = (value or "").strip()
    if not candidate:
        candidate = PurePosixPath(unquote(urlparse(source_url).path)).name
    if not candidate:
        candidate = "attachment.bin"
    candidate = re.sub(r"[^A-Za-z0-9._() -]+", "_", candidate).strip(" .")
    return candidate[:180] or "attachment.bin"


def _absolute_url(value: str | None) -> str | None:
    if not value:
        return None
    url = value.strip()
    if not url:
        return None
    if url.startswith(("http://", "https://")):
        return url
    return urljoin(LEGISTAR_WEB_BASE, url)


def _s3_client() -> Any:
    return boto3.client(
        "s3",
        endpoint_url=_required_env("MINIO_ENDPOINT"),
        aws_access_key_id=_required_env("MINIO_ACCESS_KEY"),
        aws_secret_access_key=_required_env("MINIO_SECRET_KEY"),
        region_name="us-east-1",
        config=Config(signature_version="s3v4", retries={"max_attempts": 4}),
    )


def sync_legistar_attachments(limit: int = 100) -> dict[str, int]:
    if limit < 1:
        raise ValueError("limit must be at least 1")

    bucket = _required_env("MINIO_BUCKET")
    max_bytes = int(os.environ.get("MAX_DOCUMENT_BYTES", str(100 * 1024 * 1024)))

    conn = connect()
    seen = 0
    written = 0
    skipped = 0
    failed = 0
    errors: list[str] = []

    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id
                FROM core.sources
                WHERE source_key = %s
                """,
                (SOURCE_KEY,),
            )
            source = cur.fetchone()
            if not source:
                raise RuntimeError("Legistar source is not registered.")
            source_id = int(source["id"])

        run_id = start_run(
            conn,
            source_id,
            {"kind": "legistar-attachments", "limit": limit, "bucket": bucket},
        )
        conn.commit()

        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    a.id AS attachment_id,
                    a.event_item_id,
                    a.external_id AS attachment_external_id,
                    a.name,
                    a.hyperlink,
                    a.file_name,
                    i.title AS agenda_title,
                    i.agenda_number,
                    m.event_id,
                    m.event_date,
                    m.body_name
                FROM gov.agenda_item_attachments AS a
                JOIN gov.agenda_items AS i
                  ON i.event_item_id = a.event_item_id
                JOIN gov.meetings AS m
                  ON m.event_id = i.meeting_event_id
                WHERE NULLIF(BTRIM(COALESCE(a.hyperlink, '')), '') IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM core.documents AS d
                      WHERE d.source_id = m.source_id
                        AND d.external_id = (
                            'agenda-attachment:' || a.event_item_id::text || ':' || a.external_id
                        )
                        AND d.object_key IS NOT NULL
                        AND d.sha256 IS NOT NULL
                  )
                ORDER BY m.event_date DESC, a.event_item_id, a.id
                LIMIT %s
                """,
                (limit,),
            )
            rows = list(cur.fetchall())

        if not rows:
            finish_run(
                conn,
                run_id,
                status="success",
                records_seen=0,
                records_written=0,
                metadata={"skipped": 0, "failed": 0},
            )
            conn.commit()
            return {"seen": 0, "written": 0, "skipped": 0, "failed": 0}

        s3 = _s3_client()

        with httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(90.0),
            follow_redirects=True,
        ) as client:
            for row in rows:
                seen += 1
                source_url = _absolute_url(row["hyperlink"])
                if not source_url:
                    skipped += 1
                    continue

                external_id = (
                    f"agenda-attachment:{row['event_item_id']}:"
                    f"{row['attachment_external_id']}"
                )

                try:
                    response = client.get(source_url)
                    response.raise_for_status()
                    content = response.content
                    if len(content) > max_bytes:
                        raise RuntimeError(
                            f"attachment exceeds {max_bytes} byte safety limit"
                        )

                    content_type = (
                        response.headers.get("content-type", "")
                        .split(";", 1)[0]
                        .strip()
                        or None
                    )
                    filename = _safe_filename(row["file_name"], source_url)
                    if "." not in filename and content_type:
                        extension = mimetypes.guess_extension(content_type) or ""
                        filename += extension

                    digest = hashlib.sha256(content).hexdigest()
                    event_date = row["event_date"]
                    date_path = event_date.isoformat() if event_date else "undated"
                    object_key = (
                        f"legistar/{date_path}/{row['event_id']}/"
                        f"{row['event_item_id']}/{row['attachment_id']}-{filename}"
                    )

                    put_args: dict[str, Any] = {
                        "Bucket": bucket,
                        "Key": object_key,
                        "Body": content,
                        "Metadata": {
                            "sha256": digest,
                            "event-id": str(row["event_id"]),
                            "event-item-id": str(row["event_item_id"]),
                            "attachment-id": str(row["attachment_id"]),
                        },
                    }
                    if content_type:
                        put_args["ContentType"] = content_type
                    s3.put_object(**put_args)

                    title = (
                        (row["name"] or "").strip()
                        or (row["file_name"] or "").strip()
                        or (row["agenda_title"] or "").strip()
                        or filename
                    )

                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO core.documents (
                                source_id, external_id, title, document_type, agency,
                                reporting_period, source_url, object_key, sha256,
                                retrieved_at, metadata
                            )
                            VALUES (
                                %s, %s, %s, %s, %s,
                                %s, %s, %s, %s,
                                now(), %s
                            )
                            ON CONFLICT (source_id, external_id) DO UPDATE
                            SET title = EXCLUDED.title,
                                document_type = EXCLUDED.document_type,
                                agency = EXCLUDED.agency,
                                reporting_period = EXCLUDED.reporting_period,
                                source_url = EXCLUDED.source_url,
                                object_key = EXCLUDED.object_key,
                                sha256 = EXCLUDED.sha256,
                                retrieved_at = now(),
                                metadata = EXCLUDED.metadata
                            """,
                            (
                                source_id,
                                external_id,
                                title,
                                "legistar-attachment",
                                "County of Humboldt",
                                str(event_date.year) if event_date else None,
                                source_url,
                                object_key,
                                digest,
                                Jsonb(
                                    {
                                        "event_id": row["event_id"],
                                        "event_date": (
                                            event_date.isoformat() if event_date else None
                                        ),
                                        "body_name": row["body_name"],
                                        "event_item_id": row["event_item_id"],
                                        "agenda_number": row["agenda_number"],
                                        "agenda_title": row["agenda_title"],
                                        "attachment_id": row["attachment_id"],
                                        "attachment_external_id": row[
                                            "attachment_external_id"
                                        ],
                                        "file_name": filename,
                                        "content_type": content_type,
                                        "bytes": len(content),
                                        "bucket": bucket,
                                    }
                                ),
                            ),
                        )
                    conn.commit()
                    written += 1

                except Exception as exc:
                    conn.rollback()
                    failed += 1
                    if len(errors) < 10:
                        errors.append(
                            f"{row['attachment_id']}: {type(exc).__name__}: {exc}"
                        )

        status = "success" if failed == 0 else "partial"
        finish_run(
            conn,
            run_id,
            status=status,
            records_seen=seen,
            records_written=written,
            error_message="; ".join(errors)[:2000] if errors else None,
            metadata={"skipped": skipped, "failed": failed, "bucket": bucket},
        )
        conn.commit()
        return {
            "seen": seen,
            "written": written,
            "skipped": skipped,
            "failed": failed,
        }

    except Exception as exc:
        conn.rollback()
        if "run_id" in locals():
            finish_run(
                conn,
                run_id,
                status="error",
                records_seen=seen,
                records_written=written,
                error_message=str(exc)[:2000],
                metadata={"skipped": skipped, "failed": failed},
            )
            conn.commit()
        raise
    finally:
        conn.close()
