#!/usr/bin/env python3
from pathlib import Path

def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))
    print(f"updated {path}: {label}")

p = Path("src/core/arm/dynarmic/arm_dynarmic_64.cpp")

replace_once(
    p,
    '#include "core/hle/kernel/k_process.h"\n',
    '#include "core/hle/kernel/k_process.h"\n#include "core/hle/kernel/k_memory_block.h"\n#include "core/hle/kernel/svc_types.h"\n',
    "include page-table query types",
)

old = '''    const auto regs = jit.GetRegisters();
    const u32 instruction =
        m_memory.IsValidVirtualAddressRange(pc, sizeof(u32)) ? m_memory.Read32(pc) : 0;
'''
new = '''    const auto regs = jit.GetRegisters();

    if (count == 1) {
        const auto log_region = [&](const char* label, u64 query_address) {
            Kernel::KMemoryInfo mem_info{};
            Kernel::Svc::PageInfo page_info{};
            const auto result = m_process->GetPageTable().QueryInfo(
                std::addressof(mem_info), std::addressof(page_info), query_address);
            if (result.IsSuccess()) {
                const auto svc_info = mem_info.GetSvcMemoryInfo();
                LOG_WARNING(Core_ARM,
                            "V65_DIAG PageInfo label={} query={:#016x} base={:#016x} "
                            "size={:#x} state={:#x} attr={:#x} perm={:#x} ipc={} device={} "
                            "page_flags={:#x} valid={}",
                            label, query_address, svc_info.base_address, svc_info.size,
                            static_cast<u32>(svc_info.state),
                            static_cast<u32>(svc_info.attribute),
                            static_cast<u32>(svc_info.permission), svc_info.ipc_count,
                            svc_info.device_count, page_info.flags,
                            m_memory.IsValidVirtualAddressRange(query_address, 1));
            } else {
                LOG_WARNING(Core_ARM,
                            "V65_DIAG PageInfoFailed label={} query={:#016x} result={:#x} valid={}",
                            label, query_address, result.raw,
                            m_memory.IsValidVirtualAddressRange(query_address, 1));
            }
        };

        LOG_WARNING(Core_ARM,
                    "V65_DIAG FirstSuspectAccess target={:#016x} op={} size={} "
                    "x0={:#016x} x1={:#016x} x2={:#x} x3={:#016x} x4={:#016x} "
                    "x5={:#016x} lr={:#016x}",
                    vaddr, write ? "W" : "R", size, regs[0], regs[1], regs[2], regs[3],
                    regs[4], regs[5], regs[30]);

        log_region("target", vaddr);
        log_region("target_base", V63TargetBegin);
        log_region("x1", regs[1]);
        log_region("x3", regs[3]);
        log_region("sp", jit.GetSP());
        log_region("lr", regs[30]);

        constexpr s64 CodeOffsets[] = {-16, -12, -8, -4, 0, 4, 8, 12, 16};
        for (const s64 offset : CodeOffsets) {
            const u64 code_addr = static_cast<u64>(static_cast<s64>(jit_pc) + offset);
            if (m_memory.IsValidVirtualAddressRange(code_addr, sizeof(u32))) {
                LOG_WARNING(Core_ARM,
                            "V65_DIAG CodeWindow addr={:#016x} rel={} inst={:#010x}",
                            code_addr, offset, m_memory.Read32(code_addr));
            }
        }

        m_parent.LogBacktrace(m_process);
    }

    const u32 instruction =
        m_memory.IsValidVirtualAddressRange(pc, sizeof(u32)) ? m_memory.Read32(pc) : 0;
'''
replace_once(p, old, new, "add V65 first-hit page-table/backtrace diagnostics")

print("applied v65 suspect-pointer provenance diagnostics")
