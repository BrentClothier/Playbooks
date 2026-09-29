# ADR 0004: Git and IaC as the Infrastructure Source of Truth

Status: Accepted

## Context

The HomeLab contains a mix of manually managed Portainer stacks, existing
automation, and newer Git-backed infrastructure. This makes recovery,
maintenance, and autonomous assistance harder because not all deployed state
can be reconstructed from source control.

## Decision

Move progressively toward GitHub as the source of truth for reproducible,
non-secret infrastructure configuration:

- Docker Compose definitions;
- Ansible playbooks;
- OpenTofu;
- configuration templates;
- validation and deployment workflows.

Mutable application data, databases, media, and secrets do not belong in the
public Git repository and remain on persistent storage.

ChatGPT/MCP, Semaphore, and future isolated Codex jobs are explicitly intended
to help perform this migration.

## Backup consequence

The NFS storage LXC currently contains the authoritative user data and does not
yet have an independent backup because secondary capacity is insufficient.

Infrastructure-as-code can make compute/configuration replaceable, but it does
not replace data backups. Proxmox Backup Server may eventually be retired only
after the environment is reproducible and the authoritative NFS data has an
independent backup strategy.

## Operational consequence

When touching an older manually managed workload, prefer improving its
declarative representation in Git rather than introducing another one-off
manual configuration.
