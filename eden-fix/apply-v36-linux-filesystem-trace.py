#!/usr/bin/env python3
from pathlib import Path
import subprocess

# V35 proved that Minecraft receives the correct account UUID and that the expanded
# 288 MiB normal/journal allocation persists after restart. Cache sizes and reported
# free space are also valid. V36 therefore changes no behavior: it adds bounded INFO
# tracing around filesystem object creation, metadata/mutation operations, file writes,
# directory enumeration, and selected CMIF layouts. High-volume file reads are omitted.

patch_path = Path(__file__).with_name("v36-linux-filesystem-trace.patch")
if not patch_path.is_file():
    raise FileNotFoundError(f"missing v36 patch: {patch_path}")

subprocess.run(["git", "apply", "--check", str(patch_path)], check=True)
subprocess.run(["git", "apply", str(patch_path)], check=True)
print("applied v36 bounded filesystem and CMIF diagnostics")
