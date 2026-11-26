"""Narrow read-only TrueNAS 25.10 JSON-RPC 2.0 integration."""
import asyncio
import json
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
                return await _exchange(ws, 2, method, params or [])
    except (TimeoutError, OSError, WebSocketException, ValueError):
        raise RuntimeError(
            "TrueNAS connection or response failed; check internal DNS, TLS, WebSockets and API availability."
        ) from None


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


async def _query(method, fields, limit=100, offset=0, extra=None, transform=None, filters=None):
    count = _limit(limit)
    offset = max(0, min(int(offset), 10000))
    opts = {"limit": count, "offset": offset}
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
