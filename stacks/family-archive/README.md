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
- Gramps database, users, secret, index, thumbnails, and cache
- Valkey data and temporary working data

This keeps database I/O off NFS. Database exports still need to be copied into the NFS `backups` directories as part of the backup workflow.

## NFS prerequisite on docker-vm01

The Compose file defines the NFS mounts, but the Docker host still needs Linux NFS client support. On Debian or Ubuntu:

```bash
sudo apt update
sudo apt install -y nfs-common
```

The NFS server must export `/data/apps/family-archive` or allow its subdirectories to be mounted by `docker-vm01`. If the server presents a different NFSv4 path, change `NFS_EXPORT_ROOT` in Portainer.

## Portainer deployment

1. Confirm the directories under `/data/apps/family-archive` already exist on the NFS server.
2. Confirm `docker-vm01` can reach TCP port 2049 on `192.168.86.82`.
3. Create a Portainer Git stack using `stacks/family-archive/docker-compose.yml`.
4. Copy the variables from `.env.example` into the Portainer stack environment.
5. Replace `IMMICH_DB_PASSWORD` with a strong alphanumeric secret.
6. Deploy the stack.
7. Open Immich on port `2283` and create its initial administrator.
8. In Immich, add `/external/archive` as an external library when ready.
9. Open Gramps Web on port `5000` and complete its first-run wizard.

## Backups

- Back up the Immich PostgreSQL database to `/data/apps/family-archive/backups/immich`.
- Export Gramps packages or database backups to `/data/apps/family-archive/backups/gramps`.
- Snapshot the NFS dataset and keep at least one encrypted offsite copy.

A copy of the Immich media directory alone is not a complete Immich backup. Preserve both the media and PostgreSQL database.
