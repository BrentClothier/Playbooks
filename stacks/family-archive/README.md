# Family Archive

A single Docker Compose stack containing Immich and Gramps Web.

## Storage design

Docker mounts the remote NFS directories directly from the Compose file. No permanent host mount or `/etc/fstab` entry is required.

The default NFS server is `192.168.86.82`, and the remote root is:

```text
/data/apps/family-archive/
├── archive/             # mounted read-only in Immich at /external/archive
├── immich/library/      # writable Immich library
└── gramps/media/        # writable curated Gramps media
```

The following active application data stays in Docker-managed local volumes on `docker-vm01`:

- Immich PostgreSQL database
- Immich machine-learning cache
- Gramps PostgreSQL genealogy database
- Gramps PostgreSQL user database and search index
- Gramps tree connection metadata, secret, thumbnails, and cache
- Valkey data and temporary working data

This keeps database I/O off NFS. Database exports still need to be copied into the NFS `backups` directories as part of the backup workflow.

## Gramps PostgreSQL design

Gramps uses the specialized `ghcr.io/davidmstraub/gramps-postgres` image recommended by the Gramps Web documentation. The stack stores:

- Genealogy data in PostgreSQL database `postgres` using user `gramps`
- Gramps Web accounts in PostgreSQL database `grampswebuser`
- The Gramps search index in the `postgres` database

Before deploying, copy the exported Gramps XML file to:

```text
/data/apps/family-archive/backups/gramps/family-tree.gramps
```

The one-shot `grampsweb-db-init` service imports that file into PostgreSQL the first time the stack starts. It exits successfully after initialization and skips the import on later redeployments.

## Portainer deployment

1. Copy the exported tree to `/data/apps/family-archive/backups/gramps/family-tree.gramps` on the NFS server.
2. Add the PostgreSQL variables from `.env.example` to the existing Portainer stack.
3. Replace every `change-me` value with a unique alphanumeric secret.
4. Redeploy the stack and wait for `grampsweb-db-init` to exit with status 0.
5. Open Gramps Web and create a new owner account. The previous SQLite user database is intentionally not reused.

Generate the three Gramps PostgreSQL passwords with:

```bash
openssl rand -hex 32
openssl rand -hex 32
openssl rand -hex 32
```

## Removing the retired SQLite volumes

After PostgreSQL is running and the imported tree has been verified, remove the retired volumes from `docker-vm01`:

```bash
docker volume rm \
  family-archive_grampsweb_database \
  family-archive_grampsweb_users \
  family-archive_grampsweb_index
```

List the exact names first if Portainer used a different prefix:

```bash
docker volume ls --format '{{.Name}}' | grep grampsweb
```

## Backups

- Back up the Immich PostgreSQL database to `/data/apps/family-archive/backups/immich`.
- Back up the `gramps_postgres_data` volume and continue periodic Gramps XML exports to `/data/apps/family-archive/backups/gramps`.
- Snapshot the NFS dataset and keep at least one encrypted offsite copy.
