# Storage and Backups

## Current storage roles

The environment currently uses a mix of:

- node-local Proxmox storage;
- redundant `USB_Storage_Space`;
- Proxmox Backup Server storage;
- an NFS storage LXC;
- MinIO object storage.

The NFS storage LXC contains the HomeLab's **real/authoritative user data**. Compute and container infrastructure should be treated as more replaceable than the data stored there.

`USB_Storage_Space` has storage-level redundancy and is an important capacity tier. It is also used by the isolated Humboldt VM design.

## Application storage

The long-term goal is for Docker **deployment definitions and reproducible configuration** to live in GitHub as code: Compose files, Ansible, OpenTofu, templates, and other non-secret declarative configuration.

Mutable application datasets, media, databases, credentials, and other state that does not belong in Git must remain on appropriate persistent storage. The NFS storage LXC is currently the primary location for the data considered "real."

The environment is in the middle of a transition from manually managed infrastructure toward Git/IaC as the source of truth. A major purpose of the ChatGPT HomeLab integration is to help complete that transition.

MinIO is available for object-style storage. The Humboldt data platform is expected to use it for original/raw documents once that integration is implemented.

## Backup policy

The current infrastructure backup cadence is **weekly**.

Proxmox Backup Server currently provides VM/LXC backup capability, but the NFS storage LXC's underlying real data is **not currently backed up** because sufficient secondary storage is not yet available.

This is an acknowledged risk and should remain visible in planning. Storage redundancy protects against some device failures, but it is not a substitute for an independent backup.

## Direction

The target state is increasingly reproducible infrastructure managed through Git and IaC. Once the environment can be recreated reliably, Proxmox Backup Server is intended to be retired.

Before PBS is retired, the real NFS data needs an independent backup strategy. IaC can replace infrastructure configuration; it cannot recreate irreplaceable user data.

Future storage changes should continue to document:

- failure domains and redundancy;
- independent backup capacity;
- restore testing;
- database/iSCSI requirements where applicable;
- network bandwidth and redundancy.
