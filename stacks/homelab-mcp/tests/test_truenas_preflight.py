"""No-network tests for read-only Proxmox pre-TrueNAS checks."""
import ast
import re
import unittest
from pathlib import Path
from typing import Any


NAMES = {
    "_pve_safe_node", "_pve_safe_storage", "_pve_safe_zfs_children",
    "proxmox_cluster_quorum", "proxmox_zfs_pool_detail",
    "proxmox_physical_disks", "proxmox_disk_smart_health",
}


class DummyMCP:
    @staticmethod
    def tool(fn):
        return fn


def load_api():
    server = Path(__file__).resolve().parents[1] / "server.py"
    tree = ast.parse(server.read_text(encoding="utf-8"))
    chosen = [
        item for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name in NAMES
    ]
    assert len(chosen) == len(NAMES), "Missing preflight functions"
    env = {"re": re, "Any": Any, "mcp": DummyMCP()}
    exec(compile(ast.Module(body=chosen, type_ignores=[]), str(server), "exec"), env)
    return env


class ProxmoxTrueNASPreflightTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.api = load_api()

    async def test_cluster_quorum_is_bounded_and_does_not_leak(self):
        async def fake_get(path, params=None):
            self.assertEqual(path, "/cluster/status")
            return [
                {"type": "cluster", "name": "pve", "quorate": 1,
                 "token": "PRIVATE"},
                {"type": "node", "name": "proxmox2", "online": 1},
            ]
        self.api["pve_get"] = fake_get
        result = await self.api["proxmox_cluster_quorum"]()
        self.assertEqual(result["members"][0]["quorate"], 1)
        self.assertNotIn("PRIVATE", str(result))

    async def test_pool_vdev_tree_and_scrub(self):
        async def fake_get(path, params=None):
            self.assertEqual(
                path, "/nodes/proxmox2/disks/zfs/USB_Storage_Space"
            )
            return {
                "name": "USB_Storage_Space", "state": "ONLINE",
                "scan": "scrub repaired 0B", "errors": "No known data errors",
                "private": "SECRET",
                "children": [
                    {"name": "raidz1-0", "state": "ONLINE", "read": 0,
                     "children": [
                         {"name": "ata-disk1", "state": "ONLINE", "cksum": 0,
                          "password": "SECRET"}
                     ]}
                ],
            }
        self.api["pve_get"] = fake_get
        result = await self.api["proxmox_zfs_pool_detail"](
            "proxmox2", "USB_Storage_Space"
        )
        self.assertEqual(result["detail"]["children"][0]["state"], "ONLINE")
        self.assertEqual(result["detail"]["children"][0]["children"][0]["cksum"], 0)
        self.assertNotIn("SECRET", str(result))
        with self.assertRaises(ValueError):
            await self.api["proxmox_zfs_pool_detail"]("proxmox2", "../bad")

    async def test_disks_limited_and_selected(self):
        async def fake_get(path, params=None):
            self.assertEqual(path, "/nodes/proxmox2/disks/list")
            return [
                {"devpath": "/dev/sda", "serial": "a", "health": "PASSED",
                 "apiSecret": "NOPE"},
                {"devpath": "/dev/sdb", "serial": "b"},
            ]
        self.api["pve_get"] = fake_get
        result = await self.api["proxmox_physical_disks"](
            "proxmox2", limit=1
        )
        self.assertEqual(result["disks"][0]["serial"], "a")
        self.assertTrue(result["truncated"])
        self.assertNotIn("NOPE", str(result))
        with self.assertRaises(ValueError):
            await self.api["proxmox_physical_disks"]("../bad")

    async def test_smart_only_health_request_and_disk_validation(self):
        async def fake_get(path, params=None):
            self.assertEqual(path, "/nodes/proxmox2/disks/smart")
            self.assertEqual(
                params, {"disk": "/dev/sda", "healthonly": 1}
            )
            return {"health": "PASSED", "raw_private": "NOPE"}
        self.api["pve_get"] = fake_get
        result = await self.api["proxmox_disk_smart_health"](
            "proxmox2", "/dev/sda"
        )
        self.assertEqual(result["health"]["health"], "PASSED")
        self.assertNotIn("NOPE", str(result))
        for value in (
            "/etc/passwd", "/dev/sda/../../root", "/dev/mapper/secret",
            "sda", "/dev/nvme0n1;id",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                await self.api["proxmox_disk_smart_health"](
                    "proxmox2", value
                )


if __name__ == "__main__":
    unittest.main()
