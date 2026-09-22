import os
from typing import Any

import httpx
from fastmcp import FastMCP
from starlette.responses import JSONResponse

mcp = FastMCP("HomeLab MCP")

PVE_URL = os.environ["PVE_URL"].rstrip("/")
PVE_TOKEN_ID = os.environ["PVE_TOKEN_ID"]
PVE_TOKEN_SECRET = os.environ["PVE_TOKEN_SECRET"]
PVE_VERIFY_SSL = os.getenv("PVE_VERIFY_SSL", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

AUTH_HEADER = {
    "Authorization": f"PVEAPIToken={PVE_TOKEN_ID}={PVE_TOKEN_SECRET}",
}


async def pve_get(path: str, params: dict[str, Any] | None = None) -> Any:
    """Make an authenticated read-only request to the Proxmox VE API."""
    async with httpx.AsyncClient(
        base_url=f"{PVE_URL}/api2/json",
        headers=AUTH_HEADER,
        verify=PVE_VERIFY_SSL,
        timeout=httpx.Timeout(20.0),
    ) as client:
        response = await client.get(path, params=params)
        response.raise_for_status()
        payload = response.json()
        return payload.get("data", payload)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse(
        {
            "status": "healthy",
            "service": "homelab-mcp",
            "mode": "read-only",
        }
    )


@mcp.tool
async def homelab_mcp_info() -> dict[str, Any]:
    """Return basic information about the HomeLab MCP service."""
    return {
        "name": "HomeLab MCP",
        "mode": "read-only",
        "integrations": ["proxmox"],
        "proxmox_base_url": PVE_URL,
        "ssl_verification": PVE_VERIFY_SSL,
    }


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


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)
