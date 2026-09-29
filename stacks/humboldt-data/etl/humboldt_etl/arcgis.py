from __future__ import annotations

import json
from typing import Any

import httpx
from psycopg.types.json import Jsonb
from tenacity import retry, stop_after_attempt, wait_exponential

from .db import connect, ensure_source, finish_run, start_run


ZONING_LAYER = (
    "https://services1.arcgis.com/F1v0ufATbBQScMtY/ArcGIS/rest/services/"
    "Residential_Zoning/FeatureServer/17"
)
SOURCE_KEY = "humboldt-arcgis-residential-zoning"
USER_AGENT = "HumboldtGovernmentIntelligence/1.0 (+public-records-research)"


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _query_page(
    client: httpx.Client,
    *,
    offset: int,
    page_size: int,
) -> dict[str, Any]:
    response = client.get(
        f"{ZONING_LAYER}/query",
        params={
            "where": "1=1",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
            "orderByFields": "OBJECTID",
            "resultOffset": offset,
            "resultRecordCount": page_size,
            "f": "geojson",
        },
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("ArcGIS zoning query returned a non-object response.")
    if payload.get("error"):
        raise RuntimeError(f"ArcGIS zoning query failed: {payload['error']}")
    return payload


def sync_residential_zoning() -> dict[str, int]:
    seen = 0
    written = 0

    conn = connect()
    try:
        source_id = ensure_source(
            conn,
            source_key=SOURCE_KEY,
            name="Humboldt County Residential Zoning",
            agency="County of Humboldt",
            source_type="arcgis-feature-layer",
            base_url=ZONING_LAYER,
        )
        conn.commit()
        run_id = start_run(conn, source_id, {"layer": ZONING_LAYER})
        conn.commit()

        with httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json"},
            timeout=httpx.Timeout(60.0),
            follow_redirects=True,
        ) as client:
            offset = 0
            page_size = 1000

            while True:
                payload = _query_page(
                    client,
                    offset=offset,
                    page_size=page_size,
                )
                features = payload.get("features") or []
                if not isinstance(features, list) or not features:
                    break

                with conn.cursor() as cur:
                    for feature in features:
                        if not isinstance(feature, dict):
                            continue
                        props = feature.get("properties") or {}
                        if not isinstance(props, dict):
                            props = {}
                        object_id = props.get("OBJECTID")
                        if object_id is None:
                            continue

                        geometry = feature.get("geometry")
                        geometry_json = (
                            json.dumps(geometry, separators=(",", ":"))
                            if geometry
                            else None
                        )

                        cur.execute(
                            """
                            INSERT INTO gis.residential_zoning (
                                object_id, source_id, parcel, zone, description,
                                attributes, geom, ingest_run_id, retrieved_at
                            )
                            VALUES (
                                %s, %s, %s, %s, %s,
                                %s,
                                CASE
                                    WHEN %s::text IS NULL THEN NULL
                                    ELSE ST_Multi(
                                        ST_SetSRID(ST_GeomFromGeoJSON(%s::text), 4326)
                                    )
                                END,
                                %s, now()
                            )
                            ON CONFLICT (object_id) DO UPDATE
                            SET source_id = EXCLUDED.source_id,
                                parcel = EXCLUDED.parcel,
                                zone = EXCLUDED.zone,
                                description = EXCLUDED.description,
                                attributes = EXCLUDED.attributes,
                                geom = EXCLUDED.geom,
                                ingest_run_id = EXCLUDED.ingest_run_id,
                                retrieved_at = now()
                            """,
                            (
                                int(object_id),
                                source_id,
                                props.get("PARCEL"),
                                props.get("ZONE"),
                                props.get("DESCRIPTION"),
                                Jsonb(props),
                                geometry_json,
                                geometry_json,
                                run_id,
                            ),
                        )
                        seen += 1
                        written += 1

                conn.commit()
                offset += len(features)
                if len(features) < page_size:
                    break

        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM gis.residential_zoning
                WHERE source_id = %s
                  AND ingest_run_id IS DISTINCT FROM %s
                """,
                (source_id, run_id),
            )
        conn.commit()

        finish_run(
            conn,
            run_id,
            status="success",
            records_seen=seen,
            records_written=written,
        )
        conn.commit()
        return {"features_seen": seen, "features_written": written}

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
            )
            conn.commit()
        raise
    finally:
        conn.close()
