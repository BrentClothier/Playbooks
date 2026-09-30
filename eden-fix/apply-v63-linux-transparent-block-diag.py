#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))
    print(f"updated {path}: {label}")


# V63 is diagnostic-only. It must not change the known-good v62 execution behavior.
# It traces the transient transparent-block event seen during the long v62 test, where
# Minecraft repeatedly accessed a tiny unmapped CPU virtual-address window near
# 0x00001200000000 while gameplay continued and later recovered.

# ---------------------------------------------------------------------------
# 1. Capture the live Dynarmic guest PC/registers at accesses to the suspect range.
# ---------------------------------------------------------------------------
arm_h = Path("src/core/arm/dynarmic/arm_dynarmic_64.h")
replace_once(
    arm_h,
    """    bool CheckMemoryAccess(u64 addr, u64 size, Kernel::DebugWatchpointType type);
    void ReturnException(u64 pc, Dynarmic::HaltReason hr);
""",
    """    bool CheckMemoryAccess(u64 addr, u64 size, Kernel::DebugWatchpointType type);
    void ReturnException(u64 pc, Dynarmic::HaltReason hr);
    void TraceV63MemoryAccess(u64 vaddr, u64 size, bool write, u64 value);
""",
    "declare V63 live guest-memory trace",
)
replace_once(
    arm_h,
    """    const bool m_debugger_enabled{};
    const bool m_check_memory_access{};
    static constexpr u64 MinimumRunCycles = 10000U;
""",
    """    const bool m_debugger_enabled{};
    const bool m_check_memory_access{};
    u64 m_v63_memory_diag_count{};
    static constexpr u64 MinimumRunCycles = 10000U;
""",
    "add V63 per-core trace counter",
)

arm_cpp = Path("src/core/arm/dynarmic/arm_dynarmic_64.cpp")
trace_impl = r'''void DynarmicCallbacks64::TraceV63MemoryAccess(u64 vaddr, u64 size, bool write, u64 value) {
    constexpr u64 V63TargetBegin = 0x00001200000000ULL;
    constexpr u64 V63TargetEnd = 0x00001200010000ULL;
    constexpr u64 MinecraftTitleId = 0x0100D71004694000ULL;

    if (m_process == nullptr || m_process->GetProgramId() != MinecraftTitleId ||
        vaddr >= V63TargetEnd || vaddr + size <= V63TargetBegin) {
        return;
    }

    const u64 count = ++m_v63_memory_diag_count;
    // The old generic logger produced hundreds of thousands of lines. Capture the first
    // 64 accesses per emulated core in detail, then one sample every 8192 accesses.
    if (count > 64 && (count % 8192) != 0) {
        return;
    }

    const auto& jit = *m_parent.m_jit;
    const u64 jit_pc = jit.GetPC();
    const u64 pc = jit_pc >= 4 ? jit_pc - 4 : jit_pc;
    const auto regs = jit.GetRegisters();
    const u32 instruction =
        m_memory.IsValidVirtualAddressRange(pc, sizeof(u32)) ? m_memory.Read32(pc) : 0;

    LOG_WARNING(Core_ARM,
                "V63_DIAG GuestMemoryAccess core={} count={} op={} addr={:#016x} size={} "
                "value={:#016x} pc={:#016x} jit_pc={:#016x} inst={:#010x} sp={:#016x}",
                m_parent.m_core_index, count, write ? "W" : "R", vaddr, size, value, pc,
                jit_pc, instruction, jit.GetSP());
    LOG_WARNING(Core_ARM,
                "V63_DIAG GuestRegsA core={} count={} x0={:#016x} x1={:#016x} "
                "x2={:#016x} x3={:#016x} x4={:#016x} x5={:#016x} x6={:#016x} x7={:#016x}",
                m_parent.m_core_index, count, regs[0], regs[1], regs[2], regs[3], regs[4],
                regs[5], regs[6], regs[7]);
    LOG_WARNING(Core_ARM,
                "V63_DIAG GuestRegsB core={} count={} x8={:#016x} x9={:#016x} "
                "x10={:#016x} x11={:#016x} x12={:#016x} x13={:#016x} x14={:#016x} "
                "x15={:#016x}",
                m_parent.m_core_index, count, regs[8], regs[9], regs[10], regs[11], regs[12],
                regs[13], regs[14], regs[15]);
    LOG_WARNING(Core_ARM,
                "V63_DIAG GuestRegsC core={} count={} x16={:#016x} x17={:#016x} "
                "x18={:#016x} x19={:#016x} x20={:#016x} x21={:#016x} x22={:#016x} "
                "x23={:#016x}",
                m_parent.m_core_index, count, regs[16], regs[17], regs[18], regs[19], regs[20],
                regs[21], regs[22], regs[23]);
    LOG_WARNING(Core_ARM,
                "V63_DIAG GuestRegsD core={} count={} x24={:#016x} x25={:#016x} "
                "x26={:#016x} x27={:#016x} x28={:#016x} x29={:#016x} x30={:#016x}",
                m_parent.m_core_index, count, regs[24], regs[25], regs[26], regs[27], regs[28],
                regs[29], regs[30]);
}

'''
replace_once(
    arm_cpp,
    """u8 DynarmicCallbacks64::MemoryRead8(u64 vaddr) {
""",
    trace_impl + """u8 DynarmicCallbacks64::MemoryRead8(u64 vaddr) {
""",
    "implement V63 live guest-memory trace",
)

read_replacements = [
    (
        """u8 DynarmicCallbacks64::MemoryRead8(u64 vaddr) {
    CheckMemoryAccess(vaddr, 1, Kernel::DebugWatchpointType::Read);
    return m_memory.Read8(vaddr);
}
""",
        """u8 DynarmicCallbacks64::MemoryRead8(u64 vaddr) {
    TraceV63MemoryAccess(vaddr, 1, false, 0);
    CheckMemoryAccess(vaddr, 1, Kernel::DebugWatchpointType::Read);
    return m_memory.Read8(vaddr);
}
""",
        "trace MemoryRead8",
    ),
    (
        """u16 DynarmicCallbacks64::MemoryRead16(u64 vaddr) {
    CheckMemoryAccess(vaddr, 2, Kernel::DebugWatchpointType::Read);
    return m_memory.Read16(vaddr);
}
""",
        """u16 DynarmicCallbacks64::MemoryRead16(u64 vaddr) {
    TraceV63MemoryAccess(vaddr, 2, false, 0);
    CheckMemoryAccess(vaddr, 2, Kernel::DebugWatchpointType::Read);
    return m_memory.Read16(vaddr);
}
""",
        "trace MemoryRead16",
    ),
    (
        """u32 DynarmicCallbacks64::MemoryRead32(u64 vaddr) {
    CheckMemoryAccess(vaddr, 4, Kernel::DebugWatchpointType::Read);
    return m_memory.Read32(vaddr);
}
""",
        """u32 DynarmicCallbacks64::MemoryRead32(u64 vaddr) {
    TraceV63MemoryAccess(vaddr, 4, false, 0);
    CheckMemoryAccess(vaddr, 4, Kernel::DebugWatchpointType::Read);
    return m_memory.Read32(vaddr);
}
""",
        "trace MemoryRead32",
    ),
    (
        """u64 DynarmicCallbacks64::MemoryRead64(u64 vaddr) {
    CheckMemoryAccess(vaddr, 8, Kernel::DebugWatchpointType::Read);
    return m_memory.Read64(vaddr);
}
""",
        """u64 DynarmicCallbacks64::MemoryRead64(u64 vaddr) {
    TraceV63MemoryAccess(vaddr, 8, false, 0);
    CheckMemoryAccess(vaddr, 8, Kernel::DebugWatchpointType::Read);
    return m_memory.Read64(vaddr);
}
""",
        "trace MemoryRead64",
    ),
    (
        """Dynarmic::A64::Vector DynarmicCallbacks64::MemoryRead128(u64 vaddr) {
    CheckMemoryAccess(vaddr, 16, Kernel::DebugWatchpointType::Read);
    return {m_memory.Read64(vaddr), m_memory.Read64(vaddr + 8)};
}
""",
        """Dynarmic::A64::Vector DynarmicCallbacks64::MemoryRead128(u64 vaddr) {
    TraceV63MemoryAccess(vaddr, 16, false, 0);
    CheckMemoryAccess(vaddr, 16, Kernel::DebugWatchpointType::Read);
    return {m_memory.Read64(vaddr), m_memory.Read64(vaddr + 8)};
}
""",
        "trace MemoryRead128",
    ),
]
for old, new, label in read_replacements:
    replace_once(arm_cpp, old, new, label)

write_replacements = [
    (
        """void DynarmicCallbacks64::MemoryWrite8(u64 vaddr, u8 value) {
    if (CheckMemoryAccess(vaddr, 1, Kernel::DebugWatchpointType::Write)) {
        m_memory.Write8(vaddr, value);
    }
}
""",
        """void DynarmicCallbacks64::MemoryWrite8(u64 vaddr, u8 value) {
    TraceV63MemoryAccess(vaddr, 1, true, value);
    if (CheckMemoryAccess(vaddr, 1, Kernel::DebugWatchpointType::Write)) {
        m_memory.Write8(vaddr, value);
    }
}
""",
        "trace MemoryWrite8",
    ),
    (
        """void DynarmicCallbacks64::MemoryWrite16(u64 vaddr, u16 value) {
    if (CheckMemoryAccess(vaddr, 2, Kernel::DebugWatchpointType::Write)) {
        m_memory.Write16(vaddr, value);
    }
}
""",
        """void DynarmicCallbacks64::MemoryWrite16(u64 vaddr, u16 value) {
    TraceV63MemoryAccess(vaddr, 2, true, value);
    if (CheckMemoryAccess(vaddr, 2, Kernel::DebugWatchpointType::Write)) {
        m_memory.Write16(vaddr, value);
    }
}
""",
        "trace MemoryWrite16",
    ),
    (
        """void DynarmicCallbacks64::MemoryWrite32(u64 vaddr, u32 value) {
    if (CheckMemoryAccess(vaddr, 4, Kernel::DebugWatchpointType::Write)) {
        m_memory.Write32(vaddr, value);
    }
}
""",
        """void DynarmicCallbacks64::MemoryWrite32(u64 vaddr, u32 value) {
    TraceV63MemoryAccess(vaddr, 4, true, value);
    if (CheckMemoryAccess(vaddr, 4, Kernel::DebugWatchpointType::Write)) {
        m_memory.Write32(vaddr, value);
    }
}
""",
        "trace MemoryWrite32",
    ),
    (
        """void DynarmicCallbacks64::MemoryWrite64(u64 vaddr, u64 value) {
    if (CheckMemoryAccess(vaddr, 8, Kernel::DebugWatchpointType::Write)) {
        m_memory.Write64(vaddr, value);
    }
}
""",
        """void DynarmicCallbacks64::MemoryWrite64(u64 vaddr, u64 value) {
    TraceV63MemoryAccess(vaddr, 8, true, value);
    if (CheckMemoryAccess(vaddr, 8, Kernel::DebugWatchpointType::Write)) {
        m_memory.Write64(vaddr, value);
    }
}
""",
        "trace MemoryWrite64",
    ),
    (
        """void DynarmicCallbacks64::MemoryWrite128(u64 vaddr, Dynarmic::A64::Vector value) {
    if (CheckMemoryAccess(vaddr, 16, Kernel::DebugWatchpointType::Write)) {
        m_memory.Write64(vaddr, value[0]);
        m_memory.Write64(vaddr + 8, value[1]);
    }
}
""",
        """void DynarmicCallbacks64::MemoryWrite128(u64 vaddr, Dynarmic::A64::Vector value) {
    TraceV63MemoryAccess(vaddr, 16, true, value[0]);
    if (CheckMemoryAccess(vaddr, 16, Kernel::DebugWatchpointType::Write)) {
        m_memory.Write64(vaddr, value[0]);
        m_memory.Write64(vaddr + 8, value[1]);
    }
}
""",
        "trace MemoryWrite128",
    ),
]
for old, new, label in write_replacements:
    replace_once(arm_cpp, old, new, label)


# ---------------------------------------------------------------------------
# 2. Trace CPU map/unmap and rasterizer-cache transitions for the suspect VAddr,
#    while rate-limiting the pre-existing generic unmapped Read/Write spam.
# ---------------------------------------------------------------------------
memory_cpp = Path("src/core/memory.cpp")
replace_once(
    memory_cpp,
    """#include <algorithm>
#include <cstring>
""",
    """#include <algorithm>
#include <atomic>
#include <cstring>
""",
    "include atomic for V63 log rate limiting",
)

replace_once(
    memory_cpp,
    """namespace Core::Memory {

static inline bool AddressSpaceContains""",
    """namespace Core::Memory {

namespace {
constexpr u64 V63DiagBegin = 0x00001200000000ULL;
constexpr u64 V63DiagEnd = 0x00001200010000ULL;

[[nodiscard]] bool V63DiagIntersects(u64 address, u64 size) {
    return address < V63DiagEnd && address + size > V63DiagBegin;
}

std::atomic<u64> v63_unmapped_read_count{};
std::atomic<u64> v63_unmapped_write_count{};

[[nodiscard]] bool V63DiagShouldLog(std::atomic<u64>& counter) {
    const u64 count = counter.fetch_add(1, std::memory_order_relaxed) + 1;
    return count <= 32 || (count % 8192) == 0;
}
} // namespace

static inline bool AddressSpaceContains""",
    "add V63 suspect-range helpers",
)

replace_once(
    memory_cpp,
    """    void MapMemoryRegion(Common::PageTable& page_table, Common::ProcessAddress base, u64 size,
                         Common::PhysicalAddress target, Common::MemoryPermission perms,
                         bool separate_heap) {
        ASSERT_MSG((size & YUZU_PAGEMASK) == 0, "non-page aligned size: {:016X}", size);
""",
    """    void MapMemoryRegion(Common::PageTable& page_table, Common::ProcessAddress base, u64 size,
                         Common::PhysicalAddress target, Common::MemoryPermission perms,
                         bool separate_heap) {
        if (V63DiagIntersects(GetInteger(base), size)) {
            LOG_WARNING(HW_Memory,
                        "V63_DIAG CpuMap base={:#016x} size={:#x} phys={:#016x} perms={:#x} "
                        "separate_heap={}",
                        GetInteger(base), size, GetInteger(target), static_cast<u32>(perms),
                        separate_heap);
        }
        ASSERT_MSG((size & YUZU_PAGEMASK) == 0, "non-page aligned size: {:016X}", size);
""",
    "trace V63 CPU maps",
)

replace_once(
    memory_cpp,
    """    void UnmapRegion(Common::PageTable& page_table, Common::ProcessAddress base, u64 size,
                     bool separate_heap) {
        ASSERT_MSG((size & YUZU_PAGEMASK) == 0, "non-page aligned size: {:016X}", size);
""",
    """    void UnmapRegion(Common::PageTable& page_table, Common::ProcessAddress base, u64 size,
                     bool separate_heap) {
        if (V63DiagIntersects(GetInteger(base), size)) {
            LOG_WARNING(HW_Memory,
                        "V63_DIAG CpuUnmap base={:#016x} size={:#x} separate_heap={}",
                        GetInteger(base), size, separate_heap);
        }
        ASSERT_MSG((size & YUZU_PAGEMASK) == 0, "non-page aligned size: {:016X}", size);
""",
    "trace V63 CPU unmaps",
)

replace_once(
    memory_cpp,
    """        if (auto const ptr = GetPointerImpl(addr, [addr]() {
            LOG_ERROR(HW_Memory, "Unmapped Read{} @ {:#016x}", sizeof(T) * 8, addr);
        }, [&]() {
""",
    """        if (auto const ptr = GetPointerImpl(addr, [addr]() {
            if (!V63DiagIntersects(addr, sizeof(T)) ||
                V63DiagShouldLog(v63_unmapped_read_count)) {
                LOG_ERROR(HW_Memory, "Unmapped Read{} @ {:#016x}", sizeof(T) * 8, addr);
            }
        }, [&]() {
""",
    "rate-limit V63 suspect unmapped reads",
)

replace_once(
    memory_cpp,
    """        if (auto const ptr = GetPointerImpl(addr, [addr, data]() {
            LOG_ERROR(HW_Memory, "Unmapped Write{} @ {:#016x} = {:#016x}", sizeof(T) * 8, addr, u64(data));
        }, [&]() { HandleRasterizerWrite(addr, sizeof(T)); }); ptr) [[likely]]
""",
    """        if (auto const ptr = GetPointerImpl(addr, [addr, data]() {
            if (!V63DiagIntersects(addr, sizeof(T)) ||
                V63DiagShouldLog(v63_unmapped_write_count)) {
                LOG_ERROR(HW_Memory, "Unmapped Write{} @ {:#016x} = {:#016x}",
                          sizeof(T) * 8, addr, u64(data));
            }
        }, [&]() { HandleRasterizerWrite(addr, sizeof(T)); }); ptr) [[likely]]
""",
    "rate-limit V63 suspect unmapped writes",
)

replace_once(
    memory_cpp,
    """    void RasterizerMarkRegionCached(u64 vaddr, u64 size, bool cached) {
        if (vaddr == 0 || !AddressSpaceContains(*current_page_table, vaddr, size)) {
            return;
        }
""",
    """    void RasterizerMarkRegionCached(u64 vaddr, u64 size, bool cached) {
        if (V63DiagIntersects(vaddr, size)) {
            LOG_WARNING(HW_Memory,
                        "V63_DIAG RasterizerCacheRange base={:#016x} size={:#x} cached={}",
                        vaddr, size, cached);
        }
        if (vaddr == 0 || !AddressSpaceContains(*current_page_table, vaddr, size)) {
            return;
        }
""",
    "trace V63 rasterizer cache ranges",
)

replace_once(
    memory_cpp,
    """        for (u64 i = 0; i < num_pages; ++i, vaddr += YUZU_PAGESIZE) {
            const Common::PageType page_type= current_page_table->entries[vaddr >> YUZU_PAGEBITS].ptr.Type();
            if (cached) {
""",
    """        for (u64 i = 0; i < num_pages; ++i, vaddr += YUZU_PAGESIZE) {
            const u64 page_vaddr = vaddr;
            const Common::PageType page_type= current_page_table->entries[vaddr >> YUZU_PAGEBITS].ptr.Type();
            if (V63DiagIntersects(page_vaddr, YUZU_PAGESIZE)) {
                LOG_WARNING(HW_Memory,
                            "V63_DIAG RasterizerCachePageBefore vaddr={:#016x} cached={} "
                            "type={} backing={:#016x}",
                            page_vaddr, cached, static_cast<u32>(page_type),
                            GetInteger(current_page_table->entries[vaddr >> YUZU_PAGEBITS].addr));
            }
            if (cached) {
""",
    "trace V63 rasterizer cache page before",
)

replace_once(
    memory_cpp,
    """                default:
                    UNREACHABLE();
                }
            }
        }
    }

    /**
     * Maps a region of pages as a specific type.
""",
    """                default:
                    UNREACHABLE();
                }
            }
            if (V63DiagIntersects(page_vaddr, YUZU_PAGESIZE)) {
                const Common::PageType after_type =
                    current_page_table->entries[page_vaddr >> YUZU_PAGEBITS].ptr.Type();
                LOG_WARNING(HW_Memory,
                            "V63_DIAG RasterizerCachePageAfter vaddr={:#016x} cached={} "
                            "type={} backing={:#016x}",
                            page_vaddr, cached, static_cast<u32>(after_type),
                            GetInteger(current_page_table->entries[page_vaddr >> YUZU_PAGEBITS].addr));
            }
        }
    }

    /**
     * Maps a region of pages as a specific type.
""",
    "trace V63 rasterizer cache page after",
)


# ---------------------------------------------------------------------------
# 3. Correlate CPU backing with GPU device virtual addresses and cache refcounts.
# ---------------------------------------------------------------------------
devmem = Path("src/core/device_memory_manager.inc")
replace_once(
    devmem,
    """namespace {

class MultiAddressContainer {
""",
    """namespace {

constexpr VAddr V63DiagCpuBegin = 0x00001200000000ULL;
constexpr VAddr V63DiagCpuEnd = 0x00001200010000ULL;

[[nodiscard]] bool V63DiagCpuIntersects(VAddr address, size_t size) {
    return address < V63DiagCpuEnd && address + size > V63DiagCpuBegin;
}

class MultiAddressContainer {
""",
    "add V63 device-memory suspect-range helper",
)

replace_once(
    devmem,
    """void DeviceMemoryManager<Traits>::Map(DAddr address, VAddr virtual_address, size_t size, Asid asid,
                                      bool track) {
    Core::Memory::Memory* process_memory = registered_processes[asid.id];
""",
    """void DeviceMemoryManager<Traits>::Map(DAddr address, VAddr virtual_address, size_t size, Asid asid,
                                      bool track) {
    Core::Memory::Memory* process_memory = registered_processes[asid.id];
    if (V63DiagCpuIntersects(virtual_address, size)) {
        LOG_WARNING(HW_Memory,
                    "V63_DIAG DeviceMap gpu={:#016x} cpu={:#016x} size={:#x} asid={} track={}",
                    address, virtual_address, size, asid.id, track);
    }
""",
    "trace V63 device mappings",
)

replace_once(
    devmem,
    """        auto* ptr = process_memory->GetPointerSilent(Common::ProcessAddress(new_vaddress));
        if (ptr == nullptr) [[unlikely]] {
            tracked_entries[start_page_d + i].compressed_physical_ptr = 0;
            continue;
        }
""",
    """        auto* ptr = process_memory->GetPointerSilent(Common::ProcessAddress(new_vaddress));
        if (ptr == nullptr) [[unlikely]] {
            if (V63DiagCpuIntersects(new_vaddress, Memory::YUZU_PAGESIZE)) {
                LOG_WARNING(HW_Memory,
                            "V63_DIAG DeviceMapMissingCpuBacking gpu_page={:#016x} "
                            "cpu_page={:#016x} asid={}",
                            address + i * Memory::YUZU_PAGESIZE, new_vaddress, asid.id);
            }
            tracked_entries[start_page_d + i].compressed_physical_ptr = 0;
            continue;
        }
""",
    "trace V63 missing CPU backing during device map",
)

replace_once(
    devmem,
    """    for (size_t i = 0; i < num_pages; i++) {
        auto phys_addr = tracked_entries[start_page_d + i].compressed_physical_ptr;
        tracked_entries[start_page_d + i].compressed_physical_ptr = 0;
""",
    """    for (size_t i = 0; i < num_pages; i++) {
        const auto [v63_asid, v63_cpu_vaddr] = ExtractCPUBacking(start_page_d + i);
        if (V63DiagCpuIntersects(v63_cpu_vaddr, Memory::YUZU_PAGESIZE)) {
            LOG_WARNING(HW_Memory,
                        "V63_DIAG DeviceUnmap gpu_page={:#016x} cpu_page={:#016x} asid={}",
                        address + i * Memory::YUZU_PAGESIZE, v63_cpu_vaddr, v63_asid.id);
        }
        auto phys_addr = tracked_entries[start_page_d + i].compressed_physical_ptr;
        tracked_entries[start_page_d + i].compressed_physical_ptr = 0;
""",
    "trace V63 device unmaps",
)

replace_once(
    devmem,
    """        auto [asid_2, vpage] = ExtractCPUBacking(page);
        vpage >>= Memory::YUZU_PAGEBITS;

        if (vpage == 0) [[unlikely]] {
""",
    """        auto [asid_2, vpage] = ExtractCPUBacking(page);
        const VAddr v63_cpu_vaddr = vpage;
        vpage >>= Memory::YUZU_PAGEBITS;

        if (vpage == 0) [[unlikely]] {
""",
    "retain V63 CPU backing before page shift",
)

replace_once(
    devmem,
    """        // Adds or subtracts 1, as count is a unsigned 8-bit value
        count.fetch_add(static_cast<CounterType>(delta), std::memory_order_release);

        // Assume delta is either -1 or 1
""",
    """        // Adds or subtracts 1, as count is a unsigned 8-bit value
        const auto v63_count_before = count.load(std::memory_order_relaxed);
        count.fetch_add(static_cast<CounterType>(delta), std::memory_order_release);
        const auto v63_count_after = count.load(std::memory_order_relaxed);
        if (V63DiagCpuIntersects(v63_cpu_vaddr, Memory::YUZU_PAGESIZE)) {
            LOG_WARNING(HW_Memory,
                        "V63_DIAG DeviceCacheRef gpu_page={:#016x} cpu_page={:#016x} "
                        "asid={} delta={} before={} after={}",
                        page << Memory::YUZU_PAGEBITS, v63_cpu_vaddr, asid_2.id, delta,
                        static_cast<u32>(v63_count_before), static_cast<u32>(v63_count_after));
        }

        // Assume delta is either -1 or 1
""",
    "trace V63 device cache reference transitions",
)

print("applied v63 transparent-block memory/GPU diagnostics")
