#!/usr/bin/env python3
from pathlib import Path

# V25 proved that Minecraft's final fullscreen draws target the exact three Nvnflinger scanout
# images. The scanout images are 1280x720, but Eden derives RenderTargets::size from the guest's
# 16384x16384 surface clip. Vulkan then creates a 16384x16384 VkFramebuffer around a 1280x720
# attachment, violating the framebuffer attachment extent requirements. The preceding offscreen
# passes use 1280x720 render areas and valid attachment extents. Clamp the framebuffer/render area
# to the smallest active attachment's actual host extent while leaving the guest viewport and
# scissor state untouched.

texture_path = Path("src/video_core/texture_cache/texture_cache.h")
texture_text = texture_path.read_text()

old_extent = '''    render_targets.size = Extent2D{
        (maxwell3d->regs.surface_clip.width * up_scale) >> down_shift,
        (maxwell3d->regs.surface_clip.height * up_scale) >> down_shift,
    };
    render_targets.is_rescaled = is_rescaling;
'''

new_extent = '''    render_targets.size = Extent2D{
        (maxwell3d->regs.surface_clip.width * up_scale) >> down_shift,
        (maxwell3d->regs.surface_clip.height * up_scale) >> down_shift,
    };

    // A Vulkan framebuffer cannot be larger than any attachment used by its render pass. Some
    // newer NVN command streams use a deliberately oversized surface clip (for example 16384x16384)
    // while binding a normal 1280x720 scanout image. Keep the guest viewport/scissor semantics, but
    // clamp the framebuffer and render area to the active attachments' real host extents.
    u32 attachment_width = (std::numeric_limits<u32>::max)();
    u32 attachment_height = (std::numeric_limits<u32>::max)();
    bool has_attachment = false;
    const auto clamp_to_attachment = [&](ImageViewId view_id) {
        if (!view_id) {
            return;
        }
        const ImageViewBase& view = slot_image_views[view_id];
        const ImageBase& image = slot_images[view.image_id];
        const auto [samples_x, samples_y] = SamplesLog2(image.info.num_samples);
        const u32 native_width = (std::max)(view.size.width >> samples_x, 1u);
        const u32 native_height = (std::max)(view.size.height >> samples_y, 1u);
        const u32 host_width = (std::max)((native_width * up_scale) >> down_shift, 1u);
        const u32 host_height = (std::max)((native_height * up_scale) >> down_shift, 1u);
        attachment_width = (std::min)(attachment_width, host_width);
        attachment_height = (std::min)(attachment_height, host_height);
        has_attachment = true;
    };
    for (const ImageViewId view_id : render_targets.color_buffer_ids) {
        clamp_to_attachment(view_id);
    }
    clamp_to_attachment(render_targets.depth_buffer_id);

    if (has_attachment &&
        (render_targets.size.width > attachment_width ||
         render_targets.size.height > attachment_height)) {
        static u32 v26_extent_clamp_diag_count{};
        if (v26_extent_clamp_diag_count < 120) {
            LOG_WARNING(HW_GPU,
                        "V26_FIX ClampFramebufferExtent count={} requested={}x{} attachment_limit={}x{} active_mask={:#x}",
                        v26_extent_clamp_diag_count, render_targets.size.width,
                        render_targets.size.height, attachment_width, attachment_height,
                        rt_active_mask);
            ++v26_extent_clamp_diag_count;
        }
        render_targets.size.width = (std::min)(render_targets.size.width, attachment_width);
        render_targets.size.height = (std::min)(render_targets.size.height, attachment_height);
    }
    render_targets.is_rescaled = is_rescaling;
'''

count = texture_text.count(old_extent)
if count != 1:
    raise RuntimeError(f"clamp framebuffer extent: expected one match, found {count}")

texture_path.write_text(texture_text.replace(old_extent, new_extent, 1))
print(f"updated {texture_path}: clamp framebuffer/render area to active attachment extents")
