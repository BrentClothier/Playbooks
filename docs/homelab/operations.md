# Operations, Safety Rules, and Known Issues

## High-level operating rules

1. Prefer declarative changes in Git over one-off manual changes.
2. Prefer Semaphore for controlled writes.
3. Query live state before making assumptions about runtime status.
4. Do not expose arbitrary shell, SSH, or Docker-socket access to ChatGPT.
5. Never commit secrets to this repository.
6. Do not treat a successful API response as proof of an asynchronous deployment; verify final state.
7. Treat Git/IaC as the target source of truth for reproducible infrastructure.
8. Preserve the NFS storage LXC as the current authoritative user-data tier; infrastructure reproducibility does not replace data backup.

## Portainer incident and lesson

A previous Portainer redeploy path on an older server version resulted in stack environment metadata being lost. A subsequent generic stack update also converted the HomeLab MCP stack away from its original Git-backed representation.

The recovery led to several permanent rules:

- do not send an empty Env array as a repair strategy;
- use the dedicated Git-redeploy endpoint only for eligible Git stacks;
- fail closed on untested Portainer versions;
- compare environment metadata and Git identity before/after;
- never have `homelab-mcp` redeploy itself through the tunnel it is currently serving.

Portainer server and active agents were subsequently updated to 2.45.1 and the guarded path was successfully tested against `family-archive`.

## Current transition goal

The HomeLab is actively moving from manually configured workloads toward a reproducible Git/IaC model. ChatGPT, Semaphore, MCP, and future Codex jobs are intended to accelerate that migration.

The practical target is:

```text
GitHub definitions -> Semaphore/Codex validation -> controlled deployment
                                      |
                                      +-> live-state verification
```

Manual Portainer stacks should gradually become Git-backed where appropriate. Secrets and mutable application data must stay outside the public repository.

## Current known issues / cleanup candidates

- `homelab-mcp` remains editor-managed in Portainer. Its Compose source is still in Git, but restoring a clean Git-backed Portainer association is a future housekeeping task.
- Paperless LXC 103 has been retired and removed from Proxmox. Stale Portainer endpoint/stack metadata may remain until it is deleted from Portainer.
- Some workloads are historical/manual Portainer stacks rather than Git-backed stacks.
- Redis/Valkey on Family Archive has reported the common Linux `vm.overcommit_memory` warning. This is worth fixing on the Docker host when that project resumes.
- The Humboldt data platform is provisioned and operational; current follow-up work is focused on meeting-date semantics and GIS geometry/data validation.
- The NFS storage LXC contains the real/authoritative data and currently has no independent backup due to storage-capacity limits.
- PBS is intended to be retired eventually, but only after infrastructure is reproducible and irreplaceable NFS data has an independent backup path.

## Change-risk model

Classify a proposed operation mentally before executing:

- **read-only:** inspect health, logs, config metadata;
- **reversible:** restart/redeploy an application with preserved persistence;
- **infrastructure-changing:** create/delete VM, modify storage/network, apply IaC;
- **destructive:** delete volumes, data, backups, credentials, or state.

The higher the class, the more explicit the verification and rollback plan should be.
