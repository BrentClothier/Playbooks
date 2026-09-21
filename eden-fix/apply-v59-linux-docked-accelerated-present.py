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
    """    const bool v20_minecraft_framebuffer =
        framebuffer.width == 1920 && framebuffer.height == 1080 &&
        framebuffer.stride == 1920 &&
        framebuffer.pixel_format == Service::android::PixelFormat::Rgba8888;
    if (v20_minecraft_framebuffer) {
""",
    """    const bool v59_minecraft_docked_framebuffer =
        framebuffer.width == 1920 && framebuffer.height == 1080 &&
        framebuffer.stride == 1920 &&
        framebuffer.pixel_format == Service::android::PixelFormat::Rgba8888;

    // V20 was an early blank-screen diagnostic workaround. It synchronously downloaded every
    // Docked framebuffer, discarded the accelerated display image, and forced Eden's raw CPU
    // upload path. Later v26-v30 renderer fixes made the accelerated path functional, while the
    // V20 workaround remained active only at 1920x1080. Retire that legacy bypass so Docked uses
    // the same accelerated presentation path as the known-good Handheld mode.
    const bool v20_minecraft_framebuffer = false;

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
    "retire legacy v20 Docked raw-framebuffer fallback",
)

print("applied v59 Docked accelerated presentation restore")
