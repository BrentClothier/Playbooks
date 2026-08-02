#!/usr/bin/env python3
from pathlib import Path

# V23b proved that the selected presented Vulkan image itself downloads as all zeroes. The next
# question is whether Eden is skipping Minecraft's draw configuration, or successfully drawing to
# a different render target that never reaches the queued display image.

texture_path = Path("src/video_core/texture_cache/texture_cache.h")
texture_text = texture_path.read_text()

old_mark = '''template <class P>
void TextureCache<P>::MarkModification(ImageId id) noexcept {
    MarkModification(slot_images[id]);
}
'''
new_mark = '''template <class P>
void TextureCache<P>::MarkModification(ImageId id) noexcept {
    auto& image = slot_images[id];
    static u32 v24_modification_diag_count{};
    const bool v24_interesting_size =
        image.info.size.width >= 320 && image.info.size.height >= 180;
    if (v24_interesting_size && v24_modification_diag_count < 240) {
        LOG_WARNING(HW_GPU,
                    "V24_DIAG MarkModification count={} id={} cpu={:#x} gpu={:#x} format={} type={} size={}x{}x{} samples={} guest={:#x} unswizzled={:#x} flags_before={:#x}",
                    v24_modification_diag_count, id.Value(), image.cpu_addr, image.gpu_addr,
                    static_cast<u32>(image.info.format), static_cast<u32>(image.info.type),
                    image.info.size.width, image.info.size.height, image.info.size.depth,
                    image.info.num_samples, image.guest_size_bytes, image.unswizzled_size_bytes,
                    static_cast<u32>(image.flags));
        ++v24_modification_diag_count;
    }
    MarkModification(image);
}
'''

count = texture_text.count(old_mark)
if count != 1:
    raise RuntimeError(f"instrument MarkModification: expected one match, found {count}")
texture_path.write_text(texture_text.replace(old_mark, new_mark, 1))
print(f"updated {texture_path}: log large GPU-modified images")

raster_path = Path("src/video_core/renderer_vulkan/vk_rasterizer.cpp")
raster_text = raster_path.read_text()

old_prepare = '''    GraphicsPipeline* const pipeline{pipeline_cache.CurrentGraphicsPipeline()};
    if (!pipeline) {
        return;
    }
    std::scoped_lock lock{buffer_cache.mutex, texture_cache.mutex};
    // update engine as channel may be different.
    pipeline->SetEngine(maxwell3d, gpu_memory);
    if (!pipeline->Configure(is_indexed))
        return;

    UpdateDynamicStates();
'''
new_prepare = '''    static u32 v24_prepare_diag_count{};
    const u32 v24_prepare_call = v24_prepare_diag_count++;
    GraphicsPipeline* const pipeline{pipeline_cache.CurrentGraphicsPipeline()};
    if (!pipeline) {
        if (v24_prepare_call < 240) {
            LOG_WARNING(Render_Vulkan,
                        "V24_DIAG PrepareDraw call={} indexed={} result=no_pipeline",
                        v24_prepare_call, is_indexed);
        }
        return;
    }
    std::scoped_lock lock{buffer_cache.mutex, texture_cache.mutex};
    // update engine as channel may be different.
    pipeline->SetEngine(maxwell3d, gpu_memory);
    if (!pipeline->Configure(is_indexed)) {
        if (v24_prepare_call < 240) {
            LOG_WARNING(Render_Vulkan,
                        "V24_DIAG PrepareDraw call={} indexed={} result=configure_failed",
                        v24_prepare_call, is_indexed);
        }
        return;
    }
    if (v24_prepare_call < 240) {
        LOG_WARNING(Render_Vulkan,
                    "V24_DIAG PrepareDraw call={} indexed={} result=configured",
                    v24_prepare_call, is_indexed);
    }

    UpdateDynamicStates();
'''

count = raster_text.count(old_prepare)
if count != 1:
    raise RuntimeError(f"instrument PrepareDraw: expected one match, found {count}")
raster_text = raster_text.replace(old_prepare, new_prepare, 1)

old_draw = '''        const DrawParams draw_params{MakeDrawParams(draw_state, num_instances, is_indexed)};

        scheduler.Record([draw_params](vk::CommandBuffer cmdbuf) {
'''
new_draw = '''        const DrawParams draw_params{MakeDrawParams(draw_state, num_instances, is_indexed)};
        static u32 v24_draw_diag_count{};
        if (v24_draw_diag_count < 240) {
            LOG_WARNING(Render_Vulkan,
                        "V24_DIAG Draw submit={} indexed={} vertices={} instances={} first_index={} base_vertex={} base_instance={}",
                        v24_draw_diag_count, draw_params.is_indexed, draw_params.num_vertices,
                        draw_params.num_instances, draw_params.first_index, draw_params.base_vertex,
                        draw_params.base_instance);
            ++v24_draw_diag_count;
        }

        scheduler.Record([draw_params](vk::CommandBuffer cmdbuf) {
'''

count = raster_text.count(old_draw)
if count != 1:
    raise RuntimeError(f"instrument direct draws: expected one match, found {count}")
raster_text = raster_text.replace(old_draw, new_draw, 1)

old_indirect = '''    PrepareDraw(params.is_indexed, [this, &params] {
        const auto indirect_buffer = buffer_cache.GetDrawIndirectBuffer();
'''
new_indirect = '''    PrepareDraw(params.is_indexed, [this, &params] {
        static u32 v24_indirect_diag_count{};
        if (v24_indirect_diag_count < 120) {
            LOG_WARNING(Render_Vulkan,
                        "V24_DIAG DrawIndirect submit={} indexed={} include_count={} byte_count={} max_draws={} stride={}",
                        v24_indirect_diag_count, params.is_indexed, params.include_count,
                        params.is_byte_count, params.max_draw_counts, params.stride);
            ++v24_indirect_diag_count;
        }
        const auto indirect_buffer = buffer_cache.GetDrawIndirectBuffer();
'''

count = raster_text.count(old_indirect)
if count != 1:
    raise RuntimeError(f"instrument indirect draws: expected one match, found {count}")
raster_path.write_text(raster_text.replace(old_indirect, new_indirect, 1))
print(f"updated {raster_path}: log draw configuration and submissions")
