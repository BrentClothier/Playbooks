import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import semaphore_db_backup as b


class ContainerTests(unittest.TestCase):
    def test_exact_container(self):
        mounts = [{"Type": "bind", "Source": str(b.SOURCE),
                   "Destination": "/var/lib/postgresql/data", "RW": True}]
        with patch.object(b, "capture", side_effect=["123456abcdef", b.IMAGE, json.dumps(mounts)]) as c:
            self.assertEqual(b.container_id(), "123456abcdef")
            self.assertIn("label=com.docker.compose.project=ix-semaphore", c.call_args_list[0].args[0])

    def test_reject_multiple(self):
        with patch.object(b, "capture", return_value="123456abcdef\nabcdef123456"):
            with self.assertRaises(ValueError):
                b.container_id()

    def test_reject_wrong_image(self):
        with patch.object(b, "capture", side_effect=["123456abcdef", "postgres:latest"]):
            with self.assertRaises(ValueError):
                b.container_id()

    def test_reject_wrong_mount(self):
        with patch.object(b, "capture", side_effect=["123456abcdef", b.IMAGE, "[]"]):
            with self.assertRaises(ValueError):
                b.container_id()


class ArchiveTests(unittest.TestCase):
    def test_publish_only_after_catalog_and_mount_checks(self):
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d)
            steps = []
            def fake_run(args, **kw):
                if "pg_dump" in args:
                    self.assertIn("--no-password", args)
                    self.assertIn("--dbname=semaphore", args)
                    kw["stdout"].write(b"PGDMP test")
                    steps.append("dump")
                else:
                    self.assertIn("pg_restore", args)
                    self.assertIn("--list", args)
                    self.assertEqual(kw["stdin"].read(), b"PGDMP test")
                    self.assertEqual(list(dest.glob("*.dump")), [])
                    steps.append("catalog")
            def check():
                self.assertEqual(list(dest.glob("*.dump")), [])
                steps.append("mount")
            with patch.object(b, "run", side_effect=fake_run):
                self.assertEqual(b.create_archive("123456abcdef", dest, check), 10)
            self.assertEqual(steps, ["dump", "catalog", "mount"])
            files = list(dest.iterdir())
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].read_bytes(), b"PGDMP test")
            self.assertEqual(files[0].stat().st_mode & 0o077, 0)

    def test_failed_catalog_does_not_publish(self):
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d)
            def fake_run(args, **kw):
                if "pg_dump" in args:
                    kw["stdout"].write(b"bad dump")
                else:
                    raise subprocess.CalledProcessError(1, args)
            with patch.object(b, "run", side_effect=fake_run):
                with self.assertRaises(subprocess.CalledProcessError):
                    b.create_archive("123456abcdef", dest, lambda: None)
            self.assertEqual(list(dest.iterdir()), [])

    def test_mount_failure_does_not_publish(self):
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d)
            def fake_run(args, **kw):
                if "pg_dump" in args:
                    kw["stdout"].write(b"PGDMP test")
            def fail():
                raise ValueError("mount changed")
            with patch.object(b, "run", side_effect=fake_run):
                with self.assertRaises(ValueError):
                    b.create_archive("123456abcdef", dest, fail)
            self.assertEqual(list(dest.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
