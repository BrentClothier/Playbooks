# Approved TrueNAS backup operations (Stage 4)
 
This host-side helper is intentionally separate from the MCP container. It does not open a shell endpoint, run remote input, modify the current cron backup, delete destination files, or overwrite source files. It supports two fixed operations: checksum dry-run of selected legacy file data, and an isolated bounded sample content restoration. Neither establishes full media/DB/ACL recovery.

Install the reviewed script on a persistent private TrueNAS dataset, root-owned with protected ancestor directories. Keep the private JSON config root-owned mode 0600 in a protected directory, not in Git or a shared writable dataset. Fields:

- source_mount: exact mounted legacy source dataset, whose data/ directory contains the selected groups.
- backup_files_mount: mounted files dataset on the independent Backup pool.
- backup_applications_mount: mounted applications dataset on the same Backup pool.
- sample_group: files or applications.
- sample_relative_path: one existing nonempty regular file <=64 MiB inside the selected group's fixed directory set. Choose a representative nonsecret file; no symlinks.

Both operations validate mountpoints and pool layout first. Verify reads all selected data and can take time; do not run on every health poll. Schedule it separately from the nightly rsync, or operate against consistent snapshots after adapting the workflow. A mismatch may mean legitimate changes since the last nightly backup, not corruption. Restore copies one backup sample to a newly created private temporary directory and compares its SHA-256 and size to the restored copy; it also checks the current source when available. It does not preserve ACLs or test databases.

Use a fixed local invocation or a separately approved Semaphore task that invokes the reviewed, installed script and private config path with one fixed operation. Do not expose a generic host shell, runtime arguments, arbitrary file paths, or a root-capable SSH proxy through MCP. Configure and verify the exact task template and dedicated execution identity before permitting execution through the existing Semaphore action. If elevated privileges are necessary for access, grant only the exact reviewed fixed invocation; never authorize a generic Python or shell interpreter. Prefer read-only ACLs on selected data when feasible. Do not enable a broad TrueNAS SYSTEM_CRON_WRITE role just to run these helpers.

This repository change does not install a script, create a task, or prove actual backup results. The current nightly cron stays unchanged. Check the GitHub tests and run a controlled live restore before claiming protection.
