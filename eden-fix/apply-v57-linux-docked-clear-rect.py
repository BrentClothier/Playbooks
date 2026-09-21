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


replace_once(
    "src/video_core/renderer_vulkan/vk_rasterizer.h",
    """    boost::container::static_vector<VkSampler, MAX_TEXTURES> sampler_handles;

    u32 draw_counter = 0;
""",
    """    boost::container::static_vector<VkSampler, MAX_TEXTURES> sampler_handles;

    bool v57_minecraft_title_active = false;
    u32 draw_counter = 0;
""",
    "track Minecraft title for Docked clear-rectangle compatibility",
)

replace_once(
    "src/video_core/renderer_vulkan/vk_rasterizer.cpp",
    """void RasterizerVulkan::LoadDiskResources(u64 title_id, std::stop_token stop_loading,
                                         const VideoCore::DiskResourceLoadCallback& callback) {
    pipeline_cache.LoadDiskResources(title_id, stop_loading, callback);
}
""",
    """void RasterizerVulkan::LoadDiskResources(u64 title_id, std::stop_token stop_loading,
                                         const VideoCore::DiskResourceLoadCallback& callback) {
    v57_minecraft_title_active = title_id == 0x0100D71004694000ULL;
    if (v57_minecraft_title_active) {
        LOG_WARNING(Render_Vulkan,
                    "V57_DIAG MinecraftDockedClearRectCompatActive title_id={:#x}", title_id);
    }
    pipeline_cache.LoadDiskResources(title_id, stop_loading, callback);
}
""",
    "activate title-specific Docked clear-rectangle compatibility",
)

replace_once(
    "src/video_core/renderer_vulkan/vk_rasterizer.cpp",
    """    const bool v56_minecraft_half_screen_clear =
        v53_minecraft_half_screen_clear || v56_minecraft_docked_half_screen_clear;
    const bool v56_effective_use_scissor =
        regs.clear_control.use_scissor || v56_minecraft_half_screen_clear;

    constexpr bool ENABLE_DEFERRED_CLEAR = true;
""",
    """    const bool v56_minecraft_half_screen_clear =
        v53_minecraft_half_screen_clear || v56_minecraft_docked_half_screen_clear;
    const bool v56_effective_use_scissor =
        regs.clear_control.use_scissor || v56_minecraft_half_screen_clear;

    const bool v57_minecraft_docked_clear_rect =
        v57_minecraft_title_active && render_area.width == 1920 && render_area.height == 1080 &&
        static_cast<u32>(regs.clear_control.use_clear_rect) != 0;
    const bool v57_effective_partial_clear =
        v56_effective_use_scissor || v57_minecraft_docked_clear_rect;

    constexpr bool ENABLE_DEFERRED_CLEAR = true;
""",
    "recognize actual Maxwell clear-rectangle use in Minecraft Docked mode",
)

replace_once(
    "src/video_core/renderer_vulkan/vk_rasterizer.cpp",
    """    const bool can_defer_clear = ENABLE_DEFERRED_CLEAR && !v56_effective_use_scissor &&
""",
    """    const bool can_defer_clear = ENABLE_DEFERRED_CLEAR && !v57_effective_partial_clear &&
""",
    "prevent deferred full clear for Minecraft Docked clear rectangles",
)

replace_once(
    "src/video_core/renderer_vulkan/vk_rasterizer.cpp",
    """    VkClearRect clear_rect{
        .rect = v56_effective_use_scissor ? GetScissorState(regs, 0, up_scale, down_shift)
                                          : default_scissor,
        .baseArrayLayer = regs.clear_surface.layer,
        .layerCount = layer_count,
    };
""",
    """    VkRect2D selected_clear_rect =
        v56_effective_use_scissor ? GetScissorState(regs, 0, up_scale, down_shift)
                                  : default_scissor;

    if (v57_minecraft_docked_clear_rect) {
        const u32 guest_x_min = static_cast<u32>(regs.clear_rect.x_min);
        const u32 guest_x_max = static_cast<u32>(regs.clear_rect.x_max);
        const u32 guest_y_min = static_cast<u32>(regs.clear_rect.y_min);
        const u32 guest_y_max = static_cast<u32>(regs.clear_rect.y_max);
        const auto scale_coord = [up_scale, down_shift](u32 value) -> s32 {
            return static_cast<s32>((static_cast<u64>(value) * up_scale) >> down_shift);
        };

        selected_clear_rect.offset.x = scale_coord(guest_x_min);
        selected_clear_rect.offset.y = scale_coord(guest_y_min);
        selected_clear_rect.extent.width =
            guest_x_max > guest_x_min
                ? static_cast<u32>(scale_coord(guest_x_max) - selected_clear_rect.offset.x)
                : 0;
        selected_clear_rect.extent.height =
            guest_y_max > guest_y_min
                ? static_cast<u32>(scale_coord(guest_y_max) - selected_clear_rect.offset.y)
                : 0;

        if (regs.clear_control.use_scissor && static_cast<u32>(v53_scissor.enable) != 0) {
            const VkRect2D guest_scissor = GetScissorState(regs, 0, up_scale, down_shift);
            const s64 clear_left = selected_clear_rect.offset.x;
            const s64 clear_top = selected_clear_rect.offset.y;
            const s64 clear_right = clear_left + selected_clear_rect.extent.width;
            const s64 clear_bottom = clear_top + selected_clear_rect.extent.height;
            const s64 scissor_left = guest_scissor.offset.x;
            const s64 scissor_top = guest_scissor.offset.y;
            const s64 scissor_right = scissor_left + guest_scissor.extent.width;
            const s64 scissor_bottom = scissor_top + guest_scissor.extent.height;
            const s64 left = (std::max)(clear_left, scissor_left);
            const s64 top = (std::max)(clear_top, scissor_top);
            const s64 right = (std::min)(clear_right, scissor_right);
            const s64 bottom = (std::min)(clear_bottom, scissor_bottom);
            selected_clear_rect.offset.x = static_cast<s32>(left);
            selected_clear_rect.offset.y = static_cast<s32>(top);
            selected_clear_rect.extent.width =
                right > left ? static_cast<u32>(right - left) : 0;
            selected_clear_rect.extent.height =
                bottom > top ? static_cast<u32>(bottom - top) : 0;
        }
    }

    VkClearRect clear_rect{
        .rect = selected_clear_rect,
        .baseArrayLayer = regs.clear_surface.layer,
        .layerCount = layer_count,
    };

    if (v57_minecraft_title_active && render_area.width == 1920 && render_area.height == 1080) {
        static u32 v57_docked_clear_diag_count{};
        if (v57_docked_clear_diag_count < 160) {
            LOG_WARNING(
                Render_Vulkan,
                "V57_DIAG DockedClear count={} control=(clear_rect={},scissor={},viewport_clip0={}) "
                "hw_clear_rect=({},{})-({},{}) reg_scissor=({},{},{},{},{}) "
                "selected=({},{},{}x{}) rt0_addr={:#x}",
                v57_docked_clear_diag_count,
                static_cast<u32>(regs.clear_control.use_clear_rect),
                static_cast<u32>(regs.clear_control.use_scissor),
                static_cast<u32>(regs.clear_control.use_viewport_clip0),
                static_cast<u32>(regs.clear_rect.x_min), static_cast<u32>(regs.clear_rect.y_min),
                static_cast<u32>(regs.clear_rect.x_max), static_cast<u32>(regs.clear_rect.y_max),
                static_cast<u32>(v53_scissor.enable), static_cast<u32>(v53_scissor.min_x),
                static_cast<u32>(v53_scissor.min_y), static_cast<u32>(v53_scissor.max_x),
                static_cast<u32>(v53_scissor.max_y), clear_rect.rect.offset.x,
                clear_rect.rect.offset.y, clear_rect.rect.extent.width,
                clear_rect.rect.extent.height, regs.rt[0].Address());
            ++v57_docked_clear_diag_count;
        }
    }

    if (v57_minecraft_docked_clear_rect) {
        static u32 v57_docked_clear_fix_count{};
        if (v57_docked_clear_fix_count < 160) {
            LOG_WARNING(Render_Vulkan,
                        "V57_FIX DockedClearRect count={} guest=({},{})-({},{}) "
                        "effective=({},{},{}x{})",
                        v57_docked_clear_fix_count,
                        static_cast<u32>(regs.clear_rect.x_min),
                        static_cast<u32>(regs.clear_rect.y_min),
                        static_cast<u32>(regs.clear_rect.x_max),
                        static_cast<u32>(regs.clear_rect.y_max),
                        clear_rect.rect.offset.x, clear_rect.rect.offset.y,
                        clear_rect.rect.extent.width, clear_rect.rect.extent.height);
            ++v57_docked_clear_fix_count;
        }
    }
""",
    "honor Maxwell CLEAR_RECT for Minecraft Docked and trace actual geometry",
)

print("applied v57 Minecraft Docked Maxwell clear-rectangle semantics")
