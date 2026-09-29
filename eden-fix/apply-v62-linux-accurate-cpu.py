#!/usr/bin/env python3
from pathlib import Path

p = Path("src/core/arm/dynarmic/arm_dynarmic_64.cpp")
s = p.read_text()

old = """void ArmDynarmic64::MakeJit(Common::PageTable* page_table, std::size_t address_space_bits) {
    Dynarmic::A64::UserConfig config;

    // Callbacks
"""

new = """void ArmDynarmic64::MakeJit(Common::PageTable* page_table, std::size_t address_space_bits) {
    Dynarmic::A64::UserConfig config;

    // Minecraft split-screen is stable enough to reach a repeatable ~21 minute guest ARM
    // failure, with multiple threads branching through address zero. Test whether Dynarmic's
    // Auto-mode unsafe optimizations are corrupting long-lived guest state by using the Accurate
    // configuration for Minecraft only. Do not alter the user's setting or any other title.
    const auto requested_cpu_accuracy = Settings::values.cpu_accuracy.GetValue();
    const bool v62_minecraft_accurate =
        m_cb.has_value() && m_cb->m_process != nullptr &&
        m_cb->m_process->GetProgramId() == 0x0100D71004694000ULL;
    const auto effective_cpu_accuracy =
        v62_minecraft_accurate ? Settings::CpuAccuracy::Accurate : requested_cpu_accuracy;

    if (v62_minecraft_accurate) {
        LOG_WARNING(Core_ARM,
                    "V62_FIX MinecraftCpuAccuracy requested={} effective={} address_space_bits={}",
                    static_cast<u32>(requested_cpu_accuracy),
                    static_cast<u32>(effective_cpu_accuracy), address_space_bits);
    }

    // Callbacks
"""

count=s.count(old)
if count != 1:
    raise RuntimeError(f"v62 MakeJit prologue anchor: expected 1 match, found {count}")
s=s.replace(old,new,1)

old_switch="""    switch (Settings::values.cpu_accuracy.GetValue()) {
"""
new_switch="""    switch (effective_cpu_accuracy) {
"""
count=s.count(old_switch)
if count != 1:
    raise RuntimeError(f"v62 CPU accuracy switch anchor: expected 1 match, found {count}")
s=s.replace(old_switch,new_switch,1)

p.write_text(s)
print("applied v62 Minecraft-only Dynarmic Accurate CPU mode")
