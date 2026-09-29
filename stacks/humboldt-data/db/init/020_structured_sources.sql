CREATE SCHEMA IF NOT EXISTS gov;
CREATE SCHEMA IF NOT EXISTS gis;

CREATE TABLE IF NOT EXISTS gov.meetings (
    event_id                 BIGINT PRIMARY KEY,
    source_id                BIGINT NOT NULL REFERENCES core.sources(id),
    event_guid               TEXT,
    body_id                  BIGINT,
    body_name                TEXT,
    event_date               DATE,
    event_time               TEXT,
    location                 TEXT,
    agenda_status            TEXT,
    minutes_status           TEXT,
    agenda_url               TEXT,
    minutes_url              TEXT,
    video_url                TEXT,
    insite_url               TEXT,
    last_modified_at         TIMESTAMPTZ,
    retrieved_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw                      JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS meetings_event_date_idx
    ON gov.meetings (event_date DESC);

CREATE INDEX IF NOT EXISTS meetings_raw_gin_idx
    ON gov.meetings USING gin (raw);

CREATE TABLE IF NOT EXISTS gov.agenda_items (
    event_item_id            BIGINT PRIMARY KEY,
    meeting_event_id         BIGINT NOT NULL REFERENCES gov.meetings(event_id)
                                ON DELETE CASCADE,
    event_item_guid          TEXT,
    matter_id                BIGINT,
    agenda_number            TEXT,
    agenda_sequence          INTEGER,
    title                    TEXT,
    agenda_note              TEXT,
    minutes_note             TEXT,
    action_name              TEXT,
    action_text              TEXT,
    last_modified_at         TIMESTAMPTZ,
    retrieved_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw                      JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS agenda_items_meeting_idx
    ON gov.agenda_items (meeting_event_id);

CREATE INDEX IF NOT EXISTS agenda_items_title_trgm_idx
    ON gov.agenda_items USING gin (title gin_trgm_ops);

CREATE INDEX IF NOT EXISTS agenda_items_agenda_note_trgm_idx
    ON gov.agenda_items USING gin (agenda_note gin_trgm_ops);

CREATE INDEX IF NOT EXISTS agenda_items_minutes_note_trgm_idx
    ON gov.agenda_items USING gin (minutes_note gin_trgm_ops);

CREATE TABLE IF NOT EXISTS gov.agenda_item_attachments (
    id                       BIGSERIAL PRIMARY KEY,
    event_item_id            BIGINT NOT NULL REFERENCES gov.agenda_items(event_item_id)
                                ON DELETE CASCADE,
    external_id              TEXT NOT NULL,
    name                     TEXT,
    hyperlink                TEXT,
    file_name                TEXT,
    raw                      JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (event_item_id, external_id)
);

CREATE TABLE IF NOT EXISTS gis.residential_zoning (
    object_id                BIGINT PRIMARY KEY,
    source_id                BIGINT NOT NULL REFERENCES core.sources(id),
    parcel                   TEXT,
    zone                     TEXT,
    description              TEXT,
    attributes               JSONB NOT NULL DEFAULT '{}'::jsonb,
    geom                     geometry(MultiPolygon, 4326),
    ingest_run_id            BIGINT REFERENCES audit.ingest_runs(id),
    retrieved_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS residential_zoning_parcel_idx
    ON gis.residential_zoning (parcel);

CREATE INDEX IF NOT EXISTS residential_zoning_zone_idx
    ON gis.residential_zoning (zone);

CREATE INDEX IF NOT EXISTS residential_zoning_geom_idx
    ON gis.residential_zoning USING gist (geom);

CREATE INDEX IF NOT EXISTS residential_zoning_attributes_gin_idx
    ON gis.residential_zoning USING gin (attributes);
