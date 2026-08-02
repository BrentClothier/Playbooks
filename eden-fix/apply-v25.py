#!/usr/bin/env python3
from pathlib import Path

# V24 proved that Minecraft reaches Eden's direct Vulkan draw-recording path with a configured
# graphics pipeline. Its image-modification probe only wrapped MarkModification(ImageId), while
# normal color/depth render targets are marked through PrepareImageView -> PrepareImage ->
# MarkModification(ImageBase&). V25 logs the real bound render-target images and the guest draw
# state so we can distinguish offscreen rendering from draws that cannot write color.

texture_path = Path("src/video_core/texture_cache/texture_cache.h")
texture_text = texture_path.read_text()

old_update_start = '''template <class P>
void TextureCache<P>::UpdateRenderTargets(bool is_clear) {
    using namespace VideoCommon::Dirty;
    auto& flags = maxwell3d->dirty.flags;
    if (!flags[Dirty::RenderTargets]) {
'''
new_update_start = '''template <class P>
void TextureCache<P>::UpdateRenderTargets(bool is_clear) {
    using namespace VideoCommon::Dirty;
    auto& flags = maxwell3d->dirty.flags;
    static u32 v25_render_target_diag_count{};
    const auto v25_log_render_targets = [&](const char* phase) {
        if (v25_render_target_diag_count >= 240) {
            return;
        }
        const u32 call = v25_render_target_diag_count++;
        LOG_WARNING(HW_GPU,
                    "V25_DIAG RenderTargets call={} phase={} serial={} active_mask={:#x} surface={}x{} rescaled={}",
                    call, phase, render_targets_serial, rt_active_mask, render_targets.size.width,
                    render_targets.size.height, render_targets.is_rescaled);
        for (size_t index = 0; index < NUM_RT; ++index) {
            const ImageViewId view_id = render_targets.color_buffer_ids[index];
            if (!view_id) {
                continue;
            }
            const ImageId image_id = slot_image_views[view_id].image_id;
            const ImageBase& image = slot_images[image_id];
            LOG_WARNING(HW_GPU,
                        "V25_DIAG ColorTarget call={} slot={} draw_buffer={} view={} image={} cpu={:#x} gpu={:#x} format={} type={} size={}x{}x{} samples={} guest={:#x} unswizzled={:#x} gpu_modified={} tick={} flags={:#x}",
                        call, index, static_cast<u32>(render_targets.draw_buffers[index]),
                        view_id.Value(), image_id.Value(), image.cpu_addr, image.gpu_addr,
                        static_cast<u32>(image.info.format), static_cast<u32>(image.info.type),
                        image.info.size.width, image.info.size.height, image.info.size.depth,
                        image.info.num_samples, image.guest_size_bytes, image.unswizzled_size_bytes,
                        True(image.flags & ImageFlagBits::GpuModified), image.modification_tick,
                        static_cast<u32>(image.flags));
        }
        const ImageViewId depth_view_id = render_targets.depth_buffer_id;
        if (depth_view_id) {
            const ImageId image_id = slot_image_views[depth_view_id].image_id;
            const ImageBase& image = slot_images[image_id];
            LOG_WARNING(HW_GPU,
                        "V25_DIAG DepthTarget call={} view={} image={} cpu={:#x} gpu={:#x} format={} type={} size={}x{}x{} samples={} guest={:#x} unswizzled={:#x} gpu_modified={} tick={} flags={:#x}",
                        call, depth_view_id.Value(), image_id.Value(), image.cpu_addr,
                        image.gpu_addr, static_cast<u32>(image.info.format),
                        static_cast<u32>(image.info.type), image.info.size.width,
                        image.info.size.height, image.info.size.depth, image.info.num_samples,
                        image.guest_size_bytes, image.unswizzled_size_bytes,
                        True(image.flags & ImageFlagBits::GpuModified), image.modification_tick,
                        static_cast<u32>(image.flags));
        }
    };
    if (!flags[Dirty::RenderTargets]) {
'''

count = texture_text.count(old_update_start)
if count != 1:
    raise RuntimeError(f"instrument UpdateRenderTargets start: expected one match, found {count}")
texture_text = texture_text.replace(old_update_start, new_update_start, 1)

old_reuse_return = '''        const ImageViewId depth_buffer_id = render_targets.depth_buffer_id;
        PrepareImageView(depth_buffer_id, true, is_clear && IsFullClear(depth_buffer_id));
        return;
    }
'''
new_reuse_return = '''        const ImageViewId depth_buffer_id = render_targets.depth_buffer_id;
        PrepareImageView(depth_buffer_id, true, is_clear && IsFullClear(depth_buffer_id));
        v25_log_render_targets("reuse");
        return;
    }
'''

count = texture_text.count(old_reuse_return)
if count != 1:
    raise RuntimeError(f"instrument reused render targets: expected one match, found {count}")
texture_text = texture_text.replace(old_reuse_return, new_reuse_return, 1)

old_update_end = '''    if (render_targets != previous_render_targets) {
        ++render_targets_serial;
    }

    flags[Dirty::DepthBiasGlobal] = true;
}
'''
new_update_end = '''    if (render_targets != previous_render_targets) {
        ++render_targets_serial;
    }

    v25_log_render_targets("rebuild");
    flags[Dirty::DepthBiasGlobal] = true;
}
'''

count = texture_text.count(old_update_end)
if count != 1:
    raise RuntimeError(f"instrument rebuilt render targets: expected one match, found {count}")
texture_path.write_text(texture_text.replace(old_update_end, new_update_end, 1))
print(f"updated {texture_path}: log actual color/depth render-target images")

raster_path = Path("src/video_core/renderer_vulkan/vk_rasterizer.cpp")
raster_text = raster_path.read_text()

old_configured = '''    if (v24_prepare_call < 240) {
        LOG_WARNING(Render_Vulkan,
                    "V24_DIAG PrepareDraw call={} indexed={} result=configured",
                    v24_prepare_call, is_indexed);
    }

    UpdateDynamicStates();
'''
new_configured = '''    if (v24_prepare_call < 240) {
        LOG_WARNING(Render_Vulkan,
                    "V24_DIAG PrepareDraw call={} indexed={} result=configured",
                    v24_prepare_call, is_indexed);
        const auto& v25_regs = maxwell3d->regs;
        const auto& v25_color0 = v25_regs.color_mask[0];
        LOG_WARNING(Render_Vulkan,
                    "V25_DIAG DrawState call={} rasterize={} topology={} clip=({},{} {}x{}) viewport_scale_offset={} rt_count={} rt0_addr={:#x} rt0_format={} color0_rgba={}{}{}{} depth_test={} depth_write={} stencil={} transform_feedback={}",
                    v24_prepare_call, static_cast<u32>(v25_regs.rasterize_enable),
                    static_cast<u32>(maxwell3d->draw_manager.draw_state.topology),
                    static_cast<u32>(v25_regs.surface_clip.x),
                    static_cast<u32>(v25_regs.surface_clip.y),
                    static_cast<u32>(v25_regs.surface_clip.width),
                    static_cast<u32>(v25_regs.surface_clip.height),
                    static_cast<u32>(v25_regs.viewport_scale_offset_enabled),
                    static_cast<u32>(v25_regs.rt_control.count), v25_regs.rt[0].Address(),
                    static_cast<u32>(v25_regs.rt[0].format),
                    static_cast<u32>(v25_color0.R), static_cast<u32>(v25_color0.G),
                    static_cast<u32>(v25_color0.B), static_cast<u32>(v25_color0.A),
                    static_cast<u32>(v25_regs.depth_test_enable),
                    static_cast<u32>(v25_regs.depth_write_enabled),
                    static_cast<u32>(v25_regs.stencil_enable),
                    static_cast<u32>(v25_regs.transform_feedback_enabled));
    }

    UpdateDynamicStates();
'''

count = raster_text.count(old_configured)
if count != 1:
    raise RuntimeError(f"instrument draw state: expected one match, found {count}")
raster_path.write_text(raster_text.replace(old_configured, new_configured, 1))
print(f"updated {raster_path}: log rasterization and color-write state")
