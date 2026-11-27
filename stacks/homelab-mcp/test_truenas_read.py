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



    def test_backup_projection_drops_credentials_and_scripts(self):
        result = tn._task_projection({"id": 3, "enabled": True, "source_datasets": ["tank/data"],
            "credentials": {"secret": "secret-value"}, "password": "secret-value",
            "pre_script": "secret-value", "schedule": {"hour": "3", "secret": "secret-value"},
            "state": {"state": "FINISHED", "error": "secret-value"},
            "job": {"id": 5, "state": "SUCCESS", "arguments": ["secret-value"],
                    "progress": {"percent": 100, "description": "secret-value"}}})
        self.assertNotIn("secret-value", json.dumps(result))
        self.assertEqual(result["schedule"], {"hour": "3"})
        self.assertEqual(result["job"]["progress"], {"percent": 100})

    async def test_backup_group_failure_is_not_empty_inventory(self):
        with patch.object(tn, "_read", new_callable=AsyncMock) as read:
            read.side_effect = RuntimeError("credential value")
            result = await tn._task_group("replication.query", 10, 0)
            self.assertIsNone(result["items"])
            self.assertNotIn("credential value", json.dumps(result))

    async def test_reporting_metric_rejects_unknown_graph_and_traversal(self):
        with patch.object(tn, "_read", new_callable=AsyncMock) as read:
            for metric, identifier in [("bad", None), ("disk", "../secret"),
                                       ("cpu", "sda")]:
                with self.assertRaises(ValueError):
                    await tn._reporting_metric(metric, identifier, 2)
            read.assert_not_awaited()

    async def test_reporting_bounds_and_numeric_projection(self):
        with patch.object(tn, "_read", new_callable=AsyncMock) as read:
            read.return_value = [{"name": "cpu", "identifier": None, "data": [
                {"timestamp": 1, "usage": 2.5, "password": "secret-value"}],
                "aggregations": {"mean": {"usage": 2.5, "nan": float("nan"),
                "secret": "secret-value"}}}]
            result = await tn._reporting_metric("cpu", None, 500)
            self.assertEqual(result["hours_requested"], 24)
            self.assertEqual(result["items"][0]["aggregations"]["mean"], {"usage": 2.5})
            self.assertNotIn("secret-value", json.dumps(result))
            self.assertEqual(read.call_args.args[1][1]["end"] - read.call_args.args[1][1]["start"], 86400)

    async def test_temperatures_uses_inventoried_names(self):
        with patch.object(tn, "_read", new_callable=AsyncMock) as read:
            read.side_effect = [[{"name": "sda"}, {"name": "sdb"}, {"name": "../etc"}],
                                {"sda": 32, "sdb": None, "secret": "secret-value"}]
            result = await tn._temperatures()
            self.assertEqual(result["items"], [{"name": "sda", "celsius": 32},
                                               {"name": "sdb", "celsius": None}])
            read.assert_awaited_with("disk.temperatures", [["sda", "sdb"], False])

    def test_update_projection_omits_error_text_and_manifest(self):
        result = tn._update_projection({"code": "NORMAL",
            "status": {"current_version": {"train": "25.10", "profile": "STABLE"},
                "new_version": {"version": "25.10.8", "manifest": {"secret": "secret-value"}}},
            "error": {"errname": "TEST", "reason": "secret-value"}})
        self.assertEqual(result["new_version"], {"version": "25.10.8"})
        self.assertNotIn("secret-value", json.dumps(result))

    async def test_new_mutating_methods_still_denied(self):
        for method in ("pool.import_pool", "pool.scrub.run", "replication.run",
                       "cloud_backup.sync", "update.download", "vm.start"):
            with self.assertRaises(ValueError):
                await tn._read(method, [])


    def test_cron_projection_drops_sensitive_fields(self):
        result = tn._cron_projection({"id": 4, "enabled": True, "command": "secret-value",
            "description": "secret-value", "user": "secret-value",
            "schedule": {"hour": "2", "secret": "secret-value"}})
        self.assertEqual(result, {"id": 4, "enabled": True, "schedule": {"hour": "2"}})

    async def test_dataset_root_stat_rejects_unverified_paths(self):
        with patch.object(tn, "_read", new_callable=AsyncMock) as read:
            for name in ("../etc", "/etc", "tank/../data", "tank/."):
                with self.assertRaises(ValueError):
                    await tn._dataset_root_stat(name)
            read.assert_not_awaited()
            read.return_value = [{"id": "tank/data", "type": "FILESYSTEM",
                                  "mountpoint": "/etc"}]
            with self.assertRaises(ValueError):
                await tn._dataset_root_stat("tank/data")
            self.assertEqual(read.await_count, 1)

    async def test_dataset_root_stat_projection_and_mount_guard(self):
        with patch.object(tn, "_read", new_callable=AsyncMock) as read:
            dataset = {"id": "tank/data", "type": "FILESYSTEM", "mountpoint": "/mnt/tank/data"}
            stat = {"realpath": "/mnt/tank/data", "type": "DIRECTORY",
                    "is_mountpoint": True, "uid": 1000, "gid": 1000,
                    "mode": 16877, "secret": "secret-value"}
            read.side_effect = [ [dataset], stat, [dataset], dict(stat, is_mountpoint=False)]
            result = await tn._dataset_root_stat("tank/data")
            self.assertEqual(result["stat"]["uid"], 1000)
            self.assertNotIn("secret-value", json.dumps(result))
            with self.assertRaises(RuntimeError):
                await tn._dataset_root_stat("tank/data")

    async def test_app_containers_checks_inventory_and_omits_config(self):
        with patch.object(tn, "_read", new_callable=AsyncMock) as read:
            with self.assertRaises(ValueError):
                await tn._app_containers("../app")
            read.assert_not_awaited()
            read.side_effect = [[{"id": "test-app"}], {"abc": {"id": "abc",
                "service_name": "web", "image": "example:1", "state": "running",
                "config": {"password": "secret-value"}}}, []]
            result = await tn._app_containers("test-app")
            self.assertEqual(result["items"][0]["state"], "running")
            self.assertNotIn("secret-value", json.dumps(result))
            with self.assertRaises(ValueError):
                await tn._app_containers("missing")

    def test_latest_sample_handles_array_and_dictionary(self):
        self.assertEqual(tn._latest_sample([1, 2.5], ["time", "usage"]),
                         {"time": 1, "usage": 2.5})
        self.assertEqual(tn._latest_sample({"usage": 2.5, "secret": "hidden"}, None),
                         {"usage": 2.5})
        self.assertIsNone(tn._latest_sample([1, 2], ["time"]))
        self.assertIsNone(tn._latest_sample([1, 2], ["time", "time"]))

    async def test_stage2_write_methods_denied(self):
        for method in ("cronjob.run", "cronjob.create", "filesystem.setacl",
                       "filesystem.get_file", "app.start", "app.stop", "app.create"):
            with self.assertRaises(ValueError):
                await tn._read(method, [])


if __name__ == "__main__":
    unittest.main()
