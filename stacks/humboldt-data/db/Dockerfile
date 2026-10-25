FROM postgis/postgis:17-3.5

# PGDG retired Bullseye in September 2026. Use its official signed archive
# without changing the PostgreSQL/PostGIS base or the inherited signing key.
# This compatibility repair does not restore updates for the retired base.
RUN sed -i \
        's|http://apt.postgresql.org/pub/repos/apt|https://apt-archive.postgresql.org/pub/repos/apt|' \
        /etc/apt/sources.list.d/pgdg.list \
    && grep -q 'https://apt-archive.postgresql.org/pub/repos/apt' /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-17-pgvector \
    && rm -rf /var/lib/apt/lists/*
