#!/usr/bin/env python3
from pathlib import Path

path = Path("src/core/hle/kernel/svc/svc_transfer_memory.cpp")
text = path.read_text()

old_include = '''#include "core/hle/kernel/k_process.h"\n'''
new_include = '''#include "core/hle/kernel/k_memory_block.h"\n#include "core/hle/kernel/k_process.h"\n'''
if text.count(old_include) != 1:
    raise RuntimeError("expected one k_process include")
text = text.replace(old_include, new_include, 1)

old = '''    // Initialize the transfer memory.\n    R_TRY(trmem->Initialize(system.Kernel(), address, size, map_perm));\n'''

new = '''    // Initialize the transfer memory.\n    const Result init_result = trmem->Initialize(system.Kernel(), address, size, map_perm);\n    if (init_result.IsError()) {\n        LOG_CRITICAL(Kernel_SVC,\n                     "V16_DIAG CreateTransferMemory failed address={:#x} size={:#x} perm={:#x}",\n                     address, size, static_cast<u32>(map_perm));\n\n        auto& page_table = process.GetPageTable();\n        const u64 end_address = address + size;\n        u64 current_address = address;\n        while (current_address < end_address) {\n            KMemoryInfo memory_info{};\n            PageInfo page_info{};\n            const Result query_result = page_table.QueryInfo(std::addressof(memory_info),\n                                                             std::addressof(page_info),\n                                                             current_address);\n            if (query_result.IsError()) {\n                LOG_CRITICAL(Kernel_SVC,\n                             "V16_DIAG QueryInfo failed at address={:#x}", current_address);\n                break;\n            }\n\n            const auto info = memory_info.GetSvcMemoryInfo();\n            LOG_CRITICAL(Kernel_SVC,\n                         "V16_DIAG memory block base={:#x} size={:#x} state={:#x} perm={:#x} attr={:#x}",\n                         info.base_address, info.size, static_cast<u32>(info.state),\n                         static_cast<u32>(info.permission), static_cast<u32>(info.attribute));\n\n            const u64 next_address = info.base_address + info.size;\n            if (next_address <= current_address) {\n                break;\n            }\n            current_address = next_address;\n        }\n\n        return init_result;\n    }\n'''

if text.count(old) != 1:
    raise RuntimeError("expected one transfer memory initialize block")
text = text.replace(old, new, 1)
path.write_text(text)
print(f"updated {path}")
