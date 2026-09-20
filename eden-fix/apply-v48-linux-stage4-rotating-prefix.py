#!/usr/bin/env python3
"""Repair Minecraft stage-4 rotating UI shaders without requiring an unmapped block tail."""
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
    "src/video_core/shader_environment.cpp",
    '''        const bool stage0_boundary =
            stage == 0 && (start == 0xfd30 || start == 0xfe30 || start == 0xff30);
        const bool stage4_boundary = stage == 4 && start == 0xff30;
        if (address == 0x10008 && insn == 0 && (stage0_boundary || stage4_boundary)) {
            constexpr u64 MaxwellExitInstruction = 0xe30000000007000fULL;
            static std::atomic<u32> repaired_boundary_count{};
            const u32 count =
                repaired_boundary_count.fetch_add(1, std::memory_order_relaxed);
            if (count < 32) {
                if (stage4_boundary) {
                    LOG_WARNING(HW_GPU,
                                "V47_FIX RepairStage4RotatingBoundary count={} stage={} "
                                "start={:#x} pc={:#x}",
                                count, stage, start, address);
                } else if (start == 0xff30) {
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
    '''        const bool stage0_boundary =
            stage == 0 && (start == 0xfd30 || start == 0xfe30 || start == 0xff30);
        const bool stage4_rotating_boundary =
            stage == 4 && start >= 0xf030 && start <= 0xff30 && (start & 0xff) == 0x30;
        if (address == 0x10008 && insn == 0 &&
            (stage0_boundary || stage4_rotating_boundary)) {
            constexpr u64 MaxwellExitInstruction = 0xe30000000007000fULL;
            static std::atomic<u32> repaired_boundary_count{};
            const u32 count =
                repaired_boundary_count.fetch_add(1, std::memory_order_relaxed);
            if (count < 32) {
                if (stage4_rotating_boundary) {
                    LOG_WARNING(HW_GPU,
                                "V48_FIX RepairStage4RotatingBoundary count={} stage={} "
                                "start={:#x} pc={:#x}",
                                count, stage, start, address);
                } else if (start == 0xff30) {
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

replace_once(
    "src/video_core/shader_environment.cpp",
    '''    while (size <= MAXIMUM_SIZE) {
        if (!gpu_memory->IsFullyMappedRange(guest_addr, BLOCK_SIZE)) {
            analysis_failure_address = guest_addr;
            analysis_stopped_at_unmapped_memory = true;
            return std::nullopt;
        }
        u64* const data = code.data() + offset / INST_SIZE;
        gpu_memory->ReadBlock(guest_addr, data, BLOCK_SIZE);

        // Minecraft rotates this split-screen UI vertex shader to 0xff30. Its zero-filled
        // boundary instruction is inside the first mapped block, but no normal terminator appears
        // before v42 reaches the next unmapped range. Synthesize only the confirmed boundary so
        // size discovery can retain the draw; every other malformed shader keeps v42's rejection.
        constexpr u32 RotatingShaderStart = 0xff30;
        constexpr u32 RotatingShaderExit = 0x10008;
        const u32 rotating_stage = static_cast<u32>(stage);
        if (RejectInvalidShaders() && (rotating_stage == 0 || rotating_stage == 4) &&
            start_address == RotatingShaderStart && offset == 0) {
            constexpr size_t repair_offset = RotatingShaderExit - RotatingShaderStart;
            u64& boundary_instruction = data[repair_offset / INST_SIZE];
            if (boundary_instruction == 0) {
                boundary_instruction = EXIT_VALUE;
                static std::atomic<u32> discovered_rotating_boundary_count{};
                const u32 count = discovered_rotating_boundary_count.fetch_add(
                    1, std::memory_order_relaxed);
                if (count < 32) {
                    if (rotating_stage == 4) {
                        LOG_WARNING(HW_GPU,
                                    "V47_FIX DiscoverStage4RotatingBoundary count={} stage={} "
                                    "start={:#x} pc={:#x}",
                                    count, rotating_stage, start_address,
                                    RotatingShaderExit);
                    } else {
                        LOG_WARNING(HW_GPU,
                                    "V46_FIX DiscoverRotatingShaderBoundary count={} stage={} "
                                    "start={:#x} pc={:#x}",
                                    count, rotating_stage, start_address,
                                    RotatingShaderExit);
                    }
                }
                return repair_offset + INST_SIZE;
            }
        }
''',
    '''    while (size <= MAXIMUM_SIZE) {
        u64* const data = code.data() + offset / INST_SIZE;

        // Minecraft rotates its split-screen UI shader through starts ending in 0x30 below the
        // fixed 0x10008 boundary. Requiring the whole 4-KiB scan block to be mapped can reject a
        // valid shader merely because bytes after that boundary are unmapped. For the confirmed
        // Minecraft stage-4 window, validate and read only the prefix through the boundary.
        constexpr u32 RotatingShaderExit = 0x10008;
        const u32 rotating_stage = static_cast<u32>(stage);
        const bool rotating_stage0 = rotating_stage == 0 && start_address == 0xff30;
        const bool rotating_stage4 = rotating_stage == 4 && start_address >= 0xf030 &&
                                     start_address <= 0xff30 &&
                                     (start_address & 0xff) == 0x30;
        if (RejectInvalidShaders() && offset == 0 && (rotating_stage0 || rotating_stage4)) {
            const size_t repair_offset = RotatingShaderExit - start_address;
            const size_t repair_size = repair_offset + INST_SIZE;
            if (repair_size <= BLOCK_SIZE &&
                gpu_memory->IsFullyMappedRange(guest_addr, repair_size)) {
                gpu_memory->ReadBlock(guest_addr, data, repair_size);
                u64& boundary_instruction = data[repair_offset / INST_SIZE];
                if (boundary_instruction == 0) {
                    boundary_instruction = EXIT_VALUE;
                    static std::atomic<u32> discovered_rotating_boundary_count{};
                    const u32 count = discovered_rotating_boundary_count.fetch_add(
                        1, std::memory_order_relaxed);
                    if (count < 32) {
                        if (rotating_stage4) {
                            LOG_WARNING(HW_GPU,
                                        "V48_FIX DiscoverStage4RotatingPrefix count={} stage={} "
                                        "start={:#x} pc={:#x} size={:#x}",
                                        count, rotating_stage, start_address,
                                        RotatingShaderExit, repair_size);
                        } else {
                            LOG_WARNING(HW_GPU,
                                        "V46_FIX DiscoverRotatingShaderBoundary count={} stage={} "
                                        "start={:#x} pc={:#x}",
                                        count, rotating_stage, start_address,
                                        RotatingShaderExit);
                        }
                    }
                    return repair_size;
                }
            } else if (rotating_stage4) {
                static std::atomic<u32> unmapped_rotating_prefix_count{};
                const u32 count = unmapped_rotating_prefix_count.fetch_add(
                    1, std::memory_order_relaxed);
                if (count < 32) {
                    LOG_WARNING(HW_GPU,
                                "V48_FIX Stage4RotatingPrefixUnmapped count={} stage={} "
                                "start={:#x} pc={:#x} size={:#x}",
                                count, rotating_stage, start_address,
                                RotatingShaderExit, repair_size);
                }
            }
        }

        if (!gpu_memory->IsFullyMappedRange(guest_addr, BLOCK_SIZE)) {
            analysis_failure_address = guest_addr;
            analysis_stopped_at_unmapped_memory = true;
            return std::nullopt;
        }
        gpu_memory->ReadBlock(guest_addr, data, BLOCK_SIZE);
''',
)

print("applied v48 Linux Minecraft stage-4 rotating-prefix repair")
