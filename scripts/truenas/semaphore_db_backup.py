#!/usr/bin/env python3
"""Owner-installed, fixed-purpose local Semaphore logical backup.

No MCP sudo grant. No secrets, database contents, or raw subprocess output
are emitted. Catalog validation is not a restore test.
"""
import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

SOURCE = Path("/mnt/USB_Storage_Space/appdata/semaphore/database")
BACKUP = Path("/mnt/Backup/system")
DEST = BACKUP / "semaphore-db"
PROJECT = "ix-semaphore"
IMAGE = "postgres:16.16-trixie"
DOCKER = ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock"]
ENV = {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}


def run(args, **kwargs):
    return subprocess.run(DOCKER + args, check=True, stderr=subprocess.DEVNULL,
                          env=ENV, timeout=600, **kwargs)


def capture(args):
    return run(args, stdout=subprocess.PIPE, text=True).stdout.strip()


def check_mount(path):
    if path.resolve() != path or not path.is_dir() or not os.path.ismount(path):
        raise ValueError("Expected canonical dataset mount")


def private_dir(path):
    # All path components must be protected before writing credential-bearing data.
    for parent in path.parents:
        s = parent.stat()
        if parent.resolve() != parent or s.st_uid != 0 or s.st_mode & 0o022:
            raise ValueError("Unsafe backup ancestor")
    path.mkdir(mode=0o700, exist_ok=True)
    s = path.lstat()
    if not stat.S_ISDIR(s.st_mode) or s.st_uid != 0 or s.st_mode & 0o077:
        raise ValueError("Unsafe backup directory")


def container_id():
    ids = capture(["ps", "--filter", "label=com.docker.compose.project=" + PROJECT,
                   "--filter", "label=com.docker.compose.service=postgres",
                   "--format", "{{.ID}}"]).splitlines()
    if len(ids) != 1 or not re.fullmatch(r"[0-9a-f]{12,64}", ids[0]):
        raise ValueError("Expected one running PostgreSQL service")
    cid = ids[0]
    if capture(["inspect", "--format", "{{.Config.Image}}", cid]) != IMAGE:
        raise ValueError("Unexpected database image")
    mounts = json.loads(capture(["inspect", "--format", "{{json .Mounts}}", cid]))
    matches = [m for m in mounts if m.get("Destination") == "/var/lib/postgresql/data"]
    if (len(matches) != 1 or matches[0].get("Type") != "bind"
            or matches[0].get("Source") != str(SOURCE) or matches[0].get("RW") is not True):
        raise ValueError("Unexpected database mount")
    return cid


def create_archive(cid, dest, before_publish):
    # Publish a unique final name by hard link only after a successful dump,
    # header/catalog check and mount revalidation. Never replace an archive.
    with tempfile.NamedTemporaryFile(dir=dest, prefix=".partial-", delete=False) as out:
        tmp = Path(out.name)
        try:
            run(["exec", "--user", "postgres", cid, "pg_dump", "--format=custom",
                 "--no-password", "--username=semaphore", "--dbname=semaphore"],
                stdout=out)
            out.flush()
            os.fsync(out.fileno())
            size = out.tell()
            if not size:
                raise ValueError("Empty archive")
            with tmp.open("rb") as inp:
                run(["exec", "-i", "--user", "postgres", cid,
                     "pg_restore", "--list"], stdin=inp, stdout=subprocess.DEVNULL)
            before_publish()
            stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            final = dest / ("semaphore-" + stamp + ".dump")
            os.link(tmp, final)
            fd = os.open(dest, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
            return size
        finally:
            tmp.unlink(missing_ok=True)


def backup():
    if os.geteuid() != 0:
        raise ValueError("Local root execution required")
    os.umask(0o077)
    check_mount(SOURCE)
    check_mount(BACKUP)
    device = BACKUP.stat().st_dev
    if SOURCE.stat().st_dev == device:
        raise ValueError("Backup must be on separate dataset")
    private_dir(DEST)
    if DEST.stat().st_dev != device:
        raise ValueError("Unexpected nested backup mount")
    def revalidate():
        check_mount(BACKUP)
        if BACKUP.stat().st_dev != device or DEST.stat().st_dev != device:
            raise ValueError("Backup mount changed")
    fd = os.open(DEST / ".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_uid != 0 or s.st_mode & 0o077:
            raise ValueError("Unsafe lock")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        cid = container_id()
        size = create_archive(cid, DEST, revalidate)
        return {"operation": "semaphore-db-backup", "passed": True,
                "bytes": size, "catalog_validated": True, "restore_tested": False}
    finally:
        os.close(fd)


def main():
    if sys.argv[1:] != ["backup"]:
        return 2
    try:
        result = backup()
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        result = {"operation": "semaphore-db-backup", "passed": False,
                  "error": "Local preflight, dump or catalog validation failed."}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
