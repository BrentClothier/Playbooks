#!/usr/bin/env python3
"""Repair the confirmed Minecraft split-screen vertex-shader boundary."""
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
    "#include <algorithm>",
    "#include <algorithm>\n#include <atomic>",
)

replace_once(
    "src/video_core/shader_environment.cpp",
    '''// Called only for actual instruction fetches; headers and scheduling words are not decoded.
static u64 ValidateInstruction(const Shader::Environment& env, u32 address, u64 insn) {
    if (env.RejectInvalidShaders()) {
        try {
            static_cast<void>(Shader::Maxwell::Decode(insn, true));
        } catch (Shader::Exception& exception) {
            exception.Append(fmt::format(" stage={} start={:#x} pc={:#x}",
                                        static_cast<u32>(env.ShaderStage()),
                                        env.StartAddress(), address));
            throw;
        }
    }
    return insn;
}''',
    '''// Called only for actual instruction fetches; headers and scheduling words are not decoded.
static u64 ValidateInstruction(const Shader::Environment& env, u32 address, u64 insn) {
    if (env.RejectInvalidShaders()) {
        const u32 stage = static_cast<u32>(env.ShaderStage());
        const u32 start = env.StartAddress();

        // Minecraft's split-screen UI vertex shaders branch to the first instruction after a
        // 64-KiB shader-code boundary. The guest leaves that instruction zero-filled. Treat only
        // the three confirmed shader layouts as having reached their end; EXIT ignores the other
        // instruction fields, so the opcode prefix is sufficient and preserves earlier control
        // flow. Every other invalid instruction remains subject to v43's safe rejection path.
        if (stage == 0 && address == 0x10008 && insn == 0 &&
            (start == 0xfd30 || start == 0xfe30)) {
            constexpr u64 MaxwellExitInstruction = 0xe300000000000000ULL;
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
        }

        try {
            static_cast<void>(Shader::Maxwell::Decode(insn, true));
        } catch (Shader::Exception& exception) {
            exception.Append(fmt::format(" stage={} start={:#x} pc={:#x}", stage, start,
                                        address));
            throw;
        }
    }
    return insn;
}''',
)

print("applied v44 Linux Minecraft shader-boundary repair")
