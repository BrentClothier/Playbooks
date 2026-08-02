#!/usr/bin/env python3
from pathlib import Path

# V28's forced magenta clear reached all three rotating scanout images and survived GPU staging
# download, guest-memory writeback, raw upload, and presentation. The remaining blank frame is
# therefore inside Minecraft's guest draw. Its final fragment shader samples image 5 at GPU address
# 0x4131c0000 as a single-sample 2560x720 texture, while the immediately preceding offscreen pass
# writes image 2 at the same GPU address as a 2x-MSAA 2560x768 render target.
#
# Eden correctly records these images as aliases, but SynchronizeAliases always calls CopyImage.
# Vulkan image copies require matching sample counts, so the 2x -> 1x alias transfer is invalid and
# the sampled image remains blank. Eden already has CopyImageMSAA for exactly this conversion and
# uses it while joining newly created overlapping images. Use the same sample-aware path whenever
# an existing alias is synchronized.

texture_path = Path("src/video_core/texture_cache/texture_cache.h")
texture_text = texture_path.read_text()

old_sync = '''    const auto& resolution = Settings::values.resolution_info;
    for (const AliasedImage* const aliased : aliased_images) {
        if (!resolution.active || !any_rescaled) {
            CopyImage(image_id, aliased->id, aliased->copies);
            continue;
        }
        Image& aliased_image = slot_images[aliased->id];
        if (!can_rescale) {
            ScaleDown(aliased_image);
            CopyImage(image_id, aliased->id, aliased->copies);
            continue;
        }
        ScaleUp(aliased_image);
        CopyImage(image_id, aliased->id, aliased->copies);
    }
'''

new_sync = '''    const auto& resolution = Settings::values.resolution_info;
    static u32 v29_alias_sample_diag_count{};
    const auto copy_alias = [&](const AliasedImage& aliased) {
        Image& source = slot_images[aliased.id];
        if (image.info.num_samples != source.info.num_samples) {
            if (v29_alias_sample_diag_count < 120) {
                LOG_WARNING(HW_GPU,
                            "V29_FIX SyncAliasSamples count={} dst_id={} dst_gpu={:#x} dst_samples={} dst_size={}x{} src_id={} src_gpu={:#x} src_samples={} src_size={}x{} copies={}",
                            v29_alias_sample_diag_count, image_id.Value(), image.gpu_addr,
                            image.info.num_samples, image.info.size.width, image.info.size.height,
                            aliased.id.Value(), source.gpu_addr, source.info.num_samples,
                            source.info.size.width, source.info.size.height,
                            aliased.copies.size());
                ++v29_alias_sample_diag_count;
            }
            const std::span<const ImageCopy> copies{aliased.copies.data(), aliased.copies.size()};
            runtime.CopyImageMSAA(image, source, copies);
            return;
        }
        CopyImage(image_id, aliased.id, aliased.copies);
    };
    for (const AliasedImage* const aliased : aliased_images) {
        if (!resolution.active || !any_rescaled) {
            copy_alias(*aliased);
            continue;
        }
        Image& aliased_image = slot_images[aliased->id];
        if (!can_rescale) {
            ScaleDown(aliased_image);
            copy_alias(*aliased);
            continue;
        }
        ScaleUp(aliased_image);
        copy_alias(*aliased);
    }
'''

count = texture_text.count(old_sync)
if count != 1:
    raise RuntimeError(f"make alias synchronization sample-aware: expected one match, found {count}")

texture_path.write_text(texture_text.replace(old_sync, new_sync, 1))
print(f"updated {texture_path}: use CopyImageMSAA for aliases with different sample counts")
