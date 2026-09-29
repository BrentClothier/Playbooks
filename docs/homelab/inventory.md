# Logical Inventory

This is a logical inventory, not a real-time monitoring dashboard. Runtime status should be queried from the relevant system.

## Proxmox nodes

| Node | Role |
| --- | --- |
| `proxmox1` | General Proxmox capacity |
| `proxmox2` | Primary HomeLab application/control workloads and major storage attachment |
| `proxmox3` | Application workloads, workstation VM, automation, and object storage |

All three nodes were online at the 2026-09-29 structured review.

## Important virtualized workloads

### proxmox2

- `admin-vm01` - administrative Docker host; HomeLab MCP runs here.
- `docker-vm01` - general Docker host.
- `NFS` - network file storage.
- `Nginx` - reverse-proxy workload.
- `Portainer` - Portainer server workload.
- `MealieAudioBooks` - application host.
- `audiobookshelf` - application host.
- `Home-Assistant` - currently stopped.
- `paperless-ngx` - currently stopped; cleanup candidate.
- `ha-vm01` - currently stopped.
- `ubuntu-2504-cloud-uefi-prep` - VM template used for provisioning.

### proxmox3

- `Servarr` - media-related services.
- `Linux-Mint` - high-resource desktop/workstation VM.
- `Ansible` - automation workload.
- `MinIO` - object storage.

## Portainer-managed stacks

Current important stacks include:

- `nginx`
- `emulator_js`
- `adiobookshelf_neo`
- `mealie_neo`
- `romm`
- `paperless-ngx`
- `qbittorrent`
- `plex`
- `ansible`
- `minio`
- `authentik`
- `romm-server`
- `family-archive`
- `homelab-mcp`

Git-backed stacks currently include `authentik`, `romm-server`, and `family-archive`.

`homelab-mcp` is currently editor-managed in Portainer even though its Compose source lives in Git. It must not self-redeploy through its own MCP action.

## Authentication

Authentik is the central self-hosted identity component for services that support OIDC.

## Network

UniFi Network provides gateway/switch/AP management and exports retained system events to HomeLab MCP for troubleshooting and health analysis.

## Inventory update policy

Do not add secret values or exact attack-surface details to this file. Prefer logical names and roles.
