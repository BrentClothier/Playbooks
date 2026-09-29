# Storage and Backups

## Current storage roles

The environment currently uses a mix of:

- node-local Proxmox storage;
- ZFS-backed `USB_Storage_Space`;
- Proxmox Backup Server storage;
- an NFS workload;
- MinIO object storage.

`USB_Storage_Space` is an important capacity tier and is used by the isolated Humboldt VM design.

## Application storage

Application persistence is intentionally outside ephemeral container layers. Docker stacks should use named volumes, bind-mounted persistent paths, NFS, databases, or object storage as appropriate.

MinIO is available for object-style storage. The Humboldt data platform is expected to use it for original/raw documents once that integration is implemented.

## Backup intent

Proxmox Backup Server is attached to the Proxmox nodes and is the intended VM/LXC backup layer.

This document still needs the human policy details for:

- backup frequency;
- retention targets;
- which workloads are considered irreplaceable;
- whether application-level database dumps are required in addition to VM/container backups;
- whether any copy is kept off-site.

Until those are documented, do not assume that the mere existence of PBS means every workload meets its recovery objective.

## Storage design direction

The long-term design may move toward more centralized NAS-backed storage, potentially including all-flash storage. Any such migration should document:

- failure domains;
- ECC expectations;
- database/iSCSI requirements;
- backup independence from primary storage;
- network bandwidth and redundancy.
