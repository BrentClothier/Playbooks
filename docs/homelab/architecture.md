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

## TrueNAS consolidation target (owner decision, November 22, 2026)

The intended end state is bare-metal TrueNAS hosting production storage and
application services. The owner plans to retire both Portainer and the NFS LXC
after their replacements are verified: TrueNAS native NFS/SMB shares replace
LXC 105, while TrueNAS-managed Docker Apps (catalog or custom Compose) replace
Portainer-managed application stacks. Keep Proxmox3 for gaming, experimentation,
and independent emergency access/recovery as appropriate.

The deployment source of truth will be the existing public GitHub Playbooks
repository. Store non-secret Compose YAML, pinned image versions, deployment
manifests for catalog apps, and operating procedures in Git. Store actual
credentials, tokens, sensitive network details, and mutable application data
outside the public repository.

TrueNAS Apps is the runtime controller. Installing custom Compose YAML in
TrueNAS does **not** automatically create a live Git synchronization link.
A future scoped Git/CI/Semaphore deployment workflow should validate changes,
require approval for writes, apply them through TrueNAS's version-matched
JSON-RPC WebSocket API, verify job completion/health, and detect configuration
drift. Native catalog apps also have API create/update/upgrade operations,
but their settings require a non-secret declarative manifest and separate
synchronization logic to become reproducible from Git. Never expose a generic
administrator API proxy or self-redeploy the management tunnel.

This is the desired end state, **not** evidence that migration is complete or
authorization to shut down current hosts. Preserve the existing pool and
service dependencies until all replacement services and rollback are validated.

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
