# HomeLab Architecture

## Design goals

The HomeLab is optimized for:

1. useful self-hosted services;
2. infrastructure-as-code and repeatable automation;
3. minimal public exposure;
4. controlled ChatGPT-assisted operations;
5. preserving clear human control over state-changing actions.

## Compute layer

The virtualization layer is a three-node Proxmox environment with deliberately
different hardware roles:

- `proxmox1` - a small adjacent node providing general capacity;
- `proxmox2` - the bottom 3U Core i5 chassis hosting primary application,
  control, and storage workloads;
- `proxmox3` - the retained small-form-factor gaming system, which also hosts
  selected application, automation, and workstation workloads.

The environment is not currently dependent on shared storage for cluster-style workload mobility. Workloads are generally placed intentionally on specific nodes.

High allocated RAM on `proxmox3` is not, by itself, evidence of memory pressure.
Its fixed allocation is intentional for gaming/workstation use; evaluate live
pressure and application health before proposing memory changes.

## Provisional consolidation direction

The current planning direction is to consolidate the storage and service roles
of `proxmox1` and `proxmox2` onto a bare-metal TrueNAS system, using native
Docker/custom Compose where appropriate, while retaining `proxmox3` for gaming
and selected workloads.

This is a provisional architecture direction, not an approved purchase or
migration. Workload placement, storage capacity, backup design, hardware
compatibility, and rollback/restore procedures must be validated before an
implementation plan is approved.

## Container layer

Docker workloads are distributed across several hosts and are observed through Portainer.

Important Docker hosts include:

- `admin-vm01` - administrative/control-plane workloads, including HomeLab MCP;
- `docker-vm01` - general Docker application host;
- dedicated application hosts for services such as AudioBookShelf, Mealie, Nginx, Servarr, Ansible, and MinIO.

Portainer is primarily an observability and controlled lifecycle interface. It is not the sole source of configuration truth.

## Automation/control plane

The preferred path for state changes is:

```text
ChatGPT
   |
Secure outbound MCP tunnel
   |
HomeLab MCP
   |
   +--> Proxmox (read-only)
   +--> Portainer (guarded operations)
   +--> UniFi (visibility/telemetry)
   +--> Semaphore (approved automation)
                         |
                         +--> Ansible / OpenTofu / operational playbooks
```

The tunnel is outbound-only from the HomeLab. The intent is to avoid exposing a general administrative endpoint to the public Internet.

## Source control

`BrentClothier/Playbooks` is the infrastructure repository. It contains:

- Ansible playbooks and inventories;
- OpenTofu configuration;
- Docker Compose stacks;
- HomeLab MCP source;
- this knowledge base.

Because the repository is public, infrastructure documentation must remain public-safe.

## Network layer

UniFi is the network control/telemetry platform. The MCP integration is intended for visibility and event analysis rather than unrestricted configuration.

Exact addressing and security-policy details are deliberately omitted from this public repository.

## Design principle

Live APIs answer **what is happening now**. Git answers **what we intend to deploy**. This knowledge base answers **why the environment is designed this way and what constraints automation must respect**.
