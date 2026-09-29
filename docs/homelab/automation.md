# Automation and Control Boundaries

## HomeLab MCP

The HomeLab MCP service is the bridge between ChatGPT and local infrastructure.

Security intent:

- no arbitrary shell execution;
- no generic SSH execution;
- no Docker socket exposed directly to MCP;
- credentials stay in local environment/secrets;
- common credential material is redacted from MCP responses and logs;
- integrations should expose narrow operations rather than generic administrator APIs.

## Proxmox

MCP access is read-only. A dedicated API token is granted audit/visibility permissions rather than general administration.

Provisioning and configuration changes should go through infrastructure-as-code and Semaphore whenever practical.

## Semaphore

Semaphore is the preferred state-changing automation layer.

Current projects:

- `Clothier HomeLab`
- `Clothier Homelab IaC`

MCP may run existing templates but does not accept arbitrary playbooks, shell commands, branches, tags, inventory overrides, or free-form arguments.

### Important OpenTofu rule

Do **not** use the generic root OpenTofu Apply path for the Humboldt project.

A prior plan showed unrelated drift against existing VMs. Humboldt therefore has its own isolated OpenTofu root and state under:

`opentofu/humboldt/`

The general rule is: new projects with materially independent lifecycle should get isolated state rather than being appended casually to the original root configuration.

## Portainer

Allowed use cases include:

- read environment/container/stack state;
- inspect redacted logs;
- start/stop/restart selected containers;
- guarded redeploy of eligible Git-backed stacks.

### Git redeploy safety

The MCP Portainer redeploy path:

- is restricted to tested Portainer 2.45.x behavior;
- verifies the stack is Git-backed;
- validates environment metadata before the write;
- omits Env from the Git-redeploy payload so Portainer preserves existing values;
- verifies Git identity and environment-variable metadata after the API call;
- refuses to self-redeploy `homelab-mcp`;
- permits retry from Error state only when the latest deployment record is also an Error.

A real test against `family-archive` on Portainer 2.45.1 completed successfully with all 18 environment variables and Git metadata preserved.

## UniFi

MCP is intended for:

- device/client visibility;
- health/statistics;
- retained CEF/syslog events;
- WAN, Wi-Fi, and security troubleshooting.

It is not intended to expose unrestricted network configuration.

## Future Codex execution

A ChatGPT/Codex access token is available for future automation.

Preferred pattern:

```text
ChatGPT -> Semaphore -> isolated Codex job -> Git branch/PR -> tests -> approved deployment
```

Codex should not receive an unrestricted HomeLab administrator role. Give each job only the repo, credentials, and systems required for that task.

Good candidates:

- MCP development and tests;
- Ansible playbook maintenance;
- Compose updates;
- collector/ETL development;
- linting and infrastructure validation;
- pull-request creation.

Secrets must remain in Semaphore or another secret store and must not be committed to Git or returned through MCP output.
