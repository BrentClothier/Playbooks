#!/usr/bin/env python3
from pathlib import Path

path = Path("src/video_core/texture_cache/texture_cache.h")
text = path.read_text()

# V22b proves that Eden finds the presented non-MSAA GPU image and performs the synchronous
# download, yet the guest framebuffer remains zero. Hash the mapped Vulkan staging data after the
# transfer completes and before SwizzleImage writes it back. This distinguishes a blank GPU image
# from a broken swizzle/writeback path.
old = '''        image.DownloadMemory(map, copies);
        runtime.Finish();
        SwizzleImage(*gpu_memory, image.gpu_addr, image.info, copies, map.mapped_span,
                     swizzle_data_buffer);
'''
new = '''        image.DownloadMemory(map, copies);
        runtime.Finish();

        static u32 v23b_staging_diag_count{};
        if (v21_force_framebuffer_download && v23b_staging_diag_count < 24) {
            const size_t sample_size = map.mapped_span.size();
            u64 hash = 1469598103934665603ULL;
            u64 nonzero = 0;
            for (size_t i = 0; i < sample_size; ++i) {
                const u8 value = map.mapped_span[i];
                hash ^= value;
                hash *= 1099511628211ULL;
                nonzero += value != 0;
            }
            LOG_WARNING(HW_GPU,
                        "V23B_DIAG GPU staging sample={} image_cpu={:#x} image_gpu={:#x} format={} size={}x{} mapped_bytes={} nonzero={} hash={:#x}",
                        v23b_staging_diag_count, image.cpu_addr, image.gpu_addr,
                        static_cast<u32>(image.info.format), image.info.size.width,
                        image.info.size.height, sample_size, nonzero, hash);
            ++v23b_staging_diag_count;
        }

        SwizzleImage(*gpu_memory, image.gpu_addr, image.info, copies, map.mapped_span,
                     swizzle_data_buffer);
'''

count = text.count(old)
if count != 1:
    raise RuntimeError(f"hash Vulkan staging framebuffer: expected one match, found {count}")

path.write_text(text.replace(old, new, 1))
print(f"updated {path}: hash downloaded Vulkan framebuffer staging data")
