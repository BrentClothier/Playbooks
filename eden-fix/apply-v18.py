#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))
    print(f"updated {path}: {label}")


# 1. Make the Minecraft DeviceShared transfer-memory compatibility path symmetric.
page_table = Path("src/core/hle/kernel/k_page_table_base.cpp")
old_unlock = '''Result KPageTableBase::UnlockForTransferMemory(KProcessAddress address, size_t size,
                                               const KPageGroup& pg) {
    R_RETURN(this->UnlockMemory(address, size, KMemoryState::FlagCanTransfer,
                                KMemoryState::FlagCanTransfer, KMemoryPermission::None,
                                KMemoryPermission::None, KMemoryAttribute::All,
                                KMemoryAttribute::Locked, KMemoryPermission::UserReadWrite,
                                KMemoryAttribute::Locked, &pg));
}
'''
new_unlock = '''Result KPageTableBase::UnlockForTransferMemory(KProcessAddress address, size_t size,
                                               const KPageGroup& pg) {
    const bool minecraft_device_shared_compat =
        GetCurrentProcess(m_system.Kernel()).GetProgramId() == 0x0100D71004694000ULL;

    const auto attribute_mask = minecraft_device_shared_compat
                                    ? static_cast<KMemoryAttribute>(
                                          KMemoryAttribute::All &
                                          ~KMemoryAttribute::DeviceShared)
                                    : KMemoryAttribute::All;

    R_RETURN(this->UnlockMemory(address, size, KMemoryState::FlagCanTransfer,
                                KMemoryState::FlagCanTransfer, KMemoryPermission::None,
                                KMemoryPermission::None, attribute_mask,
                                KMemoryAttribute::Locked, KMemoryPermission::UserReadWrite,
                                KMemoryAttribute::Locked, &pg));
}
'''
replace_once(page_table, old_unlock, new_unlock, "symmetric DeviceShared transfer unlock")


# 2. Do not let an unmatched nvmap unpin drive the reference count negative.
nvmap = Path("src/core/hle/service/nvdrv/core/nvmap.cpp")
old_unpin = '''void NvMap::UnpinHandle(Handle::Id handle) {
    auto handle_description{GetHandle(handle)};
    if (!handle_description) {
        return;
    }

    std::scoped_lock lock(handle_description->mutex);
    if (--handle_description->pins < 0) {
        LOG_WARNING(Service_NVDRV, "Pin count imbalance detected!");
    } else if (!handle_description->pins) {
        std::scoped_lock queueLock(unmap_queue_lock);

        // Add to the unmap queue allowing this handle's memory to be freed if needed
        unmap_queue.push_back(handle_description);
        handle_description->unmap_queue_entry = std::prev(unmap_queue.end());
    }
}
'''
new_unpin = '''void NvMap::UnpinHandle(Handle::Id handle) {
    auto handle_description{GetHandle(handle)};
    if (!handle_description) {
        return;
    }

    std::scoped_lock lock(handle_description->mutex);
    if (handle_description->pins <= 0) {
        LOG_WARNING(Service_NVDRV,
                    "V18_COMPAT ignoring unmatched nvmap unpin for handle={}", handle);
        handle_description->pins = 0;
        return;
    }

    --handle_description->pins;
    if (!handle_description->pins && !handle_description->unmap_queue_entry) {
        std::scoped_lock queueLock(unmap_queue_lock);

        // Add to the unmap queue allowing this handle's memory to be freed if needed.
        unmap_queue.push_back(handle_description);
        handle_description->unmap_queue_entry = std::prev(unmap_queue.end());
    }
}
'''
replace_once(nvmap, old_unpin, new_unpin, "clamp nvmap pin underflow")


# 3. Expose vkCmdClearDepthStencilImage through Eden's Vulkan wrapper.
wrapper_h = Path("src/video_core/vulkan_common/vulkan_wrapper.h")
replace_once(
    wrapper_h,
    '''    PFN_vkCmdClearColorImage vkCmdClearColorImage{};\n''',
    '''    PFN_vkCmdClearColorImage vkCmdClearColorImage{};\n    PFN_vkCmdClearDepthStencilImage vkCmdClearDepthStencilImage{};\n''',
    "add depth-stencil clear dispatch",
)
replace_once(
    wrapper_h,
    '''    void ClearColorImage(VkImage image, VkImageLayout layout, VkClearColorValue color,
                         Span<VkImageSubresourceRange> ranges) {
        dld->vkCmdClearColorImage(handle, image, layout, &color, ranges.size(), ranges.data());
    }
''',
    '''    void ClearColorImage(VkImage image, VkImageLayout layout, VkClearColorValue color,
                         Span<VkImageSubresourceRange> ranges) {
        dld->vkCmdClearColorImage(handle, image, layout, &color, ranges.size(), ranges.data());
    }

    void ClearDepthStencilImage(VkImage image, VkImageLayout layout,
                                VkClearDepthStencilValue value,
                                Span<VkImageSubresourceRange> ranges) {
        dld->vkCmdClearDepthStencilImage(handle, image, layout, &value, ranges.size(),
                                         ranges.data());
    }
''',
    "add command-buffer depth-stencil clear",
)

wrapper_cpp = Path("src/video_core/vulkan_common/vulkan_wrapper.cpp")
replace_once(
    wrapper_cpp,
    '''    X(vkCmdClearColorImage);\n''',
    '''    X(vkCmdClearColorImage);\n    X(vkCmdClearDepthStencilImage);\n''',
    "load depth-stencil clear command",
)


# 4. Eden currently drops all uploads to multisampled depth/stencil images. Initialize those
# images to a valid depth/stencil value instead of leaving them undefined. This does not reproduce
# arbitrary uploaded depth data, but it gives Minecraft a usable attachment while preserving the
# existing color-MSAA conversion path.
texture_cache = Path("src/video_core/renderer_vulkan/vk_texture_cache.cpp")
old_msaa_fallback = '''    if (info.num_samples > 1) {
        LOG_WARNING(Render_Vulkan, "MSAA upload not implemented for format {}", info.format);
        if (is_rescaled) {
            ScaleUp();
        }
        return;
    }
'''
new_msaa_fallback = '''    if (info.num_samples > 1) {
        const bool is_depth_stencil =
            (aspect_mask & (VK_IMAGE_ASPECT_DEPTH_BIT | VK_IMAGE_ASPECT_STENCIL_BIT)) != 0;
        if (is_depth_stencil) {
            scheduler->RequestOutsideRenderPassOperationContext();
            const VkImage image = *original_image;
            const VkImageAspectFlags vk_aspect_mask = aspect_mask;
            const bool was_initialized = std::exchange(initialized, true);

            scheduler->Record([image, vk_aspect_mask,
                               was_initialized](vk::CommandBuffer cmdbuf) {
                const VkImageSubresourceRange range{
                    .aspectMask = vk_aspect_mask,
                    .baseMipLevel = 0,
                    .levelCount = VK_REMAINING_MIP_LEVELS,
                    .baseArrayLayer = 0,
                    .layerCount = VK_REMAINING_ARRAY_LAYERS,
                };
                const VkImageMemoryBarrier to_clear{
                    .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
                    .pNext = nullptr,
                    .srcAccessMask = was_initialized
                                         ? VK_ACCESS_MEMORY_READ_BIT |
                                               VK_ACCESS_MEMORY_WRITE_BIT
                                         : 0,
                    .dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT,
                    .oldLayout = was_initialized ? VK_IMAGE_LAYOUT_GENERAL
                                                 : VK_IMAGE_LAYOUT_UNDEFINED,
                    .newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
                    .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                    .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                    .image = image,
                    .subresourceRange = range,
                };
                cmdbuf.PipelineBarrier(
                    was_initialized ? VK_PIPELINE_STAGE_ALL_COMMANDS_BIT
                                    : VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,
                    VK_PIPELINE_STAGE_TRANSFER_BIT, 0, nullptr, nullptr, to_clear);

                const VkClearDepthStencilValue clear_value{
                    .depth = 1.0f,
                    .stencil = 0,
                };
                cmdbuf.ClearDepthStencilImage(image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
                                              clear_value, range);

                const VkImageMemoryBarrier to_general{
                    .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
                    .pNext = nullptr,
                    .srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT,
                    .dstAccessMask = VK_ACCESS_SHADER_READ_BIT |
                                     VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_READ_BIT |
                                     VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT,
                    .oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
                    .newLayout = VK_IMAGE_LAYOUT_GENERAL,
                    .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                    .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                    .image = image,
                    .subresourceRange = range,
                };
                cmdbuf.PipelineBarrier(
                    VK_PIPELINE_STAGE_TRANSFER_BIT,
                    VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT |
                        VK_PIPELINE_STAGE_EARLY_FRAGMENT_TESTS_BIT |
                        VK_PIPELINE_STAGE_LATE_FRAGMENT_TESTS_BIT,
                    0, nullptr, nullptr, to_general);
            });
            LOG_WARNING(Render_Vulkan,
                        "V18_COMPAT initialized unsupported MSAA depth/stencil format {} by clear",
                        info.format);
        } else {
            LOG_WARNING(Render_Vulkan, "MSAA upload not implemented for format {}", info.format);
        }
        if (is_rescaled) {
            ScaleUp();
        }
        return;
    }
'''
replace_once(texture_cache, old_msaa_fallback, new_msaa_fallback,
             "initialize unsupported MSAA depth-stencil images")
