#!/usr/bin/env python3
from pathlib import Path

def rep(path, old, new, label):
    p=Path(path); s=p.read_text()
    if s.count(old)!=1: raise RuntimeError(f"{label}: {s.count(old)} matches")
    p.write_text(s.replace(old,new,1))
    print(label)

rep("src/video_core/renderer_vulkan/vk_rasterizer.cpp",
"""    const bool v57_minecraft_docked_clear_rect =
        v57_minecraft_title_active && render_area.width == 1920 && render_area.height == 1080 &&
        static_cast<u32>(regs.clear_control.use_clear_rect) != 0;
""",
"""    const bool v57_minecraft_docked_clear_rect =
        v57_minecraft_title_active && render_area.width == 1920 && render_area.height == 1080 &&
        static_cast<u32>(regs.clear_control.use_clear_rect) != 0 &&
        (static_cast<u32>(regs.clear_rect.x_min) != 0 ||
         static_cast<u32>(regs.clear_rect.y_min) != 0 ||
         static_cast<u32>(regs.clear_rect.x_max) < render_area.width ||
         static_cast<u32>(regs.clear_rect.y_max) < render_area.height);
""","limit v57 clear handling to partial rectangles")

rep("src/video_core/texture_cache/texture_cache.h",
"""            const std::span<const ImageCopy> copies{aliased.copies.data(), aliased.copies.size()};
            runtime.CopyImageMSAA(image, source, copies);
""",
"""            static u32 v58_alias_sync_diag_count{};
            if (v58_alias_sync_diag_count < 160 && !aliased.copies.empty()) {
                const auto& c = aliased.copies.front();
                LOG_WARNING(HW_GPU,
                            "V58_DIAG SyncAliasMSAA count={} dst_id={} dst_gpu={:#x} dst_samples={} dst_size={}x{} src_id={} src_gpu={:#x} src_samples={} src_size={}x{} copies={} src=({},{},{}) dst=({},{},{}) extent={}x{}x{}",
                            v58_alias_sync_diag_count, image_id.Value(), image.gpu_addr,
                            image.info.num_samples, image.info.size.width, image.info.size.height,
                            aliased.id.Value(), source.gpu_addr, source.info.num_samples,
                            source.info.size.width, source.info.size.height, aliased.copies.size(),
                            c.src_offset.x, c.src_offset.y, c.src_offset.z,
                            c.dst_offset.x, c.dst_offset.y, c.dst_offset.z,
                            c.extent.width, c.extent.height, c.extent.depth);
                ++v58_alias_sync_diag_count;
            }
            const std::span<const ImageCopy> copies{aliased.copies.data(), aliased.copies.size()};
            runtime.CopyImageMSAA(image, source, copies);
""","trace MSAA alias synchronization")

rep("src/video_core/texture_cache/image_base.cpp",
"""    if (lhs.info.num_samples != rhs.info.num_samples) {
        static u32 v30_sample_alias_diag_count{};
""",
"""    if (lhs.info.num_samples != rhs.info.num_samples) {
        static u32 v58_sample_alias_diag_count{};
        if (v58_sample_alias_diag_count < 80) {
            LOG_WARNING(HW_GPU,
                        "V58_DIAG RegisterSampleAlias count={} lhs_id={} lhs_gpu={:#x} lhs_samples={} lhs_size={}x{} rhs_id={} rhs_gpu={:#x} rhs_samples={} rhs_size={}x{} copies={}",
                        v58_sample_alias_diag_count, lhs_id.Value(), lhs.gpu_addr,
                        lhs.info.num_samples, lhs.info.size.width, lhs.info.size.height,
                        rhs_id.Value(), rhs.gpu_addr, rhs.info.num_samples,
                        rhs.info.size.width, rhs.info.size.height, lhs_alias.copies.size());
            ++v58_sample_alias_diag_count;
        }
        static u32 v30_sample_alias_diag_count{};
""","trace sample alias creation")

rep("src/video_core/renderer_vulkan/vk_texture_cache.cpp",
"""void TextureCacheRuntime::CopyImageMSAA(Image& dst, Image& src,
                                        std::span<const VideoCommon::ImageCopy> copies) {
    const bool msaa_to_non_msaa = src.info.num_samples > 1 && dst.info.num_samples == 1;
""",
"""void TextureCacheRuntime::CopyImageMSAA(Image& dst, Image& src,
                                        std::span<const VideoCommon::ImageCopy> copies) {
    static u32 v58_copy_msaa_diag_count{};
    if (v58_copy_msaa_diag_count < 160 && !copies.empty()) {
        const auto& c = copies.front();
        LOG_WARNING(Render_Vulkan,
                    "V58_DIAG CopyImageMSAA count={} src_gpu={:#x} src_samples={} src_size={}x{} dst_gpu={:#x} dst_samples={} dst_size={}x{} copies={} src=({},{},{}) dst=({},{},{}) extent={}x{}x{}",
                    v58_copy_msaa_diag_count, src.gpu_addr, src.info.num_samples,
                    src.info.size.width, src.info.size.height, dst.gpu_addr,
                    dst.info.num_samples, dst.info.size.width, dst.info.size.height,
                    copies.size(), c.src_offset.x, c.src_offset.y, c.src_offset.z,
                    c.dst_offset.x, c.dst_offset.y, c.dst_offset.z,
                    c.extent.width, c.extent.height, c.extent.depth);
        ++v58_copy_msaa_diag_count;
    }
    const bool msaa_to_non_msaa = src.info.num_samples > 1 && dst.info.num_samples == 1;
""","trace Vulkan CopyImageMSAA geometry")

print("applied v58")
