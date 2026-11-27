import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import backup_ops as ops


class BackupOpsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.files = self.root / "backup-files"
        self.apps = self.root / "backup-apps"
        for p in (self.source, self.files, self.apps):
            p.mkdir()
        for group, dirs in ops.GROUPS.items():
            dest = self.files if group == "files" else self.apps
            for name in dirs:
                (self.source / name).mkdir()
                (dest / name).mkdir()
        self.config = {"sample_group": "files", "sample_relative_path": "Stuff/test.txt"}
        self.locations = patch.object(ops, "locations", return_value=(
            self.source, {"files": self.files, "applications": self.apps}))
        self.locations.start()
        self.addCleanup(self.locations.stop)

    def test_restore_verifies_and_preserves_source(self):
        for root in (self.source, self.files):
            (root / "Stuff/test.txt").write_bytes(b"test contents")
        result = ops.restore(self.config)
        self.assertTrue(result["passed"])
        self.assertTrue(result["current_source_matches_backup"])
        self.assertEqual((self.source / "Stuff/test.txt").read_bytes(), b"test contents")
        self.assertEqual((self.files / "Stuff/test.txt").read_bytes(), b"test contents")

    def test_restore_can_succeed_when_source_changed(self):
        (self.source / "Stuff/test.txt").write_bytes(b"new")
        (self.files / "Stuff/test.txt").write_bytes(b"old")
        result = ops.restore(self.config)
        self.assertTrue(result["restored_matches_backup"])
        self.assertFalse(result["current_source_matches_backup"])

    def test_sample_rejects_traversal_and_wrong_group(self):
        for path in ("Stuff/../test.txt", "/etc/passwd", "apps/test.txt",
                     "Stuff//test.txt", "Stuff/.hidden"):
            with self.assertRaises(ValueError):
                ops.sample_parts(dict(self.config, sample_relative_path=path))

    def test_sample_rejects_symlink_and_fifo(self):
        (self.files / "Stuff/test.txt").symlink_to("/etc/passwd")
        with self.assertRaises(OSError):
            ops.restore(self.config)
        (self.files / "Stuff/test.txt").unlink()
        os.mkfifo(self.files / "Stuff/test.txt")
        with self.assertRaises(ValueError):
            ops.restore(self.config)

    def test_sample_rejects_oversized_file(self):
        with (self.files / "Stuff/test.txt").open("wb") as f:
            f.truncate(ops.MAX_SAMPLE + 1)
        with self.assertRaises(ValueError):
            ops.restore(self.config)

    def test_verify_dry_run_and_bounded_projection(self):
        with patch.object(ops.subprocess, "run") as run:
            run.side_effect = [
                subprocess.CompletedProcess([], 0, "Number of regular files transferred: 0\n"),
                subprocess.CompletedProcess([], 0, "Number of regular files transferred: 2\n"),
            ]
            result = ops.verify(self.config)
            self.assertFalse(result["passed"])
            for call in run.call_args_list:
                cmd = call.args[0]
                self.assertIn("--dry-run", cmd)
                self.assertIn("--checksum", cmd)
                self.assertNotIn("--delete", cmd)
                self.assertNotIn("shell", call.kwargs)

    def test_verify_unknown_stats_fails_closed(self):
        with patch.object(ops.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "")):
            self.assertFalse(ops.verify(self.config)["passed"])


if __name__ == "__main__":
    unittest.main()
