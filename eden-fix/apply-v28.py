#!/usr/bin/env python3
from pathlib import Path

# V27 successfully separated viewport-transform pipeline variants and invalidated the old cache,
# but every presented 1280x720 Vulkan image still downloaded as all zeroes. V28 performs a binary
# render-pass probe: after Minecraft's characteristic 4-vertex scanout draw, clear the active color
# attachment to magenta. If magenta reaches the screen/staging download, attachment writes and the
# presentation path are healthy and the failure is inside the guest draw (geometry/shader/source
# texture). It also logs the scanout pipeline's shader metadata and bound image descriptors.

graphics_path = Path("src/video_core/renderer_vulkan/vk_graphics_pipeline.cpp")
graphics_text = graphics_path.read_text()

old_fill = '''    texture_cache.FillImageViews(std::span(views.data(), views.size()), false, Spec::has_images);

    VideoCommon::ImageViewInOut* texture_buffer_it{views.data()};
'''
new_fill = '''    texture_cache.FillImageViews(std::span(views.data(), views.size()), false, Spec::has_images);

    const bool v28_window_space_draw =
        regs.viewport_scale_offset_enabled == 0 && regs.surface_clip.width >= 16384 &&
        regs.surface_clip.height >= 16384 && regs.rt_control.count == 1;
    static u32 v28_pipeline_diag_count{};
    if (v28_window_space_draw && v28_pipeline_diag_count < 64) {
        const u32 v28_call = v28_pipeline_diag_count++;
        const Shader::Info& vertex_info = stage_infos[0];
        const Shader::Info& fragment_info = stage_infos[NUM_STAGES - 1];
        LOG_WARNING(Render_Vulkan,
                    "V28_DIAG ScanoutPipeline call={} key={:#x} rt0={:#x} views={} samplers={} descriptor_entries={} vertex_render_area={} fragment_color0={} fragment_depth={} fragment_demote={} fragment_textures={} fragment_images={}",
                    v28_call, key.Hash(), regs.rt[0].Address(), views.size(), samplers.size(),
                    num_descriptor_entries, vertex_info.uses_render_area,
                    fragment_info.stores_frag_color[0], fragment_info.stores_frag_depth,
                    fragment_info.uses_demote_to_helper_invocation,
                    Shader::NumDescriptors(fragment_info.texture_descriptors),
                    Shader::NumDescriptors(fragment_info.image_descriptors));
        for (size_t index = 0; index < views.size(); ++index) {
            const auto& entry = views[index];
            if (!entry.id) {
                LOG_WARNING(Render_Vulkan,
                            "V28_DIAG BoundImage call={} index={} descriptor={} view=null blacklist={}",
                            v28_call, index, entry.index, entry.blacklist);
                continue;
            }
            ImageView& image_view = texture_cache.GetImageView(entry.id);
            const bool is_buffer = image_view.IsBuffer();
            const u32 samples = is_buffer ? 0U : static_cast<u32>(image_view.Samples());
            const bool is_rescaled = texture_cache.IsRescaling(image_view);
            LOG_WARNING(Render_Vulkan,
                        "V28_DIAG BoundImage call={} index={} descriptor={} view={} image={} gpu={:#x} format={} type={} size={}x{}x{} samples={} rescaled={} buffer={} blacklist={}",
                        v28_call, index, entry.index, entry.id.Value(),
                        image_view.image_id.Value(), image_view.GpuAddr(),
                        static_cast<u32>(image_view.format), static_cast<u32>(image_view.type),
                        image_view.size.width, image_view.size.height, image_view.size.depth,
                        samples, is_rescaled, is_buffer, entry.blacklist);
        }
        for (size_t index = 0; index < samplers.size(); ++index) {
            LOG_WARNING(Render_Vulkan, "V28_DIAG BoundSampler call={} index={} sampler={}",
                        v28_call, index, samplers[index].Value());
        }
    }

    VideoCommon::ImageViewInOut* texture_buffer_it{views.data()};
'''

count = graphics_text.count(old_fill)
if count != 1:
    raise RuntimeError(f"instrument scanout descriptors: expected one match, found {count}")
graphics_path.write_text(graphics_text.replace(old_fill, new_fill, 1))
print(f"updated {graphics_path}: log scanout shader metadata and bound images")

raster_path = Path("src/video_core/renderer_vulkan/vk_rasterizer.cpp")
raster_text = raster_path.read_text()

old_after_draw = '''        scheduler.Record([draw_params](vk::CommandBuffer cmdbuf) {
            if (draw_params.is_indexed) {
                cmdbuf.DrawIndexed(draw_params.num_vertices, draw_params.num_instances,
                                   draw_params.first_index, draw_params.base_vertex,
                                   draw_params.base_instance);
            } else {
                cmdbuf.Draw(draw_params.num_vertices, draw_params.num_instances,
                            draw_params.base_vertex, draw_params.base_instance);
            }
        });

        // Log draw call
'''
new_after_draw = '''        scheduler.Record([draw_params](vk::CommandBuffer cmdbuf) {
            if (draw_params.is_indexed) {
                cmdbuf.DrawIndexed(draw_params.num_vertices, draw_params.num_instances,
                                   draw_params.first_index, draw_params.base_vertex,
                                   draw_params.base_instance);
            } else {
                cmdbuf.Draw(draw_params.num_vertices, draw_params.num_instances,
                            draw_params.base_vertex, draw_params.base_instance);
            }
        });

        const auto& v28_regs = maxwell3d->regs;
        const Framebuffer* const v28_framebuffer = texture_cache.GetFramebuffer();
        const VkExtent2D v28_render_area = v28_framebuffer->RenderArea();
        const bool v28_scanout_draw =
            !draw_params.is_indexed && draw_params.num_vertices == 4 &&
            v28_regs.viewport_scale_offset_enabled == 0 &&
            v28_regs.surface_clip.width >= 16384 && v28_regs.surface_clip.height >= 16384 &&
            v28_regs.rt_control.count == 1 && v28_render_area.width == 1280 &&
            v28_render_area.height == 720 && v28_framebuffer->HasAspectColorBit(0);
        if (v28_scanout_draw) {
            static u32 v28_clear_probe_count{};
            const u32 v28_probe = v28_clear_probe_count++;
            if (v28_probe < 64) {
                const auto& v28_scissor = v28_regs.scissor_test[0];
                const auto& v28_viewport = v28_regs.viewport_transform[0];
                LOG_WARNING(Render_Vulkan,
                            "V28_PROBE ForcedScanoutClear count={} rt0={:#x} render_area={}x{} cull_enable={} cull_face={} front_face={} window_mode={} flip_y={} alpha_test={} alpha_func={} alpha_ref={} blend0={} logic_enable={} logic_op={} scissor_enable={} scissor=({},{})->({},{}) viewport_translate=({}, {}) viewport_scale=({}, {})",
                            v28_probe, v28_regs.rt[0].Address(), v28_render_area.width,
                            v28_render_area.height,
                            static_cast<u32>(v28_regs.gl_cull_test_enabled),
                            static_cast<u32>(v28_regs.gl_cull_face),
                            static_cast<u32>(v28_regs.gl_front_face),
                            static_cast<u32>(v28_regs.window_origin.mode.Value()),
                            v28_regs.window_origin.flip_y.Value(),
                            static_cast<u32>(v28_regs.alpha_test_enabled),
                            static_cast<u32>(v28_regs.alpha_test_func), v28_regs.alpha_test_ref,
                            static_cast<u32>(v28_regs.blend.enable[0]),
                            static_cast<u32>(v28_regs.logic_op.enable),
                            static_cast<u32>(v28_regs.logic_op.op),
                            static_cast<u32>(v28_scissor.enable), v28_scissor.min_x.Value(),
                            v28_scissor.min_y.Value(), v28_scissor.max_x.Value(),
                            v28_scissor.max_y.Value(), v28_viewport.translate_x,
                            v28_viewport.translate_y, v28_viewport.scale_x,
                            v28_viewport.scale_y);
            }

            VkClearValue v28_clear_value{};
            v28_clear_value.color.float32[0] = 1.0f;
            v28_clear_value.color.float32[1] = 0.0f;
            v28_clear_value.color.float32[2] = 1.0f;
            v28_clear_value.color.float32[3] = 1.0f;
            const VkClearAttachment v28_clear_attachment{
                .aspectMask = VK_IMAGE_ASPECT_COLOR_BIT,
                .colorAttachment = 0,
                .clearValue = v28_clear_value,
            };
            const VkClearRect v28_clear_rect{
                .rect = {.offset = {0, 0}, .extent = v28_render_area},
                .baseArrayLayer = 0,
                .layerCount = 1,
            };
            scheduler.Record([v28_clear_attachment, v28_clear_rect](vk::CommandBuffer cmdbuf) {
                cmdbuf.ClearAttachments(v28_clear_attachment, v28_clear_rect);
            });
        }

        // Log draw call
'''

count = raster_text.count(old_after_draw)
if count != 1:
    raise RuntimeError(f"add forced scanout clear: expected one match, found {count}")
raster_path.write_text(raster_text.replace(old_after_draw, new_after_draw, 1))
print(f"updated {raster_path}: force magenta scanout clear and log final raster state")
