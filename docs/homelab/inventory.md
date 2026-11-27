# Logical Inventory

Reviewed November 27, 2026; not live telemetry.

| Role | Platform / lifecycle |
| --- | --- |
| Primary storage and future apps | Bare-metal TrueNAS, former proxmox2; pool imported intact |
| Legacy compute | Proxmox1 and Proxmox3; verify live guests and quorum |
| Management | Existing admin Docker host, HomeLab MCP, outbound tunnel, Semaphore and Portainer; retain until replacement verified |
| Network | UniFi Network/Protect; Tailscale native TrueNAS app, Nginx Proxy Manager retained for local access |
| Backup | Independent USB SSD on TrueNAS; selected files and app data |
| Future gaming | Proxmox3 eventually bare-metal Linux Mint, normally off |

## Application migration

Fresh Semaphore + PostgreSQL first, then management services, Plex (Intel Quick Sync), Audiobookshelf, Servarr, RomM/MariaDB, Nginx Proxy Manager, MinIO if needed. Rebuild Humboldt and Home Assistant OS VM later. Tailscale was the sole native app in the November 27 live check; dedicated appdata hierarchy was absent. Verify current inventory rather than assume this persists. Authentik retention depends on actual SSO dependencies. Mealie intentionally stopped, Family Archive and Paperless retired; do not recreate without request. Unknown guest IDs 109/111 are not confirmed cleanup candidates. Never delete the old NFS backing dataset. No self-redeployment of HomeLab MCP.
