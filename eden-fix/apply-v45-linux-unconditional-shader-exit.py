#!/usr/bin/env python3
"""Use Maxwell's canonical unconditional EXIT for the Minecraft shader repair."""
from pathlib import Path


path = Path("src/video_core/shader_environment.cpp")
text = path.read_text()
old = "constexpr u64 MaxwellExitInstruction = 0xe300000000000000ULL;"
new = "constexpr u64 MaxwellExitInstruction = 0xe30000000007000fULL;"
count = text.count(old)
if count != 1:
    raise RuntimeError(f"{path}: expected one v44 EXIT encoding, found {count}")
path.write_text(text.replace(old, new, 1))
print(f"updated {path}")
print("applied v45 Linux Minecraft unconditional shader EXIT")
