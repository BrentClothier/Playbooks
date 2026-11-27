# Storage and Backups

## Current storage (November 27, 2026)

TrueNAS is the authoritative storage platform. The former NFS LXC root filesystem dataset `USB_Storage_Space/subvol-105-disk-1` contains the real data under its data directory. **Never delete this dataset.** The original four 2 TB SSD RAIDZ1 pool was cleanly exported and imported intact; preserve existing snapshots, POSIX ACLs and compatibility. Temporary native NFS bridges legacy clients; prefer direct local dataset mounts for migrated apps. Do not blanket chown/chmod or upgrade ZFS features without a reason.

Independent single-drive USB pool `Backup` has sibling datasets files, applications and system. Old PBS backups were explicitly considered disposable by the owner; the USB SSD was reformatted for this purpose. Full media backup is not available; RAIDZ1 and same-pool snapshots are not independent backups.

## Coverage and schedule

- Personal files and audiobooks copied to Backup/files; apps, configs and ansible_data copied to Backup/applications. Movies, TV and downloads excluded for capacity.
- Owner-provided November 27 checksum dry runs verified 3,538 regular files (about 295 GB logical), with zero transfers and exit status zero. This does not prove all application databases are covered.
- Primary legacy dataset snapshots hourly, retained 14 days. Backup pool recursive snapshots daily at 06:00, retained 30 days. Both reported successful November 27 via live MCP.
- Native root cron runs independent file backup at 02:00; checks mountpoints before copying, preserves numeric ownership/ACLs/xattrs, deliberately omits delete. Owner supplied successful journal completion November 27. Cron configuration and middleware jobs alone cannot prove ordinary scheduled execution.
- Owner manually exported TrueNAS configuration including secret seed to separate private storage; do not publish it.

## Remaining protection

Perform a representative restore into isolated temporary storage and compare checksums; do not overwrite source data. Create dedicated appdata datasets with explicit snapshot and independent backup coverage. Protect PostgreSQL/MariaDB using consistent logical backups, plus application assets and configuration. Monitor capacity/retention, automate private system configuration exports, consider offsite copies of irreplaceable files. Verify backup results and restore evidence separately; never imply scheduled jobs guarantee recovery.

Live APIs are authoritative for current pool health, capacity and snapshots. Report missing cron/journal, restore, SMART or per-file ACL coverage honestly. Preserve backups and data when retiring legacy compute.
