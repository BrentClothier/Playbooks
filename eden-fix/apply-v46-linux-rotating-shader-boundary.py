#!/usr/bin/env python3
"""Repair Minecraft's rotating 0xff30 split-screen UI shader variant."""
from pathlib import Path


def replace_once(name: str, old: str, new: str) -> None:
    path = Path(name)
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{name}: expected one match, found {count}")
    path.write_text(text.replace(old, new, 1))
    print(f"updated {name}")


replace_once(
    "src/video_core/shader_cache.cpp",
    '''            GraphicsEnvironment env{*maxwell3d, *gpu_memory, program, base_addr, start_address};
            shader_info = MakeShaderInfo(env, *cpu_shader_addr);''',
    '''            GraphicsEnvironment env{*maxwell3d, *gpu_memory, program, base_addr, start_address};
            env.SetRejectInvalidShaders(program_id == 0x0100D71004694000ULL);
            shader_info = MakeShaderInfo(env, *cpu_shader_addr);''',
)

replace_once(
    "src/video_core/shader_environment.cpp",
    '''        u64* const data = code.data() + offset / INST_SIZE;
        gpu_memory->ReadBlock(guest_addr, data, BLOCK_SIZE);
        for (size_t index = 0; index < BLOCK_SIZE; index += INST_SIZE) {''',
    '''        u64* const data = code.data() + offset / INST_SIZE;
        gpu_memory->ReadBlock(guest_addr, data, BLOCK_SIZE);

        // Minecraft rotates this split-screen UI vertex shader to 0xff30. Its zero-filled
        // boundary instruction is inside the first mapped block, but no normal terminator appears
        // before v42 reaches the next unmapped range. Synthesize only the confirmed boundary so
        // size discovery can retain the draw; every other malformed shader keeps v42's rejection.
        constexpr u32 RotatingShaderStart = 0xff30;
        constexpr u32 RotatingShaderExit = 0x10008;
        if (RejectInvalidShaders() && static_cast<u32>(stage) == 0 &&
            start_address == RotatingShaderStart && offset == 0) {
            constexpr size_t repair_offset = RotatingShaderExit - RotatingShaderStart;
            u64& boundary_instruction = data[repair_offset / INST_SIZE];
            if (boundary_instruction == 0) {
                boundary_instruction = EXIT_VALUE;
                static std::atomic<u32> discovered_rotating_boundary_count{};
                const u32 count = discovered_rotating_boundary_count.fetch_add(
                    1, std::memory_order_relaxed);
                if (count < 32) {
                    LOG_WARNING(HW_GPU,
                                "V46_FIX DiscoverRotatingShaderBoundary count={} stage={} "
                                "start={:#x} pc={:#x}",
                                count, static_cast<u32>(stage), start_address,
                                RotatingShaderExit);
                }
                return repair_offset + INST_SIZE;
            }
        }

        for (size_t index = 0; index < BLOCK_SIZE; index += INST_SIZE) {''',
)

replace_once(
    "src/video_core/shader_environment.cpp",
    '''        if (stage == 0 && address == 0x10008 && insn == 0 &&
            (start == 0xfd30 || start == 0xfe30)) {
            constexpr u64 MaxwellExitInstruction = 0xe30000000007000fULL;
            static std::atomic<u32> repaired_boundary_count{};
            const u32 count =
                repaired_boundary_count.fetch_add(1, std::memory_order_relaxed);
            if (count < 32) {
                LOG_WARNING(HW_GPU,
                            "V44_FIX RepairShaderBoundary count={} stage={} start={:#x} "
                            "pc={:#x}",
                            count, stage, start, address);
            }
            return MaxwellExitInstruction;
        }''',
    '''        if (stage == 0 && address == 0x10008 && insn == 0 &&
            (start == 0xfd30 || start == 0xfe30 || start == 0xff30)) {
            constexpr u64 MaxwellExitInstruction = 0xe30000000007000fULL;
            static std::atomic<u32> repaired_boundary_count{};
            const u32 count =
                repaired_boundary_count.fetch_add(1, std::memory_order_relaxed);
            if (count < 32) {
                if (start == 0xff30) {
                    LOG_WARNING(HW_GPU,
                                "V46_FIX RepairRotatingShaderBoundary count={} stage={} "
                                "start={:#x} pc={:#x}",
                                count, stage, start, address);
                } else {
                    LOG_WARNING(HW_GPU,
                                "V44_FIX RepairShaderBoundary count={} stage={} start={:#x} "
                                "pc={:#x}",
                                count, stage, start, address);
                }
            }
            return MaxwellExitInstruction;
        }''',
)

print("applied v46 Linux Minecraft rotating shader-boundary repair")
