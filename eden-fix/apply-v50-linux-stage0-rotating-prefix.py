#!/usr/bin/env python3
from pathlib import Path

p=Path("src/video_core/shader_environment.cpp")
s=p.read_text()

def repl(old,new,label):
    global s
    n=s.count(old)
    if n!=1:
        raise RuntimeError(f"{label}: expected one match, found {n}")
    s=s.replace(old,new,1)

repl(
'''        const bool stage0_boundary =
            stage == 0 && (start == 0xfd30 || start == 0xfe30 || start == 0xff30);
        const bool stage4_rotating_boundary =
            stage == 4 && start >= 0xf030 && start <= 0xff30 && (start & 0xff) == 0x30;
        if (address == 0x10008 && insn == 0 &&
            (stage0_boundary || stage4_rotating_boundary)) {''',
'''        const bool stage0_rotating_boundary =
            stage == 0 && start >= 0xf030 && start <= 0xff30 && (start & 0xff) == 0x30;
        const bool stage4_rotating_boundary =
            stage == 4 && start >= 0xf030 && start <= 0xff30 && (start & 0xff) == 0x30;
        if (address == 0x10008 && insn == 0 &&
            (stage0_rotating_boundary || stage4_rotating_boundary)) {''',
"generalize stage0 validator")

repl(
'''                if (stage4_rotating_boundary) {
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
                }''',
'''                if (stage4_rotating_boundary) {
                    LOG_WARNING(HW_GPU,
                                "V48_FIX RepairStage4RotatingBoundary count={} stage={} "
                                "start={:#x} pc={:#x}",
                                count, stage, start, address);
                } else if (start == 0xfd30 || start == 0xfe30) {
                    LOG_WARNING(HW_GPU,
                                "V44_FIX RepairShaderBoundary count={} stage={} start={:#x} "
                                "pc={:#x}",
                                count, stage, start, address);
                } else if (start == 0xff30) {
                    LOG_WARNING(HW_GPU,
                                "V46_FIX RepairRotatingShaderBoundary count={} stage={} "
                                "start={:#x} pc={:#x}",
                                count, stage, start, address);
                } else {
                    LOG_WARNING(HW_GPU,
                                "V50_FIX RepairStage0RotatingBoundary count={} stage={} "
                                "start={:#x} pc={:#x}",
                                count, stage, start, address);
                }''',
"stage0 repair log")

repl(
'''        const bool rotating_stage0 = rotating_stage == 0 && start_address == 0xff30;
        const bool rotating_stage4 = rotating_stage == 4 && start_address >= 0xf030 &&
                                     start_address <= 0xff30 &&
                                     (start_address & 0xff) == 0x30;''',
'''        const bool rotating_stage0 = rotating_stage == 0 && start_address >= 0xf030 &&
                                     start_address <= 0xff30 &&
                                     (start_address & 0xff) == 0x30;
        const bool rotating_stage4 = rotating_stage == 4 && start_address >= 0xf030 &&
                                     start_address <= 0xff30 &&
                                     (start_address & 0xff) == 0x30;''',
"generalize stage0 discovery")

repl(
'''                        if (rotating_stage4) {
                            ActivateMinecraftSplitScreenDiagnostics();
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
                        }''',
'''                        ActivateMinecraftSplitScreenDiagnostics();
                        if (rotating_stage4) {
                            LOG_WARNING(HW_GPU,
                                        "V48_FIX DiscoverStage4RotatingPrefix count={} stage={} "
                                        "start={:#x} pc={:#x} size={:#x}",
                                        count, rotating_stage, start_address,
                                        RotatingShaderExit, repair_size);
                        } else if (start_address == 0xff30) {
                            LOG_WARNING(HW_GPU,
                                        "V46_FIX DiscoverRotatingShaderBoundary count={} stage={} "
                                        "start={:#x} pc={:#x}",
                                        count, rotating_stage, start_address,
                                        RotatingShaderExit);
                        } else {
                            LOG_WARNING(HW_GPU,
                                        "V50_FIX DiscoverStage0RotatingPrefix count={} stage={} "
                                        "start={:#x} pc={:#x} size={:#x}",
                                        count, rotating_stage, start_address,
                                        RotatingShaderExit, repair_size);
                        }''',
"stage0 discovery log")

repl(
'''            } else if (rotating_stage4) {
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
            }''',
'''            } else if (rotating_stage0 || rotating_stage4) {
                static std::atomic<u32> unmapped_rotating_prefix_count{};
                const u32 count = unmapped_rotating_prefix_count.fetch_add(
                    1, std::memory_order_relaxed);
                if (count < 32) {
                    if (rotating_stage4) {
                        LOG_WARNING(HW_GPU,
                                    "V48_FIX Stage4RotatingPrefixUnmapped count={} stage={} "
                                    "start={:#x} pc={:#x} size={:#x}",
                                    count, rotating_stage, start_address,
                                    RotatingShaderExit, repair_size);
                    } else {
                        LOG_WARNING(HW_GPU,
                                    "V50_FIX Stage0RotatingPrefixUnmapped count={} stage={} "
                                    "start={:#x} pc={:#x} size={:#x}",
                                    count, rotating_stage, start_address,
                                    RotatingShaderExit, repair_size);
                    }
                }
            }''',
"unmapped stage0 log")

p.write_text(s)
print("applied v50 Linux Minecraft stage-0 rotating-prefix repair")
