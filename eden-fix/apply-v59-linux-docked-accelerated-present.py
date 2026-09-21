#!/usr/bin/env python3
from pathlib import Path

def rep(path, old, new, label):
    p = Path(path)
    s = p.read_text()
    count = s.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 match, found {count}")
    p.write_text(s.replace(old, new, 1))
    print(label)

rep(
    "src/video_core/renderer_vulkan/present/layer.cpp",
    """    static u32 v20_display_count{};
    const bool v20_minecraft_framebuffer =
        ((framebuffer.width == 1920 && framebuffer.height == 1080 &&
          framebuffer.stride == 1920) ||
         (framebuffer.width == 1280 && framebuffer.height == 720 &&
          framebuffer.stride == 1280)) &&
        framebuffer.pixel_format == Service::android::PixelFormat::Rgba8888;
    if (v20_minecraft_framebuffer) {
""",
    """    static u32 v20_display_count{};
    const bool v59_minecraft_docked_framebuffer =
        framebuffer.width == 1920 && framebuffer.height == 1080 &&
        framebuffer.stride == 1920 &&
        framebuffer.pixel_format == Service::android::PixelFormat::Rgba8888;

    // Preserve the known-good Handheld raw-display compatibility path, but retire the old
    // forced raw path for Docked 1920x1080. If AccelerateDisplay is unavailable, Eden's normal
    // !use_accelerated fallback below still uploads the raw framebuffer.
    const bool v20_minecraft_framebuffer =
        framebuffer.width == 1280 && framebuffer.height == 720 &&
        framebuffer.stride == 1280 &&
        framebuffer.pixel_format == Service::android::PixelFormat::Rgba8888;

    static u32 v59_docked_present_diag_count{};
    if (v59_minecraft_docked_framebuffer && v59_docked_present_diag_count < 120) {
        LOG_WARNING(Render_Vulkan,
                    "V59_FIX DockedAcceleratedPresent frame={} accelerated={} address={:#x} "
                    "size={}x{} stride={}",
                    v59_docked_present_diag_count, texture_info.has_value(),
                    framebuffer.address + framebuffer.offset, framebuffer.width,
                    framebuffer.height, framebuffer.stride);
        ++v59_docked_present_diag_count;
    }

    if (v20_minecraft_framebuffer) {
""",
    "retire legacy v20 raw-display fallback only for Docked 1920x1080",
)

print("applied v59 Docked accelerated presentation restore")
