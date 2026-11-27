"""Semaphore client for a fixed, separately provisioned SSH forced command."""
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

USER = "homelab-backup"


def settings(env):
    host = env.get("HOMELAB_BACKUP_HOST", "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}", host) or ".." in host:
        raise ValueError("Invalid runner host.")
    operation = env.get("HOMELAB_BACKUP_OPERATION")
    if operation not in ("verify", "restore"):
        raise ValueError("Invalid operation.")
    public = env.get("HOMELAB_BACKUP_HOST_KEY", "")
    if not re.fullmatch(r"ssh-ed25519 [A-Za-z0-9+/]{40,100}={0,2}", public):
        raise ValueError("Expected pinned ed25519 SSH host key without comment.")
    encoded = env.get("HOMELAB_BACKUP_KEY_B64", "")
    if not 1 <= len(encoded) <= 16384:
        raise ValueError("Missing runner key.")
    key = base64.b64decode(encoded, validate=True)
    if not key.startswith(b"-----BEGIN OPENSSH PRIVATE KEY-----\n") or not key.rstrip().endswith(b"-----END OPENSSH PRIVATE KEY-----"):
        raise ValueError("Expected OpenSSH private key.")
    return host, operation, public, key


def run(env):
    host, operation, public, key = settings(env)
    with tempfile.TemporaryDirectory(prefix="backup-ssh-") as tmp:
        private = Path(tmp) / "identity"
        fd = os.open(private, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(key)
        known = Path(tmp) / "known_hosts"
        known.write_text(host + " " + public + "\n")
        command = ["ssh", "-F", "/dev/null", "-T", "-o", "BatchMode=yes",
                   "-o", "IdentitiesOnly=yes", "-o", "IdentityAgent=none",
                   "-o", "StrictHostKeyChecking=yes", "-o", "HostKeyAlgorithms=ssh-ed25519",
                   "-o", "GlobalKnownHostsFile=/dev/null", "-o", "UserKnownHostsFile=" + str(known),
                   "-o", "PasswordAuthentication=no", "-o", "KbdInteractiveAuthentication=no",
                   "-o", "ClearAllForwardings=yes", "-o", "ControlMaster=no",
                   "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=30",
                   "-o", "ServerAliveCountMax=3", "-i", str(private), "-l", USER,
                   host, "backup"]
        p = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, timeout=7350,
                           env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"}, check=False)
    if len(p.stdout) > 8192:
        raise ValueError("Unexpected runner response.")
    result = json.loads(p.stdout)
    if not isinstance(result, dict) or result.get("operation") != operation or type(result.get("passed")) is not bool:
        raise ValueError("Unexpected runner result.")
    safe = {"operation": operation, "passed": result["passed"] and p.returncode == 0}
    if operation == "verify":
        groups = result.get("groups")
        if isinstance(groups, list):
            safe["groups"] = [{k: row.get(k) for k in ("group", "rsync_exit", "regular_files_needing_transfer")}
                              for row in groups if isinstance(row, dict)
                              and row.get("group") in ("files", "applications")
                              and type(row.get("rsync_exit")) is int
                              and (row.get("regular_files_needing_transfer") is None or type(row.get("regular_files_needing_transfer")) is int)]
    else:
        for k in ("restored_matches_backup", "current_source_matches_backup"):
            if type(result.get(k)) is bool or result.get(k) is None:
                safe[k] = result.get(k)
        if type(result.get("bytes")) is int:
            safe["bytes"] = result["bytes"]
    return safe


if __name__ == "__main__":
    try:
        result = run(os.environ)
    except (OSError, ValueError, subprocess.SubprocessError):
        result = {"passed": False, "error": "Restricted runner preflight or execution failed. Inspect locally."}
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["passed"] else 1)
