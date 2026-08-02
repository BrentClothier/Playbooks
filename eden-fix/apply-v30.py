#!/usr/bin/env python3
from pathlib import Path

# V29 added a sample-aware alias synchronization path, but its diagnostic never appeared. The
# reason is earlier in image classification: FindSubresource rejects different sample counts unless
# RelaxedOptions::Samples is enabled. JoinImages therefore classified Minecraft's same-address
# 2x-MSAA render target and 1x sampled texture as a bad overlap, so no AliasedImage relationship
# existed and SynchronizeAliases had nothing to process.
#
# Eden's existing CopyImageMSAA path is explicitly designed to convert between these layouts. Its
# MSAA-to-non-MSAA shader expands each sample into the corresponding adjacent destination texel,
# matching the 1280-wide 2x render target -> 2560-wide sampled texture used by Minecraft. Permit
# sample-count-relaxed alias discovery and creation; v29 will then select CopyImageMSAA when the
# alias is synchronized.

cache_path = Path("src/video_core/texture_cache/texture_cache.h")
cache_text = cache_path.read_text()

old_join = '''        constexpr auto options = RelaxedOptions::Size | RelaxedOptions::Format;
        const ImageBase new_image_base(new_info, gpu_addr, cpu_addr);
        if (IsSubresource(new_info, overlap, gpu_addr, options, broken_views, native_bgr)) {
'''
new_join = '''        // Images that reinterpret the same guest storage with a different MSAA sample count
        // must remain linked. SynchronizeAliases is sample-aware and uses CopyImageMSAA.
        constexpr auto options =
            RelaxedOptions::Size | RelaxedOptions::Format | RelaxedOptions::Samples;
        const ImageBase new_image_base(new_info, gpu_addr, cpu_addr);
        if (IsSubresource(new_info, overlap, gpu_addr, options, broken_views, native_bgr)) {
'''
count = cache_text.count(old_join)
if count != 1:
    raise RuntimeError(f"relax JoinImages sample matching: expected one match, found {count}")
cache_path.write_text(cache_text.replace(old_join, new_join, 1))
print(f"updated {cache_path}: discover aliases across sample-count reinterpretations")

image_base_path = Path("src/video_core/texture_cache/image_base.cpp")
image_base_text = image_base_path.read_text()

old_options = '''bool AddImageAlias(ImageBase& lhs, ImageBase& rhs, ImageId lhs_id, ImageId rhs_id) {
    static constexpr auto OPTIONS = RelaxedOptions::Size | RelaxedOptions::Format;
'''
new_options = '''bool AddImageAlias(ImageBase& lhs, ImageBase& rhs, ImageId lhs_id, ImageId rhs_id) {
    // Sample-count reinterpretations share guest storage and are synchronized through
    // TextureCache::SynchronizeAliases, which dispatches CopyImageMSAA when required.
    static constexpr auto OPTIONS =
        RelaxedOptions::Size | RelaxedOptions::Format | RelaxedOptions::Samples;
'''
count = image_base_text.count(old_options)
if count != 1:
    raise RuntimeError(f"relax AddImageAlias sample matching: expected one match, found {count}")
image_base_text = image_base_text.replace(old_options, new_options, 1)

old_commit_alias = '''    ASSERT(lhs_alias.copies.empty() == rhs_alias.copies.empty());
    if (lhs_alias.copies.empty()) {
        return false;
    }
    lhs.aliased_images.push_back(std::move(lhs_alias));
'''
new_commit_alias = '''    ASSERT(lhs_alias.copies.empty() == rhs_alias.copies.empty());
    if (lhs_alias.copies.empty()) {
        return false;
    }
    if (lhs.info.num_samples != rhs.info.num_samples) {
        static u32 v30_sample_alias_diag_count{};
        if (v30_sample_alias_diag_count < 120) {
            LOG_WARNING(HW_GPU,
                        "V30_FIX RegisterSampleAlias count={} lhs_id={} lhs_gpu={:#x} lhs_samples={} lhs_size={}x{} rhs_id={} rhs_gpu={:#x} rhs_samples={} rhs_size={}x{} copies={}",
                        v30_sample_alias_diag_count, lhs_id.Value(), lhs.gpu_addr,
                        lhs.info.num_samples, lhs.info.size.width, lhs.info.size.height,
                        rhs_id.Value(), rhs.gpu_addr, rhs.info.num_samples,
                        rhs.info.size.width, rhs.info.size.height, lhs_alias.copies.size());
            ++v30_sample_alias_diag_count;
        }
    }
    lhs.aliased_images.push_back(std::move(lhs_alias));
'''
count = image_base_text.count(old_commit_alias)
if count != 1:
    raise RuntimeError(f"instrument sample alias creation: expected one match, found {count}")
image_base_path.write_text(image_base_text.replace(old_commit_alias, new_commit_alias, 1))
print(f"updated {image_base_path}: create and log aliases across sample counts")
