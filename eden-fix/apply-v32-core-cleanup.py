#!/usr/bin/env python3
from pathlib import Path

# Retain the non-renderer safety portions of v18b without its speculative Vulkan MSAA
# depth/stencil clear. These changes make the v17 transfer-memory workaround symmetric and prevent
# an unmatched nvmap unpin from underflowing the pin counter.


def replace_function(path: Path, signature: str, replacement: str, label: str) -> None:
    text = path.read_text()
    start = text.find(signature)
    if start < 0:
        raise RuntimeError(f"{label}: signature not found in {path}")
    if text.find(signature, start + 1) >= 0:
        raise RuntimeError(f"{label}: signature is not unique in {path}")

    brace = text.find("{", start)
    if brace < 0:
        raise RuntimeError(f"{label}: opening brace not found in {path}")

    depth = 0
    end = None
    for index in range(brace, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                if end < len(text) and text[end] == "\n":
                    end += 1
                break

    if end is None:
        raise RuntimeError(f"{label}: closing brace not found in {path}")

    path.write_text(text[:start] + replacement + text[end:])
    print(f"updated {path}: {label}")


page_table = Path("src/core/hle/kernel/k_page_table_base.cpp")
replace_function(
    page_table,
    "Result KPageTableBase::UnlockForTransferMemory(",
    '''Result KPageTableBase::UnlockForTransferMemory(KProcessAddress address, size_t size,
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
''',
    "symmetric DeviceShared transfer unlock",
)

nvmap = Path("src/core/hle/service/nvdrv/core/nvmap.cpp")
replace_function(
    nvmap,
    "void NvMap::UnpinHandle(Handle::Id handle)",
    '''void NvMap::UnpinHandle(Handle::Id handle) {
    auto handle_description{GetHandle(handle)};
    if (!handle_description) {
        return;
    }

    std::scoped_lock lock(handle_description->mutex);
    if (handle_description->pins <= 0) {
        LOG_WARNING(Service_NVDRV,
                    "V32_COMPAT ignoring unmatched nvmap unpin for handle={}", handle);
        handle_description->pins = 0;
        return;
    }

    --handle_description->pins;
    if (!handle_description->pins && !handle_description->unmap_queue_entry) {
        std::scoped_lock queueLock(unmap_queue_lock);
        unmap_queue.push_back(handle_description);
        handle_description->unmap_queue_entry = std::prev(unmap_queue.end());
    }
}
''',
    "clamp nvmap pin underflow",
)
