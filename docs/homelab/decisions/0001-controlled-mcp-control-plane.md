# ADR 0001: Controlled MCP Control Plane

Status: Accepted

## Context

ChatGPT needs useful HomeLab visibility and the ability to trigger selected operations without turning an Internet-connected conversational interface into an unrestricted administrator shell.

## Decision

Use an outbound-only secure MCP tunnel to a custom HomeLab MCP service.

Expose narrow integrations:

- Proxmox read-only;
- Semaphore controlled template execution;
- Portainer guarded lifecycle operations;
- UniFi visibility/telemetry.

Do not expose arbitrary shell, generic SSH, or the Docker socket.

## Consequence

Some tasks require adding purpose-built MCP tools or Semaphore templates before they can be automated. This is intentional friction and part of the security model.
