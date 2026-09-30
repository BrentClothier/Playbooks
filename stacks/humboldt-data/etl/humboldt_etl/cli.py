from __future__ import annotations

import argparse
import json

from .arcgis import sync_residential_zoning
from .db import connect
from .documents import sync_legistar_attachments
from .legistar import sync_legistar


def db_health() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT current_database(),
                       postgis_full_version(),
                       extversion
                FROM pg_extension
                CROSS JOIN LATERAL (
                    SELECT postgis_full_version()
                ) AS p
                WHERE extname = 'vector'
                """
            )
            database, postgis_version, vector_version = cur.fetchone()
    print(
        f"database={database} postgis=ready "
        f"vector={vector_version} status=ok"
    )


def stats() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    (SELECT count(*) FROM gov.meetings),
                    (SELECT count(*) FROM gov.agenda_items),
                    (SELECT count(*) FROM gis.residential_zoning),
                    (SELECT count(*) FROM core.documents)
                """
            )
            meetings, agenda_items, zoning, documents = cur.fetchone()
    print(
        json.dumps(
            {
                "meetings": meetings,
                "agenda_items": agenda_items,
                "zoning_features": zoning,
                "documents": documents,
            },
            sort_keys=True,
        )
    )


def sync_all(days_back: int, document_limit: int) -> None:
    result = {
        "legistar": sync_legistar(days_back=days_back),
        "residential_zoning": sync_residential_zoning(),
        "documents": sync_legistar_attachments(limit=document_limit),
    }
    print(json.dumps(result, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Humboldt Government Intelligence ETL utility"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "db-health",
        help="Verify PostgreSQL, PostGIS, and pgvector connectivity.",
    )
    subparsers.add_parser(
        "stats",
        help="Show row counts for structured records and captured documents.",
    )

    legistar = subparsers.add_parser(
        "sync-legistar",
        help="Ingest recent Humboldt County Legistar meetings and agenda items.",
    )
    legistar.add_argument("--days-back", type=int, default=730)

    subparsers.add_parser(
        "sync-zoning",
        help="Ingest Humboldt County parcel zoning polygons from ArcGIS.",
    )

    documents = subparsers.add_parser(
        "sync-documents",
        help="Capture pending Legistar attachments into MinIO and register provenance.",
    )
    documents.add_argument("--limit", type=int, default=100)

    sync = subparsers.add_parser(
        "sync-all",
        help="Run structured ingestion plus a bounded document-capture batch.",
    )
    sync.add_argument("--legistar-days-back", type=int, default=730)
    sync.add_argument("--document-limit", type=int, default=100)

    args = parser.parse_args()

    if args.command == "db-health":
        db_health()
    elif args.command == "stats":
        stats()
    elif args.command == "sync-legistar":
        print(json.dumps(sync_legistar(days_back=args.days_back), sort_keys=True))
    elif args.command == "sync-zoning":
        print(json.dumps(sync_residential_zoning(), sort_keys=True))
    elif args.command == "sync-documents":
        print(json.dumps(sync_legistar_attachments(limit=args.limit), sort_keys=True))
    elif args.command == "sync-all":
        sync_all(
            days_back=args.legistar_days_back,
            document_limit=args.document_limit,
        )


if __name__ == "__main__":
    main()
