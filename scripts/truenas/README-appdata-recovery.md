# Native appdata and Semaphore recovery: next-stage runbook

Status: proposed, not deployed. The legacy checksum and sample restore tests
passed November 27, 2026. This runbook adds separate protection for the native
application datasets, not a replacement for the existing nightly file backup.

## 1. Complete restricted SSH security checks

From the trusted TrueNAS console, using the installed root-owned runner path
and private keys, test forwarding with ssh -F /dev/null -o BatchMode=yes
-o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=<pinned>
-i <restore-key> -W 127.0.0.1:22 homelab-backup@<private-host>.
Require explicit administrative denial; a timeout is inconclusive. Test PTY
allocation with -tt and a harmless requested command: it must not open a
shell, and the forced restore operation may still run. Inspect the effective
sshd configuration for this account and connection address, ensure password
and keyboard-interactive authentication are disabled for it, and verify
sudo -l -U homelab-backup /usr/bin/bash, /usr/bin/python3 and /usr/bin/id
each reject the command with a nonzero status. Do not modify existing admin
access or loosen credentials. Never print private keys.

## 2. Independent native ZFS replication

Use TrueNAS Data Protection > Replication Tasks. Select local source
USB_Storage_Space/appdata, recursive, and a new separate destination
Backup/appdata, on the independent USB pool. Use existing recursive hourly
snapshots as the source. Use daily replication after the nightly file backup,
with destination retention of 30 days if supported; verify free space and
retention rather than relying on the schedule alone. Preserve destination
read-only policy, avoid destructive rollback/force or replication into an
existing legacy dataset, and do not create shares on the replica. If the
wizard requires an empty destination, create only the new dedicated dataset
through the owner UI. Verify the actual resulting dataset names, recursive
coverage and job completion before proceeding.

The replica includes sensitive config, runner keys and user files. Restrict
backup access, check encryption requirements and physical security, retain
the original encryption/configuration secrets separately in a password
manager, and never expose the replica by SMB/NFS. Appdata replication is
crash-consistent storage protection, not a logical database recovery test.
Snapshots of the main pool alone are not independent. Native catalog app
state (including Tailscale) and TrueNAS system configuration need separate
recovery planning.

## 3. Semaphore PostgreSQL logical backup

Use semaphore_db_backup.py from a reviewed commit. Install locally as root
with mode 0700 in the existing protected runner directory. Do not add a
generic Docker or root sudo grant to the MCP account. The script only
accepts backup and checks the exact running Compose project, service,
image and mounted database dataset before running pg_dump inside the
existing PostgreSQL container. If the installed project label differs,
stop and review the script; do not broaden container selection. The archive
is written directly into a root-private directory on the independent
Backup/system dataset, checked with pg_restore --list, and atomically
published only after validation. Never print database output or secrets.
Run locally first, inspect the bounded JSON and retain a private copy of
the matching Semaphore encryption key and deployment settings. Schedule
the reviewed exact root command through native TrueNAS Cron Jobs after
successful testing, daily, outside the legacy copy/replication windows.
No automatic archive deletion in this first increment; monitor space and
add reviewed retention later. A catalog check is not a restore test.

## 4. Isolated database recovery gate

Use a disposable PostgreSQL 16 instance matching the tested version, with
no published ports, no shared production database mounts and no external
network access. Import a selected archive into an empty database using
pg_restore --exit-on-error; confirm schema/table counts and expected
Semaphore records without printing credential values. Test application
recovery separately with the original access-key encryption secret and
matching config in an isolated environment, with schedules and outbound
automation disabled. Remove only the disposable test instance after
validation. Never restore into the running Semaphore database. Record
archive date, restore result and duration without identifying private files
or secrets.

## 5. Gate for application update and migration

The next MCP increment should use fixed Git-reviewed app revisions, exact
allowlisted targets, versioned native TrueNAS app.update API, preservation
of existing secrets and settings, mount/backup preflight, job result and
functional health checks. Do not redeploy the active MCP tunnel through
itself. Keep old management services until native appdata replication,
logical backup, and isolated recovery have been verified. Do not silently
expand permissions to cover this work.
