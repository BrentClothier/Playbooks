#!/usr/bin/env python3
from pathlib import Path


def replace_once(path, old, new, label):
    p = Path(path)
    text = p.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 match in {path}, found {count}")
    p.write_text(text.replace(old, new, 1))
    print(f"updated {path}: {label}")


path = "src/video_core/renderer_vulkan/vk_rasterizer.cpp"

replace_once(
    path,
    """    const auto& v53_scissor = regs.scissor_test[0];
    const bool v53_minecraft_half_screen_clear =
        VideoCommon::MinecraftSplitScreenDiagnosticsActive() && render_area.width == 1280 &&
        render_area.height == 720 && static_cast<u32>(v53_scissor.enable) != 0 &&
        static_cast<u32>(v53_scissor.min_x) == 0 &&
        static_cast<u32>(v53_scissor.max_x) == 1280 &&
        ((static_cast<u32>(v53_scissor.min_y) == 0 &&
          static_cast<u32>(v53_scissor.max_y) == 360) ||
         (static_cast<u32>(v53_scissor.min_y) == 360 &&
          static_cast<u32>(v53_scissor.max_y) == 720));
    const bool v53_effective_use_scissor =
        regs.clear_control.use_scissor || v53_minecraft_half_screen_clear;
""",
    """    const auto& v53_scissor = regs.scissor_test[0];
    const bool v53_minecraft_half_screen_clear =
        VideoCommon::MinecraftSplitScreenDiagnosticsActive() && render_area.width == 1280 &&
        render_area.height == 720 && static_cast<u32>(v53_scissor.enable) != 0 &&
        static_cast<u32>(v53_scissor.min_x) == 0 &&
        static_cast<u32>(v53_scissor.max_x) == 1280 &&
        ((static_cast<u32>(v53_scissor.min_y) == 0 &&
          static_cast<u32>(v53_scissor.max_y) == 360) ||
         (static_cast<u32>(v53_scissor.min_y) == 360 &&
          static_cast<u32>(v53_scissor.max_y) == 720));

    const bool v56_minecraft_docked_half_screen_clear =
        VideoCommon::MinecraftSplitScreenDiagnosticsActive() && render_area.width == 1920 &&
        render_area.height == 1080 && static_cast<u32>(v53_scissor.enable) != 0 &&
        static_cast<u32>(v53_scissor.min_x) == 0 &&
        static_cast<u32>(v53_scissor.max_x) == 1920 &&
        ((static_cast<u32>(v53_scissor.min_y) == 0 &&
          static_cast<u32>(v53_scissor.max_y) == 540) ||
         (static_cast<u32>(v53_scissor.min_y) == 540 &&
          static_cast<u32>(v53_scissor.max_y) == 1080));
    const bool v56_minecraft_half_screen_clear =
        v53_minecraft_half_screen_clear || v56_minecraft_docked_half_screen_clear;
    const bool v56_effective_use_scissor =
        regs.clear_control.use_scissor || v56_minecraft_half_screen_clear;
""",
    "add Docked 1080p half-screen clear predicate while preserving v53",
)

replace_once(
    path,
    """    const bool can_defer_clear = ENABLE_DEFERRED_CLEAR && !v53_effective_use_scissor &&
""",
    """    const bool can_defer_clear = ENABLE_DEFERRED_CLEAR && !v56_effective_use_scissor &&
""",
    "use combined handheld/docked clear predicate for deferred clears",
)

replace_once(
    path,
    """        .rect = v53_effective_use_scissor ? GetScissorState(regs, 0, up_scale, down_shift)
                                          : default_scissor,
""",
    """        .rect = v56_effective_use_scissor ? GetScissorState(regs, 0, up_scale, down_shift)
                                          : default_scissor,
""",
    "use combined handheld/docked clear predicate for clear rect",
)

replace_once(
    path,
    """    static u32 v51_clear_decision_diag_count{};
""",
    """    if (v56_minecraft_docked_half_screen_clear && !regs.clear_control.use_scissor) {
        static u32 v56_docked_half_screen_clear_count{};
        if (v56_docked_half_screen_clear_count < 120) {
            LOG_WARNING(Render_Vulkan,
                        "V56_FIX DockedHalfScreenClearCompat count={} generation={} "
                        "render_area={}x{} control=(clear_rect={},scissor={},viewport_clip0={}) "
                        "reg_scissor=({},{},{},{},{}) clear_rect=({},{},{}x{}) rt0_addr={:#x}",
                        v56_docked_half_screen_clear_count,
                        VideoCommon::MinecraftSplitScreenDiagnosticsGeneration(),
                        render_area.width, render_area.height,
                        static_cast<u32>(regs.clear_control.use_clear_rect),
                        static_cast<u32>(regs.clear_control.use_scissor),
                        static_cast<u32>(regs.clear_control.use_viewport_clip0),
                        static_cast<u32>(v53_scissor.enable), static_cast<u32>(v53_scissor.min_x),
                        static_cast<u32>(v53_scissor.min_y), static_cast<u32>(v53_scissor.max_x),
                        static_cast<u32>(v53_scissor.max_y), clear_rect.rect.offset.x,
                        clear_rect.rect.offset.y, clear_rect.rect.extent.width,
                        clear_rect.rect.extent.height, regs.rt[0].Address());
            ++v56_docked_half_screen_clear_count;
        }
    }

    static u32 v51_clear_decision_diag_count{};
""",
    "log limited Docked compatibility activations",
)

print("applied v56 Minecraft Docked 1920x1080 half-screen clear compatibility")
