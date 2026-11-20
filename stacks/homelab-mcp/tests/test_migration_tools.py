"""No-network unit tests for read-only HomeLab MCP Proxmox diagnostics.

Extract only the relevant decorated functions from server.py so tests can run
with the Python standard library; imports of production libraries are not needed.
"""
import ast
import asyncio
import re
import unittest
from pathlib import Path
from typing import Any


FUNCTIONS = {
    "_pve_safe_node", "_pve_safe_vmid", "_pve_safe_storage", "_pve_safe_upid",
    "_pve_safe_guest_config", "proxmox_guest_config",
    "proxmox_migration_status", "proxmox_backup_status",
    "proxmox_task_log", "proxmox_zfs_pools", "proxmox_storage_content",
}


class DummyMCP:
    @staticmethod
    def tool(fn):
        return fn


def load_api():
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / "server.py").read_text(encoding="utf-8"))
    selected = [
        item for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name in FUNCTIONS
    ]
    assert len(selected) == len(FUNCTIONS), "New diagnostic functions missing"
    env = {
        "re": re, "Any": Any, "mcp": DummyMCP(),
        "redact_log_secrets": lambda s: s.replace("password=secret", "password=<redacted>"),
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(root), "exec"), env)
    return env


class MigrationToolsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.api = load_api()

    async def test_node_and_vmid_validation(self):
        self.assertEqual(self.api["_pve_safe_node"]("proxmox3"), "proxmox3")
        for name in ("../../etc", "node/1", "", "bad:node"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.api["_pve_safe_node"](name)
        with self.assertRaises(ValueError):
            self.api["_pve_safe_vmid"](0)

    async def test_task_id_validation(self):
        upid = "UPID:proxmox3:0000002A:0000012B:00000123:qmigrate:116:root@pam:"
        self.assertEqual(self.api["_pve_safe_upid"]("proxmox3", upid), upid)
        with self.assertRaises(ValueError):
            self.api["_pve_safe_upid"]("proxmox2", upid)
        with self.assertRaises(ValueError):
            self.api["_pve_safe_upid"]("proxmox3", "/etc/passwd")

    async def test_guest_config_filters_secrets(self):
        async def fake_get(path, params=None):
            return {
                "scsi0": "local-lvm:vm-115-disk-1",
                "net0": "virtio,bridge=vmbr0",
                "cipassword": "DO_NOT_SHARE",
                "sshkeys": "DO_NOT_SHARE",
                "description": "DO_NOT_SHARE",
                "memory": 8192,
            }
        self.api["pve_get"] = fake_get
        result = await self.api["proxmox_guest_config"]("proxmox3", 115)
        self.assertEqual(result["config"]["scsi0"], "local-lvm:vm-115-disk-1")
        self.assertNotIn("DO_NOT_SHARE", str(result))
        with self.assertRaises(ValueError):
            await self.api["proxmox_guest_config"]("proxmox3", 115, "invalid")

    async def test_migration_filter(self):
        async def fake_get(path, params=None):
            self.assertEqual(params["limit"], 50)
            return [
                {"id": "116", "type": "qmigrate", "status": "OK", "upid": "x"},
                {"id": "115", "type": "qmigrate", "status": "OK"},
                {"id": "116", "type": "vzdump", "status": "OK"},
            ]
        self.api["pve_get"] = fake_get
        result = await self.api["proxmox_migration_status"]("proxmox3", 116)
        self.assertEqual(len(result["migrations"]), 1)
        self.assertEqual(result["migrations"][0]["id"], "116")

    async def test_backup_status_limited_to_safe_fields(self):
        async def fake_get(path, params=None):
            if path == "/cluster/backup":
                return [{"id": "job1", "storage": "pbs", "secret": "no"}]
            return [{"id": "116", "type": "vzdump", "status": "OK", "secret": "no"}]
        self.api["pve_get"] = fake_get
        r = await self.api["proxmox_backup_status"]("proxmox2")
        self.assertEqual(r["jobs"][0]["storage"], "pbs")
        self.assertNotIn("secret", str(r))

    async def test_log_redaction_and_limits(self):
        upid = "UPID:proxmox2:0000002A:0000012B:00000123:vzdump:116:root@pam:"
        async def fake_get(path, params=None):
            self.assertEqual(params["limit"], 200)
            self.assertIn("%3A", path)
            return [{"n": 1, "t": "password=secret"}]
        self.api["pve_get"] = fake_get
        result = await self.api["proxmox_task_log"]("proxmox2", upid, 1000)
        self.assertNotIn("password=secret", str(result))
        self.assertIn("<redacted>", result["lines"][0]["t"])

    async def test_zfs_storage_content_is_bounded(self):
        async def fake_get(path, params=None):
            return [
                {"volid": f"USB_Storage_Space:subvol-{i}", "size": 200, "secret": "no"}
                for i in range(4)
            ]
        self.api["pve_get"] = fake_get
        r = await self.api["proxmox_storage_content"]("proxmox2", "USB_Storage_Space", limit=2)
        self.assertEqual(len(r["volumes"]), 2)
        self.assertTrue(r["truncated"])
        self.assertNotIn("secret", str(r))
        with self.assertRaises(ValueError):
            await self.api["proxmox_storage_content"]("proxmox2", "../pool")


if __name__ == "__main__":
    unittest.main()
