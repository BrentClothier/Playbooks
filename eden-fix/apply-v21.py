#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))
    print(f"updated {path}: {label}")


# V20 only exercised its raw-display/readback experiment for docked 1920x1080 output. Extend the
# exact same path to Minecraft's handheld 1280x720 buffers.
layer = Path("src/video_core/renderer_vulkan/present/layer.cpp")
replace_once(
    layer,
    '''    const bool v20_minecraft_framebuffer =
        framebuffer.width == 1920 && framebuffer.height == 1080 &&
        framebuffer.stride == 1920 &&
        framebuffer.pixel_format == Service::android::PixelFormat::Rgba8888;
''',
    '''    const bool v20_minecraft_framebuffer =
        ((framebuffer.width == 1920 && framebuffer.height == 1080 &&
          framebuffer.stride == 1920) ||
         (framebuffer.width == 1280 && framebuffer.height == 720 &&
          framebuffer.stride == 1280)) &&
        framebuffer.pixel_format == Service::android::PixelFormat::Rgba8888;
''',
    "extend raw display fallback to handheld framebuffer",
)

replace_once(
    layer,
    '''    if (host_ptr && framebuffer.width == 1920 && framebuffer.height == 1080 &&
        framebuffer.stride == 1920 &&
        framebuffer.pixel_format == Service::android::PixelFormat::Rgba8888 &&
        v20_raw_sample_count < 120) {
''',
    '''    const bool v21_minecraft_framebuffer =
        ((framebuffer.width == 1920 && framebuffer.height == 1080 &&
          framebuffer.stride == 1920) ||
         (framebuffer.width == 1280 && framebuffer.height == 720 &&
          framebuffer.stride == 1280)) &&
        framebuffer.pixel_format == Service::android::PixelFormat::Rgba8888;
    if (host_ptr && v21_minecraft_framebuffer && v20_raw_sample_count < 120) {
''',
    "extend raw framebuffer sampling to handheld",
)

replace_once(
    layer,
    '''    } else if (!host_ptr && framebuffer.width == 1920 && framebuffer.height == 1080 &&
               framebuffer.stride == 1920 &&
               framebuffer.pixel_format == Service::android::PixelFormat::Rgba8888 &&
               v20_raw_sample_count < 120) {
''',
    '''    } else if (!host_ptr && v21_minecraft_framebuffer && v20_raw_sample_count < 120) {
''',
    "extend null-pointer diagnostics to handheld",
)


# FlushRegion reached TextureCache::DownloadMemory in V20, but the raw framebuffer remained all
# zeros. Eden normally refuses a download unless the selected image is marked GPU-modified, not
# CPU-modified, and non-MSAA. For only the two exact block-linear framebuffer allocation sizes used
# by Minecraft in docked and handheld modes, log those flags and allow a synchronous download of
# non-MSAA images even when the bookkeeping flags reject it. This is deliberately narrow and is
# reached by V20's title-specific display fallback.
texture_cache = Path("src/video_core/texture_cache/texture_cache.h")
old_download = '''template <class P>
void TextureCache<P>::DownloadMemory(DAddr cpu_addr, size_t size) {
    boost::container::small_vector<ImageId, 16> images;
    ForEachImageInRegion(cpu_addr, size, [&images](ImageId image_id, ImageBase& image) {
        if (!image.IsSafeDownload()) {
            return;
        }
        image.flags &= ~ImageFlagBits::GpuModified;
        images.push_back(image_id);
    });
    if (images.empty()) {
        return;
    }
    std::ranges::sort(images, [this](ImageId lhs, ImageId rhs) {
        return slot_images[lhs].modification_tick < slot_images[rhs].modification_tick;
    });
    for (const ImageId image_id : images) {
        Image& image = slot_images[image_id];
        auto map = runtime.DownloadStagingBuffer(image.unswizzled_size_bytes);
        const auto copies = FixSmallVectorADL(FullDownloadCopies(image.info));
        image.DownloadMemory(map, copies);
        runtime.Finish();
        SwizzleImage(*gpu_memory, image.gpu_addr, image.info, copies, map.mapped_span,
                     swizzle_data_buffer);
    }
}
'''
new_download = '''template <class P>
void TextureCache<P>::DownloadMemory(DAddr cpu_addr, size_t size) {
    // Minecraft's block-linear display allocations are 0x870000 bytes at 1920x1080 and
    // 0x3c0000 bytes at 1280x720. V20 calls this function synchronously only for the presented
    // framebuffer, so these exact sizes provide a narrow compatibility gate.
    const bool v21_force_framebuffer_download = size == 0x870000 || size == 0x3c0000;
    static u32 v21_download_diag_count{};

    boost::container::small_vector<ImageId, 16> images;
    ForEachImageInRegion(cpu_addr, size,
                         [&images, v21_force_framebuffer_download, cpu_addr,
                          size](ImageId image_id, ImageBase& image) {
        const bool safe_download = image.IsSafeDownload();
        const bool force_this_image =
            v21_force_framebuffer_download && image.info.num_samples == 1;

        if (v21_force_framebuffer_download && v21_download_diag_count < 120) {
            LOG_WARNING(HW_GPU,
                        "V21_DIAG framebuffer download request=[{:#x},+{:#x}] image_cpu={:#x} image_gpu={:#x} guest={:#x} unswizzled={:#x} flags={:#x} samples={} safe={} force={}",
                        cpu_addr, size, image.cpu_addr, image.gpu_addr,
                        image.guest_size_bytes, image.unswizzled_size_bytes,
                        static_cast<u32>(image.flags), image.info.num_samples,
                        safe_download, force_this_image);
            ++v21_download_diag_count;
        }

        if (!safe_download && !force_this_image) {
            return;
        }

        if (force_this_image) {
            // The GPU image is the source of truth for this explicit presentation readback.
            image.flags &= ~ImageFlagBits::CpuModified;
        }
        image.flags &= ~ImageFlagBits::GpuModified;
        images.push_back(image_id);
    });
    if (images.empty()) {
        if (v21_force_framebuffer_download && v21_download_diag_count < 120) {
            LOG_WARNING(HW_GPU,
                        "V21_DIAG framebuffer download found no eligible image request=[{:#x},+{:#x}]",
                        cpu_addr, size);
            ++v21_download_diag_count;
        }
        return;
    }
    std::ranges::sort(images, [this](ImageId lhs, ImageId rhs) {
        return slot_images[lhs].modification_tick < slot_images[rhs].modification_tick;
    });
    for (const ImageId image_id : images) {
        Image& image = slot_images[image_id];
        auto map = runtime.DownloadStagingBuffer(image.unswizzled_size_bytes);
        const auto copies = FixSmallVectorADL(FullDownloadCopies(image.info));
        image.DownloadMemory(map, copies);
        runtime.Finish();
        SwizzleImage(*gpu_memory, image.gpu_addr, image.info, copies, map.mapped_span,
                     swizzle_data_buffer);
    }
}
'''
replace_once(
    texture_cache,
    old_download,
    new_download,
    "force narrow Minecraft framebuffer image download and log cache flags",
)
