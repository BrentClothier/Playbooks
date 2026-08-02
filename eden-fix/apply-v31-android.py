#!/usr/bin/env python3
from pathlib import Path

# The Linux investigation used extensive diagnostics and forced readback paths. The Android build
# should contain only the compatibility fixes that led to the working v30 result, plus a distinct
# release package identity so it can be installed alongside the user's normal Eden APK.


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))
    print(f"updated {path}: {label}")


# Remove the high-frequency diagnostics from the otherwise-correct framebuffer extent fix.
texture_path = Path("src/video_core/texture_cache/texture_cache.h")
replace_once(
    texture_path,
    '''        static u32 v26_extent_clamp_diag_count{};
        if (v26_extent_clamp_diag_count < 120) {
            LOG_WARNING(HW_GPU,
                        "V26_FIX ClampFramebufferExtent count={} requested={}x{} attachment_limit={}x{} active_mask={:#x}",
                        v26_extent_clamp_diag_count, render_targets.size.width,
                        render_targets.size.height, attachment_width, attachment_height,
                        rt_active_mask);
            ++v26_extent_clamp_diag_count;
        }
''',
    '',
    "remove v26 framebuffer diagnostic logging",
)

# Keep the viewport-transform pipeline-key fix but omit per-pipeline warning output.
pipeline_cache_path = Path("src/video_core/renderer_vulkan/vk_pipeline_cache.cpp")
replace_once(
    pipeline_cache_path,
    '''    static u32 v27_pipeline_key_diag_count{};
    if (v27_pipeline_key_diag_count < 240) {
        LOG_WARNING(Render_Vulkan,
                    "V27_FIX PipelineKey count={} hash={:#x} viewport_transform={} topology={} vertex_b={:#x} fragment={:#x}",
                    v27_pipeline_key_diag_count, graphics_key.Hash(),
                    graphics_key.state.viewport_transform_enabled.Value(),
                    static_cast<u32>(graphics_key.state.topology.Value()),
                    graphics_key.unique_hashes[1], graphics_key.unique_hashes[5]);
        ++v27_pipeline_key_diag_count;
    }

''',
    '',
    "remove v27 pipeline-key diagnostic logging",
)

# Keep sample-aware alias synchronization while removing its bounded diagnostic counters.
replace_once(
    texture_path,
    '''    static u32 v29_alias_sample_diag_count{};
    const auto copy_alias = [&](const AliasedImage& aliased) {
''',
    '''    const auto copy_alias = [&](const AliasedImage& aliased) {
''',
    "remove v29 diagnostic counter",
)
replace_once(
    texture_path,
    '''            if (v29_alias_sample_diag_count < 120) {
                LOG_WARNING(HW_GPU,
                            "V29_FIX SyncAliasSamples count={} dst_id={} dst_gpu={:#x} dst_samples={} dst_size={}x{} src_id={} src_gpu={:#x} src_samples={} src_size={}x{} copies={}",
                            v29_alias_sample_diag_count, image_id.Value(), image.gpu_addr,
                            image.info.num_samples, image.info.size.width, image.info.size.height,
                            aliased.id.Value(), source.gpu_addr, source.info.num_samples,
                            source.info.size.width, source.info.size.height,
                            aliased.copies.size());
                ++v29_alias_sample_diag_count;
            }
''',
    '',
    "remove v29 alias-sync diagnostic logging",
)

image_base_path = Path("src/video_core/texture_cache/image_base.cpp")
replace_once(
    image_base_path,
    '''    if (lhs.info.num_samples != rhs.info.num_samples) {
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
''',
    '',
    "remove v30 sample-alias diagnostic logging",
)

# Avoid replacing the user's normal Eden installation. Release builds remain optimized and are
# signed with the repository's default development key, but use an independent Android package ID.
gradle_path = Path("src/android/app/build.gradle.kts")
replace_once(
    gradle_path,
    '''            if (isNightly) {
                applicationIdSuffix = ".nightly"
                manifestPlaceholders += mapOf("appNameSuffix" to " Nightly")
            } else {
                manifestPlaceholders += mapOf("appNameSuffix" to "")
            }
''',
    '''            if (isNightly) {
                applicationIdSuffix = ".nightly"
                manifestPlaceholders += mapOf("appNameSuffix" to " Nightly")
            } else {
                applicationIdSuffix = ".minecraftfix"
                versionNameSuffix = "-minecraftfix-v31"
                manifestPlaceholders += mapOf("appNameSuffix" to " Minecraft Fix")
            }
''',
    "brand side-by-side Android release",
)
