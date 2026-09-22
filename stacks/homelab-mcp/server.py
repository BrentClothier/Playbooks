import os
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
# Portainer read-only tools
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


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)
