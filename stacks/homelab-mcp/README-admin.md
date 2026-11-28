# TrueNAS Stage 3 administration (proposed)

Target TrueNAS 25.10 API. The first increment adds catalog inventory, creation of one explicitly permitted filesystem dataset, a nonrecursive snapshot of an explicitly permitted dataset, and start/stop of an explicitly permitted non-management application. It does not install apps, execute arbitrary Compose, delete, rollback, restart, change permissions, create snapshot schedules or execute shell commands.

## Deployment gate

Merge only after CI and review. Deploy the published image manually outside the active tunnel. Retain the old image/config and independent management access. Refresh ChatGPT Action control, approve only intended actions and verify read-only calls first. Do not turn on writes merely to test reads.

## Configuration

Defaults are fail-closed. Set TRUENAS_ADMIN_ENABLED=true only after reviewing the following private environment values. The admin key must differ from the diagnostic key. Prefer a distinct least-privilege account with the version-appropriate dataset/snapshot/app write roles and job visibility; do not assume a dedicated key alone restricts account permissions.

- TRUENAS_ADMIN_USERNAME and TRUENAS_ADMIN_API_KEY: private dedicated credentials; never commit them.
- TRUENAS_ADMIN_DATASETS: comma-separated exact names for dataset creation (no wildcards). Each parent must exist and be a standard filesystem. No auto-created ancestors.
- TRUENAS_ADMIN_SNAPSHOT_DATASETS: comma-separated exact existing dataset names.
- TRUENAS_ADMIN_APPS: comma-separated exact non-management app names, vetted by the owner. Do not allow dependencies of the MCP connection, tunnel or remote administration. Built-in protections block common management names; they do not discover dependency graphs.

The confirmation string is a target-binding input check, not an independent human consent or authorization mechanism. The user must authorize consequential writes in the current task; the backend checks its configured target scope. No generic RPC tool accepts user-supplied method/parameter objects.

## Validation

First create a deliberately approved empty application dataset, inspect its root stat, create a nonrecursive snapshot, and requery inventory. Test application lifecycle on an approved noncritical app only, not Tailscale or the management plane. Job success plus reported app state is not a functional endpoint check. A pending or unknown job outcome requires inspection before retrying. Never automatically clean up or roll back on failure. Keep write credentials disabled until CI and deployment are verified.

Documentation for the 25.10 API: https://api.truenas.com/v25.10/ (pool.dataset.create, pool.snapshot.create, app.available, app.start, app.stop). The exact deployed patch release still requires live validation.

## Git-backed Semaphore bootstrap

The first deployment action is deliberately create-only and fixed to Semaphore,
the reviewed Playbooks merge commit f6bb37ba1eda27d2fa700bfabcd4ddc52e61f32a,
and the approved Compose blob ed1c7643432311c32f0ae34abe9002f722f23df2.
The server downloads the exact file over verified HTTPS, rejects redirects and
unexpected content, and accepts no caller-supplied YAML, URL, Git ref or app name.
Future approved versions require a separately reviewed code change.

Set these private MCP environment variables only if the owner approves initial
deployment:
- TRUENAS_SEMAPHORE_DEPLOY_ENABLED=true
- TRUENAS_SEMAPHORE_DB_SECRET: unique random 32–128 URL-safe characters.
- TRUENAS_SEMAPHORE_ADMIN_SECRET: a different random 32–128 URL-safe characters.
- TRUENAS_SEMAPHORE_ENCRYPTION_SECRET: standard base64 encoding of 32 random bytes.
- TRUENAS_SEMAPHORE_BIND_ADDRESS: exact private IPv4 assigned to the TrueNAS host.

The existing separate admin credential must be enabled. Keep credentials out of
Git, chat and logs. The rendered Compose configuration is stored by TrueNAS and
is accessible to appropriately privileged NAS administrators; it is not an
encrypted secret store. Keep a secure private copy for disaster recovery.

The action checks the app does not exist, both datasets are mounted and empty,
a recursive appdata snapshot task is enabled, and the private bind address
exists. It records a nonsecret create-attempt fence in the MCP persistent
volume before the write. No automatic retries: if deployment fails or the
result is unknown, inspect TrueNAS jobs, app state and datasets manually. Only
after verifying there is no running job or app and no partial data should the
owner consider clearing the persistent attempt record; never clear it merely
to force a retry. No action exposes reset, update, delete or arbitrary shell.

The status action reports expected Git revision, live app state, selected
service image-tag matches and session-visible job metadata only. It does not
prove full Compose configuration equivalence, HTTPS, or application login.
Create only after CI, publication, manual deployment and Action control
refresh. Before production use, verify functional login and consistent
database backup and restore. The legacy Semaphore remains available until
the replacement is verified.


## Native Semaphore bootstrap

Enable SEMAPHORE_BOOTSTRAP_ENABLED=true privately and pass it through the
MCP Compose environment. Require verified HTTPS on the private Tailscale
Serve port 8443, a working token, and an empty SEMAPHORE_ALLOWED_TEMPLATES.
Call semaphore_bootstrap_truenas with confirmation
bootstrap:homelab-truenas-operations only on the new instance. It creates a
dedicated project, public HTTPS Git repository, no-auth key, empty variable
group and a Python smoke template. It re-reads resources, reuses exact
matches, rejects conflicts and does not update existing resources or run
tasks. Existing unrelated projects cause refusal. After bootstrap turn the
flag off, verify template settings and explicitly authorize only its exact
project/template pair before running. No host SSH key, host inventory,
schedules, credentials or backup templates are created. Repository main is
mutable; verify reviewed smoke source before execution, and use stronger
revision controls for future privileged tasks. The host backup helper must
run in an independently reviewed restricted execution context, not via
arbitrary root SSH or a Docker socket. Legacy Humboldt bootstrap is rejected
unless the original project ID and name match.


### Application migration preflight

The read-only truenas_app_host_resources action uses the documented 25.10
app.used_ports and app.gpu_choices RPCs. Only bounded port numbers, vendor,
description and reported usability are returned. Unknown is not port
availability or GPU absence. The fixed truenas_plex_migration_preflight
checks the already allowlisted legacy media paths, candidate config dataset
inventory, installed app identity, port 32400 and Intel GPU choices. It never
claims deployment readiness; source config, backup, image, container paths,
ACLs, host port listeners, GPU device permissions and functional tests need
separate verification. No new write RPCs, credentials, arbitrary Compose,
installation or upgrade actions. Existing Semaphore creation continues to
use its reviewed immutable revision and Git blob via a reusable internal
loader. See https://api.truenas.com/v25.10/api_methods_app.used_ports.html
and https://api.truenas.com/v25.10/api_methods_app.gpu_choices.html .
