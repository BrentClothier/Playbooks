# Family Archive

A single Docker Compose stack containing:

- **Immich** for the complete family photo and video library.
- **Gramps Web** for the family tree, relationships, sources, stories, and selected historical media.

The applications share a Compose project and Docker network, but they do not synchronize media or genealogy data automatically.

## Storage layout

The defaults create bind-mounted application data below:

```text
/mnt/data/apps/family-archive/
├── immich/
│   ├── library/
│   └── postgres/
└── gramps/
    ├── cache/
    ├── database/
    ├── index/
    ├── media/
    ├── secret/
    ├── thumbnails/
    └── users/
```

Immich's complete library and Gramps Web's curated media are deliberately separate. Do not point both applications at the same writable media directory.

## Portainer deployment

1. Create the storage directories on the Docker host.
2. Create a Portainer Git stack using `stacks/family-archive/docker-compose.yml`.
3. Copy the variables from `.env.example` into the Portainer stack environment.
4. Replace `IMMICH_DB_PASSWORD` with a strong alphanumeric secret.
5. Deploy the stack.
6. Open Immich on port `2283` and create its initial administrator.
7. Open Gramps Web on port `5000` and complete its first-run wizard.

Change the host ports in Portainer if either default is already in use. Put both applications behind HTTPS before exposing them outside the local network.

## Backups

Back up all bind-mounted directories. The critical data is:

- Immich library directory
- Immich PostgreSQL database
- Gramps database, users, secret, media, and index directories

A snapshot or copy of the Immich media directory alone is not a complete Immich backup. Preserve both the media and PostgreSQL data, and keep at least one encrypted offsite copy of the family archive.

## Updating

Immich sometimes changes its required Compose services or database image. Before changing `IMMICH_VERSION`, compare this stack with the Compose file published for the target Immich release. Gramps Web follows its official `latest` image by default; set `GRAMPSWEB_VERSION` to a specific tag if you prefer controlled upgrades.
