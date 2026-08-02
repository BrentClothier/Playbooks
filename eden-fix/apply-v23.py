#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))
    print(f"updated {path}: {label}")


path = Path("src/video_core/texture_cache/texture_cache.h")

# V22b proves that Eden finds a single non-MSAA, GPU-modified framebuffer image and executes the
# synchronous download, but guest memory remains zero. Hash the mapped Vulkan staging buffer after
# the transfer completes and before SwizzleImage writes it back. This separates a genuinely blank
# GPU image from a broken GPU-to-guest swizzle/readback path.
old_download = '''        image.DownloadMemory(map, copies);
        runtime.Finish();
        SwizzleImage(*gpu_memory, image.gpu_addr, image.info, copies, map.mapped_span,
                     swizzle_data_buffer);
'''
new_download = '''        image.DownloadMemory(map, copies);
        runtime.Finish();

        static u32 v23_staging_diag_count{};
        if (v21_force_framebuffer_download && v23_staging_diag_count < 24) {
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
                        "V23_DIAG GPU staging sample={} image_cpu={:#x} image_gpu={:#x} format={} size={}x{} mapped_bytes={} nonzero={} hash={:#x}",
                        v23_staging_diag_count, image.cpu_addr, image.gpu_addr,
                        static_cast<u32>(image.info.format), image.info.size.width,
                        image.info.size.height, sample_size, nonzero, hash);
            ++v23_staging_diag_count;
        }

        SwizzleImage(*gpu_memory, image.gpu_addr, image.info, copies, map.mapped_span,
                     swizzle_data_buffer);
'''
replace_once(path, old_download, new_download, "hash downloaded Vulkan framebuffer staging data")

# Log every candidate considered by the display lookup. If the downloaded staging image is zero,
# this tells us whether the compositor selected the only matching image or chose among aliases.
old_candidates = '''    const auto view_format = [&]() {
'''
new_candidates = '''    static u32 v23_candidate_diag_count{};
    const bool v23_display_size =
        (config.width == 1280 && config.height == 720 && config.stride == 1280) ||
        (config.width == 1920 && config.height == 1080 && config.stride == 1920);
    if (v23_display_size && v23_candidate_diag_count < 24) {
        LOG_WARNING(HW_GPU,
                    "V23_DIAG framebuffer lookup cpu={:#x} candidates={} size={}x{} stride={} format={}",
                    cpu_addr, valid_image_ids.size(), config.width, config.height, config.stride,
                    static_cast<u32>(config.pixel_format));
        for (const ImageId image_id : valid_image_ids) {
            const ImageBase& candidate = slot_images[image_id];
            LOG_WARNING(HW_GPU,
                        "V23_DIAG candidate id={} cpu={:#x} gpu={:#x} flags={:#x} tick={} guest={:#x} unswizzled={:#x} format={} size={}x{} samples={} views={}",
                        image_id.value, candidate.cpu_addr, candidate.gpu_addr,
                        static_cast<u32>(candidate.flags), candidate.modification_tick,
                        candidate.guest_size_bytes, candidate.unswizzled_size_bytes,
                        static_cast<u32>(candidate.info.format), candidate.info.size.width,
                        candidate.info.size.height, candidate.info.num_samples,
                        candidate.image_view_ids.size());
        }
        ++v23_candidate_diag_count;
    }

    const auto view_format = [&]() {
'''
replace_once(path, old_candidates, new_candidates, "log framebuffer image candidates")
