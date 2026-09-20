#!/usr/bin/env python3
"""Apply the v49 Minecraft split-screen render diagnostic patch."""
from pathlib import Path
import subprocess

patch = Path(__file__).with_name("v49-linux-split-screen-render-diag.patch")
if not patch.is_file():
    raise RuntimeError(f"missing reference patch: {patch}")
subprocess.run(["git", "apply", "--check", str(patch)], check=True)
subprocess.run(["git", "apply", str(patch)], check=True)
print("applied v49 Linux Minecraft split-screen render diagnostics")
