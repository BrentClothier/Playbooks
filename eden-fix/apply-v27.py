#!/usr/bin/env python3
from pathlib import Path

# V26 proved that clamping the invalid 16384x16384 framebuffer to its 1280x720 attachment is not
# sufficient: the exact scanout image is still all zeroes after the fullscreen draw. Source tracing
# found a separate cache-correctness defect. PositionPass generates different vertex shader code
# depending on viewport_scale_offset_enabled, but GraphicsPipelineCacheKey does not include that
# mode. With EDS1+EDS2, triangle and triangle-strip topologies are also collapsed to the same key
# class, making reuse across these passes particularly plausible. Add the mode to a free bit in the
# fixed pipeline key and bump the disk-cache version so stale variants cannot be reused.

header_path = Path("src/video_core/renderer_vulkan/fixed_pipeline_state.h")
header_text = header_path.read_text()

old_field = '''        BitField<17, 3, Tegra::Engines::Maxwell3D::EngineHint> app_stage;
'''
new_field = '''        BitField<17, 3, Tegra::Engines::Maxwell3D::EngineHint> app_stage;
        // PositionPass emits different vertex code for this mode, so it must be part of the key.
        BitField<20, 1, u32> viewport_transform_enabled;
'''
count = header_text.count(old_field)
if count != 1:
    raise RuntimeError(f"add viewport-transform key bit: expected one match, found {count}")
header_path.write_text(header_text.replace(old_field, new_field, 1))
print(f"updated {header_path}: key viewport transform mode")

state_path = Path("src/video_core/renderer_vulkan/fixed_pipeline_state.cpp")
state_text = state_path.read_text()

old_assign = '''    alpha_to_one_enabled.Assign(regs.anti_alias_alpha_control.alpha_to_one != 0 ? 1 : 0);
    app_stage.Assign(maxwell3d.engine_state);

    depth_bounds_min = static_cast<u32>(regs.depth_bounds[0]);
'''
new_assign = '''    alpha_to_one_enabled.Assign(regs.anti_alias_alpha_control.alpha_to_one != 0 ? 1 : 0);
    app_stage.Assign(maxwell3d.engine_state);
    viewport_transform_enabled.Assign(regs.viewport_scale_offset_enabled != 0 ? 1 : 0);

    depth_bounds_min = static_cast<u32>(regs.depth_bounds[0]);
'''
count = state_text.count(old_assign)
if count != 1:
    raise RuntimeError(f"populate viewport-transform key bit: expected one match, found {count}")
state_path.write_text(state_text.replace(old_assign, new_assign, 1))
print(f"updated {state_path}: populate viewport transform mode in pipeline key")

cache_path = Path("src/video_core/renderer_vulkan/vk_pipeline_cache.cpp")
cache_text = cache_path.read_text()

old_version = "constexpr u32 CACHE_VERSION = 18;"
new_version = "constexpr u32 CACHE_VERSION = 19;"
count = cache_text.count(old_version)
if count != 1:
    raise RuntimeError(f"bump Vulkan cache version: expected one match, found {count}")
cache_text = cache_text.replace(old_version, new_version, 1)

old_refresh = '''    graphics_key.state.Refresh(*maxwell3d, dynamic_features);

    if (current_pipeline) {
'''
new_refresh = '''    graphics_key.state.Refresh(*maxwell3d, dynamic_features);

    static u32 v27_pipeline_key_diag_count{};
    if (v27_pipeline_key_diag_count < 240) {
        LOG_WARNING(Render_Vulkan,
                    "V27_FIX PipelineKey count={} hash={:#x} viewport_transform={} topology={} vertex_b={:#x} fragment={:#x}",
                    v27_pipeline_key_diag_count, graphics_key.Hash(),
                    graphics_key.state.viewport_transform_enabled.Value(),
                    static_cast<u32>(graphics_key.state.topology.Value()),
                    graphics_key.unique_hashes[1], graphics_key.unique_hashes[5]);
        ++v27_pipeline_key_diag_count;
    }

    if (current_pipeline) {
'''
count = cache_text.count(old_refresh)
if count != 1:
    raise RuntimeError(f"instrument viewport pipeline keys: expected one match, found {count}")
cache_path.write_text(cache_text.replace(old_refresh, new_refresh, 1))
print(f"updated {cache_path}: invalidate stale cache and log viewport-specific keys")
