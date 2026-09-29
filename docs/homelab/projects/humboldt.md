# Humboldt Government Intelligence Data Platform

## Goal

Build a factual public-records research platform for Humboldt County government data.

The infrastructure is designed as:

```text
Public government sources
        |
Semaphore scheduled ETL
        |
PostgreSQL + PostGIS + pgvector
        |
read-only retrieval/MCP
        |
ChatGPT
```

The system should preserve provenance and make cross-source inconsistencies discoverable.

## Planned VM

Logical name: `humboldt-data01`

Planned placement:

- Proxmox node: `proxmox2`
- clone source: `ubuntu-2504-cloud-uefi-prep`
- storage: `USB_Storage_Space`
- 4 vCPU
- 6 GiB RAM
- 80 GiB system disk

Exact network addressing is deliberately omitted from this public documentation.

## IaC isolation

The project has a dedicated OpenTofu root:

`opentofu/humboldt/`

It uses separate state and must not be applied through the generic root OpenTofu configuration.

## Data services

The Compose stack under `stacks/humboldt-data/` now runs:

- PostgreSQL;
- PostGIS;
- pgvector;
- ETL worker image;
- a narrow read-only HTTP query API for structured public records.

The database itself is not published to the LAN. The query API exposes fixed,
parameterized read endpoints rather than arbitrary SQL.

Current schema concepts include:

- source registry;
- ingest-run auditing;
- document metadata;
- semantic chunks/vector search;
- provenance fields.

## First implemented sources

The initial structured ingestion set is:

- Humboldt County Legistar meetings, agenda items, minutes/action text, and
  attachment metadata;
- Humboldt County ArcGIS Residential Zoning polygons.

The County's official Board page points users to Humboldt Legistar for meeting
materials. County GIS data is planning/reference data and must not be treated
as legally authoritative for parcel-specific decisions.

## Intended sources

Additional examples include:

- Board of Supervisors / agenda systems;
- county GIS/ArcGIS;
- budgets, ACFRs, audits, and financial reports;
- California Controller data;
- Grand Jury reports;
- procurement/contracts/vendors;
- salary and labor-agreement data;
- planning/zoning;
- permits;
- grants/assets;
- County Code.

## Provenance requirement

Ingested records should retain enough metadata to answer where a fact came from, including where applicable:

- source URL/document identifier;
- agency;
- reporting period;
- retrieval timestamp;
- raw-object location;
- parser/version;
- ingestion job identifier.

## Automation

A dedicated Semaphore project is planned: `Humboldt Government Intelligence`.

Scoped templates will handle isolated OpenTofu provisioning and bootstrap automation. Generic HomeLab root apply templates must not be used for this project.

## Current status

The isolated VM has been provisioned and bootstrapped. PostgreSQL, PostGIS, and
pgvector have been verified.

The first ingestion/query implementation provides:

- repeatable Semaphore-driven public-data sync;
- audit records for each ingestion run;
- normalized Legistar meeting and agenda-item tables;
- PostGIS-backed residential zoning features;
- narrow read-only query endpoints;
- HomeLab MCP tools for status, meeting lookup, agenda search, zoning lookup,
  and ingest-run inspection.

## Next steps

1. validate the first live Legistar and ArcGIS ingestion runs;
2. schedule recurring public-data syncs in Semaphore;
3. add MinIO raw-document storage;
4. ingest agenda/document attachments and extract text;
5. add embedding generation and semantic retrieval;
6. expand to budgets, audits, contracts, finance, planning, and permits.
