# HomeLab Knowledge Base

This directory is the durable operating context for the Clothier HomeLab.

It exists so humans, ChatGPT, Codex, Semaphore jobs, and other automation can understand not only **what exists**, but also **why it exists and how it is intended to be operated**.

## Scope

The knowledge base should contain:

- architecture and control-plane design;
- logical inventory and service purpose;
- automation boundaries and safety rules;
- storage and backup intent;
- known issues and cleanup candidates;
- important architectural decisions;
- project-specific operating notes.

The live systems remain authoritative for current runtime state. This knowledge base is authoritative for **intent, conventions, safety rules, and historical decisions**.

## Security rule

This repository is public. Do **not** store:

- passwords, tokens, API keys, private keys, or session material;
- exact private IP addresses unless intentionally public;
- MAC addresses, certificate fingerprints, tunnel credentials, or secret IDs;
- raw environment-variable values;
- detailed firewall rules or other information that materially increases attack surface.

Use logical hostnames and roles instead.

## Current control model

ChatGPT reaches the HomeLab through an outbound-only secure MCP tunnel. The MCP service exposes narrowly scoped integrations:

- **Proxmox:** read-only infrastructure visibility.
- **Semaphore:** controlled execution of existing automation templates.
- **Portainer:** Docker visibility, selected container actions, and guarded Git-backed stack redeploys.
- **UniFi:** network visibility and retained system-event telemetry.

Semaphore is the preferred write/automation layer. Arbitrary shell or SSH execution is intentionally not exposed through MCP.

See [architecture.md](architecture.md), [automation.md](automation.md), and [operations.md](operations.md).

## Files

- [architecture.md](architecture.md) - system/control-plane design.
- [inventory.md](inventory.md) - logical infrastructure and services.
- [inventory.yaml](inventory.yaml) - machine-readable, public-safe inventory.
- [automation.md](automation.md) - Semaphore, Portainer, MCP, and future Codex usage.
- [storage-backups.md](storage-backups.md) - storage and backup intent.
- [operations.md](operations.md) - operating rules, known issues, and cleanup candidates.
- [projects/humboldt.md](projects/humboldt.md) - Humboldt data-platform project.
- [decisions/](decisions/) - architectural decision records.

## Maintenance model

Prefer small updates alongside infrastructure changes. Where practical, automation may refresh factual inventory, but generated data must remain public-safe and must never include secrets.

Last structured review: 2026-09-29.
