# Authentik stack

This stack is intended to be deployed from Portainer as a Git-backed stack.

## Compose path

`stacks/auth/authentik/docker-compose.yml`

## Required environment variables

- `AUTHENTIK_VERSION`
- `AUTHENTIK_SECRET_KEY`
- `PG_DB`
- `PG_USER`
- `PG_PASSWORD`

## Storage layout

### NFS-backed app files

- `/mnt/data/apps/auth/authentik/config`
- `/mnt/data/apps/auth/authentik/data/media`
- `/mnt/data/apps/auth/authentik/logs`
- `/mnt/data/apps/auth/authentik/backups`

### Local Docker volumes

- `authentik_postgres`
- `authentik_redis`

## Reverse proxy

Expected external URL:

- `https://auth.clothiernet.duckdns.org`
