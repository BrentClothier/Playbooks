from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, Query

from .db import connect


app = FastAPI(
    title="Humboldt Government Intelligence Query API",
    description=(
        "Read-only API over ingested Humboldt County public records. "
        "No state-changing endpoints are exposed."
    ),
    version="1.0.0",
)


def _fetch_all(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())


@app.get("/health")
def health() -> dict[str, Any]:
    rows = _fetch_all(
        """
        SELECT
            (SELECT count(*) FROM gov.meetings) AS meetings,
            (SELECT count(*) FROM gov.agenda_items) AS agenda_items,
            (SELECT count(*) FROM gis.residential_zoning) AS zoning_features,
            (
                SELECT max(finished_at)
                FROM audit.ingest_runs
                WHERE status = 'success'
            ) AS last_successful_ingest
        """
    )
    return {"status": "ok", **rows[0]}


@app.get("/v1/meetings")
def meetings(
    days_back: int = Query(default=90, ge=1, le=3650),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT
            event_id,
            body_name,
            event_date,
            event_time,
            location,
            agenda_status,
            minutes_status,
            agenda_url,
            minutes_url,
            video_url,
            insite_url
        FROM gov.meetings
        WHERE event_date >= CURRENT_DATE - (%s * INTERVAL '1 day')
          AND event_date <= CURRENT_DATE
        ORDER BY event_date DESC, event_id DESC
        LIMIT %s
        """,
        (days_back, limit),
    )


@app.get("/v1/agenda/search")
def agenda_search(
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=25, ge=1, le=100),
) -> list[dict[str, Any]]:
    pattern = f"%{q}%"
    return _fetch_all(
        """
        SELECT
            i.event_item_id,
            i.agenda_number,
            i.agenda_sequence,
            i.title,
            i.agenda_note,
            i.minutes_note,
            i.action_name,
            i.action_text,
            m.event_id,
            m.body_name,
            m.event_date,
            m.agenda_url,
            m.minutes_url,
            m.insite_url
        FROM gov.agenda_items AS i
        JOIN gov.meetings AS m
          ON m.event_id = i.meeting_event_id
        WHERE COALESCE(i.title, '') ILIKE %s
           OR COALESCE(i.agenda_note, '') ILIKE %s
           OR COALESCE(i.minutes_note, '') ILIKE %s
           OR COALESCE(i.action_text, '') ILIKE %s
        ORDER BY m.event_date DESC, i.agenda_sequence NULLS LAST
        LIMIT %s
        """,
        (pattern, pattern, pattern, pattern, limit),
    )


@app.get("/v1/zoning")
def zoning(
    parcel: str | None = Query(default=None, max_length=20),
    zone: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, Any]]:
    conditions = []
    params: list[Any] = []

    if parcel:
        conditions.append("parcel ILIKE %s")
        params.append(f"%{parcel}%")
    if zone:
        conditions.append("zone ILIKE %s")
        params.append(f"%{zone}%")

    where_clause = " AND ".join(conditions) if conditions else "TRUE"
    params.append(limit)

    return _fetch_all(
        f"""
        SELECT
            object_id,
            parcel,
            zone,
            description,
            ST_AsGeoJSON(ST_Centroid(geom))::jsonb AS centroid,
            retrieved_at
        FROM gis.residential_zoning
        WHERE {where_clause}
        ORDER BY parcel NULLS LAST, object_id
        LIMIT %s
        """,
        tuple(params),
    )


@app.get("/v1/ingest-runs")
def ingest_runs(
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT
            r.id,
            s.source_key,
            s.name AS source_name,
            r.started_at,
            r.finished_at,
            r.status,
            r.records_seen,
            r.records_written,
            r.error_message
        FROM audit.ingest_runs AS r
        LEFT JOIN core.sources AS s
          ON s.id = r.source_id
        ORDER BY r.started_at DESC
        LIMIT %s
        """,
        (limit,),
    )
