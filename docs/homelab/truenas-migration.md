# TrueNAS consolidation: completed cutover and remaining gates

**Status November 27, 2026:** Hardware installation and pool import are complete. The original dataset and snapshots remain authoritative; never delete the backing dataset. Independent USB backup covers selected files; checksum validation and first nightly completion were owner-reported successful. Live checks confirmed both pools online and snapshot schedules successful. Sample restore, appdata, database backups and application migration remain pending. The historical cutover steps below are recovery context, not instructions to repeat. See storage-backups.md and architecture.md for current policy.

This is an operating playbook, not authorization to execute changes. Query live state at each gate. Keep secrets, private IPs, and MAC addresses out of this public repository.

## Target and storage facts

- Consolidate Proxmox1 and Proxmox2 storage/application roles onto bare-metal TrueNAS. Proxmox3 is a temporary migration host and eventual gaming machine.
- The four-SSD RAIDZ1 pool `USB_Storage_Space` contains authoritative data. Import it intact into TrueNAS; **never create a new pool on these disks**.
- NFS LXC 105 rootfs is native ZFS filesystem `USB_Storage_Space/subvol-105-disk-1`. The user data is under `/data`, including `TVShows`, `movies`, `audiobooks`, `apps`, `Stuff`, `configs`, and downloads. The dataset also contains an Ubuntu root filesystem; import does not convert that LXC into a TrueNAS share.
- Dataset reports POSIX ACLs and `xattr=sa`. Existing exports grant broad read/write and `no_root_squash`. Preserve UID/GID and access behavior for initial validation; tighten exports after assessing each client.
- User-measured pre-migration data: TV shows ~1.6T, movies ~594G, audiobooks ~53G, apps ~188G (RomM ~187G, Family Archive ~224M), Stuff ~2.8G. These are approximations and do not prove where all application database volumes reside.
- NFS data has no verified independent full backup. Prioritize irreplaceable files, consistent database backups, configuration/secrets (stored securely), and restore testing. A 1TB removable drive cannot cover the full dataset.

## Application management end state

- Retire Portainer **after** each application stack has been deployed through
  TrueNAS Apps and validated. Retire NFS LXC 105 **after** its native TrueNAS
  shares work with the required clients; temporary TrueNAS NFS sharing can
  bridge the container-by-container migration.
- Keep custom Compose YAML and non-secret catalog-app manifests in the
  Playbooks GitHub repository. TrueNAS does not automatically redeploy an app
  when its GitHub file changes: use a separately built, approved reconciliation
  process. Pin important application and database image versions; validate
  Compose configuration, persistent host paths, and port conflicts.
- TrueNAS exposes catalog app inventory, installation, configuration, status,
  updates, and lifecycle management through its versioned JSON-RPC WebSocket
  API. These are **future HomeLab MCP capabilities**, not presently deployed.
  Begin with read-only app inventory, available updates and job outcomes.
  Make app install/update/start/stop narrowly scoped controlled writes, gated
  on approved Git changes and preflight checks. No generic shell or full-admin
  passthrough. Privileged delete, storage operations, and pool changes are
  excluded by default.
- Keep all secrets and mutable application data outside the public Git
  repository. Application data must be backed up separately from deployment
  definitions; ensure database consistency and an out-of-band recovery path.
- Protect the HomeLab MCP and secure tunnel from self-redeployment; retain an
  independent management path during the migration so a TrueNAS app outage
  cannot eliminate recovery access.

## Historical pre-cutover gates (completed hardware migration)

1. Inventory live guests, source and destination volume IDs, container storage mounts, NFS clients, DNS/proxy dependencies, and rollbacks.
2. Confirm admin-vm01, Authentik, HomeLab MCP, secure tunnel, and reverse proxy all work independently of Proxmox2. A running VM alone is not proof.
3. Migrate remaining required guests, verifying destination VM config, local disk placement, application health, and task results. A `lock: migrate` is not proof of completion.
4. Check backup warnings, job exclusions, and per-workload restore results. LXC 105 was excluded from the cluster backup job in the prior inspection; verify the current state.
5. Save `zpool status -v`, ZFS dataset and snapshot listings, mount properties, user/group ownership and NFS export definitions. The MCP Proxmox tools cannot replace native filesystem inspection.

## Historical cutover steps (do not repeat)

1. Assemble and test the new server, then install TrueNAS to the boot NVMe **with the four data SSDs disconnected**.
2. Stop all writers to the existing pool, take consistent final snapshots and independent backups, then export the ZFS pool cleanly from Proxmox2.
3. Install the four data drives and import the existing pool through the supported TrueNAS interface; do not initialize drives or upgrade ZFS feature flags during the rollback window.
4. Verify files, POSIX permissions and original datasets before introducing new application writes. Recreate NFS exports in TrueNAS and test their client behavior.
5. Validate databases, Plex libraries, RomM metadata and file paths. Reorganize into new datasets only after storage and backups permit safe migration.
6. Retire PBS and Proxmox nodes only after independent restores and application cutover tests pass; plan Proxmox cluster quorum separately.

## Read-only Proxmox disk and quorum preflight

The pre-cutover MCP enhancement adds four narrowly scoped Proxmox API reads,
subject to deploying the server version and refreshing approved ChatGPT actions:

- `proxmox_zfs_pool_detail(node,pool)`: pool topology, vdev state and
  read/write/checksum counters, last scrub/scan description and errors;
- `proxmox_physical_disks(node)`: physical disk path, model, size, serial,
  usage and reported health, for verifying data-drive identities;
- `proxmox_disk_smart_health(node,disk)`: selected local disk SMART health,
  with device-path validation and health-only response;
- `proxmox_cluster_quorum()`: current cluster membership/quorate state
  before retiring or disconnecting Proxmox nodes.

Record disk serials and private identifiers only in a secured migration record,
never in this public KB. Disk identity must be cross-checked against ZFS
vdev membership and physical labels before unplugging drives. Device names
such as `/dev/sdX` can change after reboot or replugging.

These API projections **do not** expose native `zfs list` datasets and
snapshots, LXC 105's `/data` ACLs/ownership, Ubuntu `/etc/exports`, or
verified independent restore evidence. Those are required pre-cutover checks
and must be collected by an appropriate local/approved read-only method,
not inferred from successful API calls.

For TrueNAS 25.04+ integrations use its versioned JSON-RPC WebSocket API,
not a new REST-only MCP client. Discover the installed TrueNAS version
and provision a least-privilege, user-linked key after installation.

## Diagnostic tool limits

- `proxmox_guest_config`: selected VM/LXC boot, disk and network settings, excluding cloud-init passwords, SSH keys and descriptions.
- `proxmox_migration_status`: recent migration tasks; validate target VM, storage, and services separately.
- `proxmox_backup_status`: job configuration and recent vzdump task outcomes, **not** PBS restore assurance.
- `proxmox_task_log`: bounded logs with best-effort redaction; credentials must not be intentionally logged.
- `proxmox_zfs_pools`: Proxmox ZFS disk API overview, not scrub/error/SMART proof.
- `proxmox_storage_content`: Proxmox-visible volumes; not full native ZFS dataset/snapshot/ACL inventory.
- Direct TrueNAS API, NFS export inventory and deep dataset diagnostic tools are separate future integrations, requiring appropriate read-only credentials.

## Stop and rollback

Stop if a destination volume is inaccessible, a backup/restore requirement is unmet or pool health changes. Never import the same pool read-write on two hosts simultaneously. Retain rollback compatibility by avoiding feature upgrades and destructive dataset changes until verification is complete.
