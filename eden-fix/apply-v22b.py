#!/usr/bin/env python3
from pathlib import Path

path = Path("src/video_core/texture_cache/texture_cache.h")
text = path.read_text()

old = '''    // Minecraft's block-linear display allocations are 0x870000 bytes at 1920x1080 and
    // 0x3c0000 bytes at 1280x720. V20 calls this function synchronously only for the presented
    // framebuffer, so these exact sizes provide a narrow compatibility gate.
    const bool v21_force_framebuffer_download = size == 0x870000 || size == 0x3c0000;
    static u32 v21_download_diag_count{};
'''
new = '''    // FlushRegion receives the visible RGBA byte count, not the padded block-linear nvmap
    // allocation size. The exact requests are 0x7e9000 for 1920x1080 and 0x384000 for 1280x720.
    // V20 calls this function synchronously only for the presented framebuffer, so these exact
    // sizes remain a narrow compatibility gate.
    const bool v21_force_framebuffer_download = size == 0x7e9000 || size == 0x384000;
    static u32 v21_download_diag_count{};
    if (v21_force_framebuffer_download && v21_download_diag_count < 120) {
        LOG_WARNING(HW_GPU,
                    "V22B_DIAG forcing presented framebuffer download request=[{:#x},+{:#x}]",
                    cpu_addr, size);
    }
'''

count = text.count(old)
if count != 1:
    raise RuntimeError(f"fix framebuffer download byte-count gate: expected one match, found {count}")

path.write_text(text.replace(old, new, 1))
print(f"updated {path}: use visible RGBA byte counts for Minecraft framebuffer download")
