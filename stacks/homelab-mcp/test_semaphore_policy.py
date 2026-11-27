import unittest
from unittest.mock import AsyncMock, patch
import importlib.util
from pathlib import Path
import base64
import json
from types import SimpleNamespace
import semaphore_policy as p

URL = "https://nas.example.ts.net:8443"
ROW = {"id": 2, "project_id": 1, "name": "backup", "app": "python"}
PROJECT = {"id": 1, "name": p.PROJECT}


class ScopeTests(unittest.IsolatedAsyncioTestCase):
    def test_parse(self):
        self.assertEqual(p.parse("1:*,2:3"), (False, {(2,3)}, {1}))
        self.assertEqual(p.parse("*"), (True, set(), set()))
        self.assertEqual(p.parse(""), (False, set(), set()))
        for invalid in ("0:*", "1:0", "1:*,*", "1:-1", "1:*,,2:3", "1: **"):
            with self.assertRaises(ValueError):
                p.parse(invalid)

    async def test_scope(self):
        get = AsyncMock(side_effect=[PROJECT, ROW])
        self.assertEqual(await p.authorize(get,"1:*",1,2,URL,True),ROW)
        get.assert_awaited()
        get.reset_mock()
        with self.assertRaises(PermissionError):
            await p.authorize(get,"1:*",2,2,URL,True)
        get.assert_not_awaited()

    async def test_wrong_project_and_overrides(self):
        for project, row in (({"id":1,"name":"Other"}, ROW),
                             (PROJECT, dict(ROW, allow_override_args_in_task=True)),
                             (PROJECT, dict(ROW, task_params={"allow_override_inventory":True})),
                             (PROJECT, dict(ROW, project_id=2))):
            with self.assertRaises(PermissionError):
                await p.authorize(AsyncMock(side_effect=[project,row]),"1:*",1,2,URL,True)
        with self.assertRaises(PermissionError):
            await p.authorize(AsyncMock(),"1:*",1,2,URL,False)

    async def test_exact_pair_compatibility(self):
        self.assertEqual(await p.authorize(AsyncMock(return_value=ROW),"1:2",1,2,"http://legacy",False),ROW)


spec = importlib.util.spec_from_file_location("backup_client",Path(__file__).resolve().parents[2]/"scripts/truenas/semaphore_backup.py")
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.env = {"HOMELAB_BACKUP_HOST":"nas.example",
                    "HOMELAB_BACKUP_OPERATION":"restore",
                    "HOMELAB_BACKUP_HOST_KEY":"ssh-ed25519 "+"A"*68,
                    "HOMELAB_BACKUP_KEY_B64":base64.b64encode(b"-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----\n").decode()}

    def test_host_rejection(self):
        with self.assertRaises(ValueError):
            client.settings(dict(self.env,HOMELAB_BACKUP_HOST="-oProxyCommand=evil"))

    def test_fixed_command_and_sanitized_output(self):
        def mock_run(command, **kwargs):
            self.assertEqual(command[-2:],["nas.example","backup"])
            self.assertIn("StrictHostKeyChecking=yes",command)
            self.assertEqual(Path(command[command.index("-i")+1]).stat().st_mode & 0o777,0o600)
            self.assertNotIn("HOMELAB_BACKUP_KEY_B64",kwargs["env"])
            return SimpleNamespace(returncode=0,stdout=json.dumps({"operation":"restore","passed":True,"bytes":5,"secret":"not returned"}).encode())
        with patch.object(client.subprocess,"run",side_effect=mock_run):
            result=client.run(self.env)
        self.assertTrue(result["passed"])
        self.assertNotIn("secret",result)
