import asyncio
import json
import os
import unittest
from unittest.mock import patch, AsyncMock

import truenas_read as tn


class TrueNASTests(unittest.IsolatedAsyncioTestCase):
    def test_https_only_and_default_account(self):
        with patch.dict(os.environ, {
            "TRUENAS_URL": "https://nas.example.test",
            "TRUENAS_API_KEY": "test-key", "TRUENAS_VERIFY_SSL": "true",
            "TRUENAS_USERNAME": "homelab-mcp",
        }):
            self.assertEqual(tn._endpoint(), (
                "wss://nas.example.test/api/current", "homelab-mcp", "test-key"))
            for url in ("http://nas.example.test", "https://user@nas.example.test",
                        "https://nas.example.test/api/other"):
                with patch.dict(os.environ, {"TRUENAS_URL": url}):
                    with self.assertRaises(RuntimeError):
                        tn._endpoint()
            with patch.dict(os.environ, {"TRUENAS_VERIFY_SSL": "false"}):
                with self.assertRaises(RuntimeError):
                    tn._endpoint()

    async def test_write_denied_before_network(self):
        with self.assertRaises(ValueError):
            await tn._read("pool.delete", [1])

    async def test_rpc_error_does_not_leak_server_message(self):
        ws = AsyncMock()
        ws.recv.return_value = json.dumps({
            "jsonrpc": "2.0", "id": 2, "error": {"message": "test-secret"}})
        with self.assertRaises(RuntimeError) as exc:
            await tn._exchange(ws, 2, "pool.query", [])
        self.assertNotIn("test-secret", str(exc.exception))

    async def test_rpc_ignores_unrelated_events(self):
        ws = AsyncMock()
        ws.recv.side_effect = [
            json.dumps({"jsonrpc": "2.0", "method": "event"}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "result": []}),
        ]
        self.assertEqual(await tn._exchange(ws, 2, "pool.query", []), [])
        request = json.loads(ws.send.call_args.args[0])
        self.assertEqual(request["method"], "pool.query")
        self.assertEqual(request["jsonrpc"], "2.0")

    async def test_query_limits_and_projection(self):
        with patch.object(tn, "_read", new_callable=AsyncMock) as read:
            read.return_value = [{"name": "app", "config": {"password": "secret"}}]
            result = await tn._query("app.query", ("name",), 500, -5)
            self.assertEqual(result["items"], [{"name": "app"}])
            read.assert_awaited_once_with("app.query", [[], {"limit": 200, "offset": 0}])

    def test_pool_and_dataset_projection(self):
        pool = tn._pool({"name": "tank", "status": "ONLINE", "secret": "hidden",
                        "topology": {"data": [{"type": "RAIDZ1", "children": [
                            {"path": "/dev/sda", "read_errors": 0, "secret": "hidden"}
                        ]}]}})
        self.assertEqual(pool["topology"]["data"][0]["children"][0]["read_errors"], 0)
        self.assertNotIn("hidden", json.dumps(pool))
        dataset = tn._dataset({"id": "tank/data", "acltype": {"value": "POSIX",
                              "secret": "hidden"}, "user_properties": {"secret": "hidden"}})
        self.assertEqual(dataset["acltype"]["value"], "POSIX")
        self.assertNotIn("hidden", json.dumps(dataset))


if __name__ == "__main__":
    unittest.main()
