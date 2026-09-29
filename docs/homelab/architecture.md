# HomeLab Architecture

## Design goals

The HomeLab is optimized for:

1. useful self-hosted services;
2. infrastructure-as-code and repeatable automation;
3. minimal public exposure;
4. controlled ChatGPT-assisted operations;
5. preserving clear human control over state-changing actions.

## Compute layer

The virtualization layer is a three-node Proxmox environment:

- `proxmox1`
- `proxmox2`
- `proxmox3`

The environment is not currently dependent on shared storage for cluster-style workload mobility. Workloads are generally placed intentionally on specific nodes.

A separate gaming/workstation system is outside the managed Proxmox cluster.

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
