import json
import os
import re
import socket
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastmcp import FastMCP
from starlette.responses import JSONResponse

mcp = FastMCP("HomeLab MCP")

# Proxmox
PVE_URL = os.environ["PVE_URL"].rstrip("/")
PVE_TOKEN_ID = os.environ["PVE_TOKEN_ID"]
PVE_TOKEN_SECRET = os.environ["PVE_TOKEN_SECRET"]
PVE_VERIFY_SSL = os.getenv("PVE_VERIFY_SSL", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

PVE_AUTH_HEADER = {
    "Authorization": f"PVEAPIToken={PVE_TOKEN_ID}={PVE_TOKEN_SECRET}",
}

# Semaphore (optional until configured in Portainer)
SEMAPHORE_URL = os.getenv("SEMAPHORE_URL", "").rstrip("/")
SEMAPHORE_API_TOKEN = os.getenv("SEMAPHORE_API_TOKEN", "")
SEMAPHORE_ALLOWED_TEMPLATES_RAW = os.getenv("SEMAPHORE_ALLOWED_TEMPLATES", "")
SEMAPHORE_VERIFY_SSL = os.getenv("SEMAPHORE_VERIFY_SSL", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# Portainer (optional until configured in Portainer)
PORTAINER_URL = os.getenv("PORTAINER_URL", "").rstrip("/")
PORTAINER_API_TOKEN = os.getenv("PORTAINER_API_TOKEN", "")
PORTAINER_VERIFY_SSL = os.getenv("PORTAINER_VERIFY_SSL", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# UniFi Network local Integration API (optional until configured)
UNIFI_URL = os.getenv("UNIFI_URL", "").rstrip("/")
UNIFI_API_KEY = os.getenv("UNIFI_API_KEY", "")
UNIFI_VERIFY_SSL = os.getenv("UNIFI_VERIFY_SSL", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# UniFi CEF/syslog event collector
UNIFI_SYSLOG_ENABLED = os.getenv("UNIFI_SYSLOG_ENABLED", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
UNIFI_SYSLOG_LISTEN_PORT = 5514
UNIFI_EVENT_DB = os.getenv(
    "UNIFI_EVENT_DB",
    "/data/unifi_events.db",
)
UNIFI_EVENT_RETENTION_DAYS = max(
    1,
    int(os.getenv("UNIFI_EVENT_RETENTION_DAYS", "30")),
)

_unifi_syslog_state: dict[str, Any] = {
    "started": False,
    "listening": False,
    "error": None,
    "last_received_at": None,
    "last_source_ip": None,
}


async def pve_get(path: str, params: dict[str, Any] | None = None) -> Any:
    """Make an authenticated read-only request to the Proxmox VE API."""
    async with httpx.AsyncClient(
        base_url=f"{PVE_URL}/api2/json",
        headers=PVE_AUTH_HEADER,
        verify=PVE_VERIFY_SSL,
        timeout=httpx.Timeout(20.0),
    ) as client:
        response = await client.get(path, params=params)
        response.raise_for_status()
        payload = response.json()
        return payload.get("data", payload)


def semaphore_ready() -> bool:
    return bool(SEMAPHORE_URL and SEMAPHORE_API_TOKEN)


def semaphore_allow_all_templates() -> bool:
    return SEMAPHORE_ALLOWED_TEMPLATES_RAW.strip() == "*"


def semaphore_allowed_template_pairs() -> set[tuple[int, int]]:
    """
    Parse SEMAPHORE_ALLOWED_TEMPLATES.

    Use "*" to allow every Semaphore template, including templates created
    in the future.

    Otherwise use comma-separated project_id:template_id pairs, for example:
    1:2,1:3,1:4
    """
    allowed: set[tuple[int, int]] = set()
    raw = SEMAPHORE_ALLOWED_TEMPLATES_RAW.strip()
    if not raw or raw == "*":
        return allowed

    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            project_text, template_text = item.split(":", 1)
            allowed.add((int(project_text), int(template_text)))
        except (ValueError, TypeError) as exc:
            raise RuntimeError(
                "Invalid SEMAPHORE_ALLOWED_TEMPLATES value. "
                "Use '*' or comma-separated project_id:template_id pairs."
            ) from exc

    return allowed


async def semaphore_get(path: str, params: dict[str, Any] | None = None) -> Any:
    """Make an authenticated read-only request to the Semaphore UI API."""
    if not semaphore_ready():
        raise RuntimeError(
            "Semaphore is not configured. Set SEMAPHORE_URL and "
            "SEMAPHORE_API_TOKEN in the HomeLab MCP container."
        )

    headers = {
        "Authorization": f"Bearer {SEMAPHORE_API_TOKEN}",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(
        base_url=f"{SEMAPHORE_URL}/api",
        headers=headers,
        verify=SEMAPHORE_VERIFY_SSL,
        timeout=httpx.Timeout(30.0),
    ) as client:
        response = await client.get(path, params=params)
        response.raise_for_status()
        if not response.content:
            return None
        return response.json()


async def semaphore_post(path: str, payload: dict[str, Any]) -> Any:
    """Make an authenticated, allowlisted write request to the Semaphore UI API."""
    if not semaphore_ready():
        raise RuntimeError(
            "Semaphore is not configured. Set SEMAPHORE_URL and "
            "SEMAPHORE_API_TOKEN in the HomeLab MCP container."
        )

    headers = {
        "Authorization": f"Bearer {SEMAPHORE_API_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(
        base_url=f"{SEMAPHORE_URL}/api",
        headers=headers,
        verify=SEMAPHORE_VERIFY_SSL,
        timeout=httpx.Timeout(30.0),
    ) as client:
        response = await client.post(path, json=payload)
        response.raise_for_status()
        if not response.content:
            return None
        return response.json()


def portainer_ready() -> bool:
    return bool(PORTAINER_URL and PORTAINER_API_TOKEN)


async def portainer_get(
    path: str,
    params: dict[str, Any] | None = None,
    *,
    raw: bool = False,
) -> Any:
    """Make an authenticated read-only request to the Portainer API."""
    if not portainer_ready():
        raise RuntimeError(
            "Portainer is not configured. Set PORTAINER_URL and "
            "PORTAINER_API_TOKEN in the HomeLab MCP container."
        )

    headers = {
        "X-API-Key": PORTAINER_API_TOKEN,
        "Accept": "*/*" if raw else "application/json",
    }

    async with httpx.AsyncClient(
        base_url=f"{PORTAINER_URL}/api",
        headers=headers,
        verify=PORTAINER_VERIFY_SSL,
        timeout=httpx.Timeout(30.0),
    ) as client:
        response = await client.get(path, params=params)
        response.raise_for_status()
        if raw:
            return response.content
        if not response.content:
            return None
        return response.json()


async def portainer_post(
    path: str,
    params: dict[str, Any] | None = None,
) -> Any:
    """Make an authenticated state-changing POST request through Portainer."""
    if not portainer_ready():
        raise RuntimeError(
            "Portainer is not configured. Set PORTAINER_URL and "
            "PORTAINER_API_TOKEN in the HomeLab MCP container."
        )

    headers = {
        "X-API-Key": PORTAINER_API_TOKEN,
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(
        base_url=f"{PORTAINER_URL}/api",
        headers=headers,
        verify=PORTAINER_VERIFY_SSL,
        timeout=httpx.Timeout(60.0),
    ) as client:
        response = await client.post(path, params=params)
        response.raise_for_status()
        if not response.content:
            return {
                "ok": True,
                "status_code": response.status_code,
            }
        try:
            return response.json()
        except ValueError:
            return {
                "ok": True,
                "status_code": response.status_code,
                "text": response.text,
            }


async def portainer_put(
    path: str,
    params: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> Any:
    """Make an authenticated state-changing PUT request to the Portainer API."""
    if not portainer_ready():
        raise RuntimeError(
            "Portainer is not configured. Set PORTAINER_URL and "
            "PORTAINER_API_TOKEN in the HomeLab MCP container."
        )

    headers = {
        "X-API-Key": PORTAINER_API_TOKEN,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(
        base_url=f"{PORTAINER_URL}/api",
        headers=headers,
        verify=PORTAINER_VERIFY_SSL,
        timeout=httpx.Timeout(120.0),
    ) as client:
        response = await client.put(path, params=params, json=payload or {})
        response.raise_for_status()
        if not response.content:
            return {
                "ok": True,
                "status_code": response.status_code,
            }
        try:
            return response.json()
        except ValueError:
            return {
                "ok": True,
                "status_code": response.status_code,
                "text": response.text,
            }


def unifi_ready() -> bool:
    return bool(UNIFI_URL and UNIFI_API_KEY)


def unifi_api_base_url() -> str:
    """
    Return the base URL for the official local UniFi Network Integration API.

    UNIFI_URL may be either the console root, such as https://192.168.1.1,
    or the full Network Integration base ending in /proxy/network/integration.
    """
    if UNIFI_URL.endswith("/proxy/network/integration"):
        return UNIFI_URL
    return f"{UNIFI_URL}/proxy/network/integration"


async def unifi_get(
    path: str,
    params: dict[str, Any] | None = None,
) -> Any:
    """Make an authenticated read-only request to the local UniFi Network API."""
    if not unifi_ready():
        raise RuntimeError(
            "UniFi is not configured. Set UNIFI_URL and UNIFI_API_KEY "
            "in the HomeLab MCP container."
        )

    headers = {
        "X-API-Key": UNIFI_API_KEY,
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(
        base_url=unifi_api_base_url(),
        headers=headers,
        verify=UNIFI_VERIFY_SSL,
        timeout=httpx.Timeout(30.0),
    ) as client:
        response = await client.get(path, params=params)
        response.raise_for_status()
        if not response.content:
            return None
        return response.json()


def _unescape_cef_value(value: str) -> str:
    return (
        value.replace(r"\n", "\n")
        .replace(r"\r", "\r")
        .replace(r"\=", "=")
        .replace(r"\\", "\")
    )


def _split_cef_fields(payload: str) -> tuple[list[str], str]:
    """
    Split the seven CEF header fields while respecting backslash-escaped pipes.
    """
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    index = 0

    for index, char in enumerate(payload):
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            current.append(char)
            continue
        if char == "|" and len(fields) < 7:
            fields.append("".join(current))
            current = []
            if len(fields) == 7:
                return fields, payload[index + 1 :]
            continue
        current.append(char)

    raise ValueError("CEF message did not contain the expected header fields.")


def parse_unifi_cef(raw_message: str) -> dict[str, Any]:
    """Parse a UniFi Common Event Format log message."""
    cef_index = raw_message.find("CEF:")
    if cef_index < 0:
        raise ValueError("Message does not contain a CEF payload.")

    cef = raw_message[cef_index + 4 :]
    fields, extension = _split_cef_fields(cef)

    (
        cef_version,
        device_vendor,
        device_product,
        device_version,
        event_class_id,
        event_name,
        severity,
    ) = fields

    key_matches = list(
        re.finditer(
            r"(?:^| )([A-Za-z][A-Za-z0-9_.:-]*)=",
            extension,
        )
    )
    ext: dict[str, str] = {}
    for idx, match in enumerate(key_matches):
        key = match.group(1)
        value_start = match.end()
        value_end = (
            key_matches[idx + 1].start()
            if idx + 1 < len(key_matches)
            else len(extension)
        )
        value = extension[value_start:value_end].strip()
        ext[key] = _unescape_cef_value(value)

    return {
        "cef_version": cef_version,
        "device_vendor": device_vendor,
        "device_product": device_product,
        "device_version": device_version,
        "event_class_id": event_class_id,
        "name": _unescape_cef_value(event_name),
        "severity": severity,
        "category": ext.get("UNIFIcategory"),
        "subcategory": ext.get("UNIFIsubCategory"),
        "message": ext.get("msg"),
        "fields": ext,
    }


def _unifi_db_connect() -> sqlite3.Connection:
    connection = sqlite3.connect(UNIFI_EVENT_DB, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def init_unifi_event_db() -> None:
    os.makedirs(os.path.dirname(UNIFI_EVENT_DB) or ".", exist_ok=True)
    with _unifi_db_connect() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS unifi_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                received_at TEXT NOT NULL,
                source_ip TEXT,
                event_class_id TEXT,
                name TEXT,
                severity TEXT,
                category TEXT,
                subcategory TEXT,
                message TEXT,
                fields_json TEXT NOT NULL,
                raw TEXT NOT NULL
            )
            """
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_unifi_events_received "
            "ON unifi_events(received_at)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_unifi_events_category "
            "ON unifi_events(category, subcategory)"
        )
        cutoff = (
            datetime.now(timezone.utc)
            - timedelta(days=UNIFI_EVENT_RETENTION_DAYS)
        ).isoformat()
        db.execute(
            "DELETE FROM unifi_events WHERE received_at < ?",
            (cutoff,),
        )


def store_unifi_event(raw_message: str, source_ip: str | None) -> None:
    parsed = parse_unifi_cef(raw_message)
    received_at = datetime.now(timezone.utc).isoformat()

    with _unifi_db_connect() as db:
        db.execute(
            """
            INSERT INTO unifi_events (
                received_at,
                source_ip,
                event_class_id,
                name,
                severity,
                category,
                subcategory,
                message,
                fields_json,
                raw
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                received_at,
                source_ip,
                parsed["event_class_id"],
                parsed["name"],
                parsed["severity"],
                parsed["category"],
                parsed["subcategory"],
                parsed["message"],
                json.dumps(parsed["fields"], separators=(",", ":")),
                raw_message,
            ),
        )

    _unifi_syslog_state["last_received_at"] = received_at
    _unifi_syslog_state["last_source_ip"] = source_ip


def _unifi_syslog_udp_loop() -> None:
    try:
        init_unifi_event_db()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", UNIFI_SYSLOG_LISTEN_PORT))
            _unifi_syslog_state["listening"] = True
            _unifi_syslog_state["error"] = None

            while True:
                data, address = sock.recvfrom(65535)
                raw_message = data.decode("utf-8", errors="replace").strip()
                if not raw_message:
                    continue
                try:
                    store_unifi_event(raw_message, address[0])
                except Exception as exc:
                    _unifi_syslog_state["error"] = (
                        f"Last event parse/store error: {exc}"
                    )
    except Exception as exc:
        _unifi_syslog_state["listening"] = False
        _unifi_syslog_state["error"] = str(exc)


def start_unifi_syslog_receiver() -> None:
    if not UNIFI_SYSLOG_ENABLED or _unifi_syslog_state["started"]:
        return

    _unifi_syslog_state["started"] = True
    thread = threading.Thread(
        target=_unifi_syslog_udp_loop,
        name="unifi-syslog",
        daemon=True,
    )
    thread.start()


def query_unifi_events(
    *,
    hours: int = 24,
    limit: int = 100,
    category: str | None = None,
    subcategory: str | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    safe_hours = max(1, min(hours, 24 * 90))
    safe_limit = max(1, min(limit, 1000))
    since = (
        datetime.now(timezone.utc) - timedelta(hours=safe_hours)
    ).isoformat()

    clauses = ["received_at >= ?"]
    values: list[Any] = [since]

    if category:
        clauses.append("LOWER(category) = LOWER(?)")
        values.append(category)
    if subcategory:
        clauses.append("LOWER(subcategory) = LOWER(?)")
        values.append(subcategory)
    if search:
        clauses.append(
            "(name LIKE ? OR message LIKE ? OR fields_json LIKE ? OR raw LIKE ?)"
        )
        term = f"%{search}%"
        values.extend([term, term, term, term])

    values.append(safe_limit)
    sql = (
        "SELECT * FROM unifi_events WHERE "
        + " AND ".join(clauses)
        + " ORDER BY id DESC LIMIT ?"
    )

    with _unifi_db_connect() as db:
        rows = db.execute(sql, values).fetchall()

    results: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["fields"] = json.loads(item.pop("fields_json"))
        item.pop("raw", None)
        results.append(item)
    return results


def unifi_event_count() -> int:
    if not os.path.exists(UNIFI_EVENT_DB):
        return 0
    try:
        with _unifi_db_connect() as db:
            row = db.execute(
                "SELECT COUNT(*) AS count FROM unifi_events"
            ).fetchone()
        return int(row["count"]) if row else 0
    except Exception:
        return 0


def decode_docker_logs(data: bytes) -> str:
    """
    Decode Docker log output.

    Docker may return raw text for TTY containers or multiplexed frames for
    non-TTY containers. This strips the 8-byte multiplex headers when present.
    """
    if not data:
        return ""

    chunks: list[bytes] = []
    offset = 0

    while offset + 8 <= len(data):
        stream_type = data[offset]
        if (
            stream_type not in {0, 1, 2}
            or data[offset + 1 : offset + 4] != b"\x00\x00\x00"
        ):
            break

        size = int.from_bytes(data[offset + 4 : offset + 8], "big")
        start = offset + 8
        end = start + size
        if end > len(data):
            break

        chunks.append(data[start:end])
        offset = end

    if chunks and offset == len(data):
        return b"".join(chunks).decode("utf-8", errors="replace")

    return data.decode("utf-8", errors="replace")


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse(
        {
            "status": "healthy",
            "service": "homelab-mcp",
            "mode": (
                "controlled-write"
                if (
                    semaphore_allow_all_templates()
                    or semaphore_allowed_template_pairs()
                )
                else "read-only"
            ),
            "semaphore_configured": semaphore_ready(),
            "semaphore_allow_all_templates": semaphore_allow_all_templates(),
            "semaphore_allowed_template_count": (
                None
                if semaphore_allow_all_templates()
                else len(semaphore_allowed_template_pairs())
            ),
            "portainer_configured": portainer_ready(),
            "unifi_configured": unifi_ready(),
            "unifi_syslog_enabled": UNIFI_SYSLOG_ENABLED,
            "unifi_syslog_listening": _unifi_syslog_state["listening"],
            "unifi_syslog_error": _unifi_syslog_state["error"],
            "unifi_event_count": unifi_event_count(),
        }
    )


@mcp.tool
async def homelab_mcp_info() -> dict[str, Any]:
    """Return basic information about the HomeLab MCP service."""
    integrations = ["proxmox"]
    if semaphore_ready():
        integrations.append("semaphore")
    if portainer_ready():
        integrations.append("portainer")
    if unifi_ready():
        integrations.append("unifi")

    return {
        "name": "HomeLab MCP",
        "mode": (
            "controlled-write"
            if (
                semaphore_allow_all_templates()
                or semaphore_allowed_template_pairs()
            )
            else "read-only"
        ),
        "integrations": integrations,
        "proxmox_base_url": PVE_URL,
        "proxmox_ssl_verification": PVE_VERIFY_SSL,
        "semaphore_configured": semaphore_ready(),
        "semaphore_base_url": SEMAPHORE_URL if SEMAPHORE_URL else None,
        "semaphore_ssl_verification": SEMAPHORE_VERIFY_SSL,
        "semaphore_allow_all_templates": semaphore_allow_all_templates(),
        "semaphore_allowed_template_count": (
            None
            if semaphore_allow_all_templates()
            else len(semaphore_allowed_template_pairs())
        ),
        "portainer_configured": portainer_ready(),
        "portainer_base_url": PORTAINER_URL if PORTAINER_URL else None,
        "portainer_ssl_verification": PORTAINER_VERIFY_SSL,
        "unifi_configured": unifi_ready(),
        "unifi_base_url": unifi_api_base_url() if UNIFI_URL else None,
        "unifi_ssl_verification": UNIFI_VERIFY_SSL,
        "unifi_syslog_enabled": UNIFI_SYSLOG_ENABLED,
        "unifi_syslog_listening": _unifi_syslog_state["listening"],
        "unifi_syslog_last_received_at": (
            _unifi_syslog_state["last_received_at"]
        ),
        "unifi_event_retention_days": UNIFI_EVENT_RETENTION_DAYS,
        "unifi_event_count": unifi_event_count(),
    }


# -------------------------
# Proxmox read-only tools
# -------------------------

@mcp.tool
async def proxmox_version() -> Any:
    """Return the Proxmox VE API/version information."""
    return await pve_get("/version")


@mcp.tool
async def proxmox_cluster_resources(resource_type: str | None = None) -> Any:
    """
    List Proxmox cluster resources.

    Use this for an overview of nodes, virtual machines, LXC containers,
    storage, and current state. resource_type can be vm, storage, node,
    or sdn; leave it blank for all resource types.
    """
    params = {"type": resource_type} if resource_type else None
    return await pve_get("/cluster/resources", params=params)


@mcp.tool
async def proxmox_nodes() -> Any:
    """List Proxmox nodes and their high-level status."""
    return await pve_get("/nodes")


@mcp.tool
async def proxmox_node_status(node: str) -> Any:
    """Return detailed CPU, memory, uptime, load, kernel, and status data for a node."""
    return await pve_get(f"/nodes/{node}/status")


@mcp.tool
async def proxmox_qemu_vms(node: str) -> Any:
    """List QEMU virtual machines on a Proxmox node."""
    return await pve_get(f"/nodes/{node}/qemu")


@mcp.tool
async def proxmox_lxc_containers(node: str) -> Any:
    """List LXC containers on a Proxmox node."""
    return await pve_get(f"/nodes/{node}/lxc")


@mcp.tool
async def proxmox_storage(node: str) -> Any:
    """List storage visible to a Proxmox node, including usage information."""
    return await pve_get(f"/nodes/{node}/storage")


@mcp.tool
async def proxmox_backup_jobs() -> Any:
    """List configured Proxmox cluster backup jobs."""
    return await pve_get("/cluster/backup")


@mcp.tool
async def proxmox_recent_tasks(node: str, limit: int = 25) -> Any:
    """
    Return recent administrative tasks for a Proxmox node.

    Useful for troubleshooting backups, migrations, VM operations, and
    other recent Proxmox activity.
    """
    safe_limit = max(1, min(limit, 100))
    return await pve_get(f"/nodes/{node}/tasks", params={"limit": safe_limit})


# -------------------------
# Semaphore read-only tools
# -------------------------

@mcp.tool
async def semaphore_projects() -> Any:
    """List Semaphore projects visible to the configured API token."""
    return await semaphore_get("/projects")


@mcp.tool
async def semaphore_project(project_id: int) -> Any:
    """Return details for one Semaphore project."""
    return await semaphore_get(f"/project/{project_id}/")


@mcp.tool
async def semaphore_templates(
    project_id: int,
    sort: str = "name",
    order: str = "asc",
) -> Any:
    """
    List task templates for a Semaphore project.

    sort may be name, playbook, ssh_key, inventory, environment, or repository.
    order may be asc or desc.
    """
    allowed_sort = {
        "name",
        "playbook",
        "ssh_key",
        "inventory",
        "environment",
        "repository",
    }
    if sort not in allowed_sort:
        raise ValueError(f"Invalid sort value: {sort}")
    if order not in {"asc", "desc"}:
        raise ValueError("order must be 'asc' or 'desc'")

    return await semaphore_get(
        f"/project/{project_id}/templates",
        params={"sort": sort, "order": order},
    )


@mcp.tool
async def semaphore_template(project_id: int, template_id: int) -> Any:
    """Return one Semaphore task template."""
    return await semaphore_get(
        f"/project/{project_id}/templates/{template_id}"
    )


@mcp.tool
async def semaphore_recent_tasks(project_id: int, limit: int = 25) -> Any:
    """
    Return recent Semaphore tasks for a project.

    Semaphore provides up to the last 200 tasks; this tool returns the newest
    requested subset, capped at 100 items.
    """
    safe_limit = max(1, min(limit, 100))
    tasks = await semaphore_get(f"/project/{project_id}/tasks/last")
    if isinstance(tasks, list):
        return tasks[-safe_limit:]
    return tasks


@mcp.tool
async def semaphore_task(project_id: int, task_id: int) -> Any:
    """Return status and details for a single Semaphore task."""
    return await semaphore_get(f"/project/{project_id}/tasks/{task_id}")


@mcp.tool
async def semaphore_task_output(
    project_id: int,
    task_id: int,
    max_entries: int = 200,
) -> Any:
    """
    Return recent structured output entries for a Semaphore task.

    Output can contain operational details from playbooks, so use this when
    troubleshooting a specific task.
    """
    safe_limit = max(1, min(max_entries, 1000))
    output = await semaphore_get(
        f"/project/{project_id}/tasks/{task_id}/output"
    )
    if isinstance(output, list):
        return output[-safe_limit:]
    return output


@mcp.tool
async def semaphore_allowed_templates() -> Any:
    """
    List Semaphore templates that this MCP is permitted to execute.

    Execution is denied unless a project/template pair appears in the
    SEMAPHORE_ALLOWED_TEMPLATES environment variable.
    """
    if semaphore_allow_all_templates():
        projects = await semaphore_get("/projects")
        results = []
        if not isinstance(projects, list):
            return projects

        for project in projects:
            project_id = project.get("id")
            if project_id is None:
                continue
            templates = await semaphore_get(
                f"/project/{project_id}/templates",
                params={"sort": "name", "order": "asc"},
            )
            if not isinstance(templates, list):
                continue
            for template in templates:
                results.append(
                    {
                        "project_id": project_id,
                        "template_id": template.get("id"),
                        "name": template.get("name"),
                        "playbook": template.get("playbook"),
                        "app": template.get("app"),
                    }
                )
        return results

    allowed = sorted(semaphore_allowed_template_pairs())
    results = []

    for project_id, template_id in allowed:
        try:
            template = await semaphore_get(
                f"/project/{project_id}/templates/{template_id}"
            )
            results.append(
                {
                    "project_id": project_id,
                    "template_id": template_id,
                    "name": (
                        template.get("name")
                        if isinstance(template, dict)
                        else None
                    ),
                    "playbook": (
                        template.get("playbook")
                        if isinstance(template, dict)
                        else None
                    ),
                    "app": (
                        template.get("app")
                        if isinstance(template, dict)
                        else None
                    ),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "project_id": project_id,
                    "template_id": template_id,
                    "error": str(exc),
                }
            )

    return results


@mcp.tool
async def semaphore_run_template(
    project_id: int,
    template_id: int,
    message: str = "Started by ChatGPT HomeLab MCP",
) -> Any:
    """
    Start an existing Semaphore task template.

    This is a state-changing operation. It can ONLY run templates explicitly
    allowlisted in SEMAPHORE_ALLOWED_TEMPLATES. Arbitrary playbooks, shell
    commands, inventory overrides, branches, tags, limits, survey variables,
    and extra arguments are intentionally not accepted by this tool.
    """
    allowed = semaphore_allowed_template_pairs()
    if (
        not semaphore_allow_all_templates()
        and (project_id, template_id) not in allowed
    ):
        raise PermissionError(
            f"Semaphore template {project_id}:{template_id} is not allowlisted."
        )

    template = await semaphore_get(
        f"/project/{project_id}/templates/{template_id}"
    )

    safe_message = message.strip()[:500] or "Started by ChatGPT HomeLab MCP"
    task = await semaphore_post(
        f"/project/{project_id}/tasks",
        {
            "template_id": template_id,
            "message": safe_message,
        },
    )

    return {
        "started": True,
        "project_id": project_id,
        "template_id": template_id,
        "template_name": (
            template.get("name") if isinstance(template, dict) else None
        ),
        "message": safe_message,
        "task": task,
    }


# -------------------------
# Portainer tools
# -------------------------

@mcp.tool
async def portainer_environments() -> Any:
    """
    List Portainer environments/endpoints visible to the configured API token.

    Use the returned environment ID with the container inspection tools.
    """
    return await portainer_get("/endpoints")


@mcp.tool
async def portainer_stacks() -> Any:
    """List Portainer stacks visible to the configured API token."""
    return await portainer_get("/stacks")


@mcp.tool
async def portainer_containers(
    environment_id: int,
    include_stopped: bool = True,
) -> Any:
    """
    List Docker containers in a Portainer environment.

    Set include_stopped=false to return only running containers.
    """
    return await portainer_get(
        f"/endpoints/{environment_id}/docker/containers/json",
        params={"all": "true" if include_stopped else "false"},
    )


@mcp.tool
async def portainer_container(
    environment_id: int,
    container_id: str,
) -> Any:
    """
    Inspect a Docker container through Portainer.

    container_id may be a full/short Docker ID or an unambiguous container name.
    """
    return await portainer_get(
        f"/endpoints/{environment_id}/docker/containers/{container_id}/json"
    )


@mcp.tool
async def portainer_container_logs(
    environment_id: int,
    container_id: str,
    tail: int = 200,
    timestamps: bool = True,
) -> str:
    """
    Return recent stdout/stderr logs for a Docker container through Portainer.

    tail is capped at 2000 lines to keep responses manageable.
    """
    safe_tail = max(1, min(tail, 2000))
    data = await portainer_get(
        f"/endpoints/{environment_id}/docker/containers/{container_id}/logs",
        params={
            "stdout": "true",
            "stderr": "true",
            "timestamps": "true" if timestamps else "false",
            "tail": str(safe_tail),
        },
        raw=True,
    )
    return decode_docker_logs(data)


@mcp.tool
async def portainer_stack_logs(
    stack_id: int,
    tail: int = 200,
    timestamps: bool = True,
) -> Any:
    """
    Return recent logs from every container belonging to a Portainer stack.

    The stack is resolved to its Portainer environment, then containers are
    matched by the Docker Compose project label. Logs are returned per container.
    """
    safe_tail = max(1, min(tail, 2000))
    stack = await portainer_get(f"/stacks/{stack_id}")

    if not isinstance(stack, dict):
        return stack

    environment_id = stack.get("EndpointId")
    stack_name = stack.get("Name")

    if not environment_id or not stack_name:
        raise RuntimeError(
            "Portainer stack response did not include EndpointId and Name."
        )

    filters = json.dumps(
        {
            "label": [
                f"com.docker.compose.project={stack_name}",
            ]
        }
    )

    containers = await portainer_get(
        f"/endpoints/{environment_id}/docker/containers/json",
        params={
            "all": "true",
            "filters": filters,
        },
    )

    if not isinstance(containers, list):
        return {
            "stack_id": stack_id,
            "stack_name": stack_name,
            "environment_id": environment_id,
            "containers": containers,
        }

    results = []
    for container in containers:
        container_id = container.get("Id")
        names = container.get("Names") or []
        container_name = (
            names[0].lstrip("/")
            if names
            else container_id
        )

        if not container_id:
            continue

        try:
            data = await portainer_get(
                f"/endpoints/{environment_id}/docker/containers/"
                f"{container_id}/logs",
                params={
                    "stdout": "true",
                    "stderr": "true",
                    "timestamps": "true" if timestamps else "false",
                    "tail": str(safe_tail),
                },
                raw=True,
            )
            results.append(
                {
                    "container_id": container_id[:12],
                    "container_name": container_name,
                    "state": container.get("State"),
                    "status": container.get("Status"),
                    "logs": decode_docker_logs(data),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "container_id": container_id[:12],
                    "container_name": container_name,
                    "state": container.get("State"),
                    "status": container.get("Status"),
                    "error": str(exc),
                }
            )

    return {
        "stack_id": stack_id,
        "stack_name": stack_name,
        "environment_id": environment_id,
        "containers": results,
    }


@mcp.tool
async def portainer_restart_container(
    environment_id: int,
    container_id: str,
    timeout_seconds: int = 10,
) -> Any:
    """
    Restart a Docker container through Portainer.

    This is a state-changing operation. timeout_seconds is capped at 120.
    """
    safe_timeout = max(0, min(timeout_seconds, 120))
    result = await portainer_post(
        f"/endpoints/{environment_id}/docker/containers/"
        f"{container_id}/restart",
        params={"t": safe_timeout},
    )
    return {
        "action": "restart",
        "environment_id": environment_id,
        "container_id": container_id,
        "timeout_seconds": safe_timeout,
        "result": result,
    }


@mcp.tool
async def portainer_start_container(
    environment_id: int,
    container_id: str,
) -> Any:
    """Start a stopped Docker container through Portainer."""
    result = await portainer_post(
        f"/endpoints/{environment_id}/docker/containers/"
        f"{container_id}/start"
    )
    return {
        "action": "start",
        "environment_id": environment_id,
        "container_id": container_id,
        "result": result,
    }


@mcp.tool
async def portainer_stop_container(
    environment_id: int,
    container_id: str,
    timeout_seconds: int = 10,
) -> Any:
    """
    Stop a Docker container through Portainer.

    This is a state-changing operation. timeout_seconds is capped at 120.
    """
    safe_timeout = max(0, min(timeout_seconds, 120))
    result = await portainer_post(
        f"/endpoints/{environment_id}/docker/containers/"
        f"{container_id}/stop",
        params={"t": safe_timeout},
    )
    return {
        "action": "stop",
        "environment_id": environment_id,
        "container_id": container_id,
        "timeout_seconds": safe_timeout,
        "result": result,
    }


@mcp.tool
async def portainer_redeploy_stack(
    stack_id: int,
    pull_images: bool = True,
    prune: bool = False,
    force_redeploy: bool = True,
) -> Any:
    """
    Pull and redeploy a Git-backed Portainer stack.

    By default this pulls current images and forces a redeploy. The operation
    does not delete volumes. It will fail if the selected stack is not backed
    by a Git repository.
    """
    stack = await portainer_get(f"/stacks/{stack_id}")
    if not isinstance(stack, dict):
        return stack

    environment_id = stack.get("EndpointId")
    stack_name = stack.get("Name")

    if not environment_id:
        raise RuntimeError(
            "Portainer stack response did not include an EndpointId."
        )

    try:
        result = await portainer_put(
            f"/stacks/{stack_id}/git/redeploy",
            params={"endpointId": environment_id},
            payload={
                "PullImage": pull_images,
                "Prune": prune,
                "RepullImageAndRedeploy": force_redeploy,
            },
        )
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:1000]
        raise RuntimeError(
            f"Portainer could not redeploy stack {stack_id}. "
            f"The stack may not be Git-backed or the API token may not "
            f"have permission. Portainer returned "
            f"{exc.response.status_code}: {detail}"
        ) from exc

    return {
        "action": "redeploy_stack",
        "stack_id": stack_id,
        "stack_name": stack_name,
        "environment_id": environment_id,
        "pull_images": pull_images,
        "prune": prune,
        "force_redeploy": force_redeploy,
        "result": result,
    }


# -------------------------
# UniFi Network read-only tools
# -------------------------

@mcp.tool
async def unifi_info() -> Any:
    """
    Return information about the local UniFi Network application.

    This is useful for confirming connectivity and discovering the installed
    Network application version before using version-specific features.
    """
    return await unifi_get("/v1/info")


@mcp.tool
async def unifi_sites(limit: int = 100) -> Any:
    """
    List local UniFi Network sites.

    The returned site ID is required for device and client queries.
    """
    safe_limit = max(1, min(limit, 200))
    return await unifi_get(
        "/v1/sites",
        params={"offset": 0, "limit": safe_limit},
    )


@mcp.tool
async def unifi_devices(site_id: str, limit: int = 200) -> Any:
    """
    List adopted UniFi devices for a site, including gateways, switches,
    and access points.
    """
    safe_limit = max(1, min(limit, 200))
    return await unifi_get(
        f"/v1/sites/{site_id}/devices",
        params={"offset": 0, "limit": safe_limit},
    )


@mcp.tool
async def unifi_device(site_id: str, device_id: str) -> Any:
    """Return detailed information for one adopted UniFi device."""
    return await unifi_get(
        f"/v1/sites/{site_id}/devices/{device_id}"
    )


@mcp.tool
async def unifi_device_statistics(site_id: str, device_id: str) -> Any:
    """
    Return the latest statistics for one adopted UniFi device.

    Depending on device type and Network version this can include uptime,
    traffic rates, CPU load, memory utilization, and other health metrics.
    """
    return await unifi_get(
        f"/v1/sites/{site_id}/devices/{device_id}/statistics/latest"
    )


@mcp.tool
async def unifi_clients(site_id: str, limit: int = 200) -> Any:
    """
    List currently connected clients for a UniFi site.

    This includes wired, wireless, and active VPN clients exposed by the
    installed Network application.
    """
    safe_limit = max(1, min(limit, 200))
    return await unifi_get(
        f"/v1/sites/{site_id}/clients",
        params={"offset": 0, "limit": safe_limit},
    )


@mcp.tool
async def unifi_client(site_id: str, client_id: str) -> Any:
    """Return detailed information for one currently connected UniFi client."""
    return await unifi_get(
        f"/v1/sites/{site_id}/clients/{client_id}"
    )


@mcp.tool
async def unifi_syslog_status() -> Any:
    """
    Return the UniFi CEF/syslog collector state and retained event count.

    Use this after configuring UniFi System Logging / SIEM to verify that
    events are reaching the HomeLab MCP.
    """
    return {
        "enabled": UNIFI_SYSLOG_ENABLED,
        "listening": _unifi_syslog_state["listening"],
        "listen_port_udp": UNIFI_SYSLOG_LISTEN_PORT,
        "error": _unifi_syslog_state["error"],
        "last_received_at": _unifi_syslog_state["last_received_at"],
        "last_source_ip": _unifi_syslog_state["last_source_ip"],
        "event_count": unifi_event_count(),
        "retention_days": UNIFI_EVENT_RETENTION_DAYS,
    }


@mcp.tool
async def unifi_recent_events(
    hours: int = 24,
    limit: int = 100,
    category: str | None = None,
    subcategory: str | None = None,
    search: str | None = None,
) -> Any:
    """
    Return retained UniFi System Log events received through CEF/syslog.

    Filter by category (for example Internet, Monitoring, Security, System),
    subcategory (for example WiFi), or a free-text search.
    """
    return query_unifi_events(
        hours=hours,
        limit=limit,
        category=category,
        subcategory=subcategory,
        search=search,
    )


@mcp.tool
async def unifi_wan_events(hours: int = 24, limit: int = 100) -> Any:
    """
    Return recent UniFi Internet-category events.

    This is intended for WAN outages, failover, high latency, packet loss,
    and related Internet health events exported by UniFi.
    """
    return query_unifi_events(
        hours=hours,
        limit=limit,
        category="Internet",
    )


@mcp.tool
async def unifi_wifi_events(hours: int = 24, limit: int = 100) -> Any:
    """
    Return recent Wi-Fi monitoring events.

    Disconnect records can include RSSI, channel, channel width, airtime
    utilization, interference, AP identity, SSID, duration, and usage when
    UniFi includes those CEF fields.
    """
    return query_unifi_events(
        hours=hours,
        limit=limit,
        category="Monitoring",
        subcategory="WiFi",
    )


@mcp.tool
async def unifi_security_events(hours: int = 24, limit: int = 100) -> Any:
    """
    Return recent UniFi Security events such as IDS/IPS, honeypot, or
    firewall detections exported through System Logging / SIEM.
    """
    return query_unifi_events(
        hours=hours,
        limit=limit,
        category="Security",
    )


@mcp.tool
async def unifi_event_summary(hours: int = 24) -> Any:
    """
    Summarize retained UniFi events by category and event name for a time window.
    """
    safe_hours = max(1, min(hours, 24 * 90))
    since = (
        datetime.now(timezone.utc) - timedelta(hours=safe_hours)
    ).isoformat()

    with _unifi_db_connect() as db:
        total_row = db.execute(
            "SELECT COUNT(*) AS count FROM unifi_events WHERE received_at >= ?",
            (since,),
        ).fetchone()
        categories = db.execute(
            """
            SELECT COALESCE(category, 'Uncategorized') AS category,
                   COUNT(*) AS count
            FROM unifi_events
            WHERE received_at >= ?
            GROUP BY category
            ORDER BY count DESC
            """,
            (since,),
        ).fetchall()
        names = db.execute(
            """
            SELECT name, COUNT(*) AS count
            FROM unifi_events
            WHERE received_at >= ?
            GROUP BY name
            ORDER BY count DESC
            LIMIT 20
            """,
            (since,),
        ).fetchall()

    return {
        "hours": safe_hours,
        "total_events": int(total_row["count"]) if total_row else 0,
        "categories": [dict(row) for row in categories],
        "top_events": [dict(row) for row in names],
        "last_received_at": _unifi_syslog_state["last_received_at"],
    }


if __name__ == "__main__":
    start_unifi_syslog_receiver()
    mcp.run(transport="http", host="0.0.0.0", port=8000)
