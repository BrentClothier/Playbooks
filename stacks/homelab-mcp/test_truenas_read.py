import asyncio
import json
import os
import unittest
import tempfile
from pathlib import Path
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



class TrueNASAdminTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "TRUENAS_URL": "https://nas.example.test",
            "TRUENAS_API_KEY": "read-test-key",
            "TRUENAS_VERIFY_SSL": "true",
            "TRUENAS_ADMIN_ENABLED": "true",
            "TRUENAS_ADMIN_USERNAME": "admin-test",
            "TRUENAS_ADMIN_API_KEY": "write-test-key",
            "TRUENAS_ADMIN_DATASETS": "tank/appdata,tank/appdata/semaphore",
            "TRUENAS_ADMIN_SNAPSHOT_DATASETS": "tank/appdata",
            "TRUENAS_ADMIN_APPS": "plex,tailscale,homelab-mcp",
        }, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    async def test_disabled_and_same_key_fail_before_network(self):
        with patch.object(tn, "_read", new_callable=AsyncMock) as read:
            for env in ({"TRUENAS_ADMIN_ENABLED": "false"},
                        {"TRUENAS_ADMIN_API_KEY": "read-test-key"},
                        {"TRUENAS_ADMIN_USERNAME": ""}):
                with patch.dict(os.environ, env):
                    with self.assertRaises(ValueError):
                        await tn._create_dataset("tank/appdata", "tank/appdata")
            read.assert_not_awaited()

    async def test_target_validation_and_confirmation(self):
        with patch.object(tn, "_read", new_callable=AsyncMock) as read:
            for name, confirmation in (("tank", "tank"), ("tank/../appdata", "tank/../appdata"),
                                       ("tank/appdata/evil", "tank/appdata/evil"),
                                       ("tank/appdata", "wrong")):
                with self.assertRaises(ValueError):
                    await tn._create_dataset(name, confirmation)
            read.assert_not_awaited()

    async def test_dataset_created_and_verified(self):
        def row(name):
            return {"id": name, "type": "FILESYSTEM", "mountpoint": "/mnt/" + name}
        with patch.object(tn, "_read", new_callable=AsyncMock) as read, \
                patch.object(tn, "_admin_rpc", new_callable=AsyncMock) as write:
            read.side_effect = [[], [row("tank")], [row("tank/appdata")]]
            write.return_value = row("tank/appdata")
            result = await tn._create_dataset("tank/appdata", "tank/appdata")
            self.assertTrue(result["changed"])
            write.assert_awaited_once_with("pool.dataset.create", [{
                "name": "tank/appdata", "type": "FILESYSTEM", "create_ancestors": False}])

    async def test_existing_dataset_not_modified(self):
        with patch.object(tn, "_read", new_callable=AsyncMock) as read, \
                patch.object(tn, "_admin_rpc", new_callable=AsyncMock) as write:
            read.return_value = [{"id": "tank/appdata", "type": "FILESYSTEM",
                                  "mountpoint": "/mnt/tank/appdata"}]
            self.assertFalse((await tn._create_dataset("tank/appdata", "tank/appdata"))["changed"])
            write.assert_not_awaited()

    async def test_snapshot_nonrecursive_and_verified(self):
        with patch.object(tn, "_read", new_callable=AsyncMock) as read, \
                patch.object(tn, "_admin_rpc", new_callable=AsyncMock) as write:
            ident = "tank/appdata@pre-test"
            read.side_effect = [[{"id": "tank/appdata", "type": "FILESYSTEM",
                                  "mountpoint": "/mnt/tank/appdata"}], [], [{"id": ident}]]
            write.return_value = {"id": ident, "secret": "hidden"}
            result = await tn._create_snapshot("tank/appdata", "pre-test", ident)
            self.assertTrue(result["changed"])
            self.assertNotIn("hidden", json.dumps(result))
            write.assert_awaited_once_with("pool.snapshot.create", [{
                "dataset": "tank/appdata", "name": "pre-test", "recursive": False}])

    async def test_protected_apps_and_unknown_operations(self):
        with patch.object(tn, "_read", new_callable=AsyncMock) as read:
            for name, action in (("tailscale", "stop"), ("homelab-mcp", "stop"),
                                 ("plex", "restart"), ("unknown", "start")):
                with self.assertRaises(ValueError):
                    await tn._set_app_state(name, action, action + ":" + name)
            read.assert_not_awaited()

    async def test_app_job_pending_not_verified(self):
        with patch.object(tn, "_app_state", new_callable=AsyncMock) as state, \
                patch.object(tn, "_admin_rpc", new_callable=AsyncMock) as write:
            state.side_effect = ["STOPPED", "RUNNING"]
            write.return_value = {"job_id": 5, "state": "PENDING_OR_UNKNOWN"}
            result = await tn._set_app_state("plex", "start", "start:plex")
            self.assertFalse(result["verified"])
            write.assert_awaited_once_with("app.start", ["plex"])

    async def test_arbitrary_write_rejected(self):
        for method in ("pool.dataset.delete", "app.create", "core.bulk", "cronjob.run"):
            with self.assertRaises(ValueError):
                await tn._admin_rpc(method, [])
        for method in tn._WRITE_METHODS:
            with self.assertRaises(ValueError):
                await tn._read(method, [])



class TrueNASDirectoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"TRUENAS_DIAGNOSTIC_DATASETS": "tank/data"}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    async def test_invalid_or_unapproved_paths_denied_before_rpc(self):
        with patch.object(tn, "_read", new_callable=AsyncMock) as read:
            for dataset, relative in (("tank/other", ""), ("../etc", ""), ("tank/data", "../etc"),
                                      ("tank/data", "/etc"), ("tank/data", ".zfs/snapshot"),
                                      ("tank/data", "foo//bar"), ("tank/data", "a/b/c/d/e")):
                with self.assertRaises(ValueError):
                    await tn._diagnostic_directory(dataset, relative)
            read.assert_not_awaited()

    async def test_child_symlink_and_nested_mount_denied(self):
        with patch.object(tn, "_dataset_root_stat", new_callable=AsyncMock), \
                patch.object(tn, "_read", new_callable=AsyncMock) as read:
            for row in ({"realpath": "/etc", "type": "DIRECTORY", "is_mountpoint": False},
                        {"realpath": "/mnt/tank/data/sub", "type": "DIRECTORY", "is_mountpoint": True},
                        {"realpath": "/mnt/tank/data/sub", "type": "SYMLINK", "is_mountpoint": False}):
                read.return_value = row
                with self.assertRaises(ValueError):
                    await tn._diagnostic_directory("tank/data", "sub")

    async def test_list_entries_bounds_and_projection(self):
        with patch.object(tn, "_diagnostic_directory", new_callable=AsyncMock) as directory, \
                patch.object(tn, "_read", new_callable=AsyncMock) as read:
            directory.return_value = "/mnt/tank/data"
            read.return_value = [{"name": "sample", "type": "FILE", "size": 3,
                                  "secret": "hidden", "path": "/secret"}]
            result = await tn._directory_entries("tank/data", "", 999, -1)
            self.assertEqual(result["limit"], 200)
            self.assertEqual(result["offset"], 0)
            self.assertEqual(result["items"], [{"name": "sample", "type": "FILE", "size": 3}])
            self.assertNotIn("hidden", json.dumps(result))

    async def test_acl_numeric_projection(self):
        with patch.object(tn, "_diagnostic_directory", new_callable=AsyncMock) as directory, \
                patch.object(tn, "_read", new_callable=AsyncMock) as read:
            directory.return_value = "/mnt/tank/data"
            read.return_value = {"path": "/mnt/tank/data", "uid": 1000, "gid": 1000,
                "acltype": "POSIX1E", "user": "hidden",
                "acl": [{"tag": "USER", "id": 1000, "default": False,
                         "perms": {"READ": True, "WRITE": False, "secret": "hidden"}}]}
            result = await tn._directory_acl("tank/data")
            self.assertEqual(result["entries"][0]["perms"], {"READ": True, "WRITE": False})
            self.assertNotIn("hidden", json.dumps(result))
            read.assert_awaited_once_with("filesystem.getacl", ["/mnt/tank/data", True, False])



class TrueNASSessionTests(unittest.IsolatedAsyncioTestCase):
    def make_socket(self):
        ws = AsyncMock()
        ws.state = tn.State.OPEN
        return ws

    async def test_reuse_and_serialization(self):
        gate = tn._AuthGate()
        session = tn._Session(gate)
        ws = self.make_socket()
        credentials = ("wss://nas.example.test/api/current", "reader", "key")
        active = 0
        ids = []

        async def exchange(socket, request_id, method, params):
            nonlocal active
            self.assertIs(socket, ws)
            self.assertEqual(active, 0)
            active += 1
            ids.append(request_id)
            await asyncio.sleep(0)
            active -= 1
            return method

        async def read():
            async with session.use(credentials) as conn:
                return await conn.call("system.info", [])

        with patch.object(gate, "login", new_callable=AsyncMock) as login, \
                patch.object(tn, "_exchange", side_effect=exchange):
            login.return_value = ws
            self.assertEqual(await asyncio.gather(*(read() for _ in range(25))),
                             ["system.info"] * 25)
            login.assert_awaited_once_with(credentials)
            self.assertEqual(ids, list(range(2, 27)))
        await session.close()

    async def test_separate_sessions_and_credential_change(self):
        gate = tn._AuthGate()
        read, admin = tn._Session(gate), tn._Session(gate)
        first, second, third = (self.make_socket() for _ in range(3))
        creds = ("wss://nas.example.test/api/current", "user", "key")
        admin_creds = (*creds[:2], "other-key")
        new_creds = (*creds[:2], "new-key")
        with patch.object(gate, "login", new_callable=AsyncMock) as login:
            login.side_effect = [first, second, third]
            async with read.use(creds):
                self.assertIs(read.ws, first)
            async with admin.use(admin_creds):
                self.assertIs(admin.ws, second)
            async with read.use(new_creds):
                self.assertIs(read.ws, third)
            first.close.assert_awaited_once()
            second.close.assert_not_awaited()
        await read.close()
        await admin.close()

    async def test_failed_rpc_not_replayed_and_socket_discarded(self):
        gate = tn._AuthGate()
        session = tn._Session(gate)
        ws = self.make_socket()
        credentials = ("wss://nas.example.test/api/current", "writer", "key")
        with patch.object(gate, "login", new_callable=AsyncMock) as login, \
                patch.object(tn, "_exchange", new_callable=AsyncMock) as exchange:
            login.return_value = ws
            exchange.side_effect = RuntimeError("ambiguous")
            with self.assertRaises(RuntimeError):
                async with session.use(credentials) as conn:
                    await conn.call("pool.dataset.create", [])
            exchange.assert_awaited_once()
            self.assertIsNone(session.ws)
            ws.close.assert_awaited_once()

    async def test_auth_failure_respects_shared_cooldown(self):
        gate = tn._AuthGate()
        ws = self.make_socket()
        credentials = ("wss://nas.example.test/api/current", "reader", "key")
        with patch.object(tn, "_NoRedirectConnect", new_callable=AsyncMock) as connect, \
                patch.object(tn, "_exchange", new_callable=AsyncMock) as exchange:
            connect.return_value = ws
            exchange.side_effect = RuntimeError("auth failed")
            with self.assertRaises(RuntimeError):
                await gate.login(credentials)
            with self.assertRaisesRegex(RuntimeError, "cooling down"):
                await gate.login((*credentials[:2], "other-key"))
            connect.assert_awaited_once()
            exchange.assert_awaited_once()
            ws.close.assert_awaited_once()



class TrueNASSemaphoreDeployTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "TRUENAS_URL": "https://nas.example.test",
            "TRUENAS_API_KEY": "read-test-key",
            "TRUENAS_VERIFY_SSL": "true",
            "TRUENAS_ADMIN_ENABLED": "true",
            "TRUENAS_ADMIN_USERNAME": "admin-test",
            "TRUENAS_ADMIN_API_KEY": "write-test-key",
            "TRUENAS_SEMAPHORE_DEPLOY_ENABLED": "true",
            "TRUENAS_SEMAPHORE_DB_SECRET": "D" * 48,
            "TRUENAS_SEMAPHORE_ADMIN_SECRET": "A" * 48,
            "TRUENAS_SEMAPHORE_ENCRYPTION_SECRET": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
            "TRUENAS_SEMAPHORE_BIND_ADDRESS": "192.168.10.20",
        }, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.job = patch.object(tn, "_SEMAPHORE_JOB", None)
        self.job.start()
        self.addCleanup(self.job.stop)
        self.lock = patch.object(tn, "_SEMAPHORE_LOCK", asyncio.Lock())
        self.lock.start()
        self.addCleanup(self.lock.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.attempt = patch.object(tn, "_SEMAPHORE_ATTEMPT", Path(self.temp.name) / "attempt.json")
        self.attempt.start()
        self.addCleanup(self.attempt.stop)
        self.confirm = "create:semaphore:" + tn._SEMAPHORE_REV
        self.template = (
            'POSTGRES_PASSWORD: ${SEMAPHORE_DB_PASSWORD:?Set private database password}\n'
            'SEMAPHORE_DB_PASS: ${SEMAPHORE_DB_PASSWORD:?Set private database password}\n'
            'SEMAPHORE_ADMIN_PASSWORD: ${SEMAPHORE_ADMIN_PASSWORD:?Set private administrator password}\n'
            'SEMAPHORE_ACCESS_KEY_ENCRYPTION: ${SEMAPHORE_ACCESS_KEY_ENCRYPTION:?Set private base64 key}\n'
            'port: "${SEMAPHORE_BIND_ADDRESS:?Set approved private host address}:3000:3000"\n'
            'command: $literal\n')

    async def test_disabled_wrong_revision_and_injection_denied(self):
        with patch.object(tn, "_semaphore_template", new_callable=AsyncMock) as fetch:
            with self.assertRaises(ValueError):
                await tn._deploy_semaphore("create:semaphore:main")
            with patch.dict(os.environ, {"TRUENAS_SEMAPHORE_DEPLOY_ENABLED": "false"}):
                with self.assertRaises(ValueError):
                    await tn._deploy_semaphore(self.confirm)
            for key, value in (
                ("TRUENAS_SEMAPHORE_DB_SECRET", "x\nprivileged: true"),
                ("TRUENAS_SEMAPHORE_ADMIN_SECRET", "D" * 48),
                ("TRUENAS_SEMAPHORE_BIND_ADDRESS", "0.0.0.0"),
                ("TRUENAS_SEMAPHORE_ENCRYPTION_SECRET", "not-base64"),
            ):
                with patch.dict(os.environ, {key: value}):
                    with self.assertRaises(ValueError):
                        await tn._deploy_semaphore(self.confirm)
            fetch.assert_not_awaited()

    def test_pinned_source_matches_approved_git_blob(self):
        source = Path(__file__).resolve().parents[1] / "semaphore-truenas" / "docker-compose.yml"
        data = source.read_bytes()
        self.assertEqual(tn.hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest(), tn._SEMAPHORE_BLOB)
        rendered = tn._render_semaphore(data.decode("utf-8"), tn._semaphore_secrets())
        self.assertNotIn("${", rendered)

    def test_render_only_expected_placeholders(self):
        values = tn._semaphore_secrets()
        result = tn._render_semaphore(self.template, values)
        self.assertNotIn("${", result)
        self.assertIn('POSTGRES_PASSWORD: "' + "D" * 48 + '"', result)
        self.assertIn('"192.168.10.20:3000:3000"', result)
        self.assertIn("$literal", result)
        for text in (self.template + "${UNAPPROVED}", self.template.replace("Set private base64 key", "changed")):
            with self.assertRaises(RuntimeError):
                tn._render_semaphore(text, values)

    async def test_existing_app_refused(self):
        with patch.object(tn, "_semaphore_app", new_callable=AsyncMock) as app:
            app.return_value = {"id": "semaphore"}
            with self.assertRaises(ValueError):
                await tn._semaphore_preflight("192.168.10.20")

    async def test_preflight_nonempty_dataset_rejected(self):
        with patch.object(tn, "_semaphore_app", new_callable=AsyncMock, return_value=None), \
                patch.object(tn, "_dataset_root_stat", new_callable=AsyncMock), \
                patch.object(tn, "_read", new_callable=AsyncMock, return_value=[{"name": "old-data"}]):
            with self.assertRaises(ValueError):
                await tn._semaphore_preflight("192.168.10.20")

    async def test_preflight_requires_recursive_snapshot_and_local_bind(self):
        with patch.object(tn, "_semaphore_app", new_callable=AsyncMock, return_value=None), \
                patch.object(tn, "_dataset_root_stat", new_callable=AsyncMock), \
                patch.object(tn, "_read", new_callable=AsyncMock) as read:
            read.side_effect = [[], [], [{"enabled": True, "recursive": False}]]
            with self.assertRaises(ValueError):
                await tn._semaphore_preflight("192.168.10.20")
            read.side_effect = [[], [], [{"enabled": True, "recursive": True}], []]
            with self.assertRaises(ValueError):
                await tn._semaphore_preflight("192.168.10.20")
            read.side_effect = [[], [], [{"enabled": True, "recursive": True}],
                                [{"state": {"aliases": [{"address": "192.168.10.20"}]}}]]
            await tn._semaphore_preflight("192.168.10.20")

    async def test_fixed_create_and_no_replay_or_secret_output(self):
        with patch.object(tn, "_semaphore_template", new_callable=AsyncMock, return_value=self.template), \
                patch.object(tn, "_semaphore_preflight", new_callable=AsyncMock), \
                patch.object(tn, "_admin_exchange", new_callable=AsyncMock) as write:
            write.return_value = {"job_id": 42, "state": "PENDING_OR_UNKNOWN"}
            result = await tn._deploy_semaphore(self.confirm)
            method, params = write.call_args.args
            self.assertEqual(method, "app.create")
            self.assertEqual(params[0]["app_name"], "semaphore")
            self.assertTrue(params[0]["custom_app"])
            self.assertIn("D" * 48, params[0]["custom_compose_config_string"])
            self.assertNotIn("D" * 48, json.dumps(result))
            self.assertEqual(result["job"]["job_id"], 42)
            with self.assertRaises(ValueError):
                await tn._deploy_semaphore(self.confirm)
            write.assert_awaited_once()

    async def test_ambiguous_create_not_replayed(self):
        with patch.object(tn, "_semaphore_template", new_callable=AsyncMock, return_value=self.template), \
                patch.object(tn, "_semaphore_preflight", new_callable=AsyncMock), \
                patch.object(tn, "_admin_exchange", new_callable=AsyncMock) as write:
            write.side_effect = RuntimeError("unknown")
            with self.assertRaises(RuntimeError):
                await tn._deploy_semaphore(self.confirm)
            with self.assertRaises(ValueError):
                await tn._deploy_semaphore(self.confirm)
            write.assert_awaited_once()

    async def test_persisted_attempt_denies_create_after_restart(self):
        tn._record_semaphore_attempt()
        with patch.object(tn, "_semaphore_template", new_callable=AsyncMock) as fetch:
            with self.assertRaises(ValueError):
                await tn._deploy_semaphore(self.confirm)
            fetch.assert_not_awaited()



class AppDeploymentPreflightTests(unittest.IsolatedAsyncioTestCase):
    async def test_pinned_source_rejects_mutable_refs_and_paths(self):
        for revision, blob, path in (
            ("main", "b" * 40, "stacks/plex-truenas/docker-compose.yml"),
            ("a" * 40, "bad", "stacks/plex-truenas/docker-compose.yml"),
            ("a" * 40, "b" * 40, "https://other.example/docker-compose.yml"),
            ("a" * 40, "b" * 40, "stacks/../docker-compose.yml"),
        ):
            with patch.object(tn.httpx, "AsyncClient") as client:
                with self.assertRaises(ValueError):
                    await tn._pinned_compose(revision, blob, path)
                client.assert_not_called()

    async def test_semaphore_loader_keeps_existing_pin(self):
        with patch.object(tn, "_pinned_compose", new_callable=AsyncMock,
                          return_value="approved") as fetch:
            self.assertEqual(await tn._semaphore_template(), "approved")
            fetch.assert_awaited_once_with(tn._SEMAPHORE_REV, tn._SEMAPHORE_BLOB,
                                         "stacks/semaphore-truenas/docker-compose.yml")

    async def test_resources_are_bounded_and_projected(self):
        with patch.object(tn, "_read", new_callable=AsyncMock) as read:
            read.side_effect = [[32400, 3000, 32400], {
                "0000:00:02.0": {"vendor": "Intel", "description": "iGPU", "error": None,
                                  "gpu_details": {"private": "secret-value"}},
                "0000:01:00.0": {"vendor": "Other", "error": "secret-value"},
            }]
            result = await tn._app_host_resources()
            self.assertEqual(result["app_used_ports"], [3000, 32400])
            self.assertEqual([x["usable_reported"] for x in result["gpu_choices"]], [True, False])
            self.assertNotIn("secret-value", json.dumps(result))

    async def test_failed_and_malformed_inventory_is_unknown(self):
        with patch.object(tn, "_read", new_callable=AsyncMock) as read:
            read.side_effect = [RuntimeError("private error"), {"gpu": {"vendor": "Intel"}}]
            result = await tn._app_host_resources()
            self.assertIsNone(result["app_used_ports"])
            self.assertIsNone(result["gpu_choices"])
            read.side_effect = [[True, 32400], []]
            result = await tn._app_host_resources()
            self.assertIsNone(result["app_used_ports"])
            self.assertIsNone(result["gpu_choices"])

    async def test_destination_does_not_authorize_deploy(self):
        with patch.object(tn, "_diagnostic_directory", new_callable=AsyncMock), \
                patch.object(tn, "_read", new_callable=AsyncMock) as read, \
                patch.object(tn, "_app_host_resources", new_callable=AsyncMock,
                             return_value={"app_used_ports": [3000], "gpu_choices": [
                                 {"vendor": "Intel", "usable_reported": True}]}), \
                patch.object(tn, "_admin_exchange", new_callable=AsyncMock) as write:
            read.side_effect = [[], []]
            result = await tn._plex_migration_preflight()
            self.assertEqual(result["media_directories_verified"], {"movies": True, "TVShows": True})
            self.assertFalse(result["app_installed"])
            self.assertFalse(result["port_32400_reported_in_use"])
            self.assertTrue(result["intel_gpu_reported_usable"])
            self.assertFalse(result["source_config_verified"])
            self.assertFalse(result["ready_to_deploy"])
            write.assert_not_awaited()

    async def test_missing_media_and_ports_do_not_claim_success(self):
        with patch.object(tn, "_diagnostic_directory", new_callable=AsyncMock,
                          side_effect=ValueError("private")), \
                patch.object(tn, "_read", new_callable=AsyncMock,
                             side_effect=[[], []]), \
                patch.object(tn, "_app_host_resources", new_callable=AsyncMock,
                             return_value={"app_used_ports": None, "gpu_choices": None}):
            result = await tn._plex_migration_preflight()
            self.assertIsNone(result["media_directories_verified"]["movies"])
            self.assertIsNone(result["port_32400_reported_in_use"])
            self.assertIsNone(result["intel_gpu_reported_usable"])
            self.assertFalse(result["ready_to_deploy"])



class CatalogManagementTests(unittest.IsolatedAsyncioTestCase):
    async def test_mount_projection_no_raw_values(self):
        mount = {"source": "/mnt/pool/appdata/plex", "destination": "/config",
                 "type": "bind", "mode": "rw", "options": "secret-value"}
        with patch.object(tn, "_installed_app", new_callable=AsyncMock,
                          return_value={"state": "RUNNING", "config": {"token": "secret-value"},
                                        "active_workloads": {"volumes": [mount,
                                            {"source": "//user:secret-value@nas/share", "type": "volume",
                                             "destination": "/data", "mode": "secret-value"}],
                                            "container_details": [{"service_name": "plex", "volume_mounts": [mount]}]}}):
            out = await tn._app_mounts("plex")
            self.assertEqual(out["volumes"][0]["source"], "/mnt/pool/appdata/plex")
            self.assertEqual(out["containers"][0]["mounts"][0]["destination"], "/config")
            self.assertIsNone(out["volumes"][1]["source"])
            self.assertNotIn("secret-value", json.dumps(out))

    async def test_mount_unknown_not_empty(self):
        with patch.object(tn, "_installed_app", new_callable=AsyncMock, return_value={}):
            out = await tn._app_mounts("plex")
            self.assertIsNone(out["volumes"])

    async def test_upgrade_preview_is_exact_and_read_only(self):
        with patch.object(tn, "_installed_app", new_callable=AsyncMock,
                          return_value={"custom_app": False, "version": "1.0.0"}), \
                patch.object(tn, "_read", new_callable=AsyncMock,
                             return_value={"upgrade_version": "1.0.1", "upgrade_human_version": "v2",
                                           "available_versions_for_upgrade": [{"version": "1.0.1"}],
                                           "changelog": "secret-value"}), \
                patch.object(tn, "_admin_exchange", new_callable=AsyncMock) as write:
            out = await tn._upgrade_preview("plex", "1.0.1")
            self.assertTrue(out["target_offered"])
            self.assertFalse(out["write_authorized"])
            self.assertNotIn("secret-value", json.dumps(out))
            with self.assertRaises(ValueError):
                await tn._upgrade_preview("plex", "latest")
            write.assert_not_awaited()

    def test_qbit_profile(self):
        with patch.dict(os.environ, {"TRUENAS_QBITTORRENT_BIND_ADDRESS": "192.168.1.10"}):
            v = tn._qbit_values(tn._qbit_bind())
        self.assertFalse(v["network"]["host_network"])
        self.assertEqual(v["network"]["web_port"]["host_ips"], ["192.168.1.10"])
        self.assertEqual(v["network"]["bt_port"]["port_number"], 51413)
        self.assertEqual(v["storage"]["config"]["host_path_config"]["path"], "/mnt/" + tn._QBIT_CONFIG)
        self.assertEqual(v["storage"]["downloads"]["mount_path"], "/downloads")
        self.assertFalse(v["storage"]["downloads"]["host_path_config"]["acl_enable"])
        for value in ("0.0.0.0", "8.8.8.8", "127.0.0.1", "::1"):
            with patch.dict(os.environ, {"TRUENAS_QBITTORRENT_BIND_ADDRESS": value}):
                with self.assertRaises(ValueError):
                    tn._qbit_bind()
        self.assertFalse(tn._qbit_owned({"uid": 0, "gid": 0, "mode": 0o777, "acl": False}))
        self.assertFalse(tn._qbit_owned({"uid": 1000, "gid": 1000, "mode": 0o700, "acl": True}))
        self.assertTrue(tn._qbit_owned({"uid": 1000, "gid": 1000, "mode": 0o700, "acl": False}))

    async def test_catalog_bind_choices_fail_closed(self):
        for raw, expected in (({"0.0.0.0": "Any", "::": "Any"}, ["0.0.0.0", "::"]),
                              ({"192.168.1.10": "Static"}, ["192.168.1.10"]),
                              ({}, []), ({"not-an-ip": "secret-value"}, None),
                              ([], None)):
            with patch.object(tn, "_read", new_callable=AsyncMock, return_value=raw) as read:
                self.assertEqual(await tn._app_bind_choices(), expected)
                read.assert_awaited_once_with("app.ip_choices", [])
        with patch.object(tn, "_read", new_callable=AsyncMock, side_effect=RuntimeError("unavailable")):
            self.assertIsNone(await tn._app_bind_choices())

    async def test_qbit_preflight_rejects_dhcp_only_address(self):
        bind = "192.168.1.10"
        async def read(method, params):
            if method == "app.available":
                return [{"name": "qbittorrent", "train": "community",
                         "latest_version": tn._QBIT_VERSION, "healthy": True}]
            if method == "filesystem.listdir":
                return []
            if method == "filesystem.stat":
                return {"uid": 1000, "gid": 1000, "acl": False, "mode": 0o700,
                        "realpath": "/test/download", "type": "DIRECTORY"}
            if method == "interface.query":
                return [{"state": {"aliases": [{"address": bind}]}}]
            if method == "app.ip_choices":
                return {"0.0.0.0": "Any", "::": "Any"}
            if method == "pool.snapshottask.query":
                return [{"enabled": True, "recursive": True}]
            if method == "replication.query":
                return [{"enabled": True, "recursive": True, "direction": "PUSH",
                         "transport": "LOCAL", "source_datasets": ["USB_Storage_Space/appdata"],
                         "target_dataset": "Backup/appdata"}]
            raise AssertionError(method)
        with patch.object(tn, "_read", side_effect=read), \
                patch.object(tn, "_installed_app", new_callable=AsyncMock, return_value=None), \
                patch.object(tn, "_dataset_root_stat", new_callable=AsyncMock,
                             return_value={"stat": {"uid": 1000, "gid": 1000, "acl": False, "mode": 0o700}}), \
                patch.object(tn, "_diagnostic_directory", new_callable=AsyncMock, return_value="/test/download"), \
                patch.object(tn, "_app_host_resources", new_callable=AsyncMock, return_value={"app_used_ports": []}), \
                patch.object(tn, "_qbit_bind", return_value=bind), \
                tempfile.TemporaryDirectory() as tmp, \
                patch.object(tn, "_QBIT_ATTEMPT", Path(tmp) / "attempt.json"):
            out = await tn._qbit_preflight()
            self.assertTrue(out["checks"]["bind_address_present"])
            self.assertFalse(out["checks"]["bind_address_catalog_allowed"])
            self.assertFalse(out["preflight_passed"])
            self.assertTrue(all(v for k, v in out["checks"].items() if k != "bind_address_catalog_allowed"))

    async def test_qbit_preflight_fails_closed(self):
        with patch.object(tn, "_installed_app", new_callable=AsyncMock, return_value=None), \
                patch.object(tn, "_read", new_callable=AsyncMock, return_value=[]), \
                patch.object(tn, "_dataset_root_stat", new_callable=AsyncMock, side_effect=ValueError("missing")), \
                patch.object(tn, "_diagnostic_directory", new_callable=AsyncMock, side_effect=ValueError("missing")), \
                patch.object(tn, "_app_host_resources", new_callable=AsyncMock, return_value={"app_used_ports": None}), \
                patch.object(tn, "_qbit_bind", side_effect=ValueError("missing")):
            out = await tn._qbit_preflight()
            self.assertFalse(out["preflight_passed"])
            for check in ("catalog_version_verified", "empty_owned_config", "download_root_owned",
                          "app_ports_available", "bind_address_present", "independent_replication_configured"):
                self.assertFalse(out["checks"][check])

    async def test_qbit_disabled_wrong_confirmation_and_failed_preflight(self):
        with patch.object(tn, "_write_credentials"), \
                patch.object(tn, "_admin_exchange", new_callable=AsyncMock) as write, \
                patch.object(tn, "_qbit_preflight", new_callable=AsyncMock, return_value={"preflight_passed": False}), \
                tempfile.TemporaryDirectory() as tmp, \
                patch.object(tn, "_QBIT_ATTEMPT", Path(tmp) / "attempt.json"):
            for enabled, confirm in (("false", "create-fresh:qbittorrent:community:1.4.24"),
                                     ("true", "wrong"),
                                     ("true", "create-fresh:qbittorrent:community:1.4.24")):
                with patch.dict(os.environ, {"TRUENAS_QBITTORRENT_DEPLOY_ENABLED": enabled}):
                    with self.assertRaises(ValueError):
                        await tn._deploy_qbit(confirm)
            write.assert_not_awaited()
            self.assertFalse(tn._QBIT_ATTEMPT.exists())

    async def test_qbit_fixed_create_and_no_replay(self):
        confirm = "create-fresh:qbittorrent:community:1.4.24"
        with patch.object(tn, "_write_credentials"), \
                patch.dict(os.environ, {"TRUENAS_QBITTORRENT_DEPLOY_ENABLED": "true",
                                        "TRUENAS_QBITTORRENT_BIND_ADDRESS": "192.168.1.10"}), \
                patch.object(tn, "_qbit_preflight", new_callable=AsyncMock, return_value={"preflight_passed": True}), \
                patch.object(tn, "_admin_exchange", new_callable=AsyncMock, side_effect=RuntimeError("unknown")) as write, \
                tempfile.TemporaryDirectory() as tmp, \
                patch.object(tn, "_QBIT_ATTEMPT", Path(tmp) / "attempt.json"):
            with self.assertRaises(RuntimeError):
                await tn._deploy_qbit(confirm)
            method, params = write.call_args.args
            self.assertEqual(method, "app.create")
            self.assertEqual(params[0]["app_name"], "qbittorrent")
            self.assertEqual(params[0]["catalog_app"], "qbittorrent")
            self.assertEqual(params[0]["train"], "community")
            self.assertEqual(params[0]["version"], "1.4.24")
            self.assertFalse(params[0]["custom_app"])
            self.assertTrue(tn._QBIT_ATTEMPT.exists())
            with self.assertRaises(ValueError):
                await tn._deploy_qbit(confirm)
            write.assert_awaited_once()



class ReviewedCatalogTests(unittest.IsolatedAsyncioTestCase):
    def test_abs_profile_values(self):
        v = tn._abs_values("192.168.1.10")
        self.assertEqual(v["run_as"], {"user": 1000, "group": 1000})
        self.assertEqual(v["network"]["web_port"],
                         {"bind_mode": "published", "port_number": 30067,
                          "host_ips": ["192.168.1.10"]})
        self.assertEqual(v["network"]["opds_port"]["bind_mode"], "")
        self.assertEqual(v["network"]["networks"], [])
        self.assertEqual(v["storage"]["config"]["host_path_config"]["path"],
                         "/mnt/" + tn._ABS_ROOT + "/config")
        self.assertEqual(v["storage"]["metadata"]["host_path_config"]["path"],
                         "/mnt/" + tn._ABS_ROOT + "/metadata")
        additional = v["storage"]["additional_storage"]
        self.assertEqual([x["mount_path"] for x in additional],
                         ["/podcasts", "/mnt/shared/audiobooks"])
        self.assertFalse(additional[0]["read_only"])
        self.assertTrue(additional[1]["read_only"])
        for x in [v["storage"]["config"], v["storage"]["metadata"], *additional]:
            self.assertFalse(x["host_path_config"]["acl_enable"])
        for address in ("", "0.0.0.0", "::", "8.8.8.8", "127.0.0.1"):
            with patch.dict(os.environ, {"TRUENAS_CATALOG_BIND_ADDRESS": address}):
                with self.assertRaises(ValueError):
                    tn._catalog_bind()

    async def test_profile_dispatch_and_enablement(self):
        with patch.dict(os.environ, {"TRUENAS_CATALOG_CREATE_PROFILES": "",
                                     "TRUENAS_QBITTORRENT_DEPLOY_ENABLED": "false"}):
            self.assertTrue(all(not x["enabled"] for x in tn._catalog_profiles()["profiles"]))
        with patch.object(tn, "_qbit_preflight", new_callable=AsyncMock,
                          return_value={"preflight_passed": True}) as qbit, \
                patch.object(tn, "_deploy_qbit", new_callable=AsyncMock) as deploy:
            self.assertTrue((await tn._catalog_preflight("qbittorrent-fresh"))["preflight_passed"])
            qbit.assert_awaited_once()
            await tn._catalog_create("qbittorrent-fresh", "confirm")
            deploy.assert_awaited_once_with("confirm")
        for fn, args in ((tn._catalog_preflight, ("unknown",)),
                         (tn._catalog_create, ("unknown", "anything"))):
            with self.assertRaises(ValueError):
                await fn(*args)

    async def test_abs_preflight_gates(self):
        bind = "192.168.1.10"
        bad = None
        async def read(method, params):
            if method == "app.available":
                return [{"name": "audiobookshelf", "train": "community",
                         "latest_version": tn._ABS_VERSION, "latest_app_version": "2.38.0",
                         "healthy": bad != "catalog"}]
            if method == "filesystem.stat":
                path = params[0]
                if path.endswith("/absdatabase.sqlite"):
                    return {"realpath": path, "type": "FILE", "uid": 1000,
                            "gid": 1000, "mode": 0o600, "size": 0 if bad == "db" else 10}
                if path.endswith("/audiobookshelf.tar"):
                    return {"realpath": path, "type": "FILE", "uid": 0,
                            "mode": 0o644 if bad == "archive" else 0o600, "size": 100}
                if path.endswith("/audiobookshelf-migration"):
                    return {"realpath": path, "type": "DIRECTORY", "uid": 0,
                            "mode": 0o700, "is_mountpoint": False}
                if path.endswith("/audiobooks"):
                    return {"realpath": path, "type": "DIRECTORY", "uid": 0,
                            "gid": 0, "mode": 0o700 if bad == "library" else 0o755}
                raise AssertionError(path)
            if method == "pool.snapshot.query":
                name = params[0][0][2]
                return [{"id": name, "createtxg": "2" if bad == "snapshot" and
                         "/config@" in name else "1"}]
            if method == "interface.query":
                return [{"state": {"aliases": [{"address": bind}]}}]
            if method == "app.ip_choices":
                return {"0.0.0.0": "Any"} if bad == "bind" else {bind: "Static"}
            if method == "pool.snapshottask.query":
                return [{"enabled": True, "recursive": True}]
            if method == "replication.query":
                return [{"enabled": True, "recursive": True, "direction": "PUSH",
                         "transport": "LOCAL", "source_datasets": ["USB_Storage_Space/appdata"],
                         "target_dataset": "Backup/appdata"}]
            raise AssertionError(method)

        with patch.object(tn, "_read", side_effect=read), \
                patch.object(tn, "_installed_app", new_callable=AsyncMock, return_value=None), \
                patch.object(tn, "_dataset_root_stat", new_callable=AsyncMock,
                             return_value={"stat": {"uid": 1000, "gid": 1000,
                                                    "acl": False, "mode": 0o700}}), \
                patch.object(tn, "_diagnostic_directory", new_callable=AsyncMock,
                             return_value="/test/audiobooks"), \
                patch.object(tn, "_app_host_resources", new_callable=AsyncMock,
                             return_value={"app_used_ports": []}), \
                patch.dict(os.environ, {"TRUENAS_CATALOG_BIND_ADDRESS": bind}), \
                tempfile.TemporaryDirectory() as tmp, \
                patch.object(tn, "_ABS_ATTEMPT", Path(tmp) / "attempt.json"):
            out = await tn._catalog_preflight("audiobookshelf-migration")
            self.assertTrue(out["preflight_passed"], out["checks"])
            for bad, check in (("catalog", "catalog_version_verified"),
                               ("db", "restored_database_present"),
                               ("archive", "independent_archive_present"),
                               ("library", "library_root_readable_by_mode"),
                               ("snapshot", "matching_rollback_snapshots"),
                               ("bind", "bind_address_catalog_allowed")):
                out = await tn._abs_preflight()
                self.assertFalse(out["preflight_passed"])
                self.assertFalse(out["checks"][check])

    async def test_abs_create_gates_and_no_replay(self):
        profile = "audiobookshelf-migration"
        with patch.object(tn, "_write_credentials"), \
                patch.dict(os.environ, {"TRUENAS_CATALOG_BIND_ADDRESS": "192.168.1.10"}), \
                patch.object(tn, "_abs_preflight", new_callable=AsyncMock,
                             return_value={"preflight_passed": False}) as preflight, \
                patch.object(tn, "_admin_exchange", new_callable=AsyncMock,
                             side_effect=RuntimeError("ambiguous")) as write, \
                tempfile.TemporaryDirectory() as tmp, \
                patch.object(tn, "_ABS_ATTEMPT", Path(tmp) / "attempt.json"):
            with patch.dict(os.environ, {"TRUENAS_CATALOG_CREATE_PROFILES": ""}):
                with self.assertRaises(ValueError):
                    await tn._catalog_create(profile, tn._ABS_CONFIRM)
            with patch.dict(os.environ, {"TRUENAS_CATALOG_CREATE_PROFILES": profile}):
                with self.assertRaises(ValueError):
                    await tn._catalog_create(profile, "wrong")
                with self.assertRaises(ValueError):
                    await tn._catalog_create(profile, tn._ABS_CONFIRM)
                write.assert_not_awaited()
                self.assertFalse(tn._ABS_ATTEMPT.exists())
                preflight.return_value = {"preflight_passed": True}
                with self.assertRaises(RuntimeError):
                    await tn._catalog_create(profile, tn._ABS_CONFIRM)
                method, params = write.call_args.args
                self.assertEqual(method, "app.create")
                self.assertEqual(params[0]["app_name"], "audiobookshelf")
                self.assertEqual(params[0]["version"], tn._ABS_VERSION)
                self.assertFalse(params[0]["custom_app"])
                self.assertTrue(tn._ABS_ATTEMPT.exists())
                with self.assertRaises(ValueError):
                    await tn._catalog_create(profile, tn._ABS_CONFIRM)
                write.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
