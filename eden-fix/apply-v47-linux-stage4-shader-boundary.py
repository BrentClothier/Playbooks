#!/usr/bin/env python3
"""Repair Minecraft's confirmed stage-4 0xff30 split-screen UI shader boundary."""
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
)

replace_once(
    "src/video_core/shader_environment.cpp",
    '''        constexpr u32 RotatingShaderStart = 0xff30;
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
        }''',
    '''        constexpr u32 RotatingShaderStart = 0xff30;
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
        }''',
)

print("applied v47 Linux Minecraft stage-4 shader-boundary repair")
