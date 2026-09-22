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
SEMAPHORE_VERIFY_SSL = os.getenv("SEMAPHORE_VERIFY_SSL", "true").lower() in {
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


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse(
        {
            "status": "healthy",
            "service": "homelab-mcp",
            "mode": "read-only",
            "semaphore_configured": semaphore_ready(),
        }
    )


@mcp.tool
async def homelab_mcp_info() -> dict[str, Any]:
    """Return basic information about the HomeLab MCP service."""
    integrations = ["proxmox"]
    if semaphore_ready():
        integrations.append("semaphore")

    return {
        "name": "HomeLab MCP",
        "mode": "read-only",
        "integrations": integrations,
        "proxmox_base_url": PVE_URL,
        "proxmox_ssl_verification": PVE_VERIFY_SSL,
        "semaphore_configured": semaphore_ready(),
        "semaphore_base_url": SEMAPHORE_URL if SEMAPHORE_URL else None,
        "semaphore_ssl_verification": SEMAPHORE_VERIFY_SSL,
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


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)
