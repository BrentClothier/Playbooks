#!/usr/bin/env python3
"""Apply the v51 Minecraft split-screen trace re-arm diagnostic patch."""
from pathlib import Path
import subprocess

patch = Path(__file__).with_name("v51-linux-split-screen-trace-rearm.patch")
if not patch.is_file():
    raise RuntimeError(f"missing reference patch: {patch}")
subprocess.run(["git", "apply", "--check", str(patch)], check=True)
subprocess.run(["git", "apply", str(patch)], check=True)
print("applied v51 Linux Minecraft split-screen trace re-arm diagnostics")
