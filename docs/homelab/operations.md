# Operations, Safety Rules, and Known Issues

## High-level operating rules

1. Prefer declarative changes in Git over one-off manual changes.
2. Prefer Semaphore for controlled writes.
3. Query live state before making assumptions about runtime status.
4. Do not expose arbitrary shell, SSH, or Docker-socket access to ChatGPT.
5. Never commit secrets to this repository.
6. Do not treat a successful API response as proof of an asynchronous deployment; verify final state.

## Portainer incident and lesson

A previous Portainer redeploy path on an older server version resulted in stack environment metadata being lost. A subsequent generic stack update also converted the HomeLab MCP stack away from its original Git-backed representation.

The recovery led to several permanent rules:

- do not send an empty Env array as a repair strategy;
- use the dedicated Git-redeploy endpoint only for eligible Git stacks;
- fail closed on untested Portainer versions;
- compare environment metadata and Git identity before/after;
- never have `homelab-mcp` redeploy itself through the tunnel it is currently serving.

Portainer server and active agents were subsequently updated to 2.45.1 and the guarded path was successfully tested against `family-archive`.

## Current known issues / cleanup candidates

- `homelab-mcp` remains editor-managed in Portainer. Its Compose source is still in Git, but restoring a clean Git-backed Portainer association is a future housekeeping task.
- The Paperless LXC/environment is intentionally stopped and may be removed after confirming no retained data is needed.
- Some workloads are historical/manual Portainer stacks rather than Git-backed stacks.
- Redis/Valkey on Family Archive has reported the common Linux `vm.overcommit_memory` warning. This is worth fixing on the Docker host when that project resumes.
- The Humboldt data platform is designed but not yet provisioned.

## Change-risk model

Classify a proposed operation mentally before executing:

- **read-only:** inspect health, logs, config metadata;
- **reversible:** restart/redeploy an application with preserved persistence;
- **infrastructure-changing:** create/delete VM, modify storage/network, apply IaC;
- **destructive:** delete volumes, data, backups, credentials, or state.

The higher the class, the more explicit the verification and rollback plan should be.
