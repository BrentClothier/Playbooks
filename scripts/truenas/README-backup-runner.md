# Restricted TrueNAS backup runner (owner installation required)

This stage uses two separately restricted SSH keys. No Docker socket, generic
shell tool, root login, arbitrary sudo, or automatic host installation.
The backup helper remains the trusted root-owned code installed from a reviewed
commit, not a script downloaded or run as root from Git main on every task.

## Owner setup

1. Create a dedicated non-administrator TrueNAS local user **homelab-backup**,
   with a working non-privileged shell for SSH forced commands, no password
   authentication, no other keys, no admin groups, no general sudo, and no
   Tailscale SSH bypass. Use native TrueNAS account/SSH settings; confirm the
   service is limited to the trusted network. Do not change existing admin access.
2. Select an owner-controlled persistent directory on a mounted dataset, e.g.
   a dedicated backup-runner dataset under appdata. All ancestors must be root
   owned and not group/world writable. Copy the reviewed backup_ops.py into
   that directory as root, mode 0700; do not permit the automation user to
   modify it. Record and verify its SHA256 from the reviewed Git revision.
   Create a root-owned mode 0600 config.json with keys source_mount,
   backup_files_mount, backup_applications_mount, sample_group and
   sample_relative_path. Use actual mounted dataset roots and a private
   nonempty representative file of at most 64 MiB. Never commit the config.
3. Using native TrueNAS sudo configuration, allow ONLY the two exact commands
   (replace /ABSOLUTE/ROOT-OWNED/PATH with the actual installed path):
   
   /usr/bin/python3 -I /ABSOLUTE/ROOT-OWNED/PATH/backup_ops.py verify --config /ABSOLUTE/ROOT-OWNED/PATH/config.json
   
   /usr/bin/python3 -I /ABSOLUTE/ROOT-OWNED/PATH/backup_ops.py restore --config /ABSOLUTE/ROOT-OWNED/PATH/config.json
   
   Require passwordless sudo for exactly those commands. No wildcards, no
   interpreter-only rule, no SETENV. Verify with sudo -l for the dedicated user.
   Do not install if TrueNAS cannot preserve these exact restrictions.
4. Generate two distinct dedicated ed25519 keypairs privately (no passphrase,
   because tasks are noninteractive). In the user's authorized_keys, install
   ONLY the matching forced-command public keys, each on one line:
   
   restrict,command="/usr/bin/sudo -n /usr/bin/python3 -I /ABSOLUTE/ROOT-OWNED/PATH/backup_ops.py verify --config /ABSOLUTE/ROOT-OWNED/PATH/config.json" ssh-ed25519 VERIFY_PUBLIC_KEY
   
   restrict,command="/usr/bin/sudo -n /usr/bin/python3 -I /ABSOLUTE/ROOT-OWNED/PATH/backup_ops.py restore --config /ABSOLUTE/ROOT-OWNED/PATH/config.json" ssh-ed25519 RESTORE_PUBLIC_KEY
   
   Ensure ownership/modes of home and authorized_keys meet SSH requirements.
   Verify native settings preserve the restrictions after service reload.
   Independently test that arbitrary commands are replaced by the fixed
   operation, forwarding and PTY are denied, no password or unrestricted key
   works, and unrelated sudo commands are denied. Each key is capable of its
   fixed operation even if used outside Semaphore; revoke it at the server to
   remove that capability. Do not enable Tailscale SSH for this account.
5. Obtain the NAS ed25519 host public key directly from its trusted console;
   do not trust ssh-keyscan alone. In Semaphore project HomeLab TrueNAS
   Operations create separate variable groups named TrueNAS Backup Verify
   and TrueNAS Backup Restore. Set these environment variables (not extra
   JSON arguments), with the matching operation/key in each group:
   
   HOMELAB_BACKUP_HOST = actual NAS hostname or IPv4 reachable from Semaphore
   
   HOMELAB_BACKUP_HOST_KEY = ssh-ed25519 followed by the verified base64 public key, no comment
   
   HOMELAB_BACKUP_OPERATION = verify or restore
   
   HOMELAB_BACKUP_KEY_B64 = base64 of the matching private OpenSSH key
   (store as a secret environment variable, never plain text in Git or chat)
   
   Confirm the Semaphore task image has an OpenSSH client and Python.
   Do not use the same key for both groups. Protect task editing and logs;
   the project scope trusts owner-reviewed template definitions and Git main.

## MCP

Set SEMAPHORE_ALLOWED_TEMPLATES=1:* (substitute actual dedicated project ID).
Keep SEMAPHORE_BOOTSTRAP_ENABLED=false. The wildcard is checked against the
dedicated project name and verified native HTTPS endpoint. Global wildcard is
legacy compatibility, not recommended. Project-wide scope includes future
owner-created eligible templates; it is not a guarantee those templates
are harmless. Restrict template-editing rights and review source changes.

After the owner completes runner installation and negative tests, call
semaphore_prepare_backup_templates with prepare:homelab-backup-templates.
This creates two templates bound to the respective private variable groups,
never creates or returns credentials, and does not execute tasks. Run the
restore template first (one sample to private temporary storage); the checksum
verification can run for up to two hours. Confirm status and sanitized
output. Both check only selected legacy data; appdata backup and PostgreSQL
logical backup/restore are separate future work. No destructive actions.

Rollback: remove the two forced-command keys, disable the dedicated account,
remove the two exact sudo grants, revert MCP to 1:1, and retain the data,
existing cron and backup pool. Never delete datasets for this rollback.
