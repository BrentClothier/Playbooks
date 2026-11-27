"""Narrow read-only TrueNAS 25.10 JSON-RPC 2.0 integration."""
import asyncio
import json
import math
import re
import time
import os
import ssl
from urllib.parse import urlsplit, urlunsplit

from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException


class _NoRedirectConnect(connect):
    """Never send the API key to a redirected WebSocket endpoint."""
    def process_redirect(self, exc):
        return exc


def _endpoint():
    url = os.getenv("TRUENAS_URL", "").strip()
    key = os.getenv("TRUENAS_API_KEY", "")
    if not url or not key:
        raise RuntimeError("TrueNAS is not configured.")
    try:
        parsed = urlsplit(url)
        valid = (
            parsed.scheme in ("https", "wss")
            and parsed.hostname
            and parsed.username is None
            and parsed.password is None
            and parsed.path in ("", "/", "/api/current")
            and not parsed.query and not parsed.fragment
        )
        _ = parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise RuntimeError("TRUENAS_URL must be an HTTPS origin or WSS /api/current.")
    if os.getenv("TRUENAS_VERIFY_SSL", "true").lower() not in {"true", "1", "yes", "on"}:
        raise RuntimeError("TrueNAS requires verified TLS; configure a trusted certificate.")
    username = os.getenv("TRUENAS_USERNAME", "homelab-mcp").strip()
    if not username:
        raise RuntimeError("TrueNAS service account username is missing.")
    return urlunsplit(("wss", parsed.netloc, "/api/current", "", "")), username, key


# No public tool accepts a method name, arbitrary filters, or raw RPC arguments.
_READ_METHODS = frozenset({
    "system.info", "alert.list", "disk.query", "pool.query",
    "pool.dataset.query", "pool.snapshot.query", "sharing.nfs.query",
    "sharing.smb.query", "app.query", "core.get_jobs", "interface.query",
    "vm.query", "service.query",
    "disk.temperatures", "pool.scrub.query", "pool.snapshottask.query",
    "replication.query", "cloudsync.query", "cloud_backup.query",
    "rsynctask.query", "reporting.get_data", "pool.import_find",
    "update.status", "vm.status", "nfs.client_count",
    "cronjob.query", "filesystem.stat", "app.container_console_choices", "app.available",
    "filesystem.listdir", "filesystem.getacl",
})


async def _exchange(ws, request_id, method, params):
    await ws.send(json.dumps({
        "jsonrpc": "2.0", "id": request_id, "method": method, "params": params,
    }))
    for _ in range(100):
        response = json.loads(await ws.recv())
        if not isinstance(response, dict):
            raise RuntimeError("Unexpected TrueNAS JSON-RPC response.")
        if response.get("id") != request_id:
            continue
        if "error" in response:
            # Never include server error payloads, request parameters or credentials.
            raise RuntimeError(f"TrueNAS {method} failed; check API role and version.")
        if "result" not in response:
            raise RuntimeError("TrueNAS response did not contain a result.")
        return response["result"]
    raise RuntimeError("TrueNAS response limit exceeded.")


async def _read(method, params=None):
    if method not in _READ_METHODS:
        raise ValueError("TrueNAS RPC method is not allowed.")
    uri, username, key = _endpoint()
    try:
        async with asyncio.timeout(30):
            async with _NoRedirectConnect(
                uri, ssl=ssl.create_default_context(), proxy=None,
                open_timeout=8, close_timeout=2, max_size=8 * 1024 * 1024,
            ) as ws:
                auth = await _exchange(ws, 1, "auth.login_ex", [{
                    "mechanism": "API_KEY_PLAIN", "username": username,
                    "api_key": key, "login_options": {"user_info": False},
                }])
                if not isinstance(auth, dict) or auth.get("response_type") != "SUCCESS":
                    raise RuntimeError("TrueNAS API key authentication failed.")
                result = await _exchange(ws, 2, method, params or [])
                # Discovery starts a read-only scan job, not an import. Poll only
                # the job we just initiated, on the same authenticated session.
                if method == "pool.import_find":
                    if type(result) is not int or result < 1:
                        raise RuntimeError("Unexpected pool discovery job ID.")
                    for request_id in range(3, 24):
                        jobs = await _exchange(ws, request_id, "core.get_jobs",
                            [[["id", "=", result]], {"limit": 1}])
                        if isinstance(jobs, list) and jobs:
                            job = jobs[0]
                            if not isinstance(job, dict) or job.get("id") != result:
                                raise RuntimeError("Unexpected pool discovery job.")
                            if job.get("state") == "SUCCESS":
                                return job.get("result")
                            if job.get("state") in ("FAILED", "ABORTED"):
                                raise RuntimeError("TrueNAS pool discovery did not complete successfully.")
                        await asyncio.sleep(1)
                    raise RuntimeError("TrueNAS pool discovery still pending; use the UI for longer scans.")
                return result
    except (TimeoutError, OSError, WebSocketException, ValueError):
        raise RuntimeError(
            "TrueNAS connection or response failed; check internal DNS, TLS, WebSockets and API availability."
        ) from None



# Stage 3: dedicated credentials, exact server-configured targets, no generic
# tool accepting RPC names or payloads. No destructive storage methods.
_WRITE_METHODS = frozenset({"pool.dataset.create", "pool.snapshot.create",
                            "app.start", "app.stop"})
_PROTECTED_APPS = frozenset({"homelab-mcp", "tailscale", "semaphore",
                            "nginx", "nginx-proxy-manager", "authentik",
                            "portainer", "secure-mcp-tunnel", "mcp-tunnel"})


def _write_credentials():
    if os.getenv("TRUENAS_ADMIN_ENABLED") != "true":
        raise ValueError("TrueNAS administration is disabled.")
    uri, _, read_key = _endpoint()
    username = os.getenv("TRUENAS_ADMIN_USERNAME", "").strip()
    key = os.getenv("TRUENAS_ADMIN_API_KEY", "")
    if not username or not key or key == read_key:
        raise ValueError("Separate TrueNAS administration credentials required.")
    return uri, username, key


def _allowed_target(variable, target, confirmation):
    _write_credentials()
    allowed = {x.strip() for x in os.getenv(variable, "").split(",") if x.strip()}
    if target not in allowed:
        raise ValueError("Target is not explicitly enabled in backend configuration.")
    if confirmation != target:
        raise ValueError("Exact target confirmation required.")


def _dataset_name(name):
    if not isinstance(name, str) or len(name) > 240 or not re.fullmatch(
            r"[A-Za-z0-9_.:-]+(?:/[A-Za-z0-9_.:-]+)*", name):
        raise ValueError("Invalid dataset identifier.")
    if any(p in (".", "..") or p.startswith(".") for p in name.split("/")):
        raise ValueError("Invalid dataset identifier.")
    return name


async def _exact_dataset(name, required=True):
    rows = await _read("pool.dataset.query", [[["id", "=", name]],
        {"limit": 2, "extra": {"flat": True, "retrieve_user_props": False}}])
    if not isinstance(rows, list) or len(rows) > 1:
        raise RuntimeError("Unexpected dataset inventory response.")
    if not rows:
        if required:
            raise ValueError("Required dataset does not exist.")
        return None
    row = rows[0]
    if (not isinstance(row, dict) or row.get("id") != name or
            row.get("type") != "FILESYSTEM" or row.get("locked") is True or
            row.get("mountpoint") != "/mnt/" + name):
        raise ValueError("Dataset is not an accessible standard filesystem.")
    return row


async def _admin_rpc(method, params):
    if method not in _WRITE_METHODS:
        raise ValueError("TrueNAS write method is not allowed.")
    uri, username, key = _write_credentials()
    try:
        async with asyncio.timeout(35):
            async with _NoRedirectConnect(
                uri, ssl=ssl.create_default_context(), proxy=None,
                open_timeout=8, close_timeout=2, max_size=8 * 1024 * 1024,
            ) as ws:
                auth = await _exchange(ws, 1, "auth.login_ex", [{
                    "mechanism": "API_KEY_PLAIN", "username": username,
                    "api_key": key, "login_options": {"user_info": False},
                }])
                if not isinstance(auth, dict) or auth.get("response_type") != "SUCCESS":
                    raise RuntimeError("TrueNAS administration authentication failed.")
                result = await _exchange(ws, 2, method, params)
                if method not in ("app.start", "app.stop"):
                    return result
                if type(result) is not int or result < 1:
                    raise RuntimeError("Unexpected application job identifier; verify state before retry.")
                for request_id in range(3, 20):
                    rows = await _exchange(ws, request_id, "core.get_jobs",
                        [[["id", "=", result]], {"limit": 1}])
                    if isinstance(rows, list) and len(rows) == 1:
                        job = rows[0]
                        if not isinstance(job, dict) or job.get("id") != result or job.get("method") != method:
                            raise RuntimeError("Unexpected application job metadata.")
                        state = job.get("state")
                        if state in ("SUCCESS", "FAILED", "ABORTED"):
                            return {"job_id": result, "state": state}
                    await asyncio.sleep(1)
                return {"job_id": result, "state": "PENDING_OR_UNKNOWN"}
    except (TimeoutError, OSError, WebSocketException, ValueError):
        raise RuntimeError("Administration request outcome unknown; inspect live state before retry.") from None


async def _create_dataset(name, confirmation):
    name = _dataset_name(name)
    if "/" not in name:
        raise ValueError("Pool creation is not supported.")
    _allowed_target("TRUENAS_ADMIN_DATASETS", name, confirmation)
    existing = await _exact_dataset(name, required=False)
    if existing:
        return {"dataset": name, "state": "ALREADY_EXISTS", "changed": False}
    await _exact_dataset(name.rsplit("/", 1)[0])
    result = await _admin_rpc("pool.dataset.create", [{"name": name,
        "type": "FILESYSTEM", "create_ancestors": False}])
    if not isinstance(result, dict) or result.get("id") != name:
        raise RuntimeError("Unexpected create response; inspect inventory before retry.")
    await _exact_dataset(name)
    return {"dataset": name, "state": "CREATED", "changed": True}


async def _create_snapshot(dataset, name, confirmation):
    dataset = _dataset_name(dataset)
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}", name):
        raise ValueError("Invalid snapshot name.")
    if confirmation != dataset + "@" + name:
        raise ValueError("Exact snapshot confirmation required.")
    _allowed_target("TRUENAS_ADMIN_SNAPSHOT_DATASETS", dataset, dataset)
    await _exact_dataset(dataset)
    ident = dataset + "@" + name
    async def exists():
        rows = await _read("pool.snapshot.query", [[["id", "=", ident]], {"limit": 2}])
        if not isinstance(rows, list) or len(rows) > 1:
            raise RuntimeError("Unexpected snapshot inventory response.")
        if rows and (not isinstance(rows[0], dict) or rows[0].get("id") != ident):
            raise RuntimeError("Unexpected snapshot identifier.")
        return bool(rows)
    if await exists():
        return {"snapshot": ident, "state": "ALREADY_EXISTS", "changed": False}
    result = await _admin_rpc("pool.snapshot.create", [{"dataset": dataset,
        "name": name, "recursive": False}])
    if not isinstance(result, dict) or result.get("id") != ident or not await exists():
        raise RuntimeError("Snapshot creation unverified; inspect inventory before retry.")
    return {"snapshot": ident, "state": "CREATED", "changed": True}


async def _app_state(name):
    rows = await _read("app.query", [[["id", "=", name]], {"limit": 2,
        "extra": {"retrieve_config": False, "include_app_schema": False}}])
    if (not isinstance(rows, list) or len(rows) != 1 or
            not isinstance(rows[0], dict) or rows[0].get("id") != name):
        raise ValueError("Application not found in live inventory.")
    return rows[0].get("state")


async def _set_app_state(name, action, confirmation):
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", name):
        raise ValueError("Invalid application name.")
    if name in _PROTECTED_APPS or any(word in name for word in ("mcp", "tunnel", "tailscale")):
        raise ValueError("Management and connectivity applications are protected.")
    if action not in ("start", "stop") or confirmation != action + ":" + name:
        raise ValueError("Exact action and application confirmation required.")
    _allowed_target("TRUENAS_ADMIN_APPS", name, name)
    expected = "RUNNING" if action == "start" else "STOPPED"
    before = await _app_state(name)
    if before == expected:
        return {"app": name, "state": before, "changed": False}
    if before not in ("RUNNING", "STOPPED"):
        raise ValueError("Application is not in a stable state; inspect before changing.")
    job = await _admin_rpc("app." + action, [name])
    after = await _app_state(name)
    return {"app": name, "job": job, "state": after,
            "verified": job.get("state") == "SUCCESS" and after == expected,
            "coverage": "Job and reported app state only; not endpoint health."}



# Stage 4 native filesystem metadata, disabled until explicit dataset scope.
# No file contents, arbitrary absolute paths, recursion or mount crossing.
async def _diagnostic_directory(dataset, relative_dir):
    dataset = _dataset_name(dataset)
    permitted = {x.strip() for x in os.getenv("TRUENAS_DIAGNOSTIC_DATASETS", "").split(",") if x.strip()}
    if dataset not in permitted:
        raise ValueError("Dataset not enabled for directory and ACL inspection.")
    if not isinstance(relative_dir, str) or len(relative_dir) > 240:
        raise ValueError("Invalid relative directory.")
    parts = relative_dir.split("/") if relative_dir else []
    if len(parts) > 4 or any(not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_. -]{0,79}", p)
                             or p in (".", "..") for p in parts):
        raise ValueError("Invalid relative directory.")
    await _dataset_root_stat(dataset)
    path = "/mnt/" + dataset
    for part in parts:
        path += "/" + part
        row = await _read("filesystem.stat", [path])
        if (not isinstance(row, dict) or row.get("realpath") != path or
                row.get("type") != "DIRECTORY" or row.get("is_mountpoint") is not False):
            raise ValueError("Child directory not verified or crosses a mountpoint.")
    return path


async def _directory_entries(dataset, relative_dir="", limit=50, offset=0):
    path = await _diagnostic_directory(dataset, relative_dir)
    count = _limit(limit)
    offset = max(0, min(int(offset), 10000))
    fields = ("name", "type", "size", "uid", "gid", "mode", "acl")
    rows = await _read("filesystem.listdir", [path, [], {"limit": count,
        "offset": offset, "order_by": ["name"], "select": list(fields)}])
    return {"dataset": dataset, "relative_dir": relative_dir,
            **_rows(rows, fields, count, offset),
            "coverage": "One directory, selected metadata; sizes are not recursive usage."}


_ACL_PERMS = ("BASIC", "READ", "WRITE", "EXECUTE", "READ_DATA", "WRITE_DATA",
              "APPEND_DATA", "READ_NAMED_ATTRS", "WRITE_NAMED_ATTRS",
              "DELETE_CHILD", "READ_ATTRIBUTES", "WRITE_ATTRIBUTES", "DELETE",
              "READ_ACL", "WRITE_ACL", "WRITE_OWNER", "SYNCHRONIZE")
_ACL_FLAGS = ("BASIC", "FILE_INHERIT", "DIRECTORY_INHERIT",
              "NO_PROPAGATE_INHERIT", "INHERIT_ONLY", "INHERITED")


async def _directory_acl(dataset, relative_dir=""):
    path = await _diagnostic_directory(dataset, relative_dir)
    row = await _read("filesystem.getacl", [path, True, False])
    if (not isinstance(row, dict) or row.get("path") != path or
            not isinstance(row.get("acl"), list)):
        raise RuntimeError("Unexpected ACL response.")
    entries = []
    for ace in row["acl"][:200]:
        out = _fields(ace, ("tag", "type", "id", "default"))
        for field, keys in (("perms", _ACL_PERMS), ("flags", _ACL_FLAGS)):
            if isinstance(ace.get(field), dict):
                out[field] = _fields(ace[field], keys)
        entries.append(out)
    return {"dataset": dataset, "relative_dir": relative_dir,
        **_fields(row, ("uid", "gid", "acltype")), "entries": entries,
        "truncated": len(row["acl"]) > 200,
        "coverage": "Reported directory ACL only; not effective access or recursive ACL audit."}


def _safe_value(value):
    # Do not expose arbitrary dictionaries, application configs, or job arguments.
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:512]
    if isinstance(value, list):
        return [_safe_value(v) for v in value[:100] if not isinstance(v, (dict, list))]
    return None


def _fields(row, names):
    if not isinstance(row, dict):
        raise RuntimeError("Unexpected TrueNAS result shape.")
    return {key: _safe_value(row[key]) for key in names if key in row}


def _limit(limit):
    return max(1, min(int(limit), 200))


def _rows(result, fields, limit, offset=0, transform=None):
    if not isinstance(result, list):
        raise RuntimeError("Expected a TrueNAS list result.")
    count = _limit(limit)
    return {
        "items": [(transform(row) if transform else _fields(row, fields))
                  for row in result[:count]],
        "offset": offset, "limit": count,
        "possibly_more": len(result) >= count,
    }


async def _query(method, fields, limit=100, offset=0, extra=None, transform=None, filters=None, order_by=None):
    count = _limit(limit)
    offset = max(0, min(int(offset), 10000))
    opts = {"limit": count, "offset": offset}
    if order_by is not None:
        opts["order_by"] = order_by
    if extra is not None:
        opts["extra"] = extra
    result = await _read(method, [filters or [], opts])
    return _rows(result, fields, count, offset, transform)


def _properties(row, keys):
    out = {}
    for key in keys:
        if key in row:
            value = row[key]
            out[key] = (_fields(value, ("value", "rawvalue", "parsed", "source"))
                        if isinstance(value, dict) else _safe_value(value))
    return out


def _vdev(row, depth=0):
    fields = _fields(row, ("type", "path", "device", "disk", "guid", "status",
                           "read_errors", "write_errors", "checksum_errors"))
    children = row.get("children")
    if isinstance(children, list) and depth < 8:
        fields["children"] = [_vdev(v, depth + 1) for v in children[:100] if isinstance(v, dict)]
    return fields


def _pool(row):
    out = _fields(row, ("id", "name", "guid", "status", "healthy", "warning",
                        "size", "allocated", "free", "fragmentation", "path",
                        "status_code", "status_detail"))
    topology = row.get("topology")
    if isinstance(topology, dict):
        out["topology"] = {
            group: [_vdev(v) for v in topology[group][:100] if isinstance(v, dict)]
            for group in ("data", "cache", "log", "spare", "special", "dedup")
            if isinstance(topology.get(group), list)
        }
    if isinstance(row.get("scan"), dict):
        out["scan"] = _fields(row["scan"], ("function", "state", "start_time",
            "end_time", "errors", "percentage", "bytes_processed", "bytes_to_process"))
    return out


_DATASET_PROPERTIES = ("used", "available", "usedbydataset", "usedbysnapshots",
    "quota", "refquota", "acltype", "aclmode", "xattr", "compression",
    "recordsize", "readonly", "canmount", "origin")


def _dataset(row):
    out = _fields(row, ("id", "name", "type", "pool", "mountpoint",
                        "encrypted", "key_loaded", "locked"))
    out.update(_properties(row, _DATASET_PROPERTIES))
    return out


def _snapshot(row):
    out = _fields(row, ("id", "name", "pool", "dataset", "snapshot_name", "createtxg"))
    if isinstance(row.get("properties"), dict):
        out["properties"] = _properties(row["properties"], ("creation", "used", "referenced"))
    return out


_APP_FIELDS = ("id", "name", "state", "version", "human_version", "upgrade_available",
               "image_updates_available", "custom_app")



# Stage 1 diagnostic projections. Never return raw task objects, credentials,
# script fields, arbitrary logs, or opaque nested configuration.
_SCHEDULE = ("minute", "hour", "dom", "month", "dow", "begin", "end")
_TASK_FIELDS = ("id", "enabled", "dataset", "recursive", "lifetime_value",
                "lifetime_unit", "source_datasets", "target_dataset", "direction",
                "transport", "auto", "locked", "path", "keep_last",
                "pool", "pool_name", "threshold")
_JOB_FIELDS = ("id", "state", "time_started", "time_finished", "datetime",
               "last_run", "last_success", "last_snapshot")


def _task_projection(row):
    out = _fields(row, _TASK_FIELDS)
    for key in ("schedule", "restrict_schedule"):
        if isinstance(row.get(key), dict):
            out[key] = _fields(row[key], _SCHEDULE)
    for key in ("state", "job"):
        value = row.get(key)
        if isinstance(value, dict):
            out[key] = _fields(value, _JOB_FIELDS)
            if isinstance(value.get("progress"), dict):
                out[key]["progress"] = _fields(value["progress"], ("percent",))
        elif isinstance(value, str) or value is None:
            out[key] = _safe_value(value)
    return out


async def _task_group(method, limit, offset):
    try:
        return await _query(method, (), limit, offset, transform=_task_projection)
    except (RuntimeError, ValueError):
        return {"error": "Query unavailable; check role, API version and connectivity.",
                "items": None}


def _cron_projection(row):
    # Cron commands and free-form descriptions can contain secrets.
    out = _fields(row, ("id", "enabled", "stdout", "stderr"))
    if isinstance(row.get("schedule"), dict):
        out["schedule"] = _fields(row["schedule"], _SCHEDULE)
    return out


async def _dataset_root_stat(dataset):
    # Only an exact inventoried mounted ZFS dataset root, never an arbitrary path.
    if not isinstance(dataset, str) or len(dataset) > 240 or not re.fullmatch(
            r"[A-Za-z0-9_.:-]+(?:/[A-Za-z0-9_.:-]+)*", dataset):
        raise ValueError("Invalid dataset identifier.")
    if any(part in (".", "..") for part in dataset.split("/")):
        raise ValueError("Invalid dataset identifier.")
    rows = await _read("pool.dataset.query", [[["id", "=", dataset]],
        {"limit": 1, "extra": {"flat": True, "retrieve_user_props": False}}])
    path = "/mnt/" + dataset
    if (not isinstance(rows, list) or len(rows) != 1 or
            not isinstance(rows[0], dict) or rows[0].get("id") != dataset or
            rows[0].get("type") != "FILESYSTEM" or rows[0].get("locked") is True or
            rows[0].get("mountpoint") != path):
        raise ValueError("Dataset is not an inventoried accessible filesystem at its standard mountpoint.")
    stat = await _read("filesystem.stat", [path])
    if (not isinstance(stat, dict) or stat.get("realpath") != path or
            stat.get("type") != "DIRECTORY" or stat.get("is_mountpoint") is not True):
        raise RuntimeError("Dataset mountpoint could not be verified.")
    return {"dataset": dataset, "stat": _fields(stat, (
        "type", "uid", "gid", "mode", "acl", "is_mountpoint", "mount_id")),
        "coverage": "Dataset root only; not child file ownership, ACL entries or client access."}


async def _app_containers(app_name, limit=50):
    if not isinstance(app_name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", app_name):
        raise ValueError("Invalid application name.")
    rows = await _read("app.query", [[["id", "=", app_name]],
        {"limit": 1, "extra": {"retrieve_config": False, "include_app_schema": False}}])
    if (not isinstance(rows, list) or len(rows) != 1 or
            not isinstance(rows[0], dict) or rows[0].get("id") != app_name):
        raise ValueError("Application not found in live inventory.")
    containers = await _read("app.container_console_choices", [app_name])
    if not isinstance(containers, dict):
        raise RuntimeError("Unexpected application container response.")
    return {"app": app_name, **_rows(list(containers.values()),
        ("id", "service_name", "image", "state"), limit),
        "coverage": "Container inventory and state, not health checks, logs or resource statistics."}


def _latest_sample(sample, legend):
    if isinstance(sample, list):
        if (not isinstance(legend, list) or len(sample) != len(legend) or
                len(legend) > 64 or any(not isinstance(k, str) for k in legend) or
                len(set(legend)) != len(legend)):
            return None
        sample = dict(zip(legend, sample))
    return _numeric_map(sample) or None


def _numeric_map(row):
    if not isinstance(row, dict):
        return {}
    return {str(k)[:80]: v for k, v in list(row.items())[:64]
            if v is None or (type(v) in (int, float) and math.isfinite(v))}


_SYSTEM_GRAPHS = ("cpu", "cputemp", "load", "memory", "arcsize", "arcrate",
                  "arcactualrate", "processes", "uptime")
_DEVICE_GRAPHS = ("disk", "interface", "disktemp")
_UPS_GRAPHS = ("upscharge", "upsruntime", "upsload", "upsvoltage",
               "upscurrent", "upsfrequency", "upstemperature")


async def _metric_graphs(graphs, hours):
    end = int(time.time())
    hours = max(1, min(int(hours), 24))
    rows = await _read("reporting.get_data", [graphs,
        {"start": end - hours * 3600, "end": end, "aggregate": True}])
    if not isinstance(rows, list):
        raise RuntimeError("Unexpected TrueNAS reporting result.")
    items = []
    for row in rows[:len(graphs)]:
        out = _fields(row, ("name", "identifier", "start", "end", "legend"))
        agg = row.get("aggregations")
        if isinstance(agg, dict):
            out["aggregations"] = {key: _numeric_map(agg.get(key))
                                   for key in ("min", "mean", "max")}
        data = row.get("data")
        if isinstance(data, list):
            out["sample_count"] = len(data)
            out["latest_sample"] = _latest_sample(data[-1], row.get("legend")) if data else None
        items.append(out)
    return {"hours_requested": hours, "items": items,
            "coverage": "Reported min/mean/max and latest returned sample; empty or null is unknown."}


async def _reporting_metric(metric, identifier, hours):
    if metric in _SYSTEM_GRAPHS:
        if identifier is not None:
            raise ValueError("System-wide metrics do not accept an identifier.")
    elif metric in _DEVICE_GRAPHS:
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", identifier):
            raise ValueError("A valid device identifier is required.")
        method = "interface.query" if metric == "interface" else "disk.query"
        rows = await _read(method, [[], {"limit": 200}])
        if not isinstance(rows, list) or not any(isinstance(r, dict) and identifier in
            (r.get("name"), r.get("devname"), r.get("id")) for r in rows):
            raise ValueError("Identifier is not in the live device inventory.")
    else:
        raise ValueError("Unsupported reporting metric.")
    return await _metric_graphs([{"name": metric, "identifier": identifier}], hours)


def _update_projection(row):
    out = _fields(row, ("code",))
    status = row.get("status")
    if isinstance(status, dict):
        current = status.get("current_version")
        new = status.get("new_version")
        out["current_version"] = _fields(current, ("train", "profile", "matches_profile")) if isinstance(current, dict) else None
        out["new_version"] = _fields(new, ("version",)) if isinstance(new, dict) else None
    if isinstance(row.get("error"), dict):
        out["error"] = _fields(row["error"], ("errname",))
    if isinstance(row.get("update_download_progress"), dict):
        out["update_download_progress"] = _fields(row["update_download_progress"], ("percent",))
    return out


async def _temperatures():
    rows = await _read("disk.query", [[], {"limit": 200}])
    if not isinstance(rows, list):
        raise RuntimeError("Unexpected disk inventory.")
    names = list(dict.fromkeys(row["name"] for row in rows if isinstance(row, dict)
        and isinstance(row.get("name"), str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", row["name"])))
    temps = await _read("disk.temperatures", [names, False]) if names else {}
    if not isinstance(temps, dict):
        raise RuntimeError("Unexpected disk temperature result.")
    return {"items": [{"name": name, "celsius": _numeric_map(temps).get(name)
                       if type(temps.get(name)) in (int, float) else None}
                      for name in names], "coverage": "Current reported temperatures only; null is unknown."}



def register(mcp):
    @mcp.tool
    async def truenas_system_info():
        """Read TrueNAS version, CPU, memory capacity, uptime and load averages."""
        return _fields(await _read("system.info"), (
            "version", "hostname", "physmem", "model", "cores", "physical_cores",
            "loadavg", "uptime", "uptime_seconds", "boottime", "ecc_memory"))

    @mcp.tool
    async def truenas_health(limit: int = 100):
        """List alert metadata and severity; omit potentially sensitive alert arguments and free text."""
        return _rows(await _read("alert.list"),
                     ("uuid", "source", "klass", "level", "datetime", "last_occurrence", "dismissed"), limit)

    @mcp.tool
    async def truenas_disks(limit: int = 100, offset: int = 0):
        """Read physical disk inventory. This is not a full SMART test or temperature check."""
        return await _query("disk.query", ("name", "devname", "identifier", "model",
            "serial", "size", "type", "bus", "rotationrate", "pool", "expiretime"), limit, offset)

    @mcp.tool
    async def truenas_pools(limit: int = 50, offset: int = 0):
        """Read imported ZFS pool health, capacity, topology and reported scrub status."""
        return await _query("pool.query", (), limit, offset, transform=_pool)

    @mcp.tool
    async def truenas_datasets(limit: int = 100, offset: int = 0):
        """Read dataset paths, capacity, ZFS ACL type and encryption status; not per-file ACLs."""
        return await _query("pool.dataset.query", (), limit, offset,
            extra={"flat": True, "retrieve_user_props": False,
                   "properties": list(_DATASET_PROPERTIES)}, transform=_dataset)

    @mcp.tool
    async def truenas_snapshots(limit: int = 100, offset: int = 0):
        """Read snapshot inventory and selected properties; does not create or restore snapshots."""
        return await _query("pool.snapshot.query", (), limit, offset,
            extra={"properties": ["creation", "used", "referenced"]}, transform=_snapshot)

    @mcp.tool
    async def truenas_shares(limit: int = 100, offset: int = 0):
        """Read NFS and SMB share paths and access configuration; no changes."""
        nfs = await _query("sharing.nfs.query", ("id", "path", "enabled", "ro",
            "networks", "hosts", "maproot_user", "maproot_group", "mapall_user",
            "mapall_group", "security", "locked"), limit, offset)
        smb = await _query("sharing.smb.query", ("id", "name", "path", "enabled",
            "ro", "browsable", "guestok", "hostsallow", "hostsdeny", "locked"), limit, offset)
        return {"nfs": nfs, "smb": smb}

    @mcp.tool
    async def truenas_apps(limit: int = 100, offset: int = 0):
        """Read installed apps, states, versions and update flags; exclude app configs and secrets."""
        return await _query("app.query", _APP_FIELDS, limit, offset,
            extra={"retrieve_config": False, "include_app_schema": False})

    @mcp.tool
    async def truenas_app_updates(limit: int = 100, offset: int = 0):
        """Read installed apps reporting an available version upgrade."""
        return await _query("app.query", _APP_FIELDS, limit, offset,
            extra={"retrieve_config": False, "include_app_schema": False},
            filters=[["upgrade_available", "=", True]])

    @mcp.tool
    async def truenas_jobs(limit: int = 50, offset: int = 0):
        """Read session-visible jobs only. A read-only account may not see jobs owned by other sessions."""
        def job(row):
            out = _fields(row, ("id", "method", "state", "time_started", "time_finished", "abortable"))
            if isinstance(row.get("progress"), dict):
                out["progress"] = _fields(row["progress"], ("percent",))
            return out
        result = await _query("core.get_jobs", (), limit, offset, transform=job)
        result["coverage"] = "Session-visible jobs; an empty result is not proof no other jobs exist."
        return result

    @mcp.tool
    async def truenas_network(limit: int = 100, offset: int = 0):
        """Read network interfaces, link state and IP addresses; no network changes."""
        def iface(row):
            out = _fields(row, ("id", "name", "type", "ipv4_dhcp", "ipv6_auto", "mtu"))
            if isinstance(row.get("state"), dict):
                state = row["state"]
                out["state"] = _fields(state, ("link_state", "mtu", "active_media_type"))
                out["state"]["aliases"] = [_fields(a, ("type", "address", "netmask"))
                    for a in (state.get("aliases") or [])[:100] if isinstance(a, dict)]
            return out
        return await _query("interface.query", (), limit, offset, transform=iface)

    @mcp.tool
    async def truenas_vms(limit: int = 100, offset: int = 0):
        """Read configured virtual machines; exclude raw devices and credentials."""
        return await _query("vm.query", ("id", "name", "vcpus", "cores", "threads",
            "memory", "autostart"), limit, offset)

    @mcp.tool
    async def truenas_services(limit: int = 100, offset: int = 0):
        """Read TrueNAS service status and boot-enable flags."""
        return await _query("service.query", ("id", "service", "state", "enable"), limit, offset)

    @mcp.tool
    async def truenas_disk_temperatures():
        """Read current reported drive temperatures in Celsius; no SMART test or polling override."""
        return await _temperatures()

    @mcp.tool
    async def truenas_backup_status(limit: int = 50, offset: int = 0):
        """Read periodic snapshots, replication, cloud sync, cloud backup and rsync schedules and reported state. No raw credentials or scripts; not restore verification."""
        groups = ("pool.snapshottask.query", "replication.query", "cloudsync.query",
                  "cloud_backup.query", "rsynctask.query")
        values = await asyncio.gather(*(_task_group(m, limit, offset) for m in groups))
        return {"snapshot_tasks": values[0], "replication": values[1],
                "cloud_sync": values[2], "cloud_backup": values[3], "rsync": values[4],
                "coverage": "Configuration and reported task state, not independent backup or restore proof."}

    @mcp.tool
    async def truenas_scrub_status(limit: int = 50, offset: int = 0):
        """Read configured scrub schedules and the imported pools' reported scan state. Does not start a scrub."""
        schedules, pools = await asyncio.gather(
            _task_group("pool.scrub.query", limit, offset),
            _query("pool.query", (), limit, offset, transform=_pool))
        return {"schedules": schedules, "pools": pools}

    @mcp.tool
    async def truenas_performance(metric: str = "cpu", identifier: str | None = None, hours: int = 2):
        """Read bounded historical TrueNAS reporting aggregates: cpu, cputemp, load, memory, arcsize, arcrate, arcactualrate, processes, uptime; disk, disktemp or interface with an exact inventoried identifier. 1–24 hours."""
        return await _reporting_metric(metric, identifier, hours)

    @mcp.tool
    async def truenas_importable_pools():
        """Run a bounded read-only pool discovery scan. Does not import any pool. Use on demand, not continuous health polling."""
        return _rows(await _read("pool.import_find"), ("name", "guid", "status", "hostname"), 50)

    @mcp.tool
    async def truenas_system_updates():
        """Read OS update status and offered version. Does not download, install or reboot."""
        return _update_projection(await _read("update.status"))

    @mcp.tool
    async def truenas_ups_status(hours: int = 2):
        """Read recent UPS charge, runtime and load graphs when UPS telemetry is configured. No control actions."""
        services = await _read("service.query", [[["service", "=", "ups"]], {"limit": 1}])
        if not isinstance(services, list):
            raise RuntimeError("Unexpected UPS service response.")
        service = _fields(services[0], ("state", "enable")) if services else None
        if not service or service.get("state") != "RUNNING":
            return {"service": service, "coverage": "UPS service not reported running; telemetry not queried."}
        result = await _metric_graphs([{"name": name, "identifier": None}
                                      for name in ("upscharge", "upsruntime", "upsload")], hours)
        return {"service": service, "reporting": result}

    @mcp.tool
    async def truenas_vm_status(vm_id: int):
        """Read one VM's actual reported runtime state and PID, not memory or CPU usage."""
        if type(vm_id) is not int or vm_id < 1:
            raise ValueError("Positive VM ID required.")
        return _fields(await _read("vm.status", [vm_id]), ("state", "pid", "domain_state"))

    @mcp.tool
    async def truenas_nfs_client_count():
        """Read reported connected NFS client count; does not prove client mount correctness."""
        result = await _read("nfs.client_count")
        if type(result) is not int or result < 0:
            raise RuntimeError("Unexpected NFS client count.")
        return {"client_count": result}

    @mcp.tool
    async def truenas_cron_jobs(limit: int = 50, offset: int = 0):
        """Read cron schedule metadata without shell commands, descriptions or credentials. Does not run a job."""
        result = await _query("cronjob.query", (), limit, offset, transform=_cron_projection)
        result["coverage"] = "Schedule configuration only; not execution history or proof of successful backups."
        return result

    @mcp.tool
    async def truenas_cron_history(limit: int = 50, offset: int = 0):
        """Read session-visible cronjob.run job metadata. Does not read system journal or prove scheduled execution."""
        result = await _query("core.get_jobs",
            ("id", "method", "state", "time_started", "time_finished"), limit, offset,
            filters=[["method", "=", "cronjob.run"]], order_by=["-id"])
        result["coverage"] = "Session-visible middleware jobs only; ordinary cron execution may not appear."
        return result

    @mcp.tool
    async def truenas_dataset_root_stat(dataset: str):
        """Inspect exact inventoried dataset root mountpoint, numeric owner, mode and ACL presence. No arbitrary paths or file contents."""
        return await _dataset_root_stat(dataset)

    @mcp.tool
    async def truenas_app_containers(app_name: str, limit: int = 50):
        """Read service/container image and state for one installed application; no console or shell access."""
        return await _app_containers(app_name, limit)

    @mcp.tool
    async def truenas_catalog_apps(name: str | None = None, limit: int = 50, offset: int = 0):
        """Read available catalog app names, trains and versions; optional exact name. Does not install apps."""
        if name is not None and not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", name):
            raise ValueError("Invalid catalog application name.")
        return await _query("app.available", ("name", "title", "train",
            "latest_version", "latest_app_version", "latest_human_version", "healthy"),
            limit, offset, filters=[["name", "=", name]] if name else [])

    @mcp.tool
    async def truenas_create_dataset(name: str, confirmation: str):
        """Create one explicitly enabled filesystem dataset. Confirm exact full name; no ancestors, ACL edits, volumes or deletion."""
        return await _create_dataset(name, confirmation)

    @mcp.tool
    async def truenas_create_snapshot(dataset: str, name: str, confirmation: str):
        """Create one nonrecursive snapshot of an enabled dataset. Confirm exact dataset@snapshot. No deletion or rollback."""
        return await _create_snapshot(dataset, name, confirmation)

    @mcp.tool
    async def truenas_set_app_state(name: str, action: str, confirmation: str):
        """Start or stop one enabled non-management application. Confirm start:name or stop:name. No redeploy, restart or delete."""
        return await _set_app_state(name, action, confirmation)

    @mcp.tool
    async def truenas_directory_entries(dataset: str, relative_dir: str = "", limit: int = 50, offset: int = 0):
        """List bounded metadata for one directory on an explicitly enabled dataset; no content, symlink traversal or nested mounts."""
        return await _directory_entries(dataset, relative_dir, limit, offset)

    @mcp.tool
    async def truenas_directory_acl(dataset: str, relative_dir: str = ""):
        """Read numeric owner and selected ACL entries for one verified directory on an enabled dataset. No permission changes."""
        return await _directory_acl(dataset, relative_dir)
