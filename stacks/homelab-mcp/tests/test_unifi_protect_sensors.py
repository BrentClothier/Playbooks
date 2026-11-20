"""No-network tests for the narrowly scoped UniFi Protect sensor MCP tools."""
import ast
import re
import unittest
from pathlib import Path
from typing import Any

FUNCTIONS = {
    "unifi_protect_ready",
    "unifi_protect_api_base_url",
    "unifi_protect_get",
    "_unifi_protect_sensor_summary",
    "unifi_protect_sensors",
    "unifi_protect_sensor",
}

class DummyMCP:
    @staticmethod
    def tool(fn):
        return fn

def load_api():
    server = Path(__file__).resolve().parents[1] / "server.py"
    tree = ast.parse(server.read_text(encoding="utf-8"))
    selected = [
        item for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name in FUNCTIONS
    ]
    assert len(selected) == len(FUNCTIONS), "Protect tools or guards missing"
    env = {
        "Any": Any, "re": re, "mcp": DummyMCP(),
        "UNIFI_PROTECT_URL": "https://192.0.2.1",
        "UNIFI_PROTECT_API_KEY": "TEST_KEY_NOT_REAL",
        "UNIFI_PROTECT_VERIFY_SSL": True,
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(server), "exec"), env)
    return env

class ProtectSensorToolsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.api = load_api()

    async def test_sensor_list_is_bounded_and_redacted(self):
        async def fake_get(path):
            self.assertEqual(path, "/v1/sensors")
            return [
                {"id": "abc123", "name": "Door", "state": "CONNECTED",
                 "isOpened": False, "stats": {"temperature": 20.5},
                 "password": "SECRET", "settings": {"credential": "SECRET"}},
                {"id": "def456", "name": "Window"},
            ]
        self.api["unifi_protect_get"] = fake_get
        result = await self.api["unifi_protect_sensors"](limit=1)
        self.assertEqual(result["returned"], 1)
        self.assertTrue(result["truncated"])
        self.assertFalse(result["sensors"][0]["isOpened"])
        self.assertNotIn("SECRET", str(result))

    async def test_single_sensor_id_validation(self):
        async def fake_get(path):
            self.assertEqual(path, "/v1/sensors/abc123")
            return {"id": "abc123", "state": "CONNECTED", "secret": "NOPE"}
        self.api["unifi_protect_get"] = fake_get
        self.assertEqual(
            (await self.api["unifi_protect_sensor"]("abc123"))["id"],
            "abc123",
        )
        for value in ("", "../cameras", "abc/123", "x" * 65):
            with self.subTest(value=value), self.assertRaises(ValueError):
                await self.api["unifi_protect_sensor"](value)

    async def test_endpoint_allowlist_and_auth_requirement(self):
        class FakeClient:
            def __init__(self, **kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, exc_type, exc, tb): return False
        class FakeHttpx:
            AsyncClient = FakeClient
            @staticmethod
            def Timeout(value): return value
        self.api["httpx"] = FakeHttpx()
        with self.assertRaises(ValueError):
            await self.api["unifi_protect_get"]("/v1/cameras")
        with self.assertRaises(ValueError):
            await self.api["unifi_protect_get"]("/v1/sensors/../../settings")
        self.api["UNIFI_PROTECT_API_KEY"] = ""
        with self.assertRaises(RuntimeError):
            await self.api["unifi_protect_get"]("/v1/sensors")

    async def test_base_url(self):
        self.assertEqual(
            self.api["unifi_protect_api_base_url"](),
            "https://192.0.2.1/proxy/protect/integration",
        )
        self.api["UNIFI_PROTECT_URL"] = (
            "https://192.0.2.1/proxy/network/integration"
        )
        self.assertEqual(
            self.api["unifi_protect_api_base_url"](),
            "https://192.0.2.1/proxy/protect/integration",
        )

if __name__ == "__main__":
    unittest.main()
