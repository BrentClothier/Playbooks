from __future__ import annotations

import json
from typing import Any

import httpx
from psycopg.types.json import Jsonb
from tenacity import retry, stop_after_attempt, wait_exponential

from .db import connect, ensure_source, finish_run, start_run


ZONING_LAYER = (
    "https://cty-gis-web.co.humboldt.ca.us/server/rest/services/"
    "Parcels/Parcels/MapServer/0"
)
# Preserve the existing source key so the corrected ingest replaces the
# previously imported records instead of leaving a second stale dataset behind.
SOURCE_KEY = "humboldt-arcgis-residential-zoning"
USER_AGENT = "HumboldtGovernmentIntelligence/1.0 (+public-records-research)"

# Broad guardrail around Humboldt County. The ArcGIS query requests WGS84
# geometry, so a coordinate outside this box almost certainly indicates that
# the wrong public GIS service was configured.
HUMBOLDT_BOUNDS = (-124.6, 39.8, -123.2, 41.7)


def _first_coordinate(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, list):
        return None
    if (
        len(value) >= 2
        and isinstance(value[0], (int, float))
        and isinstance(value[1], (int, float))
    ):
        return float(value[0]), float(value[1])
    for item in value:
        coordinate = _first_coordinate(item)
        if coordinate is not None:
            return coordinate
    return None


def _validate_humboldt_geometry(geometry: dict[str, Any]) -> None:
    coordinate = _first_coordinate(geometry.get("coordinates"))
    if coordinate is None:
        raise RuntimeError("ArcGIS zoning geometry did not contain coordinates.")

    longitude, latitude = coordinate
    min_lon, min_lat, max_lon, max_lat = HUMBOLDT_BOUNDS
    if not (min_lon <= longitude <= max_lon and min_lat <= latitude <= max_lat):
        raise RuntimeError(
            "ArcGIS zoning source returned geometry outside Humboldt County "
            f"(sample coordinate {longitude}, {latitude})."
        )


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
            "outFields": "OBJECTID,APN_12,ZONING,DESCRIPTIO",
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
    geometry_validated = False

    conn = connect()
    try:
        source_id = ensure_source(
            conn,
            source_key=SOURCE_KEY,
            name="Humboldt County Parcel Zoning",
            agency="County of Humboldt",
            source_type="arcgis-map-layer",
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
                        if geometry and not geometry_validated:
                            if not isinstance(geometry, dict):
                                raise RuntimeError(
                                    "ArcGIS zoning geometry was not an object."
                                )
                            _validate_humboldt_geometry(geometry)
                            geometry_validated = True

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
                                props.get("APN_12"),
                                props.get("ZONING"),
                                props.get("DESCRIPTIO"),
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

        if not geometry_validated:
            raise RuntimeError("ArcGIS zoning source returned no usable geometry.")

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
