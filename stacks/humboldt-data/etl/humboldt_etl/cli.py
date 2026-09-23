from __future__ import annotations

import argparse
import os

import psycopg


def database_dsn() -> str:
    return (
        f"host={os.environ.get('DATABASE_HOST', 'db')} "
        f"port={os.environ.get('DATABASE_PORT', '5432')} "
        f"dbname={os.environ.get('DATABASE_NAME', 'humboldt')} "
        f"user={os.environ.get('DATABASE_USER', 'humboldt_admin')} "
        f"password={os.environ['DATABASE_PASSWORD']}"
    )


def db_health() -> None:
    with psycopg.connect(database_dsn(), connect_timeout=10) as conn:
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Humboldt Government Intelligence ETL utility"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "db-health",
        help="Verify PostgreSQL, PostGIS, and pgvector connectivity.",
    )

    args = parser.parse_args()
    if args.command == "db-health":
        db_health()


if __name__ == "__main__":
    main()
