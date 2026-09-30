#!/usr/bin/env python3
from pathlib import Path

TITLE_ID = "0x0100D71004694000ULL"
TRACKED_PAGE = "0x00001200000000ULL"

p = Path("src/core/arm/dynarmic/arm_dynarmic_64.cpp")
s = p.read_text()

old = '#include "common/settings.h"\n'
new = '#include <atomic>\n\n#include "common/settings.h"\n'
if old not in s:
    raise RuntimeError("v63 include anchor not found")
s = s.replace(old, new, 1)

old = '''u8 DynarmicCallbacks64::MemoryRead8(u64 vaddr) {
    CheckMemoryAccess(vaddr, 1, Kernel::DebugWatchpointType::Read);
    return m_memory.Read8(vaddr);
}
'''
new = '''u8 DynarmicCallbacks64::MemoryRead8(u64 vaddr) {
    if (m_process != nullptr && m_process->GetProgramId() == 0x0100D71004694000ULL &&
        (vaddr & ~0xfffULL) == 0x00001200000000ULL &&
        !m_memory.IsValidVirtualAddressRange(vaddr, 1)) {
        static std::atomic<u64> v63_read_count{0};
        const u64 count = v63_read_count.fetch_add(1, std::memory_order_relaxed) + 1;
        if (count <= 16 || (count & (count - 1)) == 0) {
            LOG_WARNING(Core_ARM,
                        "V63_DIAG MinecraftUnmappedRead8 count={} addr={:#x} pc={:#x} "
                        "lr={:#x} x0={:#x} x1={:#x} x2={:#x} x8={:#x} "
                        "x19={:#x} x20={:#x} x21={:#x} x22={:#x}",
                        count, vaddr, m_parent.m_jit->GetPC(),
                        m_parent.m_jit->GetRegister(30), m_parent.m_jit->GetRegister(0),
                        m_parent.m_jit->GetRegister(1), m_parent.m_jit->GetRegister(2),
                        m_parent.m_jit->GetRegister(8), m_parent.m_jit->GetRegister(19),
                        m_parent.m_jit->GetRegister(20), m_parent.m_jit->GetRegister(21),
                        m_parent.m_jit->GetRegister(22));
            if (count == 1) {
                m_parent.LogBacktrace(m_process);
            }
        }
    }
    CheckMemoryAccess(vaddr, 1, Kernel::DebugWatchpointType::Read);
    return m_memory.Read8(vaddr);
}
'''
if s.count(old) != 1:
    raise RuntimeError(f"v63 MemoryRead8 anchor count={s.count(old)}")
s = s.replace(old, new, 1)

old = '''void DynarmicCallbacks64::MemoryWrite8(u64 vaddr, u8 value) {
    if (CheckMemoryAccess(vaddr, 1, Kernel::DebugWatchpointType::Write)) {
        m_memory.Write8(vaddr, value);
    }
}
'''
new = '''void DynarmicCallbacks64::MemoryWrite8(u64 vaddr, u8 value) {
    if (m_process != nullptr && m_process->GetProgramId() == 0x0100D71004694000ULL &&
        (vaddr & ~0xfffULL) == 0x00001200000000ULL &&
        !m_memory.IsValidVirtualAddressRange(vaddr, 1)) {
        static std::atomic<u64> v63_write_count{0};
        const u64 count = v63_write_count.fetch_add(1, std::memory_order_relaxed) + 1;
        if (count <= 16 || (count & (count - 1)) == 0) {
            LOG_WARNING(Core_ARM,
                        "V63_DIAG MinecraftUnmappedWrite8 count={} addr={:#x} value={:#x} "
                        "pc={:#x} lr={:#x} x0={:#x} x1={:#x} x2={:#x} x8={:#x} "
                        "x19={:#x} x20={:#x} x21={:#x} x22={:#x}",
                        count, vaddr, value, m_parent.m_jit->GetPC(),
                        m_parent.m_jit->GetRegister(30), m_parent.m_jit->GetRegister(0),
                        m_parent.m_jit->GetRegister(1), m_parent.m_jit->GetRegister(2),
                        m_parent.m_jit->GetRegister(8), m_parent.m_jit->GetRegister(19),
                        m_parent.m_jit->GetRegister(20), m_parent.m_jit->GetRegister(21),
                        m_parent.m_jit->GetRegister(22));
            if (count == 1) {
                m_parent.LogBacktrace(m_process);
            }
        }
    }
    if (CheckMemoryAccess(vaddr, 1, Kernel::DebugWatchpointType::Write)) {
        m_memory.Write8(vaddr, value);
    }
}
'''
if s.count(old) != 1:
    raise RuntimeError(f"v63 MemoryWrite8 anchor count={s.count(old)}")
s = s.replace(old, new, 1)
p.write_text(s)

p = Path("src/core/memory.cpp")
s = p.read_text()
old = '''        if (auto const ptr = GetPointerImpl(addr, [addr]() {
            LOG_ERROR(HW_Memory, "Unmapped Read{} @ {:#016x}", sizeof(T) * 8, addr);
        }, [&]() {
'''
new = '''        if (auto const ptr = GetPointerImpl(addr, [this, addr]() {
            const bool v63_sampled_minecraft_page =
                system.GetApplicationProcessProgramID() == 0x0100D71004694000ULL &&
                (addr & ~0xfffULL) == 0x00001200000000ULL;
            if (!v63_sampled_minecraft_page) {
                LOG_ERROR(HW_Memory, "Unmapped Read{} @ {:#016x}", sizeof(T) * 8, addr);
            }
        }, [&]() {
'''
if s.count(old) != 1:
    raise RuntimeError(f"v63 Read logging anchor count={s.count(old)}")
s = s.replace(old, new, 1)

old = '''        if (auto const ptr = GetPointerImpl(addr, [addr, data]() {
            LOG_ERROR(HW_Memory, "Unmapped Write{} @ {:#016x} = {:#016x}", sizeof(T) * 8, addr, u64(data));
        }, [&]() { HandleRasterizerWrite(addr, sizeof(T)); }); ptr) [[likely]]
'''
new = '''        if (auto const ptr = GetPointerImpl(addr, [this, addr, data]() {
            const bool v63_sampled_minecraft_page =
                system.GetApplicationProcessProgramID() == 0x0100D71004694000ULL &&
                (addr & ~0xfffULL) == 0x00001200000000ULL;
            if (!v63_sampled_minecraft_page) {
                LOG_ERROR(HW_Memory, "Unmapped Write{} @ {:#016x} = {:#016x}", sizeof(T) * 8, addr, u64(data));
            }
        }, [&]() { HandleRasterizerWrite(addr, sizeof(T)); }); ptr) [[likely]]
'''
if s.count(old) != 1:
    raise RuntimeError(f"v63 Write logging anchor count={s.count(old)}")
s = s.replace(old, new, 1)
p.write_text(s)

print("applied v63 Minecraft unmapped graphics-page diagnostics")
