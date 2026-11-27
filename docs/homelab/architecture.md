# HomeLab Architecture

## Design goals

The HomeLab is optimized for:

1. useful self-hosted services;
2. infrastructure-as-code and repeatable automation;
3. minimal public exposure;
4. controlled ChatGPT-assisted operations;
5. preserving clear human control over state-changing actions.

## Current architecture (November 27, 2026)

Bare-metal TrueNAS 25.10.7 is the primary always-on storage and future application host. The former proxmox2 system has been converted; its four-SSD RAIDZ1 pool was imported intact. Hardware selection is complete: Intel Core i5-14400, ASRock B760M Pro-A/D4, 32 GB DDR4, boot NVMe and four 2 TB SATA SSDs. The independent USB SSD is now the Backup pool. No additional hardware is required for current migration work.

Proxmox1 and Proxmox3 are transitional hosts; verify guests and quorum before retirement. Preserve the existing management host and tunnel until replacement access is tested. Proxmox3 is intended to become bare-metal Linux Mint for gaming and on-demand compute. Fixed guest RAM allocation is not itself evidence of pressure.

## Application architecture

TrueNAS native catalog Apps and custom Compose replace Portainer-managed workloads incrementally. Git is the nonsecret declarative source; TrueNAS is the runtime controller and does not automatically synchronize Git changes. Pin tested versions, keep databases in persistent datasets, use separate secret storage, and verify backups and runtime health before retiring old services.

Fresh official Semaphore with PostgreSQL is the next application. Home Assistant OS remains a VM for Supervisor, Matter and Thread. Audit Authentik dependencies before deciding whether to retain it. Mealie is intentionally stopped; Family Archive was deleted by the owner. Rebuild Humboldt from public sources rather than migrating its old database. Keep management and Humboldt lifecycles separate.

Tailscale is installed and trusted HTTPS through Serve was owner-verified; retain Nginx Proxy Manager/DuckDNS for local non-tailnet devices while evaluating dependencies. No Funnel for administration. Verify policies, key expiration, restart persistence and exposure separately.

## Automation/control plane

The preferred path for state changes is:

```text
ChatGPT
   |
Secure outbound MCP tunnel
   |
HomeLab MCP
   |
   +--> TrueNAS (read-only today; scoped administration planned)
   +--> Proxmox (transitional read-only)
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
