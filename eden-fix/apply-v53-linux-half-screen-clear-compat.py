#!/usr/bin/env python3
from pathlib import Path
import subprocess

patch = Path(__file__).with_name("v53-linux-half-screen-clear-compat.patch")
if not patch.is_file():
    raise RuntimeError(f"missing reference patch: {patch}")
subprocess.run(["git", "apply", "--check", str(patch)], check=True)
subprocess.run(["git", "apply", str(patch)], check=True)
print("applied v53 Minecraft split-screen half-screen clear compatibility test")
