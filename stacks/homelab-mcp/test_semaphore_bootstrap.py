import os
import unittest
from unittest.mock import patch
import json
import httpx
import semaphore_bootstrap as sb


class BootstrapTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "SEMAPHORE_BOOTSTRAP_ENABLED": "true",
            "SEMAPHORE_URL": "https://nas.example.ts.net:8443",
            "SEMAPHORE_API_TOKEN": "private-test-token",
            "SEMAPHORE_VERIFY_SSL": "true",
            "SEMAPHORE_ALLOWED_TEMPLATES": "",
        }, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.rows = {}
        self.posts = []
        self.next_id = 1

    def handler(self, request):
        path = request.url.path.removeprefix("/api")
        if request.method == "GET":
            return httpx.Response(200, json=self.rows.get(path))
        if request.method != "POST":
            raise AssertionError("unexpected write")
        payload = json.loads(request.content)
        self.posts.append(path)
        row = dict(payload, id=self.next_id)
        self.next_id += 1
        self.rows.setdefault(path, []).append(row)
        return httpx.Response(201, json=row)

    async def run_bootstrap(self):
        async with httpx.AsyncClient(base_url="https://nas.example.ts.net:8443/api",
                transport=httpx.MockTransport(self.handler)) as client:
            return await sb._bootstrap(client)

    async def test_create_and_repeat(self):
        result = await self.run_bootstrap()
        self.assertEqual(len(self.posts), 5)
        self.assertFalse(result["execution_enabled"])
        self.assertEqual(result["project"]["id"], 1)
        self.assertTrue(result["smoke_template"]["created"])
        self.assertNotIn("private-test-token", json.dumps(result))
        self.assertFalse((await self.run_bootstrap())["smoke_template"]["created"])
        self.assertEqual(len(self.posts), 5)

    async def test_legacy_instance_denied(self):
        self.rows["/projects"] = [{"id": 1, "name": "Clothier HomeLab"}]
        with self.assertRaises(ValueError):
            await self.run_bootstrap()
        self.assertEqual(self.posts, [])

    async def test_drift_denied_without_overwrite(self):
        await self.run_bootstrap()
        self.rows["/project/1/repositories"][0]["git_url"] = "https://example.com/other"
        with self.assertRaises(RuntimeError):
            await self.run_bootstrap()
        self.assertEqual(len(self.posts), 5)

    async def test_template_drift_denied(self):
        await self.run_bootstrap()
        self.rows["/project/1/templates"][0]["allow_override_args_in_task"] = True
        with self.assertRaises(RuntimeError):
            await self.run_bootstrap()
        self.assertEqual(len(self.posts), 5)

    async def test_disabled_or_unsafe_configuration(self):
        for env in ({"SEMAPHORE_BOOTSTRAP_ENABLED": "false"},
                    {"SEMAPHORE_VERIFY_SSL": "false"},
                    {"SEMAPHORE_URL": "http://nas.example.ts.net:8443"},
                    {"SEMAPHORE_URL": "https://nas.example.ts.net:443"},
                    {"SEMAPHORE_ALLOWED_TEMPLATES": "1:*"}):
            with patch.dict(os.environ, env):
                with self.assertRaises(ValueError):
                    await sb.bootstrap("bootstrap:homelab-truenas-operations")
        with self.assertRaises(ValueError):
            await sb.bootstrap("wrong")

    async def test_error_body_not_exposed(self):
        async with httpx.AsyncClient(base_url="https://nas.example.ts.net:8443/api",
                transport=httpx.MockTransport(lambda req: httpx.Response(403, text="private-test-token"))) as client:
            with self.assertRaisesRegex(RuntimeError, "bootstrap request failed") as ctx:
                await sb._bootstrap(client)
            self.assertNotIn("private-test-token", str(ctx.exception))

    def test_collection_rejects_wrong_shape(self):
        for value in ({}, "bad", [42]):
            with self.assertRaises(RuntimeError):
                sb._rows(value)


if __name__ == "__main__":
    unittest.main()
