#!/usr/bin/env python3
from pathlib import Path
import shutil
import sys

# V35 proved that Minecraft receives the correct account UUID and that the expanded
# 288 MiB normal/journal allocation persists after restart. Cache sizes and reported
# free space are also valid. V36 therefore changes no behavior: it adds bounded INFO
# tracing around filesystem object creation, metadata/mutation operations, file writes,
# directory enumeration, and selected CMIF layouts. High-volume file reads are omitted.
#
# Install the exact locally validated source overlay rather than depending on patch-tool
# context matching in CI. These four files are otherwise the Eden baseline plus the v34
# capacity log additions; none contains graphics code or changes storage semantics.

source_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
overlay_root = Path(__file__).with_name("v36-overlay")
relative_paths = (
    Path("src/core/hle/service/cmif_serialization.h"),
    Path("src/core/hle/service/filesystem/fsp/fs_i_filesystem.cpp"),
    Path("src/core/hle/service/filesystem/fsp/fs_i_file.cpp"),
    Path("src/core/hle/service/filesystem/fsp/fs_i_directory.cpp"),
)

for relative_path in relative_paths:
    overlay_file = overlay_root / relative_path
    target_file = source_root / relative_path
    if not overlay_file.is_file():
        raise FileNotFoundError(f"missing v36 overlay file: {overlay_file}")
    if not target_file.is_file():
        raise FileNotFoundError(f"missing Eden source file: {target_file}")
    shutil.copyfile(overlay_file, target_file)
    print(f"installed v36 diagnostics: {relative_path}")

print("applied v36 bounded filesystem and CMIF diagnostics")
