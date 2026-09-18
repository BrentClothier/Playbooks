#!/usr/bin/env python3
"""Reject malformed Minecraft Vulkan graphics shaders before pipeline submission."""
from pathlib import Path


def replace_once(name, old, new):
    path = Path(name)
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{name}: expected one match, found {count}")
    path.write_text(text.replace(old, new, 1))
    print(f"updated {name}")


replace_once("src/shader_recompiler/frontend/maxwell/decode.h",
             "Opcode Decode(u64 insn);",
             "Opcode Decode(u64 insn, bool reject_invalid = false);")
replace_once("src/shader_recompiler/frontend/maxwell/decode.cpp",
             "Opcode Decode(u64 insn) {",
             "Opcode Decode(u64 insn, bool reject_invalid) {")
replace_once("src/shader_recompiler/frontend/maxwell/decode.cpp",
             '    ASSERT_MSG(false, "Invalid insn {:#016x}", insn);',
             '''    if (reject_invalid) {
        throw Shader::LogicError("V43_FIX InvalidInstruction insn={:#018x}", insn);
    }
    ASSERT_MSG(false, "Invalid insn {:#016x}", insn);''')

replace_once("src/shader_recompiler/environment.h",
             "    virtual ~Environment() = default;",
             '''    virtual ~Environment() = default;

    void SetRejectInvalidShaders(bool enabled) noexcept {
        reject_invalid_shaders = enabled;
    }

    [[nodiscard]] bool RejectInvalidShaders() const noexcept {
        return reject_invalid_shaders;
    }''')
replace_once("src/shader_recompiler/environment.h",
             "    bool is_proprietary_driver{};",
             "    bool is_proprietary_driver{};\n    bool reject_invalid_shaders{};")

replace_once("src/video_core/shader_environment.cpp",
             '#include "shader_recompiler/environment.h"',
             '''#include "shader_recompiler/environment.h"
#include "shader_recompiler/exception.h"
#include "shader_recompiler/frontend/maxwell/decode.h"''')
replace_once("src/video_core/shader_environment.cpp",
             "constexpr size_t INST_SIZE = sizeof(u64);",
             '''constexpr size_t INST_SIZE = sizeof(u64);

// Called only for actual instruction fetches; headers and scheduling words are not decoded.
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
}''')
replace_once("src/video_core/shader_environment.cpp",
             '''        return code[(address - cached_lowest) / INST_SIZE];
    }
    has_unbound_instructions = true;
    return gpu_memory->Read<u64>(program_base + address);''',
             '''        return ValidateInstruction(*this, address,
                                   code[(address - cached_lowest) / INST_SIZE]);
    }
    if (RejectInvalidShaders() &&
        !gpu_memory->IsFullyMappedRange(program_base + address, INST_SIZE)) {
        throw Shader::LogicError("V43_FIX UnmappedInstruction stage={} pc={:#x}",
                                 static_cast<u32>(stage), address);
    }
    has_unbound_instructions = true;
    return ValidateInstruction(*this, address, gpu_memory->Read<u64>(program_base + address));''')
replace_once("src/video_core/shader_environment.cpp",
             '''u32 GraphicsEnvironment::ReadCbufValue(u32 cbuf_index, u32 cbuf_offset) {
    const auto& cbuf{maxwell3d->state.shader_stages[stage_index].const_buffers[cbuf_index]};
    ASSERT(cbuf.enabled);''',
             '''u32 GraphicsEnvironment::ReadCbufValue(u32 cbuf_index, u32 cbuf_offset) {
    const auto& buffers{maxwell3d->state.shader_stages[stage_index].const_buffers};
    if (RejectInvalidShaders() &&
        (cbuf_index >= buffers.size() || !buffers[cbuf_index].enabled)) {
        throw Shader::LogicError("V43_FIX InvalidConstantBuffer stage={} index={} offset={:#x}",
                                 static_cast<u32>(stage), cbuf_index, cbuf_offset);
    }
    const auto& cbuf{buffers[cbuf_index]};
    ASSERT(cbuf.enabled);''')
replace_once("src/video_core/shader_environment.cpp",
             "    return code[(address - read_lowest) / sizeof(u64)];",
             '''    return ValidateInstruction(*this, address,
                               code[(address - read_lowest) / sizeof(u64)]);''')

replace_once("src/video_core/renderer_vulkan/vk_pipeline_cache.cpp",
             '#include <algorithm>',
             '#include <algorithm>\n#include <atomic>')
replace_once("src/video_core/renderer_vulkan/vk_pipeline_cache.cpp",
             '''    const auto load_graphics{[&](std::ifstream& file, std::vector<FileEnvironment> envs) {
        GraphicsPipelineCacheKey key;''',
             '''    const auto load_graphics{[&](std::ifstream& file, std::vector<FileEnvironment> envs) {
        for (auto& env : envs) {
            env.SetRejectInvalidShaders(title_id == 0x0100D71004694000ULL);
        }
        GraphicsPipelineCacheKey key;''')
replace_once("src/video_core/renderer_vulkan/vk_pipeline_cache.cpp",
             '''} catch (const Shader::Exception& exception) {
    auto hash = key.Hash();
    size_t env_index{0};''',
             '''} catch (const Shader::Exception& exception) {
    // Rebuilding the failed CFG here can throw again or repeat the original hang.
    // The null pipeline is retained by the existing graphics cache and skips this draw.
    if (std::ranges::any_of(envs, [](const auto* env) { return env->RejectInvalidShaders(); })) {
        static std::atomic<u32> rejected_pipeline_count{};
        const u32 count = rejected_pipeline_count.fetch_add(1, std::memory_order_relaxed);
        if (count < 32) {
            LOG_ERROR(Render_Vulkan,
                      "V43_FIX RejectGraphicsPipeline count={} hash={:#018x} reason={}",
                      count, key.Hash(), exception.what());
        }
        return nullptr;
    }
    auto hash = key.Hash();
    size_t env_index{0};''')
replace_once("src/video_core/renderer_vulkan/vk_pipeline_cache.cpp",
             '''    GetGraphicsEnvironments(environments, graphics_key.unique_hashes);

    main_pools.ReleaseContents();''',
             '''    GetGraphicsEnvironments(environments, graphics_key.unique_hashes);
    for (auto* env : environments.Span()) {
        env->SetRejectInvalidShaders(program_id == 0x0100D71004694000ULL);
    }

    main_pools.ReleaseContents();''')

print("applied v43 Linux Minecraft invalid-shader guard")
