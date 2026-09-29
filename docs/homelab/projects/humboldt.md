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

The Compose stack under `stacks/humboldt-data/` is designed around:

- PostgreSQL;
- PostGIS;
- pgvector;
- ETL worker image.

Current schema concepts include:

- source registry;
- ingest-run auditing;
- document metadata;
- semantic chunks/vector search;
- provenance fields.

## Intended sources

Examples include:

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

## Next steps

1. create/verify scoped Semaphore templates;
2. plan isolated OpenTofu root;
3. verify plan contains only Humboldt resources;
4. apply and bootstrap;
5. verify PostgreSQL/PostGIS/pgvector;
6. implement first collectors;
7. add MinIO raw-document storage;
8. expose read-only retrieval through MCP.
