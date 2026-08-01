#!/usr/bin/env python3
from pathlib import Path

path = Path("src/core/hle/kernel/k_page_table_base.cpp")
text = path.read_text()

old_include = '''#include "core/hle/kernel/k_page_table_base.h"\n'''
new_include = '''#include "core/hle/kernel/k_page_table_base.h"\n#include "core/hle/kernel/k_process.h"\n'''
if text.count(old_include) != 1:
    raise RuntimeError("expected one k_page_table_base include")
text = text.replace(old_include, new_include, 1)

old = '''Result KPageTableBase::LockForTransferMemory(KPageGroup* out, KProcessAddress address, size_t size,\n                                             KMemoryPermission perm) {\n    R_RETURN(this->LockMemoryAndOpen(out, nullptr, address, size, KMemoryState::FlagCanTransfer,\n                                     KMemoryState::FlagCanTransfer, KMemoryPermission::All,\n                                     KMemoryPermission::UserReadWrite, KMemoryAttribute::All,\n                                     KMemoryAttribute::None, perm, KMemoryAttribute::Locked));\n}\n'''

new = '''Result KPageTableBase::LockForTransferMemory(KPageGroup* out, KProcessAddress address, size_t size,\n                                             KMemoryPermission perm) {\n    const bool minecraft_device_shared_compat =\n        GetCurrentProcess(m_system.Kernel()).GetProgramId() == 0x0100D71004694000ULL;\n\n    const auto attribute_mask = minecraft_device_shared_compat\n                                    ? static_cast<KMemoryAttribute>(\n                                          KMemoryAttribute::All &\n                                          ~KMemoryAttribute::DeviceShared)\n                                    : KMemoryAttribute::All;\n\n    if (minecraft_device_shared_compat) {\n        LOG_WARNING(Kernel_SVC,\n                    "V17_COMPAT allowing DeviceShared transfer-memory source address={:#x} size={:#x}",\n                    GetInteger(address), size);\n    }\n\n    R_RETURN(this->LockMemoryAndOpen(out, nullptr, address, size, KMemoryState::FlagCanTransfer,\n                                     KMemoryState::FlagCanTransfer, KMemoryPermission::All,\n                                     KMemoryPermission::UserReadWrite, attribute_mask,\n                                     KMemoryAttribute::None, perm, KMemoryAttribute::Locked));\n}\n'''

count = text.count(old)
if count != 1:
    raise RuntimeError(f"expected one LockForTransferMemory block, found {count}")

path.write_text(text.replace(old, new, 1))
print(f"updated {path}")
