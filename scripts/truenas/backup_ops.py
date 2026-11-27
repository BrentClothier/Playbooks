#!/usr/bin/env python3
"""Fixed-purpose, local legacy backup verification and isolated sample restore.

Run only from an owner-approved local command or fixed Semaphore template.
Never expose CLI arguments, configuration path or arbitrary commands through MCP.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

GROUPS = {"files": ("Stuff", "audiobooks"),
          "applications": ("apps", "configs", "ansible_data")}
MAX_SAMPLE = 64 * 1024 * 1024
CONFIG_KEYS = {"source_mount", "backup_files_mount", "backup_applications_mount",
               "sample_group", "sample_relative_path"}


def load_config(path):
    path = Path(path)
    if not path.is_absolute() or str(path.resolve()) != str(path):
        raise ValueError("Configuration must be an absolute non-symlink path.")
    # The config and every ancestor must be protected from untrusted edits.
    for parent in path.parents:
        st = parent.stat()
        if st.st_uid != 0 or st.st_mode & 0o022:
            raise ValueError("Configuration ancestors must be root-owned and protected.")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "r", encoding="utf-8") as f:
        st = os.fstat(f.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o077:
            raise ValueError("Configuration must be a private root-owned regular file.")
        if st.st_size > 16384:
            raise ValueError("Configuration too large.")
        config = json.load(f)
    if not isinstance(config, dict) or set(config) != CONFIG_KEYS:
        raise ValueError("Unexpected configuration fields.")
    if any(not isinstance(value, str) for value in config.values()):
        raise ValueError("Configuration values must be strings.")
    return config


def mounted(path):
    p = Path(path)
    if not p.is_absolute() or not str(p).startswith("/mnt/") or str(p.resolve()) != str(p):
        raise ValueError("Expected a canonical dataset mount under /mnt.")
    if not p.is_dir() or not os.path.ismount(p):
        raise ValueError("Required dataset mount absent.")
    return p


def child_dir(root, name):
    path = root / name
    if path.resolve() != path or not path.is_dir() or path.stat().st_dev != root.stat().st_dev:
        raise ValueError("Required directory missing, symlinked or on another mount.")
    return path


def locations(config):
    source = mounted(config["source_mount"])
    files = mounted(config["backup_files_mount"])
    apps = mounted(config["backup_applications_mount"])
    if len({p.stat().st_dev for p in (source, files, apps)}) != 3:
        raise ValueError("Expected three distinct mounted datasets.")
    # Separate pool names are necessary here; physical independence is verified
    # separately by the operator using the live ZFS topology.
    pool = lambda p: p.relative_to("/mnt").parts[0]
    if pool(source) == pool(files) or pool(files) != pool(apps):
        raise ValueError("Unexpected source/backup pool layout.")
    return child_dir(source, "data"), {"files": files, "applications": apps}


def verify(config):
    source, destinations = locations(config)
    results = []
    for group, dirs in GROUPS.items():
        dest = destinations[group]
        sources = [child_dir(source, name) for name in dirs]
        for name in dirs:
            child_dir(dest, name)
        proc = subprocess.run(
            ["/usr/bin/rsync", "--dry-run", "--archive", "--hard-links",
             "--acls", "--xattrs", "--numeric-ids", "--checksum", "--stats",
             "--", *map(str, sources), str(dest) + "/"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            timeout=7200, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
            check=False,
        )
        match = re.search(r"^Number of regular files transferred:\s*([0-9,]+)\s*$",
                          proc.stdout, re.MULTILINE)
        transfers = int(match.group(1).replace(",", "")) if match else None
        results.append({"group": group, "rsync_exit": proc.returncode,
                        "regular_files_needing_transfer": transfers})
    passed = all(x["rsync_exit"] == 0 and x["regular_files_needing_transfer"] == 0
                 for x in results)
    return {"operation": "verify", "passed": passed, "groups": results,
            "coverage": "Selected legacy data; no delete; does not verify extra destination files, database consistency or metadata-only drift."}


def sample_parts(config):
    group = config["sample_group"]
    rel = config["sample_relative_path"]
    parts = rel.split("/")
    if group not in GROUPS or not 2 <= len(parts) <= 12 or parts[0] not in GROUPS[group]:
        raise ValueError("Sample must be inside a selected backup group.")
    if len(rel) > 512 or any(not p or p.startswith(".") or "\\" in p or
                            any(ord(c) < 32 for c in p) for p in parts):
        raise ValueError("Invalid sample path.")
    return group, parts


def sample_digest(root, parts, destination=None):
    """Open every path component relative to a verified directory descriptor."""
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY
    directory = os.open(root, flags)
    try:
        device = os.fstat(directory).st_dev
        for part in parts[:-1]:
            new = os.open(part, flags, dir_fd=directory)
            os.close(directory)
            directory = new
            if os.fstat(directory).st_dev != device:
                raise ValueError("Sample crosses a mount.")
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=directory)
        with os.fdopen(fd, "rb") as f:
            before = os.fstat(f.fileno())
            if (not stat.S_ISREG(before.st_mode) or before.st_dev != device or
                    before.st_size > MAX_SAMPLE or before.st_size == 0):
                raise ValueError("Sample must be a nonempty bounded regular file.")
            sha = hashlib.sha256()
            size = 0
            while chunk := f.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_SAMPLE:
                    raise ValueError("Sample exceeded size limit.")
                sha.update(chunk)
                if destination is not None:
                    destination.write(chunk)
            after = os.fstat(f.fileno())
            if (size != before.st_size or
                    (before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
                    (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
                raise ValueError("Sample changed while being read.")
            return sha.digest(), size
    finally:
        os.close(directory)


def restore(config):
    source, destinations = locations(config)
    group, parts = sample_parts(config)
    # No destination path is accepted from callers. Private temporary file,
    # content only, bounded size; never overwrite source or backup.
    with tempfile.TemporaryDirectory(prefix="homelab-restore-") as temp:
        restored = Path(temp) / "sample"
        with restored.open("xb") as out:
            backup_hash, size = sample_digest(destinations[group], parts, out)
            out.flush()
            os.fsync(out.fileno())
        restored_hash, restored_size = sample_digest(Path(temp), ["sample"])
        source_match = None
        try:
            source_hash, source_size = sample_digest(source, parts)
            source_match = (source_hash, source_size) == (backup_hash, size)
        except (OSError, ValueError):
            pass
        passed = (restored_hash, restored_size) == (backup_hash, size)
        return {"operation": "restore", "passed": passed, "bytes": size,
                "restored_matches_backup": passed, "current_source_matches_backup": source_match,
                "coverage": "One sample's contents only; temporary copy removed; source differences may be legitimate; not an ACL or database restore test."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("verify", "restore"))
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        result = verify(config) if args.operation == "verify" else restore(config)
    except (OSError, ValueError, subprocess.SubprocessError):
        # Do not print private paths, filenames, raw subprocess output or config.
        result = {"operation": args.operation, "passed": False,
                  "error": "Preflight or operation failed; inspect locally."}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
