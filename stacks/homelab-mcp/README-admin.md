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
