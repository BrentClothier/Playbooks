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

### Migration diagnostic actions

The MCP provides bounded read-only Proxmox API views for guest disk/configuration metadata (`proxmox_guest_config`), recent migration tasks (`proxmox_migration_status`), backup job definitions and task results (`proxmox_backup_status`), redacted task output (`proxmox_task_log`), Proxmox-visible ZFS pool summaries (`proxmox_zfs_pools`), and Proxmox-visible storage volume listings (`proxmox_storage_content`). These do not offer arbitrary commands, pool export/import, migration initiation, snapshots, or backup creation. They cannot replace `zpool status -v`, a recursive `zfs list`, guest filesystem inspection, or restore tests.

Require node/guest/task path validation, finite result limits, selected config fields, and redacted log text. Confirm errors and the destination storage independently after any migration. For any new permissions, grant the minimum appropriate Proxmox Audit read access; do not broaden write privileges.

## Semaphore

Current direction: fresh official Semaphore image with PostgreSQL on TrueNAS, Git-backed Compose, dedicated persistent datasets, private credentials, consistent database backup. Recreate needed templates; preserve old management access until tested. The owner does not require old database migration unless an actual dependency warrants it.

Semaphore is the preferred state-changing automation layer.

Current projects:

- `Clothier HomeLab`
- `Clothier Homelab IaC`

MCP may run existing templates but does not accept arbitrary playbooks, shell commands, branches, tags, inventory overrides, or free-form arguments.

### Replacement plan during TrueNAS consolidation (owner intent, November 22, 2026)

The owner prefers a fresh, current Semaphore deployment over continuing the
existing version-constrained installation built around a particular OpenTofu
toolchain. Keep Semaphore as an option for approved repeatable tasks, especially
Humboldt ETL; do not assume that a pre-existing OpenTofu version is required
once the Proxmox VM workflow is retired. Verify tooling/runner versions before
replacing any still-needed OpenTofu automation.

Live inspection found three projects: `Clothier HomeLab`,
`Clothier Homelab IaC`, and `Humboldt Government Intelligence`. The latter two
had no task templates; legacy HomeLab tasks and Humboldt automation live in the
first project. Existing template IDs, schedules, inventories, variable groups,
credentials, SSH keys, and database history are not automatically reconstructed
from the Git-tracked Ansible and OpenTofu source. Export needed project
configuration and make a consistent backup of the Semaphore MySQL database
and application encryption settings **privately** before a clean reinstall.
Check new project/template IDs and refresh the MCP's authorized template scope
and credentials after migration. Never publish exports or secrets to GitHub.

Current installed container metadata identified upstream Semaphore 2.18.10
despite a floating image tag at the observation time; no proof of the specific
custom OpenTofu build is available from the metadata alone. Pin tested versions
and preserve the old service until new task execution and connection tests pass.
Do not have the HomeLab MCP redeploy itself.

### Template allowlist semantics

The historical MCP setup intentionally used
`SEMAPHORE_ALLOWED_TEMPLATES=*`. In the current source, `*` means any template
visible to the configured Semaphore API token, including templates created
later. A narrower configuration uses explicit `project_id:template_id` pairs.

This setting changes which existing templates MCP may start; it does not widen
the MCP input surface. The run tool still does not accept arbitrary playbooks,
shell commands, branches, tags, inventory or survey overrides, limits, or extra
arguments. The currently deployed allowlist value is runtime configuration and
must be checked through safe configuration metadata rather than inferred from
this historical record. Do not expose the raw environment or credential values.

### Important OpenTofu rule

Do **not** use the generic root OpenTofu Apply path for the Humboldt project.

A prior plan showed unrelated drift against existing VMs. Humboldt therefore has its own isolated OpenTofu root and state under:

`opentofu/humboldt/`

The general rule is: new projects with materially independent lifecycle should get isolated state rather than being appended casually to the original root configuration.

The HomeLab MCP/control-plane work and the Humboldt public-data application are
separate projects even when they use the same MCP transport and Semaphore
service. Shared transport does not merge their permissions, deployment
lifecycle, or IaC state; Humboldt remains isolated under `opentofu/humboldt/`.

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

### UniFi Protect sensor integration

The HomeLab MCP also exposes two narrowly scoped read-only UniFi Protect
sensor actions:

- `unifi_protect_sensors` — current sensor inventory and selected contact,
  motion, environmental, connectivity, and battery data (bounded output).
- `unifi_protect_sensor` — selected live telemetry for one validated sensor ID.

These use the official local Protect Integration API on the UniFi console.
Runtime credentials (`UNIFI_PROTECT_URL`, `UNIFI_PROTECT_API_KEY`,
`UNIFI_PROTECT_VERIFY_SSL`) are optional overrides; when they are absent,
the deployed server reuses the existing UniFi Network URL, API key, and TLS
verification settings. Protect permission must still be confirmed by a real
sensor request, not inferred from Network API success.

Both MCP actions allow GET requests only to Protect sensor endpoints. They
do not expose camera footage, snapshots, audio, Protect configuration, alarm
controls, or a generic API proxy. Avoid logging API keys and never record
private sensor identifiers, locations, event histories, or personal room
names in this public KB.

A successful Protect sensor status query proves API connectivity and the
reported sensor telemetry only. A smoke/CO listener appearing connected does
not independently prove its alarm-detection or notification chain works.
Verify alarm functionality through the vendor's supported testing procedure.

### Additional read-only Proxmox preflight diagnostics

For hardware and ZFS migration, narrowly scoped read-only API actions
`proxmox_cluster_quorum`, `proxmox_zfs_pool_detail`,
`proxmox_physical_disks`, and `proxmox_disk_smart_health` are implemented
in the MCP source. Availability requires deployment and a refreshed ChatGPT
action snapshot. No export, import, wipe, reformat, SMART-test initiation,
ZFS modification, node shutdown or cluster-member removal is exposed.

Use these before changing hardware to check cluster quorum, disk identity,
pool vdev state and scrub descriptions. They cannot replace LXC-rootfs
permissions, NFS export inventory, ZFS dataset/snapshot listings, independent
backups or verified restore testing. Keep private disk serials in a secured
migration record, not this public repository.

## TrueNAS integration

TrueNAS is the primary target platform for storage and applications. The first
13 read-only actions were verified against the deployed TrueNAS 25.10.7 system
on November 26, 2026. Stage-one diagnostics extend that backend with:

- `truenas_disk_temperatures`: current disk readings, null means unknown;
  this is not SMART attributes, endurance or a health certification.
- `truenas_backup_status`: periodic snapshot, replication, cloud sync,
  cloud backup and rsync task definitions, schedules and reported state.
  An unavailable group is explicitly unknown; a configured task is not proof
  of completion, independent retention or a tested restore.
- `truenas_scrub_status`: schedules and reported pool scan state.
- `truenas_performance`: bounded 1–24 hour reporting aggregates and latest
  sample for approved system and inventoried-device metrics.
- `truenas_importable_pools`: bounded read-only discovery scan; never imports
  a pool. Use only on demand rather than each scheduled health check.
- `truenas_system_updates`: update status and offered version; no download,
  installation or restart.
- `truenas_ups_status`: service state and supported reporting graphs when
  the UPS service is running; unavailable telemetry is not healthy status.
- `truenas_vm_status`: runtime state, not VM resource consumption.
- `truenas_nfs_client_count`: reported connected client count, not proof
  of functional mounts.

Treat stage-one code, published image, deployed revision, refreshed ChatGPT
action set and successful live calls as separate milestones. Verify actual
availability before relying on any new tool. Full SMART/endurance, raw
application logs, app statistics streaming, arbitrary filesystem ACL reads and
free-text alert details are not included in this release; do not invent them
or substitute shell access. Alert class and severity remain available through
the existing alert metadata tool.

Use fixed read RPCs over verified TLS WebSockets. Runtime username must match
the API key owner. Prefer a dedicated least-privilege read account, not a full
administrator key. No generic API proxy, shell, storage mutations, implicit
imports or app lifecycle changes are authorized by these diagnostics.

### Scheduled health watch

Use the current KB and live API evidence to distinguish expected service
availability from actual status. For automated six-hour checks, notify only
on meaningful new or worsening exceptions, material monitoring failures, or
resolved incidents. Consolidate nonurgent warnings, suppress duplicates and
expected maintenance, and omit routine healthy reports. Prefer native
immediate alerts for critical hardware faults; a scheduled model check is
not a substitute. Keep scheduled checks strictly read-only. Do not claim that
an empty list or missing telemetry establishes health. During migration do
not alarm on deliberately offline services or disks until they are expected
online. Never publish private device identifiers, credentials or live logs.


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


### Stage 2 diagnostics (deployed and verified November 27, 2026)

The first expansion adds cron schedule metadata (no command or description),
session-visible cron middleware job history (not the host journal), exact
inventoried ZFS dataset-root stat metadata (no arbitrary paths or file
contents), and installed application container inventory (no console access).
Historical reporting accepts either dictionary samples or legend-aligned
array samples, otherwise reports unknown. PR #20 passed CI and was merged. Image publication, deployment and action refresh are separate gates. The four new actions remain
read-only and require the deployed API version and corresponding read roles.
The cron history endpoint cannot prove an ordinary scheduled cron run.

The owner has requested additional controlled administrative and shell
execution capabilities. Implement these separately: fixed-purpose native API
operations with explicit target validation and write enablement, and approved
Semaphore templates or narrowly scoped scripts for host diagnostics, backup
verification and restoration. No generic root shell, arbitrary RPC proxy,
Docker socket, credential disclosure, or self-redeployment. Keep actual
authorization and allowlists enforced by the backend. Destructive operations
remain outside automatic execution. Preserve an independent recovery path.
Raw database files are not a substitute for consistent logical backups.

Current migration evidence (owner report, November 27): selected personal
files, audiobooks and application files passed checksum comparison; the
nightly file backup reported successful completion at 02:00; primary hourly
and backup daily snapshot tasks reported successful runs. The sample restore,
database backups, full media coverage and offsite protection remain
unverified or out of scope. These are dated observations, not ongoing state.
The new application datasets require their own snapshot and backup coverage.

Deployment requires CI, merge, image publication, manual redeploy outside the
active MCP tunnel, action refresh and live validation. Update bundled and
standalone skills only after reconciling the actual deployed capabilities.

### Stages 3 and 4 (merged and published November 27, 2026)

PRs #21 and #22 passed CI, merged, and were included in the published MCP image
`ghcr.io/brentclothier/homelab-mcp:b19fbe51d6ab9742f3eb1635da359636b03abba8`.
The owner redeployed and refreshed Action control November 27; all 32 TrueNAS actions were visible. Catalog reads, directory metadata and ACL reads succeeded; the scoped write credential successfully created the appdata and Semaphore parent datasets. Further writes stopped after temporary authentication failures. Stage 3 adds catalog reads, explicitly allowlisted dataset creation,
nonrecursive snapshots and start/stop of non-management applications. Writes
are disabled by default and require a separate administration credential,
exact configured targets and target-specific confirmation. Confirmation binds
intent to the target but is not independent human authorization. Configure the
least privileged account supported by TrueNAS. Stage 4 adds bounded directory
metadata and ACL reads for explicitly permitted dataset roots, and sorts cron
job history. No arbitrary file contents or host shell are exposed.

Configuration keys: TRUENAS_ADMIN_ENABLED, TRUENAS_ADMIN_USERNAME,
TRUENAS_ADMIN_API_KEY, TRUENAS_ADMIN_DATASETS,
TRUENAS_ADMIN_SNAPSHOT_DATASETS, TRUENAS_ADMIN_APPS and
TRUENAS_DIAGNOSTIC_DATASETS. Keep credentials out of Git and model output.
See stacks/homelab-mcp/.env.example and README-admin.md for configuration.

The fixed-purpose scripts/truenas/backup_ops.py helper has passed CI but is
not installed on the host or wired to an approved execution template. No
live restore has been performed. Install and approve the exact command and
private configuration separately; never expose a general-purpose shell.
Custom Compose deployment, application installation, backup runner wiring
and consistent database backup remain future work. The existing MCP tunnel
must not redeploy itself.

### Persistent connection reliability (November 27, 2026)

PR #23 passed CI and merged at ee56191889b659d2e5ae80399c2fad0b65e8b4a8. Separate persistent read/admin sessions serialize requests, pace new logins and respect a ten-minute authentication cooldown on failure. No automatic RPC replay. Keep verified TLS, backend target scopes and independent administration credentials. Temporary authentication failure recovered without key changes; rate limiting is the leading explanation, not a confirmed server-side diagnosis. Image was published and the owner manually redeployed November 27. Portainer reported the recreated MCP container running and healthy; a batch of ten TrueNAS read-only actions (including multi-RPC backup and mount checks) completed successfully in 8.3 seconds with no authentication failures. Long-term reliability and exact running image revision are not independently established. Action schemas and environment variables are unchanged. Before resuming writes verify live inventory and preserve existing datasets. Subsequent authorized live operations successfully created and verified both Semaphore child datasets (config and database) and the nonrecursive parent snapshot pre-deployment-2026-11-27. Recurring recursive snapshot coverage, independent appdata backup, consistent database backups and the legacy sample restore remain pending. Do not confuse a parent-only snapshot with child protection.

### Git-backed application deployment (November 27, 2026)

Semaphore Compose is merged on main via PR #24, pinned to f6bb37ba1eda27d2fa700bfabcd4ddc52e61f32a. PR #25 passed both CI workflows and merged at 1286a91ea5f64cf3bb43ba52a30d7b5dc4fd5797. It adds a default-disabled create-only Semaphore action, fixed Git source/blob verification, private runtime secrets, mounted/empty dataset and recursive snapshot preflight, a persistent attempt fence, and bounded deployment status. No arbitrary YAML, app updates, full drift comparison or deletion. Image publication, manual redeployment, action refresh, private runtime configuration and live app creation remain distinct gates. The owner created the hourly recursive appdata snapshot task, retention 14 days, verified enabled; initial run was pending at inspection. See stacks/homelab-mcp/README-admin.md and stacks/semaphore-truenas/README.md. Do not retire the old Semaphore until replacement login, representative safe task, backup/restore and MCP access are verified.

On November 27 the owner configured private deployment settings, redeployed and refreshed actions. The fixed Git-backed Semaphore creation passed preflight and TrueNAS job 3262 returned SUCCESS. The native custom app reported RUNNING, with both Semaphore v2.20.23 and PostgreSQL 16.16-trixie containers running and matching expected image tags. This verifies initial deployment, not functional login, full Compose equivalence, database backup/restore or migration of old automation. The old control plane remains unchanged. Configure trusted HTTPS, test login and create a dedicated API token privately before reconnecting MCP; retain existing access until the new automation path is validated.


### Native Semaphore bootstrap and restricted runner (November 27, 2026)

PR #26 passed all validation and published the image from merge
b06e0a66c80f6ae0b41abe11f02ec988df1e6725. Owner deployed and refreshed actions.
Bootstrap created the native HomeLab project, public Git repository, no-auth
key, empty variable group and smoke template; repeat invocation reused all
five resources. After disabling bootstrap and authorizing the exact template,
task 1 succeeded and emitted HOMELAB_SEMAPHORE_RUNNER_OK from the reviewed
merge revision. This verifies Git checkout, API execution and log retrieval,
not host execution or backup recovery.

Owner selected Tailscale Serve as the preferred private HTTPS access layer,
and intends to retain Authentik for centralized identity/SSO when sharing
selected services. Keep administrators separate from shared service users;
verify restrictive network grants and app access policies before sharing.
Do not retire existing proxies or identity services until dependencies are
audited. Native Semaphore HTTPS and MCP connectivity were verified; the
management VM required its own Tailscale client.

Next increment proposes native project:* scope with live name and fixed-task
settings checks, and create-only backup templates. See
scripts/truenas/README-backup-runner.md for the owner-controlled restricted
SSH keys, exact sudo commands, private variable groups, pinned host identity
and negative tests. No generic shell or root login. The scope is not a
sandbox for arbitrary Git code: trust only reviewed project templates and
restrict editors. Live runner installation, restore, independent appdata
backup and database protection remain unverified.


### Restricted backup runner: live verification (November 27, 2026)

PR #27 merged at 4044e87243d389db43710ed40b216a463e724752. The owner
installed the reviewed root-owned helper and private config, two separate
forced-command SSH keys and exact sudo rules, then deployed the dedicated
project scope (1:*) and disabled bootstrap. Template preparation created
verify template 2 and restore template 3 in project 1. Task 2 completed at
14:53 PST: a 53,805-byte temporary restored sample matched the backup and
current source. Task 3 failed preflight/execution; root cause not confirmed.
Retry task 4 succeeded at 15:25 PST after 17m13s: both legacy backup groups
returned rsync exit 0 and zero regular files needing transfer. The MCP
read back the task status and sanitized results independently. No source
or backup data was modified. These are dated observations, not guarantees
of future execution or complete recovery.

Owner-reported local sudo and forced-command restore tests succeeded. SSH
forwarding and PTY denial, effective password policy and unrelated sudo
negative tests still need explicit evidence; do not claim full security
validation. Do not widen the existing SSH or sudo scope. Git main and
project editors are trusted; the project wildcard is not a sandbox.

Next: native independent appdata replication with private destination,
consistent Semaphore PostgreSQL dump and isolated restore test, recovery
of the matching encryption/configuration secrets, then Git-backed app
update and migration. Do not retire old management infrastructure yet.


### Native application protection and migration preflight (November 27, 2026)

PR #28 merged at 4211bf9dcd718d158f3065307218b5c308569c87. Owner installed the pinned PostgreSQL backup helper after verifying Git blob identity. Owner-reported first logical archive was 214,287 bytes with catalog validation successful; isolated PostgreSQL 16 restore passed and recovered 58 public-schema tables. This does not test Semaphore login, stored credential decryption, or full application recovery. MCP verified the daily 01:00 cron configuration and local recursive appdata replication at 04:00, retention 30 days. Initial replication job 4525 succeeded; all four expected destination datasets were read-only. First scheduled database backup remains unverified. No automatic logical archive expiry yet.

Owner-reported SSH negative tests: forwarding explicitly administratively prohibited (exit 255), PTY allocation denied, and unrelated sudo policy lookups for Bash, Python and id each denied (exit 1). Together with earlier forced-command restore and both successful native tasks, these establish the tested restrictions. Effective password and keyboard-interactive policy remains unverified. Do not widen host execution permissions.

The legacy Plex stack is recorded in Portainer, but its Servarr environment is offline and Proxmox reports the source guest stopped. API inspection returned 502 and no volumes were listed by the configured Proxmox storage content endpoint. This does not prove the source volume is destroyed. Preserve the stopped guest, investigate its backing storage and backup inventory before starting it, and locate the original Plex config and database before creating a replacement. Native media directories are on the authoritative imported pool; do not relocate or delete the underlying dataset. No Plex create/update authorization or image/path guess has been added. New read-only app host resources and fixed Plex destination preflight actions require tested MCP deployment and action refresh; the preflight cannot authorize deployment or establish source recovery. Reusable pinned Compose loading keeps immutable revision and blob checks; all actual create/update definitions must be reviewed individually.
