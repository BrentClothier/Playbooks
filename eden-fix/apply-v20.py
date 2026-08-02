#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))
    print(f"updated {path}: {label}")


path = Path("src/video_core/renderer_vulkan/present/layer.cpp")

# Minecraft 1.26.32 reaches the display compositor with valid 1920x1080 RGBA framebuffer
# handles and addresses, but the accelerated display path still presents black. For this
# experimental build, flush that framebuffer back to guest memory and use Eden's existing raw
# framebuffer upload path. This also logs a small sample hash so we can distinguish an all-black
# guest framebuffer from a bad accelerated presentation image.
old_configure = '''    const auto texture_info = rasterizer.AccelerateDisplay(
        framebuffer, framebuffer.address + framebuffer.offset, framebuffer.stride);
    const u32 texture_width = texture_info ? texture_info->width : framebuffer.width;
'''
new_configure = '''    auto texture_info = rasterizer.AccelerateDisplay(
        framebuffer, framebuffer.address + framebuffer.offset, framebuffer.stride);

    static u32 v20_display_count{};
    const bool v20_minecraft_framebuffer =
        framebuffer.width == 1920 && framebuffer.height == 1080 &&
        framebuffer.stride == 1920 &&
        framebuffer.pixel_format == Service::android::PixelFormat::Rgba8888;
    if (v20_minecraft_framebuffer) {
        if (v20_display_count < 120) {
            LOG_WARNING(Render_Vulkan,
                        "V20_COMPAT display frame={} accelerated={} address={:#x} size={}x{} stride={}",
                        v20_display_count, texture_info.has_value(),
                        framebuffer.address + framebuffer.offset, framebuffer.width,
                        framebuffer.height, framebuffer.stride);
        }

        if (texture_info) {
            const DAddr framebuffer_addr = framebuffer.address + framebuffer.offset;
            const u64 framebuffer_size = GetSizeInBytes(framebuffer);
            rasterizer.FlushRegion(framebuffer_addr, framebuffer_size);
            scheduler.Finish();
            texture_info.reset();
        }
        ++v20_display_count;
    }

    const u32 texture_width = texture_info ? texture_info->width : framebuffer.width;
'''
replace_once(path, old_configure, new_configure, "force raw Minecraft display fallback")

old_pointer = '''    const u8* const host_ptr = device_memory.GetPointer<u8>(framebuffer_addr);

    // TODO(Rodrigo): Read this from HLE
'''
new_pointer = '''    const u8* const host_ptr = device_memory.GetPointer<u8>(framebuffer_addr);

    // TODO(Rodrigo): Read this from HLE
'''
# Keep this anchor replacement as a structural check before inserting diagnostics below.
replace_once(path, old_pointer, new_pointer, "verify raw framebuffer pointer anchor")

old_sizes = '''    const u64 tiled_size{Tegra::Texture::CalculateSize(
        true, bytes_per_pixel, framebuffer.stride, framebuffer.height, 1, block_height_log2, 0)};
    if (host_ptr) {
'''
new_sizes = '''    const u64 tiled_size{Tegra::Texture::CalculateSize(
        true, bytes_per_pixel, framebuffer.stride, framebuffer.height, 1, block_height_log2, 0)};

    static u32 v20_raw_sample_count{};
    if (host_ptr && framebuffer.width == 1920 && framebuffer.height == 1080 &&
        framebuffer.stride == 1920 &&
        framebuffer.pixel_format == Service::android::PixelFormat::Rgba8888 &&
        v20_raw_sample_count < 120) {
        const u64 sample_size = (std::min)(tiled_size, u64{65536});
        u64 hash = 1469598103934665603ULL;
        u64 nonzero = 0;
        for (u64 i = 0; i < sample_size; ++i) {
            const u8 value = host_ptr[i];
            hash ^= value;
            hash *= 1099511628211ULL;
            nonzero += value != 0;
        }
        LOG_WARNING(Render_Vulkan,
                    "V20_DIAG raw framebuffer sample={} address={:#x} bytes={} nonzero={} hash={:#x}",
                    v20_raw_sample_count, framebuffer_addr, sample_size, nonzero, hash);
        ++v20_raw_sample_count;
    } else if (!host_ptr && framebuffer.width == 1920 && framebuffer.height == 1080 &&
               framebuffer.stride == 1920 &&
               framebuffer.pixel_format == Service::android::PixelFormat::Rgba8888 &&
               v20_raw_sample_count < 120) {
        LOG_WARNING(Render_Vulkan,
                    "V20_DIAG raw framebuffer sample={} address={:#x} has null host pointer",
                    v20_raw_sample_count, framebuffer_addr);
        ++v20_raw_sample_count;
    }

    if (host_ptr) {
'''
replace_once(path, old_sizes, new_sizes, "sample raw Minecraft framebuffer memory")
