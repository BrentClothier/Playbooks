#!/usr/bin/env python3
from pathlib import Path

p = Path("src/core/arm/dynarmic/arm_dynarmic_64.cpp")
s = p.read_text()

old = '''        LOG_WARNING(Core_ARM,
                    "V62_FIX MinecraftCpuAccuracy requested={} effective={} address_space_bits={}",
                    static_cast<u32>(requested_cpu_accuracy),
                    static_cast<u32>(effective_cpu_accuracy), address_space_bits);
'''
new = '''        LOG_WARNING(Core_ARM,
                    "V62_FIX MinecraftCpuAccuracy requested={} effective={} address_space_bits={}",
                    static_cast<u32>(requested_cpu_accuracy),
                    static_cast<u32>(effective_cpu_accuracy), address_space_bits);
        LOG_WARNING(Core_ARM,
                    "V64_DIAG Active transparent_block_trace=1 suspect_begin={:#x} suspect_end={:#x}",
                    0x00001200000000ULL, 0x00001200010000ULL);
'''

count = s.count(old)
if count != 1:
    raise RuntimeError(f"v64 startup marker anchor: expected 1 match, found {count}")

p.write_text(s.replace(old, new, 1))
print("applied v64 diagnostic startup marker")
